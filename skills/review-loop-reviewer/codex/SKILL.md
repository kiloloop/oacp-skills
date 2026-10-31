---
name: review-loop-reviewer
description: "Run one stateless reviewer round for an OACP inbox-based PR review loop: verify the request snapshot, review one exact PR head, enforce the findings quality gate, and send review_feedback or review_lgtm. Use for OACP review_request traffic or review_addressed with explicit human approval or an accepted grant listing that type; do not use for an ordinary local code review or GitHub comment triage."
---

# OACP review loop: reviewer

Review exactly one PR head and emit exactly one terminal protocol response.

## Inputs

Require the PR number and author. Accept `project`, `task_id`, and `dry_run`
when supplied. Resolve omitted project context from session init and repo
markers; use the canonical `$OACP_HOME/projects/<project>/` runtime.

Bundled helpers need Python 3.10+, PyYAML, Git, and the GitHub CLI. Protocol
intake and cancellation require OACP CLI 0.5.3+ and the installed `check-inbox`
skill. Capability-check optional stack operations before relying on them.

## Load before acting

1. Read the nearest `AGENTS.md`, including scoped code-review rules and GitHub
   identity requirements.
2. Read the active runtime's `docs/protocol/dispatch_states.yaml`,
   `docs/protocol/review_loop.md`, and findings packet template. They override
   this skill on conflict.
3. Use `check-inbox` for every inbound candidate. Its verified snapshot reader
   and archival sequence are the only boundary for message fields, hashes, and
   terminal inbox consumption.
4. Run `check-inbox`'s mechanical OACP version gate and require `>=0.5.3`.
5. Read [findings-contract.md](references/findings-contract.md) before creating
   a verdict or terminal message.

Set `REVIEW_LOOP_REVIEWER_SKILL` to the absolute directory containing this
`SKILL.md`; use that path when invoking bundled resources from a project.

## Non-negotiable invariants

- Stay stateless: send one `review_feedback` or `review_lgtm`, then exit. Never
  wait in-session for `review_addressed`.
- Review a full commit SHA, not a moving branch. Capture the head before
  analysis and compare it again before and after terminal side effects.
- Require one schema-valid incoming conversation ID and carry it unchanged on
  the terminal reply; direct parent linkage is additional, not a substitute.
- Keep the base repository (PR/comments/reviews) distinct from the head
  repository (fork commit materialization).
- Default to two rounds; accept an ordinary project/request maximum only up to
  three. Beyond that cap, proceed only with fresh round-specific human
  direction or when the canonical evaluator returns `auto_accepted` with
  `continuation_grant_accepted` for the invocation. The accepted flat scope's
  cumulative `max_round` remains a ceiling; sender-declared context is never
  authority.
- Honor request budgets (`8` turns and `600` seconds by default), while
  reserving enough budget for verdict validation, exact-head guards, terminal
  delivery, audit read-back, and archival. If the remaining review work is
  unlikely to fit, pause before exhaustion and request a receiver-human budget
  extension. Exhaustion without a current extension produces feedback with
  `escalation: reviewer_budget_exceeded` and exits.
- Treat `P0`/`P1` as blocking, `P2` by judgment, and `P3` as non-blocking.
  Deferred `P2`/`P3` findings must become structured LGTM nits.
- A passing gate requires no unresolved blockers, all recorded validation
  commands passing, and all deferred findings tracked as nits.
- When the accepted review scope includes a formal GitHub approval, treat that
  approval and the signed OACP `review_lgtm` as one exact-head delivery. If
  approval is outside that scope, deliver the quality verdict with the approval
  named in `withheld_side_effects`; landing still requires an eligible approver.
- Keep the leader responsible for evidence, verdict, packet/message writes,
  GitHub side effects, and cleanup. Treat native read-only review or explicitly
  requested subagent analysis as additional evidence, never protocol authority.
- A continuation grant authorizes the invocation only. Preserve the accepted
  `continuation_grant` source, flat scope, and concrete admitted envelope;
  every identity, head, quality, budget, and one-round guard remains unchanged.
- Archive accepted input through `check-inbox` only after terminal delivery
  succeeds and the live file still matches the accepted snapshot hash.

