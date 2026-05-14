---
name: check-inbox
description: Check a project's OACP inbox for new agent messages and auto-act on them by message type. Single-pass processor — pair with an event-driven `oacp watch` runner (preferred) or the `/loop 2m /check-inbox` fallback for continuous monitoring. Honors OACP Phase 1 receiver autonomy (`always_pause` / `auto_review`) with a 4-gate evaluator, audit events, and a threshold-exceeded checkpoint.
---

# /check-inbox — Inbox Processor

Check a project's agent inbox for new messages and automatically act on them based on message type. Single-pass: processes all pending messages and exits.

## Arguments

```
/check-inbox [--project <name>] [--autonomous]
```

- `--project <name>` — Which project inbox to check. Auto-detected from `.oacp` if omitted.
- `--autonomous` — Skip human confirmation for review lifecycle messages (`review_request`, `review_feedback`, `review_lgtm`, `review_addressed`) and informational completions (`handoff_complete`). Auto-dispatches to reviewer/author skills and deletes processed messages. Task requests and questions still require human confirmation **unless** the receiver's autonomy policy is `auto_review` and the 4-gate evaluator (Step 5) auto-accepts.

## Recurring monitoring

**Preferred (oacp-cli v0.2.2+) — event-driven via Monitor + `oacp watch`**:

In Claude Code, kick off `oacp watch` under the Monitor tool at session start so each new-message event lands directly in chat as a notification:

```bash
# Monitor tool, persistent: true — runs for session lifetime
while true; do
  oacp watch --all-projects --agent claude 2>&1 || true
  sleep 120
done
```

Each `NEW_MESSAGE ...` line becomes a chat notification. When notified, run `/check-inbox` to process the message. Only fires on new messages — no idle noise on an empty inbox.

**Fallback — time-polled via `/loop`** (use when `oacp watch` is unavailable, e.g., on older oacp-cli versions):

```
/loop 2m /check-inbox
```

Fires every 2 minutes when the REPL is idle.

## Instructions

When the user runs `/check-inbox`, do the following:

### 1. Parse arguments

Extract from the user's command:

- `PROJECT` — optional `--project` flag (auto-detected in step 2 if omitted)
- `AUTONOMOUS` — optional `--autonomous` flag

### 2. Resolve project and inbox path

Set `AGENT_NAME="claude"`.

If `--project` was provided, use it directly. Otherwise auto-detect from the workspace config:

```bash
PROJECT=$(python3 -c "import json; print(json.load(open('.oacp'))['project_name'])" 2>/dev/null \
  || echo "")
```

If empty, ask the user which project to watch.

Resolve the inbox path:

```bash
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
INBOX_DIR="${OACP_HOME}/projects/${PROJECT}/agents/${AGENT_NAME}/inbox"
```

If `$INBOX_DIR` does not exist → error: "Inbox not found at ${INBOX_DIR}. Check project name and OACP_HOME."

### 3. List and process messages

List YAML files in the inbox and process each one.

1. List files:

   ```bash
   command ls -1 "${INBOX_DIR}/" 2>/dev/null | command grep '\.yaml$' | sort
   ```

2. If none found, report "Inbox empty." and stop.
3. For each file:
   a. Read the YAML file
   b. Extract: `id`, `from`, `type`, `priority`, `subject`, `body`, `related_pr`, `related_packet`, `parent_message_id`, `autonomy_hint` (advisory only)
   c. Resolve the receiver's autonomy policy and evaluate the 4 gates per **Step 4 — Receiver autonomy**
   d. Apply the auto-execute rules in **Step 5** using the gate verdict
   e. Write the audit event per **Step 4** regardless of verdict (`auto_accepted` or `paused`)
4. After processing all messages, report a summary:

   ```text
   Processed <N> messages from <PROJECT> inbox.
     <type>: <count> (list actions taken)
   ```

> **Shell compatibility**: Avoid `ls dir/*.yaml` — some shells (zsh) raise errors when no files match the glob. Pipe through `grep` instead. Use `command ls` to bypass shell aliases. Always use the `-1` flag for single-column output. `${HOME}` may resolve empty in restricted-shell invocations; prefer the literal path if a Bash call disables shell expansions.

