---
name: review-loop-author
description: "Run the author side of the review loop: request review, poll for feedback, optionally delegate triage or isolated fixes to Codex subagents, address findings, and report progress through inbox plus PR comments."
---

# /review-loop-author

Run the author-side review loop for one PR.

## Interface

`/review-loop-author <PR_NUMBER> --reviewer <name> [--project <name>] [--task-id <task-id>] [--model <model>]`

- `PR_NUMBER` is required.
- `--reviewer` is required.
- `--project` is optional. If omitted, detect from repo markers and fall back to the repo name.
- `--task-id` is optional. When present, review messages include task metadata and task review fields are updated automatically.
- `--model` is optional. Default is to inherit the parent model; pass an override only when the user requested it or the task clearly needs it.

## Codex Execution Model

- The leader owns review-loop state, polling, inbox writes and deletes, task-state mutations, validation decisions, commits, pushes, and PR comments.
- Keep polling local. Do not delegate inbox polling.
- Treat delegation as opt-in. If the user did not ask for delegation, subagents, or parallel fix work, stay leader-only.
- The best delegation point is after `review_feedback` is parsed: use an `explorer` to triage findings, gather evidence, map impacted files, and suggest tests.
- Use a `worker` only for accepted fixes with a clear, isolated write scope. Default to one writer at a time.
- Parallel writers are allowed only when write scopes are clearly disjoint and the next local step is not blocked on one of them. When unsure, stay single-writer.
- If a delegated worker already owns the same file set and follow-up arrives, prefer `send_input` to that worker over spawning an overlapping one.

## Setup

```bash
set -euo pipefail

AGENT_NAME="codex"
PR_NUMBER="<PR_NUMBER>"
REVIEWER="<reviewer_name>"
TASK_ID="${TASK_ID:-}"
MODEL="${MODEL:-}"

REPO_PATH="$(git rev-parse --show-toplevel)"
PROJECT="${PROJECT:-$(python3 - <<'PY'
import json, pathlib

root = pathlib.Path.cwd()
for marker in (".oacp", "workspace.json"):
    path = root / marker
    if not (path.exists() or path.is_symlink()):
        continue
    try:
        resolved = path.resolve() if path.is_symlink() else path
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        project = data.get("project_name", "")
        if project:
            print(project)
            raise SystemExit
    except Exception:
        pass
print(root.resolve().name)
PY
)}"

OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
PROJECT_ROOT="${OACP_ROOT}/projects/${PROJECT}"
INBOX_DIR="${PROJECT_ROOT}/agents/${AGENT_NAME}/inbox"
EVAL_FIX="${EVAL_FIX:-}"
APP_GH_TOKEN="${APP_GH_TOKEN:-}"

EXPECTED_GH_USER="<account>"

get_app_token() {
  [ -n "${APP_GH_TOKEN}" ]
}

ensure_human_gh_auth() {
  if ! gh auth switch --hostname github.com --user "${EXPECTED_GH_USER}" >/dev/null 2>&1; then
    ACTIVE_GH_USER="$(gh api user --jq '.login' 2>/dev/null || true)"
    [ "${ACTIVE_GH_USER}" = "${EXPECTED_GH_USER}" ] || {
      echo "GitHub auth mismatch: expected ${EXPECTED_GH_USER}, got ${ACTIVE_GH_USER}"
      return 1
    }
  fi
}

repo_gh() {
  if get_app_token; then
    local output rc
    if output="$(GH_TOKEN="${APP_GH_TOKEN}" GITHUB_TOKEN="${APP_GH_TOKEN}" gh "$@" 2>&1)"; then
      printf '%s\n' "${output}"
      return 0
    fi
    rc=$?
    case "${output}" in
      *"Resource not accessible by integration"*|*"Bad credentials"*|*"Requires authentication"*|*"HTTP 401"*|*"HTTP 403"*)
        printf '%s\n' "${output}" >&2
        echo "GitHub App token auth/scope failure; falling back to human gh auth" >&2
        ;;
      *)
        printf '%s\n' "${output}" >&2
        return "${rc}"
        ;;
    esac
  fi
  ensure_human_gh_auth
  gh "$@"
}

BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json headRefName -q .headRefName)"
BASE_BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json baseRefName -q .baseRefName)"
REPO="$(repo_gh repo view --json nameWithOwner -q .nameWithOwner)"
```

Validate preconditions:

