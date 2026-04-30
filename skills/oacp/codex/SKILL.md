---
name: oacp
description: Use the OACP CLI and protocol from Codex to coordinate agents through inbox/outbox messages, task dispatch, review loops, and project memory.
---

# OACP

Run this version gate first. If `oacp` is missing or older than `0.3.0`, stop
and tell the user to install or upgrade `oacp-cli` before continuing.

```bash
if ! command -v oacp >/dev/null 2>&1; then
  echo "oacp CLI not found; install oacp-cli >= 0.3.0" >&2
  exit 1
fi

OACP_VERSION="$(oacp --version)"
printf '%s\n' "${OACP_VERSION}"
python3 - "${OACP_VERSION}" <<'PY'
import re
import sys

version = sys.argv[1].strip()
match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
if not match:
    raise SystemExit(f"could not parse oacp version: {version}")
parts = tuple(int(part) for part in match.groups())
if parts < (0, 3, 0):
    raise SystemExit(f"oacp {version} is older than required 0.3.0")
PY
```

OACP is a filesystem coordination protocol. Use the installed `oacp` command
as the primary interface, and use the public
[OACP specification](https://github.com/kiloloop/oacp/blob/main/SPEC.md) when
you need protocol details that are not summarized here.

## Start

Resolve the project before reading or writing messages. Prefer an explicit
`--project` from the user; otherwise detect `.oacp` from the repo root.

```bash
PROJECT="$(python3 - <<'PY'
import json
import os

project = ""
if os.path.islink(".oacp"):
    target = os.path.realpath(".oacp")
    marker = os.path.join(target, "workspace.json") if os.path.isdir(target) else target
    try:
        with open(marker, "r", encoding="utf-8") as f:
            project = json.load(f).get("project_name", "") or ""
    except Exception:
        project = os.path.basename(target) if os.path.isdir(target) else os.path.basename(os.path.dirname(target))
elif os.path.isfile(".oacp"):
    try:
        with open(".oacp", "r", encoding="utf-8") as f:
            project = json.load(f).get("project_name", "") or ""
    except Exception:
        project = ""
print(project)
PY
)"
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
test -n "${PROJECT}"
```

Run health checks before substantial coordination work:

```bash
oacp doctor --project "${PROJECT}" --oacp-dir "${OACP_ROOT}" --json
```

If the project uses memory sync, run `oacp memory pull` before relying on
shared memory and `oacp memory push` after intentional memory updates.

## Read

Use CLI JSON for inbox discovery. Do not recurse through inbox directories or
parse processed archives unless the user asks.

```bash
oacp inbox "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json
```

When handling a message, parse the YAML, inspect `id`, `from`, `type`,
`priority`, `subject`, `body`, `related_pr`, `parent_message_id`, and
`expires_at`, then follow the protocol for that type.

Keep these routing defaults:

- `task_request`, `brainstorm_request`, and `review_request`: summarize and
  get user confirmation before live execution.
- `question`: answer with a reply `notification` using `--in-reply-to`.
- `notification`: summarize; acknowledge only when the sender requested it.
- `review_lgtm`: report the quality gate result, then proceed according to the
  repo's merge policy.
- Unknown, malformed, or expired messages: report and leave them in the inbox.

Delete an inbox file only after its handling path succeeds.

## Send

Use `oacp send` for all message writes. Prefer `--dry-run --json` first when
composing a new message type or a complex body.

```bash
oacp send "${PROJECT}" \
  --from codex \
  --to "<agent>" \
  --type notification \
  --subject "Re: <subject>" \
  --body-file "<body-file>" \
  --in-reply-to "<message-id>" \
  --priority P2 \
  --oacp-dir "${OACP_ROOT}" \
  --dry-run \
  --json
```

Use `--body-file` for multi-line YAML bodies. Use `--in-reply-to` for replies
so OACP can inherit conversation context from the parent message; use
`--parent-message-id` only when you need to set the parent field directly. Use
`--related-pr` on review-loop messages. After the dry run is correct and the
user has approved the live write, rerun the same command without `--dry-run`.
When a live send succeeds, verify the reported `inbox_path` exists before
treating the message as delivered.

Validate hand-written or edited message files before relying on them:

```bash
oacp validate "<message-file>"
```

## Poll

For recurring checks, use the user's runtime loop support or one shell loop.
Do not spend repeated LLM turns polling the same wait state.

```bash
oacp watch --project "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json --since now
```

Use `--since epoch` only when you intentionally need to replay existing inbox
messages. Use `--show-archived` only when archive/delete events are part of the
task; it is noisy when watching your own inbox.

## Review Loops

Author flow:

1. Open or update the PR and run the repo's required checks.
2. Send a `notification` with subject prefix `WIP:` if a dispatcher needs PR
   progress.
3. Send `review_request` directly to the reviewer with `related_pr`, `pr`,
   `branch`, and `diff_summary` in the body.
4. If the reviewer sends `review_feedback`, address findings, then send
   `review_addressed`.
5. Send a fresh `review_request` for re-review. `review_addressed` is context;
   it is not the trigger for a stateless reviewer invocation.
6. Merge only after `review_lgtm`, required checks are green, and the repo's
   merge policy is satisfied.

Reviewer flow:

1. On `review_request`, inspect the PR diff and relevant project rules.
2. Send exactly one terminal response: `review_feedback` or `review_lgtm`.
3. Exit after the terminal response. Do not wait in-session for
   `review_addressed`.

Review feedback should point to a findings packet when the project uses one.
LGTM bodies should include `quality_gate_result: pass` and
`merge_ready: true`.

## Safety

- Read the nearest repo instructions before running repo-scoped Git or GitHub
  commands.
- Do not print tokens, cookies, private headers, or full secrets in messages,
  logs, PR comments, or final replies.
- Do not put absolute local paths in shared OACP artifacts; prefer
  `$OACP_HOME`, `$HOME`, repo-relative paths, or public URLs.
- Ask before live writes when the message type or repo protocol requires user
  approval.
- Keep PR comments concise and data-minimized; detailed machine state belongs
  in inbox messages or packets.

## Examples

Check health and the Codex inbox:

```bash
PROJECT="my-project"
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
oacp --version
oacp doctor --project "${PROJECT}" --oacp-dir "${OACP_ROOT}" --json
oacp inbox "${PROJECT}" --agent codex --oacp-dir "${OACP_ROOT}" --json
```

Draft a `task_request` before sending it:

```bash
BODY_FILE="$(mktemp)"
cat > "${BODY_FILE}" <<'EOF'
Implement the requested change.

Acceptance criteria:
- Keep the patch scoped.
- Run the relevant validation.
- Reply with results and follow-ups.
EOF

oacp send "${PROJECT}" \
  --from codex \
  --to "<agent>" \
  --type task_request \
  --subject "Implement scoped change" \
  --body-file "${BODY_FILE}" \
  --priority P2 \
  --oacp-dir "${OACP_ROOT}" \
  --dry-run \
  --json
```

Request review for a PR:

```bash
PR_NUMBER="123"
BRANCH="$(git branch --show-current)"
DIFF_SUMMARY="$(git diff --stat "origin/main...${BRANCH}" | sed 's/^/  /')"
BODY_FILE="$(mktemp)"
cat > "${BODY_FILE}" <<EOF
pr: ${PR_NUMBER}
branch: ${BRANCH}
diff_summary: |
${DIFF_SUMMARY}
max_turns_reviewer: 8
max_runtime_s_reviewer: 600
EOF

oacp send "${PROJECT}" \
  --from codex \
  --to "<reviewer-agent>" \
  --type review_request \
  --subject "Review: PR #${PR_NUMBER}" \
  --body-file "${BODY_FILE}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1 \
  --oacp-dir "${OACP_ROOT}" \
  --dry-run \
  --json
```