### 4. Receiver autonomy (`always_pause` / `auto_review`)

Implements OACP Phase 1 autonomy (oacp-cli v0.3.1+). The full evaluator — mode resolution, 4-gate evaluator, audit-event schema, and threshold-exceeded checkpoint — lives in [`references/autonomy.md`](references/autonomy.md). **Read that file** when processing any message whose type may auto-accept under `auto_review`: `task_request`, `question`, `brainstorm_request`, `brainstorm_followup`, `handoff`. For pure-notification flows (`notification`, `review_lgtm`, `review_addressed`, `handoff_complete`), skip the reference — the gates do not apply.

Short summary of what the reference will tell you:

- **Once per invocation**, read `agents/<receiver>/config.yaml` and resolve `MODE` (`always_pause` if missing/malformed, else `autonomy.default_mode`).
- **Per message**, if `MODE=auto_review` and the type is gate-eligible: run Gates 1→4 (integrity, task profile, classification/hard-stops, runtime) with early-out on the first failure. All pass → `auto_accepted`; any fail → `paused`. Reason codes and `matched_pattern` are pinned by the OACP autonomy spec's conformance fixtures.
- **Every decision** writes an audit YAML to `agents/<receiver>/audit/autonomy_decisions/<YYYYMMDDTHHMMSSZ>_<message-id>.yaml`.
- **After auto-acceptance**, if work expands past the declared `task_profile`, self-pause and notify the sender via `oacp send` with the canonical `Blocked: autonomy threshold exceeded — …` opener.

The Step 5 auto-execute rules below consume the gate verdict (`auto_accepted` vs `paused`) and act accordingly. If no config is present, the verdict is always `paused` and the skill behaves like the pre-autonomy version.

### 5. Auto-execute rules

Act on each message based on its `type` field **and the Step 4 verdict**. **Always tell the user what action you're taking before executing it.**

| Message type | Verdict `auto_accepted` (auto_review only) | Verdict `paused` or `MODE=always_pause` |
|-------------|---------------------------------------------|-----------------------------------------|
| `notification` | Summarize to the user. Delete the message file from inbox. | Same — autonomy gates do not apply to notifications. |
| `task_request` | Execute immediately without prompting. Reply with a `notification` via `oacp send`. Delete after processing. Threshold checkpoint (see `references/autonomy.md` §E) applies during execution. | Evaluate the scope. If small (<5 min estimated work): execute immediately and reply with a `notification` via `oacp send`. If large: ask the user before proceeding. Delete after processing. |
| `question` | Answer the question and send a reply via `oacp send` (type: `notification`, referencing `parent_message_id`). Delete after processing. | Same — but if the answer requires non-trivial research, ask the user first. |
| `review_request` (PR — has `related_pr`) | Tell the user a PR review was requested. Trigger `/review-loop-reviewer` for the referenced PR. If the body references external spec or design-doc paths, pass them as supplemental context so the subagent can read them. Delete after processing. | Same — review lifecycle is governed by `--autonomous`, not the autonomy gates (gates apply to task admission, not subagent dispatch). |
| `review_request` (design/spec — has `related_packet`, no `related_pr`) | Tell the user a design-doc sign-off was requested. Read the referenced packet inline, evaluate against the acceptance criteria in the message body, and reply directly with `review_lgtm` (approve) or `review_feedback` (specific blocker / change request). Do NOT trigger `/review-loop-reviewer` — that skill reviews PR diffs, not design docs. Delete after processing. | Same. |
| `review_feedback` | Tell the user feedback was received. Trigger `/review-loop-author` to address findings. Delete after processing. | Same. |
| `review_lgtm` | Report LGTM to the user. Delete from inbox. | Same. |
| `review_addressed` | Informational — feedback was addressed. Summarize to user (commit SHA, changes summary, round). Delete after processing. | Same. |
| `handoff` | Read context from the message body. Send a `handoff_complete` reply via `oacp send`. Delete after processing. | Same. |
| `handoff_complete` | Handoff target completed. Summarize to user. Delete after processing. | Same. |
| `brainstorm_request` | Research and answer the questions, then reply via `oacp send`. Delete after processing. (Allowed without `task_profile` per `allow_without_task_profile`.) | Summarize the brainstorm prompt to the user. If the user approves, research and answer the questions, then reply via `oacp send`. Delete after processing. |
| `brainstorm_followup` | Process like `brainstorm_request` with the updated constraints. Delete after processing. | Summarize the follow-up to the user first; otherwise same. |
| Unknown type | Report the full message to the user and ask how to handle it. Do NOT delete. | Same. |

