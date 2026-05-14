---
name: check-inbox
description: "Process the current Codex project inbox in a single pass. Use when triaging pending inbox YAML messages or handling notification/question/review-loop traffic through the OACP CLI. Honors OACP Phase 1 receiver autonomy (`always_pause` / `auto_review`) per the active OACP autonomy protocol."
---

# /check-inbox - Codex Inbox Poller & Processor

Poll a project's `codex` inbox and process messages by type using the OACP
inbox/outbox protocol.

## Interface

```bash
/check-inbox [--project <name>] [--once]
```

- `--project <name>` - project name. If omitted, auto-detect from `.oacp` or
  `workspace.json`.
- `--once` - optional explicit form of the default single-pass behavior.

Default mode: if neither flag is supplied, run one ordered drain pass over the
current inbox and exit.

Legacy watch-mode flags (`--watch`, `--interval`, `--max-empty-polls`,
`--max-runtime-min`) are not supported in Codex. If the user asks for recurring
polling, stop and tell them to use `/loop 2m /check-inbox` or another interval.

## Workflow

### 1. Parse Arguments

Extract:

- `PROJECT` (optional)
- `ONCE` (boolean)

If legacy watch or polling flags are present, stop and recommend
`/loop 2m /check-inbox` for recurring monitoring.

### 2. Resolve Project And Inbox

If `--project` is provided, use it. Otherwise auto-detect:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os

def project_from_marker(path: str) -> str:
    if not (os.path.isfile(path) or os.path.islink(path)):
        return ""
    try:
        resolved = os.path.realpath(path) if os.path.islink(path) else path
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("project_name", "") or ""
    except Exception:
        return ""

for marker in (".oacp", "workspace.json"):
    project = project_from_marker(marker)
    if project:
        print(project)
        break
else:
    print("")
PY
)"
```

If still empty, ask the user which project to use and stop.

Set:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
INBOX_JSON_FILE="$(mktemp)"
trap 'rm -f "${INBOX_JSON_FILE}"' EXIT
oacp inbox "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json >"${INBOX_JSON_FILE}"
INBOX_DIR="$(python3 - "${INBOX_JSON_FILE}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)
agents = report.get("agents") or []
print((agents[0] if agents else {}).get("inbox_path", ""))
PY
)"
```

Verify `test -d "${INBOX_DIR}"`. If missing, report:

```text
Inbox not found at ${OACP_ROOT}/projects/${PROJECT}/agents/codex/inbox.
Check project name and OACP_HOME.
```

### 3. Snapshot And Parse Messages

Use the CLI snapshot as the source of truth for pending files:

```bash
oacp inbox "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json >"${INBOX_JSON_FILE}"
python3 - "${INBOX_JSON_FILE}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)
for agent in report.get("agents", []):
    for message in agent.get("messages", []):
        path = str(message.get("path", "")).strip()
        if path.endswith(".yaml"):
            print(path)
PY
```

Never recurse into subdirectories, including `processed/`.

Parse each message with Python and PyYAML:

```bash
python3 - "$MSG_FILE" <<'PY'
import json
import sys
import yaml
from pathlib import Path

path = Path(sys.argv[1])
msg = yaml.safe_load(path.read_text(encoding="utf-8"))
if not isinstance(msg, dict):
    raise ValueError("message is not a YAML mapping")
keys = [
    "id", "from", "type", "priority", "subject", "body",
    "related_pr", "related_packet", "parent_message_id", "expires_at",
    "autonomy_hint",
]
print(json.dumps({k: msg.get(k) for k in keys}))
PY
```

If PyYAML is unavailable, use Ruby's YAML parser as a fallback. If parsing
fails or required fields are missing, report the message as malformed and keep
it in the inbox.

Expiry rule:

- If `expires_at` exists and is in the past UTC, report and skip.
- Do not delete expired messages automatically.

### 4. Receiver Autonomy

Apply the active OACP receiver-autonomy protocol before processing
gate-eligible messages.

Resolve the receiver policy:

```bash
CONFIG_PATH="${INBOX_DIR%/inbox}/config.yaml"
```

- Missing config -> `MODE=always_pause`.
- Malformed config -> `MODE=always_pause`; write a paused audit decision with
  `reason_codes: [config_malformed]` for gate-eligible messages.
- Valid config -> `MODE=<autonomy.default_mode>` (`always_pause` or
  `auto_review`) and `THRESHOLDS=<autonomy.auto_review_thresholds>`.

For gate-eligible message types (`task_request`, `question`,
`brainstorm_request`, `brainstorm_followup`, `handoff`), read the package
reference `../references/autonomy.md` before acting. That reference contains the
full evaluator:

1. Gate 1: message integrity and replay detection.
2. Gate 2: declared `task_profile` and risk thresholds.
3. Gate 3: deterministic hard stops and ambiguous file scope.
4. Gate 4: runtime/workspace check.

Every gate-eligible message writes an audit YAML under:

```text
agents/<receiver>/audit/autonomy_decisions/<YYYYMMDDTHHMMSSZ>_<message-id>.yaml
```

Write `result.final_state: pending` immediately after gate evaluation, then
update it after processing finishes. A partial audit is better than no audit.

Pure notification and lifecycle flows (`notification`, `review_lgtm`,
`review_addressed`, `handoff_complete`) do not run autonomy gates.

Verdicts:

- `auto_accepted`: all gates passed in `auto_review`; processing may proceed
  without human confirmation for gate-eligible work.
- `paused`: `always_pause`, malformed config, missing profile, threshold
  exceedance, hard stop, replay, expiry, or runtime failure; use the paused
  handling path.

Hard stops are absolute. `autonomy_hint: auto_proceed` is advisory only and
never overrides a pause.

