---
name: review-loop-reviewer
description: Run the reviewer side of the review loop — review PR diffs, produce findings, and evaluate quality gate.
---

# /review-loop-reviewer

Run the reviewer side of a review loop for one pull request.

This workflow works best as a split:

- the leader session does all Git, GitHub, and inbox I/O
- an optional helper handles read-only analysis only

If the runtime does not support a read-only helper, perform the analysis in the
main session and keep the same verdict format.

## Interface

```bash
/review-loop-reviewer <PR_NUMBER> --author <name> [--project <name>] [--task-id <task-id>] [--model <name>] [--dry-run]
```

- `PR_NUMBER`: required
- `--author`: required reviewer-loop author agent name
- `--project`: optional project override
- `--task-id`: optional task context
- `--model`: optional helper model when the runtime supports it
- `--dry-run`: gather and print context, then stop before analysis

## Workflow

### 1. Parse arguments

Extract:

- `PR_NUMBER`
- `AUTHOR`
- `PROJECT`
- `TASK_ID`
- `MODEL`
- `DRY_RUN`

Error if `PR_NUMBER` or `--author` is missing.

### 2. Resolve auth and repo context

Before any repo-scoped `gh` command:

- inspect the nearest repo `AGENTS.md`
- use the repo's preferred GitHub identity, usually a GitHub App token when the
  repo requires it
- fall back to verified human auth only after a concrete app failure

Use a wrapper such as:

```bash
REPO_GH_MODE="app-or-human"
APP_GH_TOKEN="${APP_GH_TOKEN:-}"

repo_gh() {
  if [ "${REPO_GH_MODE}" = "app" ]; then
    GH_TOKEN="${APP_GH_TOKEN}" GITHUB_TOKEN="${APP_GH_TOKEN}" gh "$@"
  else
    gh "$@"
  fi
}
```

Resolve the PR context:

```bash
BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json headRefName -q .headRefName)"
BASE_BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json baseRefName -q .baseRefName)"
REPO="$(repo_gh pr view "${PR_NUMBER}" --json headRepositoryOwner,headRepository -q '\"\(.headRepositoryOwner.login)/\(.headRepository.name)\"' 2>/dev/null || repo_gh repo view --json nameWithOwner -q .nameWithOwner)"
REPO_PATH="$(git rev-parse --show-toplevel)"
```

Detect the project name from `--project`, `.oacp`, or the repo name:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os
from pathlib import Path

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
    project = Path.cwd().resolve().name
print(project)
PY
)"
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
INBOX_DIR="${OACP_ROOT}/projects/${PROJECT}/agents/codex/inbox"
SCRIPTS_DIR="${OACP_ROOT}/scripts"
PACKETS_DIR="${OACP_ROOT}/projects/${PROJECT}/packets/findings"
```

Validate:

- the PR exists
- the inbox directory exists
- the scripts directory exists

Create the findings directory if needed:

```bash
mkdir -p "${PACKETS_DIR}"
```

### 3. Pre-gather everything the analysis step needs

Read the project memory files when they exist:

- `${OACP_ROOT}/projects/${PROJECT}/memory/project_facts.md`
- `${OACP_ROOT}/projects/${PROJECT}/memory/open_threads.md`

Then gather:

1. the matching inbox `review_request` for this author and PR, if present
2. all existing PR comments and reviews, so you do not duplicate prior findings
3. the full diff between `BASE_BRANCH` and `BRANCH`
4. the PR title and body

Suggested GitHub calls:

```bash
INLINE_COMMENTS="$(repo_gh api repos/${REPO}/pulls/${PR_NUMBER}/comments --jq '.[].body' 2>/dev/null || true)"
REVIEW_COMMENTS="$(repo_gh api repos/${REPO}/pulls/${PR_NUMBER}/reviews --jq '.[] | \"\\(.state): \\(.body)\"' 2>/dev/null || true)"
ISSUE_COMMENTS="$(repo_gh api repos/${REPO}/issues/${PR_NUMBER}/comments --jq '.[].body' 2>/dev/null || true)"

git fetch origin "${BRANCH}" "${BASE_BRANCH}"
DIFF_TEXT="$(git diff "origin/${BASE_BRANCH}...origin/${BRANCH}")"
PR_INFO="$(repo_gh pr view "${PR_NUMBER}" --json title,body)"
```

If a matching `review_request` exists, extract `task_id` and `review_round`
from it. Otherwise fall back to CLI arguments and default `CURRENT_ROUND=1`.

### 4. Show the plan

Print a concise summary for the user:

```text
Review Loop - Reviewer Side
  PR:          #<PR_NUMBER> (<REPO>)
  Branch:      <BRANCH>
  Base branch: <BASE_BRANCH>
  Author:      <AUTHOR>
  Project:     <PROJECT>
  Task ID:     <TASK_ID or empty>
  Round:       <CURRENT_ROUND>
  Model:       <MODEL or default>
  Inbox:       <INBOX_DIR>
  Packets dir: <PACKETS_DIR>
