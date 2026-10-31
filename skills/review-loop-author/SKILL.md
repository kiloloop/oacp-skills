---
name: review-loop-author
description: Run the author side of the OACP review loop — request exact-head review, address verified findings, and drive to LGTM. Single-pass (exits after sending round messages; /check-inbox re-invokes it on the reviewer's reply). The leader session owns all protocol state and side effects.
---

# /review-loop-author — Author-Side Review Loop

The **leader** (this session) owns all protocol state and side effects: inbox
I/O, verification, git/gh, message sends, and the final decision each round.
Code fixes are leader-direct for small fix sets; for larger sets spawn the
fix-only subagent per [references/fix-subagent-prompt.md](references/fix-subagent-prompt.md).
Subagents never hold OACP state or perform side effects.

Protocol truth lives in the OACP runtime's `docs/protocol/review_loop.md` and
`dispatch_states.yaml`; they override this skill on conflict.

`SKILL_DIR="${CLAUDE_SKILL_DIR}"` — the directory holding this file and its
`scripts/` (set it by hand if your runtime does not substitute the variable).
Snippets here use named variables only: the Skill tool substitutes invocation
arguments into `$`-digit tokens at render time, so a bare positional in a code
block silently becomes an argument value.

## Arguments

```
/review-loop-author <PR_NUMBER> --reviewer <name> [--project <name>] [--task-id <id>] [--max-rounds 2] [--dry-run]
```

- `PR_NUMBER` — required positional.
- `--reviewer` — required. Exception: when the inbox already holds a verified
  `review_feedback` (or review-shaped `notification`) for this PR, infer the
  reviewer from its `from:` field.
- `--project` — for a new loop, must match the PR repository's OACP binding
  (Step 1); an existing loop keeps its original project.
- `--task-id` — optional; enables task-state updates.
- `--max-rounds` — default **2** (protocol default), maximum 3. A round past
  the cap needs fresh human direction (Step 10).
- `--dry-run` — show the plan, change nothing.

## Instructions

### 1. Gather context and check preconditions

For a new loop, resolve the PR's base repository to its OACP project through
that repository's `.oacp` marker, and confirm the checkout's remote is the PR
repository — a directory name or the session's current project is not enough.
Validate any `--project` override against that binding; with no readable
marker, stop and ask. Run the loop from the owning repository's author session
so the reviewer's replies reach its own-project watcher. An existing loop keeps
its original project and conversation for every later round; moving it needs
an explicit supersede (Step 4), never a duplicate request.

```bash
REPO_PATH=$(git rev-parse --show-toplevel)
BRANCH=$(git -C "$REPO_PATH" rev-parse --abbrev-ref HEAD)
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
BASE=$(gh pr view <PR_NUMBER> --json baseRefName -q .baseRefName)
# .oacp sits at the MAIN checkout root; in a linked worktree --show-toplevel is the worktree
MAIN_ROOT=$(dirname "$(git -C "$REPO_PATH" rev-parse --path-format=absolute --git-common-dir)")
PROJECT=${PROJECT_FLAG:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project_name"])' "$MAIN_ROOT/.oacp")}
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
INBOX_DIR="${OACP_HOME}/projects/${PROJECT}/agents/claude/inbox"
```

Use the GitHub identity the project's instructions require — for example a
short-lived App token generated inline per command, exported as `GH_TOKEN`
for `gh`, and injected per push via
`git -c http.https://github.com/.extraheader=…`, never persisted to a file or
the remote URL.

**Receiver routing:** send a new loop's `review_request` to the reviewer
registered in the PR repository's project workspace. Confirm the sender and
reviewer are both registered there and that each has pinned the other's key —
an inbox directory alone is not readiness evidence. Missing, ambiguous, or
stale registration holds the send for setup; never fall back to another
workspace because its reviewer is easier to reach. Registration and delivery
do not admit the review — the reviewer's autonomy gate does.

Verify, report failures, and stop on: PR exists; current branch is the PR head
branch; PR is `MERGEABLE` (if `CONFLICTING`, rebase onto the base branch and
`git push --force-with-lease --force-if-includes` **before** requesting review
— a post-review force-push dismisses the approval and wastes a round);
`INBOX_DIR` and the reviewer's inbox exist; `oacp send --help` works;
`gh auth status` passes. A missing inbox in an existing workspace means that
agent was never registered there: `oacp agent add <project> <agent> --runtime
<runtime>`, then exchange keys (`oacp trust import`) before the first send.

### 2. Scan the inbox (verified intake)

```bash
command ls -1 "$INBOX_DIR" | command grep '\.yaml$'      # candidates; archive/ is a subdir
SNAP="$(mktemp)"; cp "$INBOX_DIR/<file>" "$SNAP"         # immutable snapshot, read once
ACCEPTED_SHA=$(shasum -a 256 "$SNAP" | cut -d' ' -f1)
oacp verify "$SNAP" --project "$PROJECT" --receiver claude --oacp-dir "$OACP_HOME" --json
```

Candidates are messages from the reviewer with `related_pr` equal to this PR.
**Verified-intake rule** (every inbound read in this skill): verify and parse
only the snapshot; the live file is compared against `ACCEPTED_SHA` only at
archival, which the archival script does. Shell variables do not persist
between Bash calls — carry the literal `SNAP` path and `ACCEPTED_SHA` forward.
Process a message only when `oacp verify` reports `signed-verified` (JSON
`status: verified`), under any verify posture. Any other outcome — unsigned,
unverifiable, `signed-INVALID` — means do NOT process and do NOT archive: keep
the evidence (`--quarantine` copies an INVALID message to `dead_letter/`) and
surface it to the user.

Route by type: `review_lgtm` → Step 8. `review_feedback` (or a review-shaped
`notification` — see [references/terminal-checkpoints.md](references/terminal-checkpoints.md))
→ Step 6. Nothing → Step 3.

Also check GitHub for out-of-band feedback (issue comments, review comments,
reviews via `gh api`); note anything actionable that is not in the inbox.

### 3. Show plan

Print PR, repo, branch, reviewer, project, task id, round, max rounds, inbox
path. If `--dry-run`, stop here.

### 4. Send review_request

Idempotency first: if your outbox or the reviewer's inbox already holds a
`review_request` for this PR+round, skip the send.

```bash
REQUESTED_HEAD=$(git -C "$REPO_PATH" rev-parse HEAD)   # full SHA, verbatim; must equal the pushed PR head
git -C "$REPO_PATH" diff --histogram --shortstat "origin/$BASE...$BRANCH"
CONV_ID="conv-$(date -u +%Y%m%d)-claude-<PR_NUMBER>"   # schema: conv-<YYYYMMDD>-<agent>-<seq>
```

Body fields (review_loop.md names; `requested_head` and `review_round` are
legacy duplicates for older reviewer tooling):

```yaml
pr: <PR_NUMBER>
repo: <OWNER/REPO>
branch: <BRANCH>
round: <N>
max_rounds: <MAX_ROUNDS>
declared_head: <REQUESTED_HEAD>
requested_head: <REQUESTED_HEAD>
review_round: <N>
diff_summary: |
  <2-4 lines>
task_id: <TASK_ID>
max_turns_reviewer: 8
max_runtime_s_reviewer: 600
side_effects:
  - writes_findings_packet
  - sends_oacp_reply
  - comments_on_github        # status comments; only when intended and permitted
  - submits_github_review     # GitHub approval; only when needed and permitted
```

The reviewer parses the body with `yaml.safe_load`, and a hand-written scalar
containing a colon-space or a leading quote breaks it. Build the body as a mapping,
`yaml.safe_dump(body, sort_keys=False, width=100000)`, assert
`yaml.safe_load(text) == body`, write it to a temp file, and send:

```bash
oacp send "$PROJECT" \
  --from claude --to <REVIEWER> --type review_request \
  --subject "Review: PR #<PR_NUMBER> (round <N>)" \
  --conversation-id "$CONV_ID" --body-file "$BODY_FILE" \
  --related-pr <PR_NUMBER> --priority P1 --oacp-dir "$OACP_HOME"
```

This contract applies to every `review_request` you send as author, from any
flow — task dispatch, inline continuation rounds, batched sibling PRs. Re-read
this step before composing one, and after any context compaction; the
`side_effects:` block and the verbatim heads are the parts that drop.

- **Heads**: both head fields carry the same verbatim `rev-parse` output. They
  are context for the reviewer, never evidence — the reviewer binds its
  verdict to the live head it fetches.
- **Thread identity**: `CONV_ID` must match
  `^conv-\d{8}-[A-Za-z0-9._-]{1,64}-\d{1,6}$` (UTC date; the PR number is a
  natural sequence when it has six digits or fewer — pick a fresh sequence for
  a second thread on the same PR and day). Carry it verbatim on EVERY loop
  message: continuation-grant evidence matches an equal `conversation_id` or
  an immediate parent only (no chain traversal), and an archived message
  cannot donate a conversation to `--in-reply-to` — thread to one with
  explicit `--parent-message-id` + `--conversation-id`.
- **Grants**: the receiver's continuation gate reads only `round` and
  `side_effects`; `repo` is required on granted rounds so the reviewer can
  validate the thread's repository and PR.
- **Side effects**: declare the round's GitHub actions on every request that
  expects one. Omission declares only the defaults (findings packet + OACP
  reply), and the reviewer withholds anything undeclared — on a
  ruleset-protected repository a withheld `submits_github_review` blocks the
  merge and costs a round-trip. On a grant-governed thread declare only what
  the grant permits; an expanding declaration pauses the round
  (`continuation_grant_scope_exceeded`).

**Superseding a request** (review_loop.md → Superseding a Request):

- **Defective request already sent**: send a contract-complete replacement
  with `supersedes_message_id: <defective id>` and `supersede_reason:` ("same
  ask, same head" when only the body was wrong), `--in-reply-to` the defective
  message, same `--conversation-id`. The reviewer acts on the replacement only
  and closes the original. Never leave two live requests for one round, or
  re-send without the marker.
- **Head change before the reviewer starts — no round cost**: before pushing
  over an in-flight request, check the reviewer's
  `agents/<reviewer>/audit/autonomy_decisions/` for a record naming the
  request's id, and its `status.yaml` `current_task`. Both empty → no head is
  materialized: push, then send the replacement at the NEW head with
  `supersede_reason` naming the old head void.
- **Head change after the reviewer started, before any verdict**: announce
  first. (1) Before any push, a `notification` threaded on the request —
  "author pause: declared_head `<sha>` will be replaced, stop at that head" —
  naming the human direction behind it; (2) do the work locally, one push;
  (3) the replacement at the new head at the same `round: <N>` — a fresh
  admission, not a continuation of the cancelled round, which produced no
  verdict and consumes nothing — with `supersede_reason` (old head void, what
  changed), `human_direction:` when a human asked for the scope change, and
  what is new since the superseded request so the reviewer can reuse its
  partial work. A verdict that lands before your push is round-N
  output: process it, and the replacement becomes round N+1.

**Pre-request checks, every round:**

- **Round 1 declares the artifact's class and threat model** in the body
  (`artifact_class:` plus what it defends against). Authorization, evidence,
  and transaction machinery earns invariant-maximal closure — and where that
  bar is "every X is collected" over a finite grammar, the enumerated grammar
  is the round-1 bar (Step 7). Diagnostics, docs, and convenience surfaces do
  not, so out-of-model hardening findings can be answered as advisory.
  Undeclared, the reviewer discovers the bar one adjacent gap per round.
- **Size the reviewable surface before asking.** Count the diff minus
  fixtures, lockfiles, snapshots, and generated payloads: ~100 such lines
  review well, ~1,000 do not. Above a few hundred, split before requesting or
  say in the body why it must land whole — a split now is free; after
  `max_rounds_exceeded` it costs the loop. Every size figure in the request is
  pasted from the output of
  `bash "$SKILL_DIR/scripts/diff_sizes.sh" "$REPO_PATH" <base> <head>` run at
  the declared head — its per-file `--histogram --numstat` rows and
  `--shortstat` totals. Build the body from that output: a figure estimated,
  summed by hand from the rows, or retyped from an earlier round's body is an
  estimate. For a lockfile, add a semantic compare of its package map
  (removed / added / changed counts) — paste the output of
  `python3 "$SKILL_DIR/scripts/lockfile_compare.py" --repo <dir> --base main --head <branch> [--path package-lock.json]`
  (`pnpm-lock.yaml` by default); a line diff turns a removed subtree into
  alignment noise.
- **A gap you noticed and deferred is a round-1 blocker when it sits inside
  the declared grammar.** Sweep your design notes for anything waved off as
  "another module's business" or "not this leg" — a predicate the code trusts
  but did not close, a check delegated to a user-editable file — and fix it or
  name it out of model. The same holds for a caveat written for a later leg
  when the current leg's code already relies on its negation.
- **When the artifact caches or mirrors an external tool's verdicts,
  enumerate the tool's inputs from its source** (what the verdict path opens),
  not from the arguments you pass, and put every input in the key or name it
  out of model. Every input that moves the key must also be in the
  change-detection path, or the cached verdict stays stale until an unrelated
  event. The tool's answer vocabulary gets the same treatment: one value can
  fold several states, so enumerate what each answer is emitted for before
  mapping it to a trusted display. Two verbs of one tool are two sources —
  know which one does the fresh work, never let the stale verb's headline
  out-vote the fresh verb's rows, and never read a summary flag as the verdict
  when warning rows carry the state.
- **Every cell a test header, PR body, or request names must exist.** Grep
  each claimed case to the test that establishes it; a design-time header
  lists intended cells, and the reviewer reads it as coverage. A method
  sentence ("every launch sets X") is the same class — grep each script for
  how it sets X.
- **A scorer, gate, or live check you ship is itself under test — make it FAIL
  before round 1.** Feed every PASS predicate an empty result and one omitted
  element: a predicate whose denominator comes from the output it scores
  cannot fail, and `<=` where coverage is claimed is not a coverage check.
  Build the expected side from a source independent of the thing scored, and
  ship the negative controls as executed checks.
- **The requested head is green in CI before the request goes out** (or the
  body says CI is pending at that head). A local pass proves your platform
  only; a red check at the declared head spends the round on a head you will
  replace. After the push, assert the head with
  `git ls-remote origin refs/heads/<branch>` before `gh pr checks --watch`:
  `gh pr view` can report the previous head for some seconds, and a watch
  chained on it returns the old head's green checks.
- **Never push while a reviewer round is in flight against the declared
  head** (outside the supersede paths above). Drift during the round makes the
  reviewer abort for a fresh round — even with a head-amendment `follow_up`
  sent ahead — and spends one of `max_rounds`; on stacked PRs a fix on the
  base branch drifts both. Land everything for round N+1 in one push per
  branch, immediately before its `review_request`.
- **Deletion PRs: sweep before requesting.** Grep the whole tree bare (no
  `--include` filters — they skip `.sh`, templates, YAML) for every deleted
  basename and every retired target as `make <name>`; recovery hints and
  template header comments are the hiding spots. Land a word-boundary-anchored
  regression scan so the class stays closed.
- **Send when the checks above pass, and on a dispatched leg project the
  clock first.** A control beyond the list — a second harness, a negative
  control past the scorer's own — runs after the send or not at all: the
  reviewer re-verifies independently, and a held request costs their idle
  wait. When the leg runs under an autonomy admission, its clock runs until
  the Done reply, so each round is paid from the declared
  `estimated_minutes`: elapsed since work start + the round's wait
  (`max_runtime_s_reviewer`) + close-out (merge, bookkeeping, Done). Over the
  declaration → ask the human for a budget now, before the breach
  (check-inbox → `references/autonomy.md` §E, prospective clear), not after
  Done is composed, when the terminal finalize checkpoints and the reply
  waits on a human clear. When no human is reachable, do not hold the round
  on the ask — proceed, say in the status message that the clock will
  breach, and take the terminal-time checkpoint at the finalize.

For round > 1 add `--in-reply-to <id of the reviewer's last message>` — take
the id from the message's `id:` field, **never** from the filename hash — and
keep `--conversation-id "$CONV_ID"` (parenting directly to the round-1 request
id is the alternative only when no conversation id was established).

**Every round, round 1 included**: post the status-only "Review requested" PR
comment (template in
[references/terminal-checkpoints.md](references/terminal-checkpoints.md)) — it
is the only trace of the round on the PR itself. After the send, confirm the
delivered copy exists at the `inbox:` path `oacp send` printed, then verify it
against the reviewer's pins (`oacp verify <that path> --project "$PROJECT"
--receiver <REVIEWER>`): `signed-unknown-kid` means the reviewer has not
pinned your key and will reject the request at intake —
tell them now, threaded, instead of losing the round to it. Exit here.

### 5. Wait for the reply — never in-session

The inbox watcher (`oacp watch` under a Monitor, dispatching `/check-inbox`)
starts the next invocation when the reviewer's message lands: `review_lgtm` →
Step 8; `review_feedback` → Step 6. Re-scanning the inbox inside model turns
violates review_loop.md → Shell-Only Polling Rule; a stale round is the
human's call to escalate (Step 10).

### 6. Parse verified feedback

From the verified `review_feedback` snapshot: `findings_packet`, `round`,
`blocking_count`, `validated_head`, and the message `id` and
`conversation_id` (for threading); optional `task_id`/`review_round`.

- `escalation: max_rounds_exceeded` or `reviewer_budget_exceeded` → Step 10.
- Read the packet at `${OACP_HOME}/projects/${PROJECT}/<findings_packet>` as
  `FINDINGS_CONTENT`.
- **Leave the feedback message in the inbox**, keeping its Step 2
  `ACCEPTED_SHA`. It is archived in Step 7 only after BOTH outbound sends
  (`review_addressed` + the round-N+1 `review_request`) succeed, so a crash
  re-dispatches cleanly.
- If a task id is present: set `review_round`, `review_status:
  needs_changes`, and append the packet path to `findings_packets`.

### 7. Address findings

**Leader-direct** (default for ≤2 findings, doc-only fixes, or fixes already
verified while processing): read, edit, done. **Subagent** (larger sets):
spawn per [references/fix-subagent-prompt.md](references/fix-subagent-prompt.md),
then parse its `FIX_SUMMARY` block and review the actual diff.

Before replying, **replay the reviewer's validation suite** at your head:
rerun the packet's `qa_validation.commands_run` (retarget pinned checkout
paths to your tree, and hardcoded temp dirs to one your sandbox permits — a
denied `mkdtemp` kills the probe before it proves anything) and fix what
fails. A repro probe encodes the defect, so after the fix it may throw at the
line that assumed the defect happened — that throw is the pass: wrap that
read, keep the assertion, and say so in `review_addressed` rather than
silently editing the probe's claim. Name any proactively fixed, unfiled probe
in `review_addressed`. A booted-app or render check may stay un-rerun only
when the fix's files sit outside the bundle's import graph — grep the
importers and say so.

**Adversarially probe your own fix before sending `review_addressed`.** Probe
a library the way the fix configures it — the same options, callbacks, and
predicates the app passes — never bare. When you author both implementation
and tests, the tests encode your blind spot: reproduce every filed finding
first, then probe past the filed set with cases chosen to break the fix; the
reviewer's cases are a sample, not the class. When the fix is executable copy
(a command recipe in a page, README, or doc), run the text as rendered —
extract the command lines from the build output and run them under zsh and
bash with their variables unset; a hand-substituted equivalent tests your
paraphrase, not the page.

**Close the class, not the row.** When a finding is one instance of a finite
grammar (shell redirect operators, an option table, a long-option
abbreviation rule), the fix round enumerates the whole grammar in tests
instead of fixing the filed row plus a hand-picked neighbour — every
un-enumerated round loses to the next neighbour. When the grammar has two
strip passes or two operator classes, enumerate their compositions, not each
class alone: a command grammar closed for keywords and for wrappers
separately still let `time ! git commit` through, because the keyword strip
ran once, before the wrapper strip exposed the `!`. If a fix moves an internal
call path the reviewer's probes monkeypatch, name the new patch target in
`review_addressed`. When the fix adds a lock, say that too: a probe that nests
a second invocation in the same thread now blocks on it (`flock` is not
reentrant), so run their probe retargeted — the overlap on a thread or a
second process — before the reply, never as written.

**Measure a convention finding against the whole file before fixing it.** A
reviewer sees the diff; complying with "your changed lines deviate from the
documented contract" can make the changed lines the only ones that follow it.
Run a comparator over every row first: if the untouched rows share your
deviation, the documentation is the defect — correct it and push back with
the counts instead of normalizing a few rows.

**Check the aggregate before composing any fix round.** A blocking count flat
across two consecutive rounds, or a cumulative fix delta (`git diff
<round-1-head> --shortstat`) rivaling the original change, means the loop is
inflating the artifact rather than converging — raise the scope question to
the human ("is this the right depth?") instead of pushing the fix.

**On a dispatched task, recount the files between the commit and the push
below.** An envelope hook cannot count files a scratchpad script writes, so
the recount is the guard — and it runs after the commit, because a
`<base>...HEAD` range compares commits only and misses the fix it is about to
add:

```bash
git -C "$REPO_PATH" diff --name-only <base>...HEAD | sort -u | wc -l   # after the commit, before the push; every PR and repo of the task, vs the dispatch's expected_files_touched
```

A fix round that crosses the declared count is the check-inbox §E
checkpoint: record it and get the in-session clear BEFORE the push, not at
the terminal finalize, where the Done then waits on the human.

Then commit and push:

```bash
git -C "$REPO_PATH" add <files_modified>        # explicit paths, never -A
git -C "$REPO_PATH" commit -m "Address review findings (round <N>)

<F-xxx: one line each>

<your runtime's attribution trailer, verbatim>"
git -C "$REPO_PATH" push origin "$BRANCH"        # auth per Step 1
NEW_HEAD=$(git -C "$REPO_PATH" rev-parse HEAD)
```

Send replies, each with `--conversation-id "$CONV_ID"` and `--in-reply-to
<feedback message id>`, bodies built as in Step 4:

1. Per pushed-back finding: a `question` carrying the reason.
2. `review_addressed` (idempotency check first), subject `Feedback addressed:
   round <N> (#<PR_NUMBER>)`:

   ```yaml
   commit_sha: <NEW_HEAD>
   validated_head: <NEW_HEAD>
   round: <N>                 # the round whose feedback this addresses
   changes_summary: |
     <fixed / deferred / pushed-back summary>
   touched_files:
     - <each modified file>
   addressed_finding_ids:
     - <each fixed F-id>
   task_id: <TASK_ID>
   review_round: <N>
   ```

3. A fresh round-N+1 `review_request` (Step 4 contract at `NEW_HEAD`,
   `side_effects:` included).
4. Status-only PR comments: "Feedback addressed (round N)" for this round,
   then the "Review requested" comment the round-N+1 request takes under
   Step 4's every-round rule — templates in
   [references/terminal-checkpoints.md](references/terminal-checkpoints.md).
5. **Now** archive the feedback message with the terminal archival helper
   (below) against `ACCEPTED_SHA`. If the next round would exceed
   `MAX_ROUNDS`, the next feedback escalates (Step 10). Exit; the watcher
   re-dispatches on the reply.

### 8. Handle LGTM

Full checkpoint in
[references/terminal-checkpoints.md](references/terminal-checkpoints.md):
`quality_gate_result: pass` + `merge_ready: true`; **compare `validated_head`
to the live PR head** (mismatch = stale LGTM — request a fresh round instead);
read `withheld_side_effects`; adopt structured `nits`; update task fields; PR
comment; archive the message after bookkeeping (`ACCEPTED_SHA` captured at
read time, terminal archival helper). Do NOT merge here. Then Step 9 and
report `STATUS: PASSED`.

**Exception — a dispatched task whose admission approved `merges_pr`** (the
task profile declares it and the human's approval covered it): the author
merges right after this checkpoint, still bound to the validated head —
`gh pr merge <N> --repo <owner/repo> --squash --match-head-commit
<validated_head>`, from a cwd outside any worktree that has the branch
checked out, without `--delete-branch` — then the dispatch's close-out (Done
reply, terminal finalize, archive). An LGTM outside such an admission still
ends at Step 9 with the merge left to the human.

**A post-LGTM commit trades the approval — so a nit fix is a decision, not a
courtesy.** On a ruleset-protected repository, a push after the approval
dismisses the review and the PR needs another round to become mergeable.
Default: do not push a nit fix after LGTM — adopt the nit per the LGTM
checkpoint in
[references/terminal-checkpoints.md](references/terminal-checkpoints.md),
which owns where it lives (including the `files_issues` bound on a dispatched
task), and say so in the terminal report. Push it only when it is blocking,
when the reviewer is live and will re-approve in the same round, or when the
human says to — never silently.

### 9. Clean up

Archive remaining processed messages for **this PR only** with the terminal
archival helper; anything pending, held, or unverified stays in the inbox.

### 10. Timeout or escalation

**Timeout only — mandatory final drain**: re-run the Step 2 scan one last
time; a matching response voids the timeout (process it normally, send no
timeout messaging). Otherwise follow
[references/terminal-checkpoints.md](references/terminal-checkpoints.md):
escalation notification to the team lead, status-only PR comment, Step 9,
then `STATUS: ESCALATED` or `STATUS: TIMEOUT`. After an escalation the loop
stops pending fresh human direction; a per-round sanction never becomes a
standing grant unless the human explicitly grants one.

**When the human sanctions more rounds**, compose per
[references/terminal-checkpoints.md → Sanctioned continuation](references/terminal-checkpoints.md):
`human_direction:` (who, when, scope) + `max_rounds` bumped + explicit
`--parent-message-id`/`--conversation-id` threading to the archived
escalating feedback for a per-round sanction; a standing
continue-until-LGTM grant rides EVERY later round with `max_rounds` at
current+1 and a named circuit-breaker round. Fix and push BEFORE the sanction
ask. Passing your own breaker needs an explicit human "continue until merged",
stated verbatim on both messages, re-armed, and disclosed in the Done reply.

**Before putting options in front of the human**, read the organization's
standing rules for the escalation reason and offer a standing answer as one
of the options; executing a split or closing the escalation by scope
reduction follows
[references/terminal-checkpoints.md → Options, splits, and descoping](references/terminal-checkpoints.md).

## Terminal archival helper

Processed messages are archived, never deleted: a digest-checked, no-clobber
move of the bare inbox filename to `inbox/archive/` that preserves signed
evidence:

```bash
bash "$SKILL_DIR/scripts/oacp_archive.sh" "$INBOX_DIR" "<filename>" "$ACCEPTED_SHA"
```

Exit 0 and `ARCHIVED:` only on success; every guard fails closed and exits 1.
`RETAINED:` means nothing moved and the message stays pending (on digest
drift, re-verify before any further processing); `ERROR:` means the move ran
but a post-move check failed — inspect both paths before any retry. The
`archive/` directory is provisioned by workspace init or migration; never
create it here.

## Notes

- **Single-pass, always**: each invocation sends its round messages and
  exits; `/check-inbox` dispatches the next invocation when the reviewer
  replies. Resumable by re-running.
- The reviewer does not merge; the author (or human) merges only with the
  approval the repository's policy requires, bound to `validated_head`.
- **PR comment data-minimization**: status-only comments via `--body-file`;
  no command output, logs, stack traces, credentials, or local paths — detail
  belongs in protocol messages and findings packets.
- **A stacked PR dies with its base branch — merge the parent without
  `--delete-branch`.** `gh pr merge --delete-branch` deletes the parent's ref
  through the API, GitHub then closes every PR based on it, and `gh pr reopen`
  is refused once the head is force-pushed. On a repository that deletes
  merged branches itself, merge the parent without the flag and GitHub
  retargets the child to the parent's base. On one that does not, run
  `gh pr edit <child> --base main` before the merge (no head change, no review
  drift). Either way: record the parent's head before merging, merge, confirm
  the child is still open on main, then `git fetch origin main` and check that
  `origin/main` contains the parent's merge commit (`git merge-base
  --is-ancestor <merge-commit> origin/main`; a stale `origin/main` drops the
  parent's changes from the restacked child), then `git rebase --onto
  origin/main <parent-pre-merge-head> <child-branch>`, then — BEFORE the
  lease-push — run Step 4's reviewer-started check. Not started → push and send a superseding
  `review_request` at the new head (tree identity stated in
  `supersede_reason`), at no round cost. Started, no verdict yet → Step 4's
  author-pause sequence: the threaded pause notice before the push, then the
  replacement `review_request` at the new head. A `follow_up` cannot re-point
  a started round — the reviewer stops on the drift and only a fresh request
  starts a new invocation. Verdict already landed → process it, then push and
  request round N+1 at the new head. Recovery when the parent already merged:
  open a successor PR from the same branch onto main ("Supersedes #N", carry
  its `Closes` lines), comment on the dead PR, and send a fresh round-1
  `review_request` for the successor; a sanction given for the dead PR does
  not carry over to it without the human's word. Either way the child's head
  changes once, so budget that one re-request when a stack is coming — or,
  when the child need not be reviewed in parallel, open it for visibility and
  send its round-1 request only after the restack: no re-request, CI at the
  final head, serial review latency as the cost. When CI runs
  only on PRs into main, the child gets no checks while it targets the parent
  branch: its request says CI fires on the retarget and names the local suite
  run instead.
