# review-loop-author — Shared Intent

## Contract

Coordinate a PR from a bounded review request through verified feedback, fixes,
re-review, and an authorized landing or explicit parked checkpoint. The author
owns re-invocation; every reviewer invocation exits after one terminal verdict.

## Requests and authority

Resolve the PR's base repository to its registered reviewer project. Confirm
registration, trust and a working pickup path; never route a new review to an
unrelated inbox merely because it is reachable. Existing verified threads retain
their project and parent/conversation identifiers until explicitly migrated.

Each request carries the full declared/requested head, repository/PR identity,
round and maximum rounds, reviewer turn/runtime budgets, validation evidence and
intended effects. Findings and OACP replies are explicit baseline effects;
formal GitHub reviews and status comments are separate capabilities. When the
landing gate needs approval and an eligible authorized reviewer can provide
it, declare that effect before requesting the round. If it cannot be accepted
in scope, state why and arrange a separately authorized eligible approver
before landing. A passing reviewer still sends terminal `review_lgtm` with
`withheld_side_effects` naming the outstanding approval; OACP verdict and
GitHub landing gate remain separate. An approval accepted in scope whose
submission or exact-head readback fails holds the composite approval/LGTM path.

A grant is receiver-validated authority, not a sender assertion. Default to two
rounds, with an ordinary override up to three; requests beyond the governing cap
need recorded current human direction or a valid bounded continuation grant.

## Feedback and re-review

Use verified intake for every response and validate sender, thread, PR, round
and packet. Reproduce blockers, fix the underlying invariant, and run proportional
checks. For systemic findings, map failure and recovery paths to acceptance
probes before editing. The leader owns protocol state, writes and outward effects;
optional delegation follows the active runtime and authorization.

After fixes, send `review_addressed` for the feedback round and a fresh
`review_request` for the new full head. A superseding request names its predecessor
and reason; a `follow_up` cannot repoint an already-started review. Archive feedback
only after replacement sends and required state readbacks succeed.

## Landing gate

Require a passing quality gate, `merge_ready: true`, and `validated_head` equal to
the live full head. Adopt every deferred nit with an owner and next action.
Require all applicable checks passing and any required formal eligible GitHub
approval at that same head. Recheck the head and use an expected-head merge guard.
LGTM alone provides no merge authority. An authorized private task whose scope
includes landing completes after the merge and delivered Done reply with its SHA;
an explicit park hold can instead define the terminal result.

## Completion and waits

Keep inbox evidence until required replies, audit/state updates and terminal
readbacks succeed, then archive through verified intake's no-clobber path.
Pending checks, missing authority or failed delivery retain the input. Wait with
an event-driven watcher, scheduler or script loop; never idle-poll in model turns.
On timeout, perform a final authoritative inbox scan before escalation.