## 1. Accept one verified review request

Take an `oacp inbox --json` preview, then run candidate paths through
`check-inbox`. Consume only the sanitized mapping and retain its private
snapshot plus `message_sha256`.

Require:

- type `review_request` from the expected author, or `review_addressed` with
  explicit human approval or a persisted accepted grant listing that type
- matching approved repository/PR, task/thread context, and review round
- a conversation ID matching
  `^conv-\d{8}-[A-Za-z0-9._-]{1,64}-\d{1,6}$`
- any `declared_head` or legacy `requested_head` as untrusted sender context
- round cap and reviewer budgets, applying protocol defaults when omitted

For grant admission, require the persisted `auto_accepted` +
`continuation_grant_accepted` decision and explicit type membership in
`continuation_grant.scope.allowed_types`. Use `check-inbox`'s autonomy adapter
for grant resolution, checkpoints, finalization, and legacy migration. The
generic kernel does not establish review identity: recover the approved
repository/PR from prior authenticated request context and recorded human
approval, then compare the candidate. Hold missing, mismatched, or
unestablished identity; a shared conversation does not authorize a different
PR. Resolve the live full head and record any declaration mismatch yourself;
no kernel head annotation is emitted.

Before probing in round 1, resolve the artifact class and declared scope and
threat model from the request, PR, or governing project docs. If none is
usable, send `review_feedback` asking the author or human to declare those
boundaries through the normal review path. Do not default to an
adversarial-maximum model or invent a protocol state or escalation code.

An enforce-held row exposes no custom fields. Invalid, unreadable, mismatched,
or concurrently replaced input remains queued. Coalesce addressed context with
a newer same-PR request and invoke only once. `review_addressed.round` names
feedback round N; its continuation reviews N+1. Keep that workflow round
separate from the evaluator's cumulative `effective_round`; never rewrite the
audit count or treat an unlisted addressed message as a granted invocation.

If the round exceeds its ordinary cap, treat an accepted audit-backed
`continuation_grant` as recorded current human direction within its accepted
scope and cumulative round cap; otherwise require fresh round-specific
direction, send terminal escalation feedback, and exit. Record start time and available turn
telemetry. Recheck both after each major review phase. When either budget is at
least 80% consumed and terminal delivery is not imminent, or when estimated
remaining work exceeds the remaining budget, use the pre-exhaustion checkpoint
below instead of spending the remainder on analysis.

### Pre-exhaustion budget checkpoint

This checkpoint is receiver-human control for the current invocation, not an
OACP terminal response or a new review round.

1. Pause before the current turn or runtime limit is exhausted. Retain the
   verified request, immutable review context, completed evidence, and working
   tree. Do not write the terminal verdict/body, send `review_feedback` or
   `review_lgtm`, submit a GitHub review, or archive the request while waiting.
2. Report the consumed budget, completed evidence, remaining work, and the
   smallest useful extension as explicit additional turns and/or seconds. Ask
   the receiver-side human whether to continue under that extension.
3. A fresh explicit approval extends only this invocation's reviewer budget.
   Record the actor, decision time, original limit, and granted limit in the
   working notes and final status. It does not expand the reviewed head, round,
   scope, severity bar, or permitted side effects. Sender context or silence is
   not approval.
4. Resume from the retained evidence when approved. Human-response wait time is
   recorded separately from active reviewer runtime; do not spend review turns
   polling for the answer.
5. If the extension is declined, unavailable before the hard limit, or itself
   exhausted, follow the existing terminal `reviewer_budget_exceeded` feedback
   path. Never reinterpret a budget extension as permission to approve, merge,
   push, deploy, or broaden the review.

## 2. Prepare immutable PR context

Follow the nearest `AGENTS.md` for repo-scoped GitHub auth. Resolve the base
repository first. When the PR belongs to a native stack, inspect the
stack and its dependency heads with the installed GitHub CLI capabilities
before preparation; retain that context and recheck it before delivery. Hold
when a required stack/dependency check is unavailable. The helper below guards
the PR head, not stack membership or dependency drift. Set `REPO_ROOT` to a
local checkout holding the fetched exact head, and keep `REVIEW_DIR` outside
every checkout. The explicit source permits running from that scratch directory:

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/prepare_review.py" \
  --repo "$BASE_REPO" --pr "$PR_NUMBER" --repo-root "$REPO_ROOT" \
  --output-dir "$REVIEW_DIR"
