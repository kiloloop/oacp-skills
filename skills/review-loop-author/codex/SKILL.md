---
name: review-loop-author
description: Run the author side of the review loop — address findings and drive to LGTM.
---

# /review-loop-author

Run the author side of a review loop for one pull request.

## Interface

```bash
/review-loop-author <PR_NUMBER> --reviewer <name> [--project <name>] [--task-id <task-id>]
```

- `PR_NUMBER` is required.
- `--reviewer` is required.
- `--project` is optional. If omitted, detect it from `.oacp` or fall back
  to the repo name.
- `--task-id` is optional. Include it when the review loop is tied to a tracked
  task file.

## Execution Model

- Set `AGENT_NAME="codex"` and keep it consistent in every inbox message.
- Run commands directly in the current Codex session.
- Use inbox messages for machine state and PR comments for short human-visible
  status updates.
- Keep comments data-minimized. Do not include logs, stack traces, secrets, or
  local-only paths.
- For wait states, use one shell or terminal polling loop rather than repeated
  manual turns.

## Setup

```bash
set -euo pipefail

AGENT_NAME="codex"
PR_NUMBER="<PR_NUMBER>"
REVIEWER="<reviewer>"
TASK_ID="${TASK_ID:-}"

REPO_PATH="$(git rev-parse --show-toplevel)"
BRANCH="$(gh pr view "${PR_NUMBER}" --json headRefName -q .headRefName)"
BASE_BRANCH="$(gh pr view "${PR_NUMBER}" --json baseRefName -q .baseRefName)"
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

if [[ -z "${BASE_BRANCH}" ]]; then
  BASE_BRANCH="main"
fi
```

Project detection:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os
from pathlib import Path

repo = Path(".")
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
if not project:
    project = repo.resolve().name
print(project)
PY
)"
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
PROJECT_ROOT="${OACP_ROOT}/projects/${PROJECT}"
INBOX_DIR="${PROJECT_ROOT}/agents/${AGENT_NAME}/inbox"
SCRIPTS_DIR="${OACP_ROOT}/scripts"
SEND_MSG="${SCRIPTS_DIR}/send_inbox_message.py"
```

GitHub auth rule:

- Read the nearest repo `AGENTS.md` before any repo-scoped `gh` command.
- If the repo requires GitHub App auth, generate and use the short-lived app
  token exactly as that repo specifies.
- Fall back to verified human auth only after a concrete app failure.

Validate preconditions:

```bash
gh pr view "${PR_NUMBER}" --repo "${REPO}" >/dev/null
test -d "${INBOX_DIR}"
test -f "${SEND_MSG}"
```

## Procedure

### 1. Prepare the review request

Before you ask for review:

- Push all local commits for the PR branch.
- Make sure the PR title and description match the real scope.
- Run the repo's pre-review checks.

Build a concise diff summary:

```bash
DIFF_SUMMARY="$(git diff "${BASE_BRANCH}...${BRANCH}" --stat)"
```

### 2. Send `review_request`

```bash
python3 "${SEND_MSG}" "${PROJECT}" \
  --from "${AGENT_NAME}" \
  --to "${REVIEWER}" \
  --type review_request \
  --subject "Review: PR #${PR_NUMBER}" \
  --body "pr: ${PR_NUMBER}
branch: ${BRANCH}
diff_summary: |
  ${DIFF_SUMMARY}
task_id: ${TASK_ID:-}
review_round: 1" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

Always add a short PR comment:

```bash
COMMENT_FILE="$(mktemp)"
cat > "${COMMENT_FILE}" <<EOF
**Review requested** - ${AGENT_NAME} -> ${REVIEWER}

Round: 1
Scope: PR #${PR_NUMBER}
Details delivered via inbox review_request message.
EOF
gh pr comment "${PR_NUMBER}" --repo "${REPO}" --body-file "${COMMENT_FILE}"
rm -f "${COMMENT_FILE}"
```

Initialize:

- `current_round=1`
- `poll_interval=30`
- `max_rounds=2` unless the repo documents another limit
- `timeout_minutes=15` unless the repo documents another limit

### 3. Poll for reviewer output

Loop until you find a same-PR message from the reviewer with type
`review_feedback` or `review_lgtm`.

If no matching message appears yet:

- sleep for `poll_interval`
- re-scan the inbox
- escalate only after the configured timeout

### 4. Parse `review_feedback`

Extract:

- `findings_packet`
- `round`
- `blocking_count`
- `task_id` when present
- `review_round` when present

