# Author-side terminal checkpoints (review-loop-author)

Load when handling LGTM, timeout, escalation, a sanctioned continuation, or
crash recovery. SKILL.md owns the sequencing; this file owns the detail.

## LGTM checkpoint (SKILL.md Step 8)

Requirements before treating an LGTM as terminal:

1. The message passed the verified-intake rule (SKILL.md Step 2).
2. Body has `quality_gate_result: pass` and `merge_ready: true`.
3. **Exact-head check**: body `validated_head` (full SHA) equals the live PR
   head (`gh pr view <PR> --json headRefOid -q .headRefOid`). Missing or
   mismatched → the LGTM is stale: report it, keep the message in the inbox,
   and send a fresh round-N+1 `review_request` at the live head instead of
   proceeding. Never "approximately" match a short prefix.
4. **Read `withheld_side_effects`**: a withheld `submits_github_review` on a
   repository whose ruleset requires a submitted review still blocks the
   merge — report it with the checkpoint rather than calling the PR
   merge-ready.
5. **Adopt nits**: every `nits` entry (structured deferred P2/P3 item) is the
   author's to drive post-merge:
   - preserve the list in merge context (PR comment or completion notification);
   - a trivially bounded nit — a one-paragraph doc correction with no
     evaluator, fixture, or changelog change — lands as its own follow-up PR
     right away (file the issue for the `Closes` line, fix, one review round);
     file-and-defer below is for nits that need scoping;
   - within 24h post-merge, open one follow-up issue per PR (checklist keyed
     by `nit_id`) and record `tracking_ref` per nit — or, when the dispatch
     already carries a tracking issue with a scoped follow-on leg, add a
     `nit_id` checklist comment to that issue and use it as `tracking_ref`;
   - when the dispatching task declared `files_issues: false`, filing an issue
     is outside its envelope (it surfaces only when the terminal finalize
     refuses the checkpoint, after the reviewer has seen it): record the nit
     in the project's `memory/known_debt.md` with that reason as its
     `tracking_ref` and carry it in the Done reply, or ask before filing.
     Match the ledger's existing shape (a table gets a row — replace any
     placeholder row rather than appending below the table);
   - defaults per protocol: unresolved at 14 days → status `notification`;
     30 days (or `expires_at_utc`) → convert to `task_request` or close as
     stale/accepted-risk with rationale.
6. Update task fields if a task id exists: `review_status: approved`,
   `review_round`, append the reviewer to `lgtms`.
7. Archive the LGTM message (SKILL.md terminal archival helper, never plain
   `rm`) only after the above bookkeeping succeeds.