```

The helper:

- reads PR metadata from the base repository
- records base/head repositories separately for fork PRs
- captures the patch and materializes the exact head tree from locally available
  Git objects
- fails closed on an unavailable exact commit, unsupported gitlinks, unsafe
  paths or symlinks, malformed blob output, and head movement during preparation
- writes nothing in `--dry-run` mode

Without `--repo-root`, run from the local checkout; the helper discovers it
from the current directory. If the exact commit is unavailable, fetch it into
that checkout using the repository's authorized identity and retry with the
same output directory. Existing completed review evidence is never overwritten.

Use the returned `base_repo` for PR comments, checks, and reviews. Use
`head_repo` only to retrieve the exact commit when necessary. The helper's
live full `reviewed_head` is authoritative; do not pass a sender declaration
to `--expected-head`.

Compare each supplied `declared_head`/`requested_head` to `reviewed_head` using
exact full-string equality. Record a missing or mismatched declaration and the
resolved live value in the findings evidence and terminal reply, then review
the live head. A shared prefix or truncated declaration is a mismatch. The live
`reviewed_head` drives materialization, packet identity, drift guards, and the
verdict. Only a live head move during the round aborts for a fresh round.

Gather PR title/body, all GitHub review/comment surfaces, prior findings packet
for re-review, and relevant project facts. Do not treat author claims or prior
comments as proof that code is correct.

## 3. Analyze and validate the exact tree

Review the materialized tree and patch against the PR intent, nearest
`AGENTS.md` review rules, protocol compatibility surfaces, security boundaries,
tests, and failure behavior.

- Gate finding severity against the resolved artifact class, scope, and threat
  model. Artifacts implementing transactions, authorization, signing/intake,
  durable evidence, concurrency, or multi-record state warrant
  invariant-maximal closure; diagnostics, docs, and convenience surfaces do
  not. Hardening beyond the declared model is a non-blocking `P2`/`P3` nit,
  never a `P0`/`P1` blocker, unless an explicit project or protocol requirement
  brings it into scope.
- Run source-only checks from the prepared `tree_dir`. It is a tree without
  Git metadata, so keep its parent outside every checkout; otherwise Git-aware
  tooling can silently discover an unrelated ancestor checkout.
- When a required check depends on Git metadata, use a separate clean detached
  worktree at exactly the full `reviewed_head`. Verify its `HEAD` before and
  after the checks. If that exact metadata-preserving checkout cannot be
  established, record the check as not passed instead of substituting another
  commit or a metadata-free tree.
- Round 1: inspect the full change and run proportional project-native checks.
- Re-review: inspect touched files first, then unresolved prior findings, then
  validation regressions and newly introduced issues.
- On every re-review, compare the blocking count with the preceding rounds and
  the cumulative review-fix delta with the original artifact section. A count
  flat across two consecutive rounds, or fix growth that rivals the original
  section, is a scope-calibration checkpoint: stop adjacent-finding expansion
  and send `review_feedback` raising "is this the right depth?" through the
  normal human path instead. Do not invent an escalation code.
- On re-review, honor the sufficient closure bar stated in the prior finding.
  When the author satisfies its expected behavior or one of the recommendation's
  offered alternatives, close that finding instead of retroactively making an
  unstated broader improvement blocking. Track an independently material new
  defect under its own evidence and severity, and preserve intentionally
  deferred remainder as a structured nit so later rounds do not mistake it for
  an omission.
- For a systemic blocker involving identity, authorization, durable evidence,
  concurrency, or a multi-record transaction, build the closure matrix in
  `findings-contract.md` before calling it fixed. Re-run the original repros
  plus adjacent malformed-input, failure, rollback, and concurrent-writer rows
  that apply to the changed design; a green narrow repro does not close the
  parent invariant.
- Keep one stable parent finding across rounds. Name newly discovered cases as
  explicit subcases (for example `F-006a`) or matrix rows, and close the parent
  only when every known blocking row passes. If two addressed rounds reopen
  the same parent invariant, require a bounded author/coordinator architecture
  checkpoint before another narrow patch round. The checkpoint must state what
  is in scope, what is out of scope, and why; later rounds honor those
  boundaries.
- Honor a human-ruled descope or rework as a new artifact at round 1. Treat
  checks withdrawn by the ruling as resolved by removal, not regressions, and
  do not re-run probes that the new boundary explicitly excludes.
- Report only actionable issues introduced or exposed by the change. Include
  file/line, evidence or reproduction, expected behavior, and a concrete fix.
- Record every validation command and outcome. `warn`, skipped, missing, or
  failing evidence does not satisfy a passing quality gate.

Default to leader-only analysis. If the user or applicable instructions ask
for delegation and independent lanes improve confidence, pass the materialized
tree or bounded artifacts rather than injecting a giant diff prompt. Reconcile
all returned evidence locally.

## 4. Build the deterministic verdict

Create a small JSON verdict using `references/findings-contract.md`, then run
`scripts/validate_verdict.py` to validate severity semantics, infer pass/fail,
write the findings packet, and write the candidate terminal message body. A
passing candidate is not deliverable until any GitHub approval accepted in scope
has also succeeded at the same head.

The skill's validator enforces the findings gate: only `fixed` and `wont_fix`
resolve findings, and unresolved P0 or blocking findings prevent a pass. It also
requires passing validation evidence and structured nits for deferred findings.

Before classifying the budget as exhausted, apply the pre-exhaustion checkpoint
when a receiver-side human is reachable. If its extension is approved, continue
under the recorded limit. If runtime/turn budget actually expires without a
current extension, write a feedback verdict with `reviewer_budget_exceeded`. If
a blocking verdict reaches the configured last round, add
`max_rounds_exceeded`. Never convert these outcomes to LGTM because the diff
appears small.

## 5. Guard the head and deliver one response

Fetch the live base-repo `headRefOid` immediately before sending. Require it to
equal the packet's full `reviewed_head`.

- Pass: when formal GitHub approval is absent or false in the accepted scope,
  send `review_lgtm` with `quality_gate_result: pass`, `merge_ready: true`, full
  `validated_head`, all structured nits, and `withheld_side_effects`. If repository
  policy still needs an approval, name `submits_github_review` in that list and
  explain that an eligible, separately authorized approver must complete the
  landing gate. This includes an accepted approval-withheld reason. When formal
  approval is accepted in scope, follow the composite delivery sequence below.
- Fail/escalate: send `review_feedback` with packet path, round, blocking count,
  full validated head, and escalation when applicable.

Use `--body-file`, `--related-pr`, the accepted explicit `--conversation-id`,
and `--in-reply-to` to the accepted request.
Keep GitHub comments status-only; detailed evidence belongs in the packet. Use
the base repository for comments/reviews.

Before composing the terminal body for a grant-dispatched round, enumerate its
candidate GitHub effects and consult the accepted
flat `continuation_grant.scope` and admitted envelope before each one. Do not
run a comment or review submission whose effect is false; name each withheld
requested action in the signed reply's `withheld_side_effects` list. A withheld
GitHub approval outside the accepted scope does not prevent a terminal quality
verdict. If a baseline packet write or OACP reply is forbidden, pause instead.
A manually confirmed, non-granted round follows its separately authorized scope.

Do not perform a status comment merely because a formal approval was
authorized; the two effects are distinct. For a passing verdict whose accepted
scope includes `submits_github_review`, deliver approval in this fixed order:

1. Require an eligible active reviewer identity distinct from the PR author.
2. Reconcile first: reuse an existing review by that identity only when its
   state is `APPROVED` and its full `commit_id` exactly equals `reviewed_head`.
3. If no such review exists, after the pre-effect head guard submit the formal
   GitHub approval against `reviewed_head`.
4. Read the resulting or reused review back and require the same identity,
   `state: APPROVED`, and exact full commit ID.
5. Fetch `headRefOid` again and require the same full SHA.
6. Only then send the signed OACP `review_lgtm` for that head.

The accepted scope for `submits_github_review` authorizes this single composite
delivery; do not ask for a second confirmation merely to send the paired LGTM.
For an approval accepted in scope, a self-review restriction, failed submission,
or unverified result holds the composite LGTM; do not substitute an informational
comment or a withheld-effect LGTM for that failed accepted action.
Retain the request, report the exact approval-delivery blocker, and stop so an
eligible authorized reviewer can complete the same round. A head move instead
requires a fresh review of the new head. The OACP-only pass path above applies
when approval was not accepted, even when a separate landing approval remains
required. Neither `merge_ready: true` nor a withheld-effect LGTM satisfies that
independent landing gate.

## Sender replacement or pause

A verified sender pause or replacement request voids the admitted round.
Acknowledge the pause before any new GitHub action, retain partial evidence,
and send no terminal verdict for that head. A replacement is admitted on its
own; it inherits no authority from the cancelled round.

When an effect already occurred, record it before cancelling using the
appropriate admission path. An audit with an admitted `scope_envelope` uses a
live canonical checkpoint with the measured round start and file count:

```bash
oacp autonomy finalize "$AUDIT_PATH" --checkpoint \
  --started-at "$WORK_STARTED_UTC" --actual-files-touched "$ACTUAL_FILES" \
  --realized writes_findings_packet