```bash
repo_gh pr view "${PR_NUMBER}" --repo "${REPO}" >/dev/null
command -v oacp >/dev/null
test -d "${INBOX_DIR}"
```

## Procedure

### Step 1: Prepare and send `review_request`

Before requesting review:

- Ensure all commits are pushed to the PR branch.
- Ensure the PR description matches the actual scope.
- Ensure the relevant pre-review checks already passed.
- Treat the normal `review_request` path as a formal review round. If the PR is still draft, mark it ready for review before sending the request. Only keep the PR draft when the user explicitly wants informal draft feedback outside the normal review loop.

Create a concise diff summary:

```bash
DIFF_SUMMARY="$(git diff "${BASE_BRANCH}...${BRANCH}" --stat)"
```

Ensure the PR is ready for formal review:

```bash
IS_DRAFT="$(repo_gh pr view "${PR_NUMBER}" --repo "${REPO}" --json isDraft -q .isDraft)"
if [ "${IS_DRAFT}" = "true" ]; then
  repo_gh pr ready "${PR_NUMBER}" --repo "${REPO}"
fi
```

Send the review request:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
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

Always add a status-only PR comment.

Initialize:

- `current_round=1`
- `poll_interval=30`
- `max_rounds=3`
- `timeout_minutes=15`

### Step 2: Poll for reviewer response

Keep polling local. Prefer a single in-session loop or `/loop 30s /check-inbox` when that command is already part of the workflow.

Wait for inbox messages where:

- `from` is the reviewer
- `related_pr` is the current PR
- `type` is `review_feedback` or `review_lgtm`

If `review_feedback`, continue to Step 3. If `review_lgtm`, continue to Step 8. If the timeout is reached, continue to Step 9.

### Step 3: Parse `review_feedback`

Extract from the message body:

- `findings_packet`
- `round`
- `blocking_count`
- `task_id` when present
- `review_round` when present

If the body contains `escalation: max_rounds_exceeded`, continue to Step 9.

Resolve and verify the findings packet path:

```bash
FINDINGS_REL="packets/findings/..."
FINDINGS_PATH="${PROJECT_ROOT}/${FINDINGS_REL}"
test -f "${FINDINGS_PATH}"
```

Do not delete the feedback message yet. Record its path and delete it only after the reply path succeeds.

If `task_id` is present, update the task review fields before implementation:

- `review_round`
- `review_status: needs_changes`
- append `findings_packet` if missing

### Step 4: Triage findings

Select all findings with `status: open` and prioritize:

1. P0 blocking
2. P1 blocking
3. Non-blocking P0 or P1
4. P2 or P3

For packets with multiple findings, ambiguous findings, or uncertain scope, spawn an `explorer` to produce a compact triage plan.

Recommended prompt shape:

```text
You are the triage subagent for PR #<PR_NUMBER>.

Review the findings packet and the relevant repo files. Do not edit files or run shell commands.

Return a compact table with one row per open finding:
- finding_id
- disposition: fix | pushback | defer
- confidence: high | medium | low
- owner_files: explicit file paths likely involved
- tests_to_run: targeted checks
- notes: one short sentence
```

Use:

- `spawn_agent(agent_type="explorer", reasoning_effort="high", fork_context=false, message=PROMPT)` by default; include `model=MODEL` only when `MODEL` is non-empty.
- `wait_agent` once the leader is ready to review the triage result

The leader makes the final decision. The explorer is advisory.

### Step 5: Address each finding

For each accepted finding:

1. Read the finding details and the suggested triage output.
2. Decide whether to fix locally or delegate implementation.
3. Run targeted validation.
4. Commit and push from the leader session.

Use local implementation when:

- the change is tiny
- the next step depends immediately on the edit
- the write scope overlaps other active work

Use a `worker` when:

- the finding is valid and clear
- the write scope is explicit
- the worker can own a bounded file set without stepping on other edits

When delegating a fix:

- tell the worker it is not alone in the codebase
- give it explicit file ownership
- tell it not to commit, push, comment, or send inbox messages
- review its diff before integrating or validating

Default to one writer worker at a time. Parallel writers are an exception, not the baseline.

Pushback example:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from "${AGENT_NAME}" \
  --to "${REVIEWER}" \
  --type question \
  --subject "Question on finding F-001 (#${PR_NUMBER})" \
  --body "Please clarify finding F-001: <reason>" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

### Step 6: Run `eval_fix.py` when it is worth it

Use this pre-check when addressing 3 or more findings or when the fix set spans multiple files:

