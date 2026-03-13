# check-inbox — Shared Intent

## What it does

Single-pass inbox processor for OACP agent coordination. Scans an agent's inbox directory for pending YAML messages, acts on each based on message type, and deletes processed messages.

## Message types handled

| Type | Action pattern |
|------|---------------|
| `notification` | Read and acknowledge — no reply needed |
| `task_request` | Evaluate scope, execute or confirm with user, reply when done |
| `question` | Answer and reply with `notification` |
| `review_request` | Dispatch to reviewer skill |
| `review_feedback` | Dispatch to author skill |
| `review_lgtm` | Report approval to user |
| `review_addressed` | Informational — summarize changes to user |
| `handoff` | Accept context, reply with `handoff_complete` |
| `handoff_complete` | Acknowledge handoff completion |

## Protocol references

- **Inbox/outbox format**: Messages are YAML files with fields: `id`, `from`, `to`, `type`, `priority`, `created_at_utc`, `subject`, `body`, `related_pr`, `parent_message_id`
- **Lifecycle**: Sender writes to recipient's `inbox/` and own `outbox/`. Recipient deletes from inbox after processing.
- **Inbox path**: `$OACP_HOME/projects/<project>/agents/<agent>/inbox/`

## Acceptance criteria

- All pending messages are read and acted upon
- Replies sent for message types that require them (`task_request`, `question`, `handoff`)
- Processed messages deleted from inbox
- Unknown message types reported to user without deletion
- Safety rules enforced (large tasks confirmed, autonomous boundary respected)

## Recurring polling

This skill is single-pass by design. For continuous monitoring, wrap it in a recurring scheduler (e.g., every 2 minutes). The polling mechanism is runtime-specific — see the runtime SKILL.md for details.