8. Do NOT merge inside this skill. Merge only with the approval your
   repository's policy requires, and bind the merge to this head:
   `gh pr merge <PR> --squash --match-head-commit <validated_head>`
   (substitute the repository's merge strategy). Leave out `--delete-branch`
   on a repository that deletes merged branches itself: the flag closes any PR
   based on the branch.

## Timeout / escalation (SKILL.md Step 10)

**Mandatory final drain first (timeout only)**: re-run the inbox scan one last
time before composing ANY timeout messaging. Messages race timeouts — a
response landing seconds before the timeout decision makes a public "timeout"
claim false. If the drain matches, the timeout is VOID: process the message
normally and send nothing about a timeout.

Escalation reasons: `max_rounds_exceeded` (round cap hit),
`reviewer_budget_exceeded` (reviewer ran out of turns/runtime — treat the
attached findings as a partial round, do not re-request without addressing
them), or a stale round the human calls a timeout. After any escalation the
loop stops pending fresh human direction; a second escalation needs a fresh
sanction.

`reviewer_budget_exceeded` can arrive with `blocking_count: 0` and every
check passed — the reviewer ran out before composing the verdict. It is still
the full escalation path, not an LGTM in disguise: address any attached nit,
post the escalation comment, stop for direction, then a sanctioned round N+1
at the (possibly unchanged) head. When the sanctioned request raises
`max_runtime_s_reviewer` or `max_turns_reviewer`, say so in `human_direction`.
The reviewer's receiver may gate the bump on its own human's approval, so
expect a delay before the round starts, and never treat the bump as
self-authorizing.

Escalation notification: to the task's dispatcher, threaded on the dispatch.
With no dispatch, the human in session is the only escalation target. Never a
placeholder recipient: `oacp send` creates any named recipient's inbox, so a
made-up `--to team-lead` reports success into an inbox no agent watches.

```bash
oacp send "$PROJECT" \
  --from claude --to <dispatcher> --type notification \
  --subject "Review escalation: PR #<PR_NUMBER>" \
  --parent-message-id <dispatch id> --conversation-id <dispatch conversation_id> \
  --body "Review loop for PR #<PR_NUMBER> escalated after <round> rounds.
Reason: <reason>
Next steps: synchronous coordination or human review." \
  --related-pr <PR_NUMBER> --priority P1 --oacp-dir "$OACP_HOME"
```

Status lines: `STATUS: ESCALATED` (round cap or reviewer escalation) or
`STATUS: TIMEOUT`.

## Sanctioned continuation and standing grants (SKILL.md Step 10)

**Per-round sanction** (after `max_rounds_exceeded`): the round-N+1 request is
a normal Step 4 body plus three deltas:

- `human_direction: <who> sanctioned round <N+1> on <when>, scope <scope>` —
  review_loop.md → Escalation requires it on any round past `max_rounds`;
- `max_rounds: <N+1>` (bumped to the sanctioned round number);
- `--parent-message-id <id> --conversation-id <conv>`, both captured from the
  escalating `review_feedback`'s `id:` and `conversation_id:` when it was
  read. That feedback is already archived (or lives in another workspace when
  the round was re-routed), so never rely on `--in-reply-to` resolving it.

Echo the same `human_direction` on the paired round-N `review_addressed` so
both messages carry the sanction. Fix and push BEFORE asking for the
sanction. The sanction covers one round unless the human explicitly grants
continue-until-LGTM.

**On a dispatched task, the sanction ask carries the clock too.** Read the
work clock against the dispatch's `task_profile.estimated_minutes`, the bound
the post-accept checkpoint measures, before asking. When the extra round will
cross it, ask for a scoped minutes budget in the same question (check-inbox
`references/autonomy.md` §E, prospective clear). Approving the paused
admission or the round does not raise the bound, so without the budget the
terminal finalize pauses at the checkpoint (exit 4) and the Done reply waits
on a second human round-trip.

**Standing continue-until-LGTM grant**: offer it as the recommended option
when repeated per-round sanctions keep landing the same way on converging
findings. Executing it: carry the grant in `human_direction:` on EVERY
subsequent `review_addressed` + `review_request` ("standing
continue-until-LGTM, recorded receiver-side"), bump `max_rounds` to current+1
each round, and name an explicit circuit-breaker round ("escalate to the
human only if the loop reaches round N") — an unbounded grant with no breaker
invites a runaway loop.

**Reaching your own breaker while findings still converge** (a fixed finding
narrowed into a sub-case): proceeding under an explicit human "continue until
merged" is defensible only with the override stated verbatim in
`human_direction:` on both messages, the breaker re-armed at a named later
round, and the override disclosed in the Done reply.

## Options, splits, and descoping (SKILL.md Step 10)

**Read the standing rules before putting options in front of the human.** An
escalation asks them to choose, and the organization may already have ruled
on some of these choices. Search its standing rules (for example
`$OACP_HOME/org-memory/rules.md`) for the escalation reason first, present a
standing answer as one of the options with its rule cited, and say plainly if
you think this case is the exception — an options list that omits it quietly
reopens a settled decision. When a component still blocks at
`max_rounds_exceeded`, splitting it into its own PR (a fresh round-1 budget)
usually beats landing it defective or unreviewed on an exhausted loop.

**Executing an approved split**: withdraw the blocking component, land the
settled remainder, then rebase (never stack — SKILL.md Notes) the split branch
onto the new base and open it at round 1 with a full budget. This is
especially right for guards and gates, where a half-correct check reads green
while the thing it claims to verify is wrong. A test that cannot run until the
landed PR exists should skip with a reason naming the dependency, not pass
vacuously.

**Closing an escalation by scope reduction is not a new round, and the
terminal reply must say so**: carry `resolution:
scope_reduced_by_human_direction`, state that the reviewed content is a strict
subset of what was already reviewed minus the withdrawn component, name which
findings closed by fix versus by withdrawal, record that the human chose among
enumerated options, and state the merge blocker explicitly (a
ruleset-protected PR still needs the GitHub approval; the reviewer's earlier
`CHANGES_REQUESTED` may be what blocks it now). If the descope reworks rather
than subtracts, it is a new artifact: relabel the pending request round 1,
close the old loop's escalation state, and list the previously fixed checks
now intentionally out of scope ("resolved by removal, not regressions") so the
reviewer's gate does not re-flag them.

## PR comment templates (status-only)

Always via `--body-file` with a temp file (never inline `--body` — shell
expansion leaks to `ps`). Data-minimization: status only; no diffs, logs,
paths, command output, or credentials — detail belongs in protocol messages
and findings packets.

Review requested:

```
**Review requested** - claude -> <REVIEWER>

Round: <N>
Scope: PR #<PR_NUMBER>
Details delivered via inbox review_request message.
```

Feedback addressed:

```
**Feedback addressed (round <N>)** - claude

Status: updates pushed for re-review.
Details delivered via inbox review_addressed message.
```

Loop complete:

```
**Review loop complete** - claude

LGTM received from <REVIEWER>. PR is merge-ready.
```

Escalated:

```
**Review loop escalated** - claude

Reason: <reason>. Manual coordination needed.
```

## Idempotency and crash recovery

Before sending `review_request` or `review_addressed` after a crash/restart,
check your outbox and the reviewer's inbox for an already-sent message for
this PR+round — skip the send if a duplicate exists. The inbound
`review_feedback` file is archived only after the round's outbound sends
succeed, so a crash mid-round leaves it in place for clean re-dispatch.

## Notification-shaped feedback fallback

A verified `notification` from the reviewer carrying `related_pr` plus a
GitHub request-changes review is round feedback without a packet: treat the
notification body + the GitHub review text as `FINDINGS_CONTENT`, infer the
reviewer from `from:`, and run the normal round flow.
