# OACP — Shared Intent

Runtime-agnostic protocol facts for the OACP skill. Both the Claude Code and Codex variants reference this document.

## What OACP is

The Open Agent Coordination Protocol is a file-based message bus for multi-agent workflows. Agents coordinate by writing YAML messages to each other's inbox directories. There is no daemon, no broker, no network — just files on disk under `$OACP_HOME/projects/<project>/`.

## Workspace layout

```
$OACP_HOME/
├── org-memory/                     # cross-project facts (optional)
│   ├── decisions.md
│   ├── events/
│   └── recent.md
└── projects/
    └── <project>/
        ├── agents/
        │   ├── <agent-A>/
        │   │   ├── inbox/          # incoming messages
        │   │   └── outbox/         # sent-message archive
        │   └── <agent-B>/
        │       ├── inbox/
        │       └── outbox/
        └── memory/                 # project-scoped memory (optional)
```

## Message schema

Every inbox/outbox message is a YAML file with these fields:

| Field | Required | Description |
|-------|:---:|-------------|
| `id` | yes | Unique id, format `msg-<UTC-timestamp>-<sender>-<short-hash>`. |
| `from` | yes | Sender agent name. |
| `to` | yes | Recipient agent name (or comma-separated list for broadcast). |
| `type` | yes | One of the protocol types listed below. |
| `priority` | yes | `P0` / `P1` / `P2` / `P3`. |
| `created_at_utc` | yes | ISO 8601 timestamp. |
| `subject` | yes | One-line summary. |
| `body` | yes | Markdown body. |
| `related_pr` | no | GitHub PR number (used by `review_request` / `review_feedback`). |
| `related_packet` | no | Design-packet id (used by `review_request` for specs). |
| `parent_message_id` | no | Id of the message this replies to. (CLI flags `--parent-message-id` and `--in-reply-to` both set this field; `--in-reply-to` additionally looks up the parent in the sender's outbox to inherit `conversation_id`.) |
| `conversation_id` | no | Thread identifier. |
| `expires_at` | no | Expiration timestamp (ISO 8601 UTC, set via `oacp send --expires <duration>`). |
| `channel` | no | Optional channel namespace. |
| `context_keys` | no | Map of additional structured fields. |

## Lifecycle

1. **Send** — sender writes the message to the recipient's `inbox/` AND a copy to the sender's own `outbox/` (audit trail).
2. **Detect** — recipient discovers new messages by listing `inbox/` (one-shot) or by watching for filesystem deltas (`oacp watch`).
3. **Process** — recipient acts on the message based on `type`. Auto-execute rules live in the runtime SKILL.md and the `/check-inbox` skill.
4. **Reply** — for types that require a reply (`task_request`, `question`, `handoff`, `review_*`), the recipient sends a new message with `--parent-message-id` linking back to the original.
5. **Delete** — recipient removes the file from `inbox/` after fully processing. The outbox copy on the sender's side remains as the durable record.

## Message types (semantics)

| Type | Reply expected | Semantics |
|------|:---:|-----------|
| `notification` | no | Informational. Acknowledge, then delete. |
| `task_request` | yes (`notification`) | Asks the recipient to perform work. Reply on completion. Large tasks should be confirmed with the human first. |
| `question` | yes (`notification`) | Information request. Answer in the reply body. |
| `review_request` | yes (`review_lgtm` or `review_feedback`) | Asks for review of a PR (`related_pr`) or a design packet (`related_packet`). |
| `review_feedback` | yes (`review_addressed` + fresh `review_request`) | Reviewer → author: blocking or non-blocking findings. |
| `review_lgtm` | no | Reviewer → author: approval. Author may now merge. |
| `review_addressed` | informational only | Author → reviewer: feedback addressed. To trigger round N+1, the author must follow this with a **fresh `review_request`** — `review_addressed` alone does not invoke a stateless reviewer. |
| `handoff` | yes (`handoff_complete`) | Transfer of context between agents. |
| `handoff_complete` | no | Acknowledgement that the handoff was received and acted upon. |
| `brainstorm_request` | yes (`notification` or `brainstorm_followup`) | Open-ended exploration request. |
| `brainstorm_followup` | yes | Continuation of a brainstorm thread with new constraints. |
| `follow_up` | varies | Generic follow-up on an earlier thread when no other type fits. |

## Dispatch patterns

- **Direct dispatch** — Author sends `review_request` straight to the reviewer agent. This is the canonical pattern for review loops; do not route through a coordinator.
- **Coordinator-mediated** — A coordinator agent that owns work decomposition may send `task_request` to multiple workers. Workers reply directly to the coordinator, not to each other.
- **Broadcast** — Comma-separated `--to` produces independent inbox copies for one-to-many notifications.

## Verification invariant

After any send, the message MUST exist in both:

- The recipient's `inbox/` (delivered)
- The sender's `outbox/` (audit)

If only the outbox copy exists, the send silently failed. Always verify the inbox path that `oacp send` printed.
