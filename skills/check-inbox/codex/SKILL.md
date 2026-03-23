---
name: check-inbox
description: Process the current Codex inbox in a single ordered pass.
---

# /check-inbox

Process the current `codex` inbox in one ordered pass using the inbox/outbox
protocol.

## Interface

```bash
/check-inbox [--project <name>] [--once]
```

- `--project <name>`: optional project override. If omitted, auto-detect from
  `.oacp`.
- `--once`: optional explicit form of the default single-pass behavior.

If the user asks for recurring polling, stop and recommend
`/loop 2m /check-inbox`. Do not add an in-session watch mode.

## Workflow

### 1. Parse arguments

Extract:

- `PROJECT` (optional)
- `ONCE` (boolean)

If legacy watch flags appear, stop and explain that this Codex variant is
single-pass only.

### 2. Resolve the project and inbox path

If `--project` was provided, use it. Otherwise auto-detect:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os

project = ""
if os.path.islink(".oacp"):
    target = os.readlink(".oacp")
    project = os.path.basename(os.path.dirname(target))
elif os.path.isfile(".oacp"):
    try:
        with open(".oacp", "r", encoding="utf-8") as f:
            data = json.load(f)
        project = data.get("project_name", "") or ""
    except Exception:
        project = ""
print(project)
PY
)"
```

If the project is still empty, ask the user which project to use and stop.

Set:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
INBOX_DIR="${OACP_ROOT}/projects/${PROJECT}/agents/codex/inbox"
```

Verify the inbox exists:

```bash
test -d "${INBOX_DIR}"
```

If it does not, report:

```text
Inbox not found at ${INBOX_DIR}. Check project name.
```

### 3. Discover pending files

Only scan the inbox root:

```bash
command find "${INBOX_DIR}" -maxdepth 1 -type f -name '*.yaml' ! -name '.gitkeep' | sort
```

Do not recurse into subdirectories.

### 4. Parse each message

Extract these fields:

- `id`
- `from`
- `type`
- `priority`
- `subject`
- `body`
- `related_pr`
- `parent_message_id`
- `expires_at`

Preferred parser:

```bash
python3 - "$MSG_FILE" <<'PY'
import json, sys, yaml
from pathlib import Path

path = Path(sys.argv[1])
msg = yaml.safe_load(path.read_text(encoding="utf-8"))
if not isinstance(msg, dict):
    raise ValueError("message is not a YAML mapping")

keys = [
    "id", "from", "type", "priority", "subject", "body",
    "related_pr", "parent_message_id", "expires_at",
]
print(json.dumps({k: msg.get(k) for k in keys}))
PY
```

If `PyYAML` is unavailable, use a Ruby fallback:

```bash
ruby -ryaml -rjson -e '
msg = YAML.safe_load(File.read(ARGV[0]), permitted_classes: [Time], aliases: false) || {}
keys = %w[id from type priority subject body related_pr parent_message_id expires_at]
puts JSON.generate(keys.to_h { |k| [k, msg[k]] })
' "$MSG_FILE"
```

If parsing fails or required fields are missing, report the message as malformed
and leave it in the inbox.

Expiry rule:

- If `expires_at` exists and is in the past UTC, report and skip it.
- Do not delete expired messages automatically.

### 5. Build the ordered queue

Process messages in this order:

1. `P0`
2. `P1`
3. `P2` and `P3`

Within the same priority, handle `task_request` and `review_request` before
`notification` and `follow_up`. Within the same bucket, use arrival order based
on the filename timestamp.

After each full pass, re-scan immediately. If new files appeared while you were
processing, drain one more pass. Exit only after a re-scan is empty.

If the first snapshot is empty, report:

```text
Inbox empty - no messages to process.
```

### 6. Handle each message

Before taking any action, tell the user what you are about to do.

Delete a message only after its handling path succeeds.

Routing summary:

| Type | Action |
| --- | --- |
| `notification` | Summarize it. If it asks for acknowledgement, offer to send a receipt reply before deleting. |
| `task_request` | Summarize and ask for user approval before execution. Reply with a `notification` after completion. |
| `brainstorm_request` | Summarize and ask for approval before starting research or analysis work. |
| `brainstorm_followup` | Summarize the scope change and ask whether to continue with the next brainstorm round. |
| `question` | Draft the answer, send a reply `notification` with `--in-reply-to`, then delete on success. |
| `review_request` | Summarize it and ask for confirmation before invoking the reviewer-side flow. |
| `review_feedback` | Summarize it and ask for confirmation before invoking the author-side flow. |
| `review_addressed` | Treat it as continuation context. Prefer a fresh same-PR `review_request` before re-review. |
| `review_lgtm` | Report the LGTM to the user, then delete it. |
| `handoff` | Summarize the handoff, send `handoff_complete`, then delete on success. |
| `handoff_complete` | Report the completion notice and delete it after handling. |
| `follow_up` | Summarize the non-blocking follow-up and surface it to the user. |
| Unknown | Show the message and ask the user how to handle it. Do not delete it. |

Reply notification template:

```bash
python3 "${OACP_ROOT}/scripts/send_inbox_message.py" "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex \
  --to "${MSG_FROM}" \
  --type notification \
  --subject "Re: ${MSG_SUBJECT}" \
  --body "${REPLY_BODY}" \
  --parent-message-id "${MSG_ID}"
```

Handoff-complete template:

```bash
python3 "${OACP_ROOT}/scripts/send_inbox_message.py" "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex \
  --to "${MSG_FROM}" \
  --type handoff_complete \
  --subject "Handoff complete: ${MSG_SUBJECT}" \
  --body "${REPLY_BODY}" \
  --parent-message-id "${MSG_ID}"
```

Delete only after success:

```bash
if ! rm "${MSG_FILE}"; then
  python3 - "${MSG_FILE}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if path.exists():
    path.unlink()
PY
fi
test ! -e "${MSG_FILE}"
```

### 7. Apply message-specific rules

- If an older `notification` conflicts with a newer same-topic `task_request`,
  treat the newer `task_request` as authoritative.
- If a `notification` clearly amends an active `task_request` or
  `brainstorm_request`, merge the new requirements into that active work item.
- If a `review_addressed` and a newer same-PR `review_request` are both
  pending, treat the `review_request` as the actual re-review trigger and carry
  the `review_addressed` summary forward as context.
- Review-loop message types require `related_pr`. If it is missing, report the
  problem and keep the file.

### 8. Report the drain summary

At the end of the run, report:

```text
Processed <N> message(s) from <PROJECT> inbox.
Handled: <type=count,...>
Retained: <count> (expired/malformed/unknown/awaiting-approval)
```

## Best Practices

- Never process files outside `agents/codex/inbox`.
- Never delete a message that did not complete successfully.
- Keep the user informed before every significant action.
- Prefer protocol documents as the source of truth whenever this skill summary
  and the repo disagree.