Threshold-exceeded checkpoint: after an auto-accepted task starts, self-pause
if work expands beyond the declared `task_profile`. Notify the sender with a
`notification` whose body opens with canonical text such as
`Blocked: autonomy threshold exceeded - files_touched expected <N>, now <M>`,
update the audit with `threshold_exceeded_post_accept`, and keep the original
message for re-authorization.

### 5. Process One Message

Before any action, tell the user what action is about to run, including the
autonomy verdict and reason codes for gate-eligible messages.

| Message type | Verdict `auto_accepted` | Verdict `paused` or `MODE=always_pause` |
| --- | --- | --- |
| `notification` | Summarize to user. Delete after handling. | Same; gates do not apply. |
| `task_request` | Execute immediately without prompting. Reply with `notification`; delete after successful handling. Threshold checkpoint applies. | Summarize and ask user approval before executing. If approved and completed, reply with `notification`; delete after send succeeds. If declined or blocked, keep or delete only according to the user's decision. |
| `question` | Answer and reply with `notification` using `--in-reply-to <message_id>`; delete after send succeeds. | Draft answer; ask before non-trivial research; reply and delete after send succeeds. |
| `brainstorm_request` | Research/answer, reply with `notification`, delete after send succeeds. `allow_without_task_profile` may apply. | Summarize and ask user approval before research; reply/delete only after completion. |
| `brainstorm_followup` | Process like `brainstorm_request` with updated constraints. | Summarize and ask user approval before continuing. |
| `handoff` | Read context, send `handoff_complete`, delete after send succeeds. | Same, but ask before non-trivial follow-up work. |
| `review_request` | Notify user and ask confirmation before invoking the reviewer-side review loop. | Same; review lifecycle is not governed by autonomy gates. |
| `review_feedback` | Notify user and ask confirmation before invoking the author-side review loop. | Same. |
| `review_addressed` | Informational. If a newer same-PR `review_request` exists, merge this context into that re-review; otherwise report that the protocol expects a fresh `review_request` and keep unless the user explicitly requests manual re-review. | Same. |
| `review_lgtm` | Report LGTM, then delete. | Same. |
| `handoff_complete` | Summarize completion, then delete. | Same. |
| Unknown | Report full message and ask how to handle it. Do not delete. | Same. |

If `related_pr` is missing for `review_request`, `review_feedback`,
`review_addressed`, or `review_lgtm`, report and keep the file.

Nonterminal task wait rule:

- If a `task_request` reaches a nonterminal external wait state, such as
  `PR opened, pending user review/merge`, send the progress notification but
  keep the original inbox message until the terminal completion notification
  succeeds. Later completion replies must still use `--in-reply-to <message_id>`
  so the sender's thread stays intact.

Notification acknowledgement rule:

- If a `notification` asks for acknowledgement, ask the user whether to send a
  receipt before deletion.
- Delete only after the approved reply succeeds, or after the user explicitly
  declines a reply.

Reply notification template:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex \
  --to "${MSG_FROM}" \
  --type notification \
  --subject "Re: ${MSG_SUBJECT}" \
  --body "${REPLY_BODY}" \
  --in-reply-to "${MSG_ID}"
```

Handoff completion template:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex \
  --to "${MSG_FROM}" \
  --type handoff_complete \
  --subject "Handoff complete: ${MSG_SUBJECT}" \
  --body "${REPLY_BODY}" \
  --in-reply-to "${MSG_ID}"
```

Delete after successful handling:

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

### 6. Single-Pass Drain Loop

Process files using protocol ordering:

1. Priority: `P0` -> `P1` -> `P2/P3`.
2. Within the same priority: `task_request` and `review_request` before
   `notification` and `follow_up`.
3. Within the same priority/type bucket: oldest filename timestamp first.

Run one short drain loop:

1. Snapshot with `oacp inbox "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json`.
2. Build an ordered queue from parsed `priority`, `type`, and filename timestamp.
3. Process each file using Steps 4 and 5.
4. Re-scan once after the pass.
5. If new files appeared during processing, run another pass.
6. Exit once a re-scan is empty.

If the first snapshot is empty, report:

```text
Inbox empty - no messages to process.
```

After the run, report:

```text
Processed <N> message(s) from <PROJECT> inbox.
Handled: <type=count,...>
Retained: <count> (expired/malformed/unknown/awaiting-approval)
```

## Safety Rules

- Always tell the user what action is about to run before running it.
- `task_request`, `question`, `brainstorm_request`, `brainstorm_followup`, and
  `handoff` require explicit user approval unless Step 4 returned
  `auto_accepted`.
- `review_request`, `review_feedback`, and manual `review_addressed` re-review
  require explicit user confirmation before triggering review-loop skills.
- Never delete messages that were not successfully processed.
- Never process messages outside `agents/codex/inbox`.
- Hard stops are absolute and can only be processed manually under paused rules
  after surfacing them to the user.
- Audit events are mandatory for every gate-eligible autonomy decision,
  including `always_pause` and malformed config pauses.

Approval and confirmation prompts must be self-contained. Include:

- `Recommended: <choice>` when one path is clearly safest.
- Numbered choices.
- Message id/path and sender.
- Exact side effects, including whether an inbox reply will be sent and whether
  the message will be deleted.
- Allowed replies, for example `1`, `2`, or `skip`.

## Notes

- This skill is single-pass only. For recurring checks, prefer
  `/loop 2m /check-inbox`.
- `processed/` is legacy; do not move files there.
- Sender writes both recipient inbox and sender outbox; recipient deletes the
  inbox file after successful handling.
- Receiver autonomy is opt-in. With no `agents/<receiver>/config.yaml`, the
  skill behaves like the pre-autonomy version.
- Spec authority: when the active OACP protocol and this skill disagree, fix
  this skill.