```

If `--dry-run` was provided, stop here.

### 5. Run the analysis step

Preferred path:

- use a read-only helper
- pass only pre-gathered context
- do not let the helper run Git, GitHub, inbox, or file-write commands

Fallback path:

- perform the same analysis in the main session
- keep the output contract identical

The analysis step must output a verdict block in this exact shape:

```
---VERDICT---
result: pass|fail
blocking_count: <N>
non_blocking_count: <N>
packet_path: <full path where the leader should write the findings YAML>
summary: <1-2 sentence summary>
---FINDINGS_YAML---
<complete findings YAML>
---END_VERDICT---
```

Required findings packet schema:

```yaml
packet_id: "<date>_<topic>_codex_r<round>"
source_review_packet: ""
reviewer: "codex"
round: <N>
created_at_utc: "<ISO 8601 timestamp>"
summary:
  verdict: "fail|pass"
  blocking_count: <N>
  non_blocking_count: <N>
findings:
  - id: "F-001"
    severity: "P0|P1|P2|P3"
    blocking: true|false
    status: "open"
    area: "code|docs|tests|protocol"
    file: "<path>"
    line: <N>
    repro: "<how to reproduce>"
    expected: "<correct behavior>"
    evidence: "<supporting evidence>"
    recommendation: "<specific fix>"
```

Review heuristics:

- review only issues introduced by the diff
- compare the actual diff to the PR title and body
- treat bugs, security issues, and protocol violations as blocking
- keep stylistic issues non-blocking unless the repo says otherwise
- on re-review, check both addressed findings and regressions introduced by the
  fixes

### 6. Post-process the verdict

After the analysis step completes:

1. parse the verdict block
2. write the findings YAML to `packet_path`
3. read the written packet back to verify it

Then branch on the result.

### 7. If the gate passes, send `review_lgtm`

Send an inbox message:

```bash
python3 "${SCRIPTS_DIR}/send_inbox_message.py" "${PROJECT}" \
  --from codex \
  --to "${AUTHOR}" \
  --type review_lgtm \
  --subject "LGTM: PR #${PR_NUMBER}" \
  --body "quality_gate_result: pass
merge_ready: true
task_id: ${TASK_ID:-}
review_round: ${CURRENT_ROUND}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

Then:

- post a short PR comment for human visibility
- add a GitHub approval only when the repo allows it and the active identity is
  valid for approval

If the repo uses a shared or self-authored identity that cannot approve
meaningfully, skip the GitHub approval and rely on the inbox `review_lgtm` plus
the PR comment.

### 8. If the gate fails, send `review_feedback`

Send:

```bash
python3 "${SCRIPTS_DIR}/send_inbox_message.py" "${PROJECT}" \
  --from codex \
  --to "${AUTHOR}" \
  --type review_feedback \
  --subject "Review feedback: round ${CURRENT_ROUND} (#${PR_NUMBER})" \
  --body "findings_packet: packets/findings/<packet_filename>
round: ${CURRENT_ROUND}
blocking_count: ${BLOCKING_COUNT}
task_id: ${TASK_ID:-}
review_round: ${CURRENT_ROUND}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

If the repo's max round count is already reached, append an escalation marker to
the body and report that the loop needs manual coordination.

Always add a status-only PR comment. Do not paste the findings packet, logs, or
local paths into the comment.

### 9. Optional re-review wait

If the chosen workflow keeps the reviewer active for one more round, poll for
`review_addressed` with a shell loop and a bounded timeout. When it arrives:

1. read and parse it
2. refresh the diff
3. optionally run `eval_fix.py`
4. increment the round
5. repeat the gather-analyze-post-process flow

If no re-review message arrives within the timeout, stop and let the author
re-invoke the skill later with a new `review_request`.

### 10. Clean up

Delete processed inbox messages only after the terminal reply path succeeds.

## Best Practices

- Keep all Bash, Git, GitHub, and inbox operations in the leader session.
- Treat helper analysis as read-only.
- Use status-only PR comments.
- Do not duplicate earlier findings already present in PR comments or inbox
  packets.
- Prefer a fresh `review_request` over a bare `review_addressed` when starting a
  new stateless review round.