```bash
if [ -n "${EVAL_FIX}" ] && test -f "${EVAL_FIX}"; then
  python3 "${EVAL_FIX}" "${FINDINGS_PATH}" --diff-ref "${BASE_BRANCH}..HEAD" --verbose
fi
```

- If it reports unaddressed findings, fix them before replying.
- Skip it for single trivial findings.
- If it errors, log it and continue.

### Step 7: Send `review_addressed` and a fresh `review_request`

After fixes are pushed:

```bash
LATEST_SHA="$(git rev-parse HEAD)"
```

Send `review_addressed`:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
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

Then send a fresh `review_request` for round `N+1`:

```bash
NEXT_ROUND=$((current_round + 1))
RE_REVIEW_SUMMARY="$(git diff "${BASE_BRANCH}...HEAD" --stat)"
IS_DRAFT="$(repo_gh pr view "${PR_NUMBER}" --repo "${REPO}" --json isDraft -q .isDraft)"
if [ "${IS_DRAFT}" = "true" ]; then
  repo_gh pr ready "${PR_NUMBER}" --repo "${REPO}"
fi

oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
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

Delete the processed `review_feedback` message only after both outbound messages succeed.

Set `current_round="${NEXT_ROUND}"` and return to Step 2.

### Step 8: Handle `review_lgtm`

Confirm the body includes:

- `quality_gate_result: pass`
- `merge_ready: true`

Then:

1. Delete the `review_lgtm` message.
2. Report that the PR is merge-ready.
3. Do not auto-merge unless explicitly asked and repo policy allows it.
4. If merge is requested, run `repo_gh pr checks` first and block merge on any non-pass status.
5. If `task_id` is present, update the task review fields to approved.

Exit with success.

### Step 9: Handle timeout or escalation

Escalate when:

1. `current_round > max_rounds`
2. feedback contains `escalation: max_rounds_exceeded`
3. polling exceeds timeout

Send a notification to the team lead and add a status-only PR comment.

Exit with `ESCALATED` or `TIMEOUT`.

### Step 10: Clean up

After exit:

- Delete processed `review_feedback` and `review_lgtm` messages.
- Optionally prune sent `review_addressed` from outbox by retention policy.
- Do not update durable memory files such as `open_threads.md` during normal review-loop execution. Leave that for `/debrief` or `/self-improve`.

## Decision rules

### Fix vs push back vs defer

1. Fix when the finding is valid and in scope.
2. Push back when the finding is incorrect or unclear.
3. Defer when the finding is valid but out of scope for the current PR.

### When to delegate

1. Use an `explorer` for triage and evidence gathering.
2. Use a `worker` only for bounded implementation tasks with explicit file ownership.
3. Keep commits, pushes, comments, inbox messages, and validation gates in the leader.

### When to escalate

1. Escalate when rounds exceed the limit.
2. Escalate when the reviewer explicitly signals max rounds exceeded.
3. Escalate on reviewer timeout.

## Error handling

- Malformed `review_feedback` body: ask the reviewer to resend required fields.
- Missing findings packet path: ask for clarification and pause the loop.
- Delegated worker returns overlapping or unsafe changes: stop delegating, review locally, and continue with leader ownership.
- `git push` failure: resolve and retry; escalate only when blocked.
- `eval_fix.py` failure: log and continue because it is optional.

## PR comment rule

- Keep PR comments concise and status-oriented.
- Store details in protocol messages and findings packets, not in PR comments.
- Never include command output, logs, stack traces, credentials, environment values, or local-only paths in PR comments.

## Status outputs

- `STATUS: PASSED`
- `STATUS: ESCALATED`
- `STATUS: TIMEOUT`

## Learned from runs

- The useful delegation point for author-side review loops is after the feedback packet is in hand, not during polling or GitHub I/O.
- Triage explorers save time on multi-finding packets by mapping likely files and tests before editing starts.
- Single-writer delegation is much safer than parallel writers for review-fix work; overlapping workers create more merge risk than they remove.
- A formal inbox `review_request` should line up with GitHub review state. If the PR is still draft, mark it ready for review before sending the initial request or any re-review request.
- 2026-04-29: If a reviewer sends `review_lgtm` with non-blocking findings and the author chooses to fix those findings anyway, treat the existing LGTM as stale because the branch changed after approval. Send `review_addressed` plus a fresh `review_request`, delete the stale LGTM only after both outbound messages succeed, and wait for a new LGTM on the new head before merging.