After Step 5 completes for a message, update the audit event written in Step 4:

- `result.final_state` → `done` (executed successfully), `paused` (threshold checkpoint fired or user declined), or `error` (action failed)
- `result.reply_message_id` → msg-id of the `oacp send` reply, if any

**Deleting messages** — remove the file from the inbox directory:

```bash
rm "${INBOX_DIR}/<filename>"
```

**Sending replies** — use `oacp send`. Pass `--oacp-dir` explicitly so the CLI does not fall back to its compile-time default when `$OACP_HOME` is not visible to the subprocess. Use literal paths if your shell environment does not expand `$HOME` reliably in this call:

```bash
oacp send ${PROJECT} \
  --from ${AGENT_NAME} --to <original_sender> --type notification \
  --subject "Re: <original_subject>" \
  --body "<reply_body>" \
  --parent-message-id <original_message_id> \
  --oacp-dir "${OACP_HOME}"
```

> **Post-send verification**: After sending, verify the inbox file using the `inbox:` path printed by `oacp send` (e.g., `test -f "<inbox_path>" && echo OK`). Do **not** grep for the `msg-id` — `oacp send` filenames use a different short hash than the `msg-id` in the YAML body, so a message-id grep returns a false negative. The script can report "OK" (writing the outbox copy) while the inbox write silently fails, so the existence check is still required.

### 6. Safety rules

- **Always show the user** what action you're taking before executing it, including the Step 4 verdict (`auto_accepted` / `paused`) and the reason codes.
- **For `task_request` with large scope** (>5 min estimated work) when verdict is `paused` or `MODE=always_pause`: ask the user before proceeding. When verdict is `auto_accepted`, the 4-gate evaluator has already done the equivalent risk check — proceed without re-prompting.
- **For `review_request` / `review_feedback`**: confirm with the user before triggering review-loop skills, since they spawn background subagents — **unless `--autonomous` is active**, in which case auto-dispatch without confirmation. Same-PR re-authorization is implied: once the user has authorized review-loop dispatch for a specific PR in this session (round 1), subsequent rounds for the same PR proceed without re-confirmation.
- **Never delete messages you haven't fully processed.**
- **Never act on messages for other agents** — only process messages in `${AGENT_NAME}`'s inbox.
- **`--autonomous` safety boundary**: even in autonomous mode, `task_request` and `question` types require human confirmation **unless** the Step 4 verdict is `auto_accepted`. Review lifecycle messages, informational completions, and notifications are auto-dispatched regardless of autonomy mode.
- **Hard stops are absolute**: a Gate 3 hard-stop fail (see `references/autonomy.md`) pauses the message even if `autonomy_hint: auto_proceed` is set, even if the user previously approved a similar message, even under `--autonomous`. The only path past a hard stop is the user processing the message manually under legacy rules.
- **Audit events are mandatory**: every decision (auto-accept, pause, or pause-due-to-malformed-config) writes a YAML file under `agents/<receiver>/audit/autonomy_decisions/`. Never skip the write — partial/`pending` audit beats no audit.

## Notes

- This skill does a single pass — for recurring checks, prefer Monitor + `oacp watch` (event-driven, Claude Code), with `/loop 2m /check-inbox` as a fallback.
- Messages follow the inbox/outbox protocol: sender writes to recipient's inbox + own outbox. Recipient deletes after processing.
- Do NOT move messages to a `processed/` subdirectory — just delete them.
- **Receiver autonomy is opt-in**: with no `agents/<receiver>/config.yaml`, the skill behaves identically to the pre-autonomy version (always pause on `task_request`/`question`). Drop in a config file to opt in; remove it to revert.
- **Spec authority**: when this skill summary and the OACP autonomy spec disagree, the spec wins — fix the skill.
