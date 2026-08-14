---
name: review-loop-author
description: "Coordinate the author or coordinator side of an OACP inbox-based PR review loop: request exact-head review, route verified feedback, re-request bounded rounds, and land or park only at an authorized terminal checkpoint. Use for OACP review_request, review_feedback, review_addressed, or review_lgtm traffic; do not use for an ordinary local code review or only addressing GitHub comments."
---

# OACP review loop: author

Coordinate one PR from a ready review request through feedback, LGTM, landing,
or an explicit parked/escalated state.

## Inputs

Require the PR number and reviewer. Accept `project` and `task_id` when the
caller supplies them. Resolve omitted project context from session init and
repo markers; use the canonical `$OACP_HOME/projects/<project>/` runtime.

## Load before acting

1. Read the nearest `AGENTS.md`, especially GitHub identity, checks, merge, and
   project-specific review rules.
2. Read the active runtime's `docs/protocol/dispatch_states.yaml` and
   `docs/protocol/review_loop.md`. They override this skill on conflict.
3. Use `check-inbox` for every candidate inbound message. Its verified snapshot
   reader and archival sequence are the only boundary for custom fields,
   hashes, and terminal inbox consumption.
4. Run `check-inbox`'s mechanical OACP version gate and require `>=0.4.3`.
5. Read [terminal-checkpoints.md](references/terminal-checkpoints.md) when
   handling feedback, LGTM, timeout, escalation, or inbox archival.

Set `REVIEW_LOOP_AUTHOR_SKILL` to the absolute directory containing this
`SKILL.md`; use that path when invoking bundled resources from a project.

## Non-negotiable invariants

- Keep the reviewer stateless. One invocation sends one terminal
  `review_feedback` or `review_lgtm` and exits. The author owns re-invocation.
- Default to two rounds. Allow a project or request override only up to three.
- Carry reviewer budgets in each request: `max_turns_reviewer` defaults to `8`
  and `max_runtime_s_reviewer` defaults to `600`.
- Poll only through a shell/script loop or a Codex heartbeat. Never spend model
  turns on periodic idle checks.
- Bind requests, validation, findings, LGTM, checks, and merge to full commit
  SHAs. A moved head is new review input.
- Establish one schema-valid conversation ID at round 1 and carry it unchanged
  on every question, request, addressed reply, feedback, and LGTM in the loop.
- Treat `P0`/`P1` and blocking `P2` findings as blockers. Preserve deferred
  `P2`/`P3` items as structured LGTM nits with an owner and next action.
- Keep protocol acceptance, GitHub approval, merge authority, and task
  completion separate. Codex `--approve-for-me` is not OACP admission, GitHub
  approval, or merge authority.
- Archive inbound messages through `check-inbox` only after the required
  outbound/state side effects succeed and the live file still matches the
  accepted snapshot hash.
- Keep the leader responsible for protocol state, writes, validation, GitHub
  side effects, and the final decision. Use delegation only when the user or
  applicable instructions request it and the lanes are genuinely independent.

## 1. Resolve and validate the review round

- Confirm repo root, base repository, PR number, reviewer, project, and live
  `headRefOid`. Follow the nearest `AGENTS.md` for repo-scoped GitHub auth.
- Require a GitHub-ready PR. If project policy says a formal request implies a
  non-draft PR, mark it ready before requesting review.
- Record the exact requested head, round, task ID, validation commands/results,
  parent message ID, and validated incoming conversation ID.
- Refuse a round above the configured maximum without fresh, round-specific
  human direction. Never turn an escalation continuation into standing grant.

## 2. Prime the watch and send `review_request`

Prime a distinct cursor immediately before sending so a fast response cannot
fall between request delivery and first poll:

```bash
python3 "$REVIEW_LOOP_AUTHOR_SKILL/scripts/review_wait.py" \
  --prime --project "$PROJECT" --agent codex \
  --oacp-dir "$OACP_HOME" --state-id "review-pr-${PR_NUMBER}"
```

If priming reports existing traffic, route it through `check-inbox` before
sending. Do not infer review fields from watch metadata.

Create the conversation identity once. Its sequence must be numeric, unique for
the originating agent/date, and no more than six digits; do not blindly use a
seven-or-more-digit PR number:

```bash
CONVERSATION_SEQUENCE="$(python3 - <<'PY'
import secrets
print(secrets.randbelow(1_000_000))
PY
)"
CONVERSATION_ID="conv-$(date -u +%Y%m%d)-codex-${CONVERSATION_SEQUENCE}"
```

Validate the ID against
`^conv-\d{8}-[A-Za-z0-9._-]{1,64}-\d{1,6}$`. Pass
`--conversation-id "$CONVERSATION_ID"` on round 1 and every later loop send.
Use `--in-reply-to` as direct reply linkage, never as the only conversation
mechanism; an archived parent cannot donate a conversation ID.

Send a protocol-valid `review_request` with `--body-file`. Include:

- `pr`, `repo`, branch, exact `declared_head`, and a concise `diff_summary`
- `round`, configured maximum rounds, and legacy `review_round` when older
  reviewer tooling still consumes it