Validate the findings packet path before acting:

```bash
FINDINGS_REL="packets/findings/<packet>.yaml"
FINDINGS_PATH="${PROJECT_ROOT}/${FINDINGS_REL}"
test -f "${FINDINGS_PATH}"
```

If the message is malformed or the findings packet is missing, send a
`question` asking the reviewer to resend the required data and pause the loop.

Delete the processed feedback message only after you have safely parsed it.

### 5. Triage findings

Prioritize in this order:

1. Open blocking `P0`
2. Open blocking `P1`
3. Non-blocking `P0` or `P1`
4. `P2` and `P3`

For each finding, choose one path:

1. Fix it when it is valid and in scope.
2. Push back with a `question` when it is incorrect or unclear.
3. Defer it only when it is clearly out of scope and you can explain the next
   step.

### 6. Apply fixes and validate

For each valid finding:

- implement the fix
- run the relevant local validation
- commit the change
- push the branch update

Example commit:

```bash
git add <files>
git commit -m "Fix <finding-id>: <brief description>"
git push origin "${BRANCH}"
```

Optional pre-check when several findings or multi-file edits are involved:

- If the repo provides a findings-vs-diff helper, run it here before
  re-requesting review.
- If no such helper exists, skip this step and rely on targeted local
  validation.

### 7. Send `review_addressed` and re-request review

```bash
LATEST_SHA="$(git rev-parse HEAD)"

python3 "${SEND_MSG}" "${PROJECT}" \
  --from "${AGENT_NAME}" \
  --to "${REVIEWER}" \
  --type review_addressed \
  --subject "Feedback addressed: round ${current_round} (#${PR_NUMBER})" \
  --body "commit_sha: ${LATEST_SHA}
changes_summary: |
  ${CHANGES_SUMMARY}
round: ${current_round}
task_id: ${TASK_ID:-}
review_round: ${current_round}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

Then send a fresh `review_request` for the next round. `review_addressed`
reports what changed; the new `review_request` is the stateless re-review
trigger.

```bash
NEXT_ROUND=$((current_round + 1))
RE_REVIEW_SUMMARY="$(git diff "${BASE_BRANCH}...HEAD" --stat)"

python3 "${SEND_MSG}" "${PROJECT}" \
  --from "${AGENT_NAME}" \
  --to "${REVIEWER}" \
  --type review_request \
  --subject "Re-review: PR #${PR_NUMBER} (round ${NEXT_ROUND})" \
  --body "pr: ${PR_NUMBER}
branch: ${BRANCH}
diff_summary: |
  ${RE_REVIEW_SUMMARY}
task_id: ${TASK_ID:-}
review_round: ${NEXT_ROUND}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

Update `current_round="${NEXT_ROUND}"`, then return to polling.

### 8. Handle `review_lgtm`

Confirm the body includes:

- `quality_gate_result: pass`
- `merge_ready: true`

Then:

1. Delete the `review_lgtm` message.
2. Tell the user the PR is review-approved.
3. Do not auto-merge unless the user or project policy explicitly requests it.

If a merge is requested, apply the CI gate first:

```bash
gh pr checks "${PR_NUMBER}" --repo "${REPO}"
```

Do not merge while any required check is failing, pending, or still running.
If `preflight` exists, it must be `pass`.

### 9. Handle timeout or escalation

Escalate when any of these are true:

1. `current_round` exceeds the repo's max rounds
2. reviewer feedback includes an escalation marker
3. polling exceeds the configured timeout

Send an escalation notification:

```bash
TEAM_LEAD="${TEAM_LEAD:-team-lead}"

python3 "${SEND_MSG}" "${PROJECT}" \
  --from "${AGENT_NAME}" \
  --to "${TEAM_LEAD}" \
  --type notification \
  --subject "Review escalation: PR #${PR_NUMBER}" \
  --body "Review loop for PR #${PR_NUMBER} escalated after ${current_round} rounds.
Reason: max_rounds_exceeded|timeout|reviewer_escalation
Next steps: synchronous coordination or human review." \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

Add a short PR comment explaining that the review loop needs manual follow-up.

## Decision Rules

- Fix valid in-scope findings.
- Ask clarifying questions when a finding is incomplete or incorrect.
- Defer only with an explicit follow-up plan.
- Keep PR comments short and status-oriented.

## Status Outputs

Use one of these terminal markers when useful:

- `STATUS: PASSED`
- `STATUS: ESCALATED`
- `STATUS: TIMEOUT`
