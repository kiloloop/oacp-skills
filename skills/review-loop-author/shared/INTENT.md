# review-loop-author — Shared Intent

## What it does

Runs the author side of an asynchronous code review loop. When review feedback arrives (via inbox), the skill parses the findings, spawns a fix subagent to address them, commits and pushes the fixes, then notifies the reviewer that changes are ready for re-review. Repeats until LGTM or max rounds exceeded.

## Architecture

Hybrid leader/subagent split:

- **Leader**: handles all external I/O — inbox reads/deletes, git operations, GitHub API calls, message sending
- **Fix subagent**: read-only + edit — examines findings, modifies source files, outputs a structured fix summary. No shell access.

This separation ensures the subagent cannot accidentally perform destructive operations.

## Message types

| Direction | Type | Purpose |
|-----------|------|---------|
| Sends | `review_request` | Request initial or re-review from reviewer |
| Sends | `review_addressed` | Notify reviewer that feedback was addressed |
| Sends | `question` | Push back on a finding with reasoning |
| Receives | `review_feedback` | Findings packet from reviewer |
| Receives | `review_lgtm` | Approval — review loop complete |

## Protocol references

- **Findings packet format**: YAML with `packet_id`, `findings[]` (each with `id`, `severity`, `blocking`, `status`, `file`, `line`, `recommendation`)
- **Fix summary format**: Structured block with `fixed`, `deferred`, `pushed_back`, `files_modified` lists
- **Quality gate**: Passes when zero P0 and zero blocking findings remain open
- **Inbox path**: `$OACP_HOME/projects/<project>/agents/<agent>/inbox/`

## Acceptance criteria

- All blocking findings addressed (fixed or pushed back with reasoning)
- Changes committed and pushed to the PR branch
- `review_addressed` message sent to reviewer with commit SHA and changes summary
- New `review_request` sent for next round (enabling event-driven re-review)
- PR comment posted for human visibility (status only)
- Max rounds enforced — escalation sent if exceeded
