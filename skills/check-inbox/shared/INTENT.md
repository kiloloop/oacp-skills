# check-inbox — Shared Intent

## What it does

Single-pass inbox processor for OACP agent coordination. Scans an agent's inbox directory for pending YAML messages, acts on each based on message type, and archives terminally processed messages.

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
| `follow_up` | Informational reply/amendment on an existing thread — summarize, update parent state |

## Protocol references

- **Inbox/outbox format**: Messages are YAML files with fields: `id`, `from`, `to`, `type`, `priority`, `created_at_utc`, `subject`, `body`, `related_pr`, `parent_message_id`
- **Lifecycle**: Sender writes to recipient's `inbox/` and own `outbox/`. Recipient archives to `inbox/archive/` (no-clobber atomic move, original filename, byte-preserving) after terminal processing.
- **Inbox path**: `$OACP_HOME/projects/<project>/agents/<agent>/inbox/`

## Acceptance criteria

- Every inbound message is verified at intake (`oacp verify`, oacp-cli v0.4.2+); invalid or unsigned-from-a-pinned-sender messages are quarantined and held, never silently processed
- All pending messages are read and acted upon
- Replies sent for message types that require them (`task_request`, `question`, `handoff`)
- Fully-processed messages archived to `inbox/archive/` (never plain-deleted; pending/held messages stay in `inbox/`)
- Unknown message types reported to user without deletion
- Safety rules enforced (large tasks confirmed, autonomous boundary respected)
- Every autonomy decision writes an audit event; envelope enforcement is used only when the active runtime has a verified adapter, otherwise the audit records no enforcement

## Recurring polling

This skill is single-pass by design. For continuous monitoring, prefer the event-driven `oacp watch --state-id <id>` runner (v0.4.0+, per-subscriber cursors — duplicate delivery across concurrent watchers is the norm; confirm a message file still exists before processing) or wrap the skill in a recurring scheduler (e.g., every 2 minutes). The wiring is runtime-specific — see the runtime SKILL.md for details.