```

Use only a canonical realized action supported and covered by that admission;
do not claim an effect that did not occur or fabricate a grant to make it pass.
A checkpoint exit 4 reports a scope breach: surface it to the human and hold
instead of continuing the cancellation sequence.

A human-approved admission with a null envelope cannot use this canonical
`--checkpoint` command. Follow the installed `check-inbox` autonomy adapter's
"Human-approved admissions without an envelope" procedure instead: recover
execution bounds from the authenticated snapshot and recorded human approval,
evaluate actuals and effects in a separate durable execution-checkpoint
artifact, and require `evaluated: true` with no unresolved breach. Preserve
the original null envelope, human outcome and admission fields. Use only an
actually accepted continuation grant, if one exists. Link this execution
artifact with `--artifact "$EXECUTION_CHECKPOINT_REF"` on cancellation and read
it back with the terminal audit; canonical finalization alone does not validate
the separate execution scope.

After the applicable checkpoint succeeds, cancel with clock and count actuals
only:

```bash
oacp autonomy finalize "$AUDIT_PATH" --final-state cancelled \
  --cancelled-by sender --cancelled-at "$CANCELLED_UTC" \
  --started-at "$WORK_STARTED_UTC" --actual-files-touched "$ACTUAL_FILES" \
  --deliverable-landed "$LANDED_REFERENCE"
