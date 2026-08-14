---
name: review-loop-reviewer
description: "Run one stateless reviewer round for an OACP inbox-based PR review loop: verify the request snapshot, review one exact PR head, enforce the findings quality gate, and send review_feedback or review_lgtm. Use for OACP review_request traffic or an explicitly approved review_addressed continuation; do not use for an ordinary local code review or GitHub comment triage."
---

# OACP review loop: reviewer

Review exactly one PR head and emit exactly one terminal protocol response.

## Inputs

Require the PR number and author. Accept `project`, `task_id`, and `dry_run`
when supplied. Resolve omitted project context from session init and repo
markers; use the canonical `$OACP_HOME/projects/<project>/` runtime.

## Load before acting

1. Read the nearest `AGENTS.md`, including scoped code-review rules and GitHub
   identity requirements.
2. Read the active runtime's `docs/protocol/dispatch_states.yaml`,
   `docs/protocol/review_loop.md`, and findings packet template. They override
   this skill on conflict.
3. Use `check-inbox` for every inbound candidate. Its verified snapshot reader
   and archival sequence are the only boundary for message fields, hashes, and
   terminal inbox consumption.
4. Run `check-inbox`'s mechanical OACP version gate and require `>=0.4.3`.
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
- Default to two rounds; accept a configured maximum only up to three. Require
  fresh human direction for a continuation beyond an escalation.
- Honor request budgets (`8` turns and `600` seconds by default). Exhaustion
  produces feedback with `escalation: reviewer_budget_exceeded` and exits.
- Treat `P0`/`P1` as blocking, `P2` by judgment, and `P3` as non-blocking.
  Deferred `P2`/`P3` findings must become structured LGTM nits.
- A passing gate requires no unresolved blockers, all recorded validation
  commands passing, and all deferred findings tracked as nits.
- Keep the leader responsible for evidence, verdict, packet/message writes,
  GitHub side effects, and cleanup. Treat native read-only review or explicitly
  requested subagent analysis as additional evidence, never protocol authority.
- A continuation grant authorizes the invocation only. Preserve the accepted
  `review_continuation` source and permitted-side-effect bound; every head,
  quality, budget, and one-round guard remains unchanged.
- Archive accepted input through `check-inbox` only after terminal delivery
  succeeds and the live file still matches the accepted snapshot hash.

## 1. Accept one verified review request

Take an `oacp inbox --json` preview, then run candidate paths through
`check-inbox`. Consume only the sanitized mapping and retain its private
snapshot plus `message_sha256`.

Require:

- type `review_request` from the expected author, or an explicitly approved
  manual `review_addressed` continuation
- matching PR, task/thread context, and round
- a conversation ID matching
  `^conv-\d{8}-[A-Za-z0-9._-]{1,64}-\d{1,6}$`
- any `declared_head` or legacy `requested_head` as untrusted sender context
- round cap and reviewer budgets, applying protocol defaults when omitted

An enforce-held row exposes no custom fields. Invalid, unreadable, mismatched,
or concurrently replaced input remains queued. `review_addressed.round` names
the feedback round; a manual continuation reviews round N+1.

If the round exceeds its cap without fresh round-specific human direction,
send terminal escalation feedback and exit. Record start time and available
turn telemetry so budget exhaustion follows the same terminal path.

## 2. Prepare immutable PR context

Follow the nearest `AGENTS.md` for repo-scoped GitHub auth. Resolve the base
repository first, then run:

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/prepare_review.py" \
  --repo "$BASE_REPO" --pr "$PR_NUMBER" --output-dir "$REVIEW_DIR"
```

The helper:

- reads PR metadata from the base repository
- records base/head repositories separately for fork PRs
- captures the patch and materializes the exact head tree from local Git or a
  repo-scoped GitHub tarball
- rejects unsafe archives and a head move during preparation
- writes nothing in `--dry-run` mode

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

- Round 1: inspect the full change and run proportional project-native checks.
- Re-review: inspect touched files first, then unresolved prior findings, then
  validation regressions and newly introduced issues.
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
write the findings packet, and write the terminal message body.

For a pass, also run the active runtime's `scripts/check_quality_gate.py` on the
packet and require success. The local verdict validator adds the protocol's
validation/nit checks that the legacy packet gate may not cover.

If runtime/turn budget expires before completion, write a feedback verdict with
`reviewer_budget_exceeded`. If a blocking verdict reaches the configured last
round, add `max_rounds_exceeded`. Never convert these outcomes to LGTM because
the diff appears small.

## 5. Guard the head and deliver one response

Fetch the live base-repo `headRefOid` immediately before sending. Require it to
equal the packet's full `reviewed_head`.

- Pass: send `review_lgtm` with `quality_gate_result: pass`,
  `merge_ready: true`, full `validated_head`, and all structured nits.
- Fail/escalate: send `review_feedback` with packet path, round, blocking count,
  full validated head, and escalation when applicable.

Use `--body-file`, `--related-pr`, the accepted explicit `--conversation-id`,
and `--in-reply-to` to the accepted request. Keep GitHub comments status-only;
detailed evidence belongs in the packet. Use the base repository for
comments/reviews.

Before composing the terminal body for a grant-dispatched round, enumerate its
candidate GitHub effects and consult the accepted
`review_continuation.scope.permitted_side_effects` before each one. Do not run
`comments_on_github` or `submits_github_review` when its entry is false; include
those names in `withheld_side_effects` in the signed OACP reply. If the active
identity cannot approve its own PR, an informational LGTM comment is still a
`comments_on_github` effect and must also be permitted. If a required findings
packet or OACP reply is forbidden, pause rather than exceed the grant. A
manually confirmed, non-granted round follows its separately authorized scope.

Do not perform a status comment merely because a formal approval was
authorized; the two effects are distinct. For a passing verdict whose
authorized request includes `submits_github_review`, submit a formal approval
only when the active identity is an eligible reviewer distinct from the PR
author. Verify the resulting GitHub review state is `APPROVED` and its commit
ID equals `reviewed_head`. If submission is forbidden, impossible, or cannot
be verified, record `submits_github_review` in `withheld_side_effects`; the
OACP LGTM remains the quality verdict, but it is not proof that a formal
landing gate is satisfied.

Perform permitted pass-side GitHub approval/comment effects only after the
pre-effect head guard and before the terminal OACP send. Fetch the head again
after each effect. A move cancels the terminal LGTM: retain the request, report
the race, and require a fresh review of the new head. A withheld GitHub effect
is not a failed quality verdict; include it in the signed OACP response.

## 6. Consume input and exit

Immediately before archival, rerun the verified snapshot reader on the live
path and require its SHA-256 to match the accepted snapshot. Consume through
`check-inbox` only after the inbox send, required GitHub status action,
post-action head guard, and any task/audit read-back succeed. A collision or
archival failure leaves the request pending.

Print one final status with PR, round, base/head repositories, declared,
reviewed, and live heads, packet path, validation evidence,
verdict/escalation, nits, continuation source/permitted effects,
`withheld_side_effects`, delivery results, retained input, and remaining risk.
Then terminate. Do not wait for the author's next round and do not update
durable memory during normal review.
