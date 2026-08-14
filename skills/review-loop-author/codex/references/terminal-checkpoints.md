# Author terminal checkpoints

Use this reference only after verified feedback/LGTM arrives or an active wait
times out. The active protocol remains authoritative.

## Request contract

Create request bodies as YAML files and send them with `oacp send --body-file`.
Record at least:

```yaml
pr: 123
repo: example-org/example
branch: codex/example
declared_head: 0123456789abcdef0123456789abcdef01234567
requested_head: 0123456789abcdef0123456789abcdef01234567
diff_summary: "Short scope summary"
round: 1
review_round: 1
max_review_rounds: 2
max_turns_reviewer: 8
max_runtime_s_reviewer: 600
side_effects:
  - writes_findings_packet
  - sends_oacp_reply
  - submits_github_review
validation:
  - command: make preflight
    result: pass
```

Send round 1 with a separately validated
`--conversation-id conv-<YYYYMMDD>-<originating-agent>-<1..6 digit sequence>`.
Carry that exact ID on every later loop message and add `--in-reply-to` for the
direct parent. Include `submits_github_review` only when a formal approving
review is required and authorized; add `comments_on_github` separately only
when a status comment is intended.

The default maximum is two rounds. A project/request may set three. Values
above three require a protocol change, not local skill discretion.

## Verified intake and archival guard

Treat `oacp watch` and `oacp inbox --json` as candidate discovery only. For
each candidate:

1. Run `check-inbox/scripts/read_verified_message.py` with the project,
   receiver, and `$OACP_HOME`; it resolves the active installed runtime.
2. Consume only the sanitized `message` mapping.
3. Retain `message_sha256` and the private snapshot until disposition.
4. Under enforce mode, do not inspect or infer fields from held input.
5. Immediately before archival, read the live path again through the same
   boundary and require the same SHA-256. A mismatch is concurrent input.

Do not archive on a successful reply alone. Required state/audit writes and
read-back must also succeed. Perform terminal consumption through
`check-inbox` so the original file is moved without overwrite to
`inbox/archive/`; never delete it directly.

## Feedback disposition

| Condition | Action | Consume feedback? |
|---|---|---|
| Wrong sender, PR, round, thread, or packet | Surface mismatch and retain | No |
| Held, invalid, or unreadable | Surface verification/schema state | No |
| `reviewer_budget_exceeded` | Final scan, then request human direction | No |
| Maximum round reached | Final scan, then escalate | No |
| Fixes not yet validated/pushed | Report work in progress | No |
| `review_addressed` or replacement request failed | Retry safely | No |
| Both sends and required state read-back succeeded | Recheck snapshot hash | Yes, if unchanged |

`review_addressed.round` names the feedback round being addressed. A fresh
`review_request` carries the next round number.

## Stale-head LGTM recovery

If `validated_head` differs from the live PR head:

1. Do not merge, approve, or consume the LGTM.
2. Determine whether the author pushed the new commit or unrelated concurrent
   input appeared.
3. Send `review_addressed` or another protocol-appropriate explanation naming
   the stale and current heads.
4. Send a replacement `review_request` for the current full head.
5. Consume the stale LGTM only after both deliveries and state read-back
   succeed and its snapshot hash still matches.

## LGTM authority matrix

| State | Terminal action | Consume LGTM? |
|---|---|---|
| Private implementation task explicitly grants `merges_pr: true`, admission covers it, checks pass, head matches | Merge using project method plus expected-head guard; deliver Done with merge SHA | Yes, after delivery/state read-back |
| User explicitly granted merge, checks pass, head matches | Same authorized landing path | Yes, after delivery/state read-back |
| Explicit park/batch hold defines LGTM-parked as terminal | Record hold, validated head, and nit ownership | Yes, after state read-back |
| Public-facing PR or absent/false merge scope | Request merge approval | No |
| Any required check pending, queued, in progress, failing, errored, cancelled, or timed out | Report exact check state | No |
| Head moved before or after checks | Start stale-head recovery | No |
| Merge surface cannot enforce the expected head | Stop at merge checkpoint | No |
| Merge, final delivery, audit, or task update failed | Report exact failure | No |

Before every authorized merge:

1. When repository/task policy requires a formal approving review, verify an
   eligible identity distinct from the author has review state `APPROVED` and
   the review's commit ID equals `validated_head`. An OACP LGTM alone does not
   satisfy that separate gate.
2. Run the repo's required check command (`gh pr checks` when applicable) and
   require every mandatory result to pass.
3. Fetch `headRefOid` again and require equality with `validated_head`.
4. Use the repository-approved merge strategy and an expected-head option such
   as `--match-head-commit <validated_head>`.
5. Verify the landed result and capture the merge commit SHA.

An identity that cannot approve its own PR cannot satisfy a required formal
approval gate. A permitted status comment is informational and remains a
separate `comments_on_github` effect.

## Nit adoption

Each deferred item must include `nit_id`, `tier` (`P2` or `P3`), summary,
owner, and next action. Preserve tracking/source/expiry fields when present.
Adopt nits into the merge or parked-state context; do not silently discard
them because they are non-blocking.

## Timeout sequence

The author's wait budget owns timeout handling:

1. Run a direct final `oacp inbox --json` snapshot for the project/agent.
2. Verify and route all candidate rows through `check-inbox`.
3. If the expected response exists, continue normally.
4. Otherwise send only the configured timeout notification/status comment.
5. Retain all unmatched, held, invalid, or unreadable rows.

Timeout does not grant authority to re-invoke beyond the round cap, merge,
archive input, or treat a reviewer as having approved.