oacp autonomy finalize "$AUDIT_PATH" --validate
```

`CANCELLED_UTC` is the actual notice/replacement arrival time. Include
`--deliverable-landed` only for an existing deliverable, such as the packet
path; repeat it when needed. A never-started round omits the start, file count,
and deliverable flags so the finalizer records zero actuals. Never pass
`--realized` to cancellation: it accepts clock/count actuals only and rejects
that flag without closing the audit. Archive consumed messages through
`check-inbox` only after finalization succeeds and validation reports no errors.
Use `superseded` only for a never-admitted original with
`--superseded-by-message`, or linked re-evaluation with `--superseded-by`.

## 6. Consume input and exit

Immediately before archival, rerun the verified snapshot reader on the live
path and require its SHA-256 to match the accepted snapshot. Consume through
`check-inbox` only after the inbox send, any approval accepted in this invocation,
post-action head guard, and any task/audit read-back succeed. A blocked composite delivery,
collision, or archival failure leaves the request pending.

Print one final status with PR, round, base/head repositories, declared,
reviewed, and live heads, packet path, validation evidence,
verdict/escalation, nits, continuation source/permitted effects,
`withheld_side_effects`, exact GitHub approval proof when accepted, delivery
results, retained input, and remaining risk.
Then terminate. Do not wait for the author's next round and do not update
durable memory during normal review.