- legacy `requested_head` as the same full SHA when older reviewer tooling
  still consumes it
- reviewer turn/runtime budgets
- task/handoff context when present
- validation commands and passing results already available to the author
- every intended outward review effect in `side_effects`

`repo`, `round`, and `declared_head` are the continuation-matching fields.
Scope matching fails closed without `repo`. Both head fields are sender context,
not proof; carry the same verbatim full SHA and let the reviewer resolve the
live head. A declaration mismatch is recorded and resolved, not used as a
hard expected-head precondition.

Declare the effects every round needs. Omission declares only the baseline
findings packet and OACP reply. Before sending, determine whether the repository
landing gate requires a formal approving GitHub review. When it does and the
selected reviewer is a distinct identity that can approve, make
`submits_github_review` explicit in both the surfaced authorization scope and
the request. Keep `comments_on_github` only when a status comment is intended:

```yaml
side_effects:
  - writes_findings_packet
  - sends_oacp_reply
  - comments_on_github
  - submits_github_review
```

Authority still depends on the admission path:

- For a continuation-grant round, list GitHub effects only when the accepted
  grant permits them. An expanded declaration pauses with the evaluator's
  scope-exceeded result.
- For a manually confirmed, non-granted round, surface each GitHub effect in
  the confirmation scope and proceed only when it was explicitly authorized.

If a required approving review cannot be requested within the authorized
scope, name it as withheld and arrange an authorized approver before treating
LGTM as landing-ready. Never spend a second review round merely because the
first request omitted an already-known landing requirement.

Use `--in-reply-to` for later rounds and pass the same explicit
`--conversation-id` on questions, `review_addressed`, and replacement
`review_request` messages. Retain the round-1 outbound message ID,
conversation ID, and live head as round state.

## 3. Wait without model polling

Prefer a project-scoped Codex heartbeat for detached waits. Each wake runs one
watch/inbox step, reports only changed state, and stops at a terminal response.

For an active foreground wait, run the same helper with `--wait`, a
roughly 30-second interval and a 10-15 minute budget unless project policy says
otherwise. The helper capability-checks `--state-id`, falls back to the legacy
direct-inbox path when necessary, and performs a direct final inbox scan on
timeout.

Route every new-message event through a normal `check-inbox` pass. Higher
priority unrelated traffic can preempt the loop. A watch cursor proves only a
delta, never the absence or authority of a full message.

## 4. Handle verified `review_feedback`

From the accepted snapshot, require the expected sender, PR, round,
schema-valid matching conversation ID, direct reply thread, findings packet,
and blocking count. Retain held, invalid, mismatched, or concurrently replaced
rows and surface the reason.

- On `reviewer_budget_exceeded` or terminal round escalation, stop for fresh
  human direction after one final inbox scan.
- Otherwise inspect the findings packet, reproduce blockers, and decide the
  smallest safe fix set. Do not blindly implement recommendations.
- If delegation was explicitly enabled, give read-only triage or disjoint fix
  lanes; the leader integrates and validates all results.
- Apply accepted fixes, run proportional project-native checks, commit/push
  under repo policy, and capture the new full head SHA.
- Send `review_addressed` for the feedback round with commit SHA, changes
  summary, touched files, addressed finding IDs, packet reference, and the new
  validated head; pass the established conversation ID and reply directly to
  the feedback.
- Send a fresh `review_request` for round N+1 with that same conversation ID,
  `repo`, canonical `round`, exact `declared_head`, reviewer budgets, and the
  authorized `side_effects`. Consume the feedback only after both sends
  succeed, task/audit read-back succeeds when applicable, and the final
  snapshot hash still matches.

The next reviewer invocation rereads the exact new head. Do not wait for it in
the old reviewer session.

## 5. Handle verified `review_lgtm`

Require `quality_gate_result: pass`, `merge_ready: true`, and a full
`validated_head`. Compare it to the live PR head immediately. A missing or
mismatched head makes the LGTM stale; retain it until the replacement-round
messages are delivered.

Adopt every structured nit before landing. Then apply the authority and exact-
head matrix in `references/terminal-checkpoints.md`:

- Authorized landing: when repository/task policy requires formal approval,
  require an eligible distinct reviewer whose GitHub review is `APPROVED` and
  whose review commit equals `validated_head`; then require all checks passing,
  recheck head, merge with an expected-head guard, deliver the final task
  result, and consume the LGTM.
- Explicit LGTM-parked hold: record the parked state and nit ownership, then
  consume only after required state updates succeed.
- Missing merge authority, pending/failing checks, or delivery/state failure:
  report the checkpoint and retain the LGTM.

## 6. Timeout, error, and terminal output

On timeout, use the helper's final inbox snapshot and run candidates through
`check-inbox` before emitting a timeout notification/comment. If a matching
response exists, cancel the timeout and handle it normally.

Report one terminal status with PR, round, requested/validated/live heads,
validation performed, packet paths, nits, authority disposition, merge commit
when landed, retained inbox rows, and remaining risk. Do not update durable
memory during ordinary review-loop execution.
