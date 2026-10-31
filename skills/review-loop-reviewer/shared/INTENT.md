# review-loop-reviewer — Shared Intent

## Contract

Run one stateless review of one exact live PR head. Verify the request, establish
admission and bounds, gather context, evaluate concrete findings, deliver one
terminal `review_feedback` or `review_lgtm`, finalize evidence, and exit. The
author owns every subsequent invocation.

## Admission and identity

Use verified intake and immutable snapshots. Coalesce addressed context with a
newer matching request; do not execute twice. A standalone `review_addressed`
requires explicit human approval or an accepted grant listing that type.
`auto_accepted` plus `continuation_grant_accepted` is valid only with a persisted
matching audit and its flat type/time/file/effect bounds. Independently verify
the human-approved repository/PR; generic thread matching does not establish it.

Resolve the live full head independently. A missing or mismatched declaration is
recorded and resolved, not silently trusted. Bind findings, tests and every verdict
to the reviewed head; movement during the invocation invalidates that verdict.
Materialized source must preserve the committed bytes, and Git-dependent checks
need an isolated checkout of the exact commit.

## Review and quality gate

Review the changed behavior against the stated scope and its callers. Prioritize
unresolved findings and regression signals on later rounds. State the threat
model and exclusions; for identity, authorization, concurrency or durable-evidence
changes, test the invariant and relevant failure/recovery boundaries. Delegate
bounded analysis only when allowed, retaining leader responsibility for effects.

Findings include a stable ID, severity, blocking flag, status, precise location,
reproduction/evidence, impact and recommendation. Only `fixed` or `wont_fix`
resolves a finding. All P0/P1 and blocking P2 findings block approval. Deferred
nonblocking P2/P3 findings become structured nits with an owner and next action.
The quality gate requires passing validation and no unresolved blockers.

## Effects and termination

Write the validated findings packet before side effects. Perform only admitted
GitHub effects; formal review and status comment permissions are distinct. Never
approve one's own PR. Record excluded requested effects in
`withheld_side_effects`. If approval is absent or false in the accepted scope,
send the passing quality verdict with
`submits_github_review` withheld when the landing gate still needs it. An
eligible, separately authorized approver must satisfy that gate before merge.
This accepted withheld-effect path always has a terminal OACP response.

Codex treats an approval it accepted in scope as composite delivery: submit or
read back the eligible exact-head approval before its LGTM; an in-scope failure,
self-review restriction or missing proof retains the request. The Claude slice
can report its signed quality verdict with withheld effects under its own
stated fallback ordering. Neither runtime may count a status comment or an
OACP-only verdict as an independent required GitHub approval.
Recheck the live head after GitHub effects and before the signed terminal reply.

A successful reply is delivered with the original parent/conversation binding,
then the audit is finalized and read back, and accepted inputs are archived
without clobbering or changing signed bytes. Never wait in the reviewer for fixes.

A sender cancellation is handled while evidence is still live: checkpoint any
already-realized effects first, then cancel with supported work clock/count and
landed-deliverable evidence. Never pass unsupported effect flags to cancellation
or archive a live audit. Budget exhaustion produces the protocol's terminal
escalation; an extension requires actual human authority before more work.
