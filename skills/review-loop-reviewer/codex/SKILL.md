---
name: review-loop-reviewer
description: "Run the reviewer side of the review loop: gather PR context, optionally delegate read-only review analysis to a Codex subagent, write findings packets, and send feedback or LGTM."
---

# /review-loop-reviewer

Run the reviewer-side review loop for one PR.

## Interface

`/review-loop-reviewer <PR_NUMBER> --author <name> [--project <name>] [--task-id <id>] [--model <model>] [--dry-run]`

- `PR_NUMBER` is required.
- `--author` is required.
- `--project` is optional. If omitted, detect from repo markers and fall back to the repo name.
- `--task-id` is optional task context.
- `--model` is optional. Default is to inherit the parent model; pass an override only when the user requested it or the task clearly needs it.
- `--dry-run` gathers context and prints the planned flow without spawning a subagent or sending review results.

## Codex Execution Model

- The leader owns all shell work: `git`, `gh`, inbox reads and deletes, packet writes, PR comments, PR approvals, and final status decisions.
- The delegated reviewer is analysis-only. Prefer `spawn_agent` with `agent_type="explorer"` or a repo-specific custom reviewer agent when one exists.
- Treat delegation as opt-in. If the user did not ask for delegation, subagents, or parallel review work, run the leader-only analysis path.
- Do not let the subagent send inbox messages, write packets, comment on the PR, or mutate the repo.
- If `spawn_agent` is unavailable, fails, or is overkill for a tiny diff, run the analysis locally in the current thread with the same verdict contract.
- For round 2+, prefer `send_input` to the same delegated reviewer when the previous context is still useful. Otherwise close the old agent and spawn a fresh one.

## 1. Parse arguments

Extract:

- `PR_NUMBER` from the first positional arg. Error if missing.
- `AUTHOR` from `--author`. Error if missing.
- `PROJECT_FLAG` from `--project`.
- `TASK_ID` from `--task-id` (default empty).
- `MODEL` from `--model` (default empty, meaning inherit the parent model).
- `DRY_RUN` from `--dry-run`.

## 2. Resolve repo, runtime, and GitHub auth

Set up the repo and auth wrappers first:

```bash
REPO_PATH="$(git rev-parse --show-toplevel)"

PROJECT="${PROJECT_FLAG:-$(python3 - <<'PY'
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
INBOX_DIR="${PROJECT_ROOT}/agents/codex/inbox"
PACKETS_DIR="${PROJECT_ROOT}/packets/findings"
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
```

Notes:

- Inspect the nearest `AGENTS.md` before repo-scoped `gh` calls and use GitHub App auth first when the repo requires it.
- Treat all PR and repo `gh` calls in this skill as repo-scoped, even read-only ones.
- If GitHub App auth is required, obtain a repo-scoped token using the nearest repo instructions and export it as `APP_GH_TOKEN`; do not hardcode helper paths or persist tokens.
- Fall back to human auth only after a concrete App-token failure and verify the active login before proceeding.
- Do not rely on `gh api user` for GitHub App installation tokens; that endpoint may return `403` even when the token is valid. Verify App auth with a repo-scoped command such as `gh pr view`, `gh pr comment`, or `gh pr review`.

Resolve PR metadata:

```bash
BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json headRefName -q .headRefName)"
BASE_BRANCH="$(repo_gh pr view "${PR_NUMBER}" --json baseRefName -q .baseRefName)"
REPO="$(repo_gh pr view "${PR_NUMBER}" --json headRepositoryOwner,headRepository -q '"\(.headRepositoryOwner.login)/\(.headRepository.name)"' 2>/dev/null || repo_gh repo view --json nameWithOwner -q .nameWithOwner)"
```

## 3. Check preconditions

Verify:

- `repo_gh pr view "${PR_NUMBER}" --repo "${REPO}"` succeeds.
- `AUTHOR` is not empty.
- `command -v oacp >/dev/null` succeeds.
- `test -d "${INBOX_DIR}"`.
- `gh` is authenticated under the repo's required identity.

Pre-create packets dir:

```bash
mkdir -p "${PACKETS_DIR}"
```

If any precondition fails, report it and stop.

## 4. Pre-gather context

The leader gathers everything needed for analysis.

### 4a. Read project memory

Read these files when present and summarize them into `MEMORY_CONTEXT`:

- `${PROJECT_ROOT}/memory/project_facts.md`
- `${PROJECT_ROOT}/memory/open_threads.md`

### 4b. Parse inbox context

List the inbox:

```bash
command ls -1 "${INBOX_DIR}/"
```

Look for:

- `*_${AUTHOR}_review_request.yaml`
- `*_${AUTHOR}_review_addressed.yaml` when this is a manual re-review continuation

Extract:

- `CURRENT_ROUND` from `review_round` when present, otherwise `1`
- `TASK_ID` from the message when present, otherwise CLI fallback
- the inbox file paths to delete only after the terminal reply succeeds

### 4c. Gather existing GitHub comments

Fetch all three comment surfaces so the reviewer does not duplicate prior feedback:

```bash
INLINE_COMMENTS="$(repo_gh api "repos/${REPO}/pulls/${PR_NUMBER}/comments" --jq '.[].body' 2>/dev/null || echo "")"
REVIEW_COMMENTS="$(repo_gh api "repos/${REPO}/pulls/${PR_NUMBER}/reviews" --jq '.[] | "\(.state): \(.body)"' 2>/dev/null || echo "")"
ISSUE_COMMENTS="$(repo_gh api "repos/${REPO}/issues/${PR_NUMBER}/comments" --jq '.[].body' 2>/dev/null || echo "")"
```

Combine them into `EXISTING_COMMENTS`.

### 4d. Gather diff and PR text

```bash
git fetch origin "${BRANCH}"
DIFF_TEXT="$(git diff "origin/${BASE_BRANCH}...origin/${BRANCH}")"
PR_INFO="$(repo_gh pr view "${PR_NUMBER}" --json title,body)"
```

Store:

- `PR_TITLE`
- `PR_BODY`
- `DIFF_TEXT`
- `DIFF_LINE_COUNT`

## 5. Show the plan

Display:

```text
Review Loop - Reviewer Side
  PR:          #<PR_NUMBER> (<REPO>)
  Branch:      <BRANCH>
  Base branch: <BASE_BRANCH>
  Author:      <AUTHOR>
  Project:     <PROJECT>
  Task ID:     <TASK_ID or empty>
  Round:       <CURRENT_ROUND>
  Model:       <MODEL or inherited parent model>
  Inbox:       <INBOX_DIR>
  Packets dir: <PACKETS_DIR>
  Diff size:   <DIFF_LINE_COUNT> lines
  Existing comments: <count>
```

If `DIFF_LINE_COUNT` is above roughly `3000`, warn that delegated prompts get large and that leader-only review or diff splitting may be better.

If `--dry-run`, stop here.

## 6. Run the analysis

### Preferred path: delegated analysis

Delegate when the diff is non-trivial or you want a second-pass reviewer. Use a prompt equivalent to:

````text
You are the analysis subagent for reviewing PR #<PR_NUMBER> on repo <REPO>.

Your only job is to analyze the PR diff and output a structured verdict with findings YAML. The leader owns all shell, inbox, GitHub, and packet-writing work.

Do not run shell commands. Do not edit files. You may inspect files in the repo when needed for context.

## Context

- PR number: <PR_NUMBER>
- Branch: <BRANCH>
- Repo: <REPO>
- Author: <AUTHOR>
- Project: <PROJECT>
- Task ID: <TASK_ID>
- Round: <CURRENT_ROUND>
- Findings packet path: <PACKETS_DIR>/<YYYYMMDD>_<topic>_codex_r<CURRENT_ROUND>.yaml

## PR Title

<PR_TITLE>

## PR Body

<PR_BODY>

## Project Context

<MEMORY_CONTEXT>

## Existing PR Comments

<EXISTING_COMMENTS or "None.">

## Full Diff

```diff
<DIFF_TEXT>
```

## Review Heuristics

- Review only issues introduced by the diff.
- Compare the actual diff to the PR title and body.
- Mark `blocking: true` only for bugs, security issues, or protocol violations.
- Include a concrete recommendation for every finding.
- On re-review rounds, check whether previous findings were addressed and whether the fixes introduced new issues.

## Output Contract

As the final block of your response, print exactly:

```text
---VERDICT---
result: pass|fail
blocking_count: <N>
non_blocking_count: <N>
packet_path: <full path>
summary: <1-2 sentence summary>
---FINDINGS_YAML---
packet_id: "<YYYYMMDD>_<topic>_codex_r<round>"
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
    evidence: "<evidence>"
    recommendation: "<suggested fix>"
---END_VERDICT---
```
````

Spawn the reviewer:

- Prefer `spawn_agent(agent_type="explorer", reasoning_effort="high", fork_context=false, message=PROMPT)` by default; include `model=MODEL` only when `MODEL` is non-empty.
- If the repo ships a custom reviewer agent and the current session already uses it successfully, that is also acceptable.
- Because the next step depends on the verdict, call `wait_agent` once with a reasonable timeout instead of busy-polling.

If the delegated path times out or fails:

- Fall back to leader-only analysis in the current thread.
- Preserve the same verdict block and YAML contract so post-processing stays identical.

### Re-review path

If a prior delegated reviewer is still open and the next round is tightly related, reuse it with `send_input` and only the delta context:

- updated round number
- updated diff
- updated comments
- any prior packet path that matters for comparison

If the prior delegated reviewer is no longer the right context holder, close it and spawn a fresh one.

Do not run multiple reviewer subagents against the same unresolved round.

## 7. Post-process the verdict

After delegated or leader-only analysis finishes:

1. Parse the `---VERDICT---` block.
2. Extract `result`, `blocking_count`, `non_blocking_count`, `packet_path`, `summary`, and the YAML between `---FINDINGS_YAML---` and `---END_VERDICT---`.
3. Write the findings packet to `packet_path`.
4. Read the file back to verify it was written correctly.

## 8. Send LGTM or feedback

### If result is `pass`

Send inbox LGTM:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex --to "${AUTHOR}" --type review_lgtm \
  --subject "LGTM: PR #${PR_NUMBER}" \
  --body "quality_gate_result: pass
merge_ready: true
task_id: ${TASK_ID:-}
review_round: ${CURRENT_ROUND}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

If the repo allows approval from the current identity, submit a PR approval using `repo_gh pr review ... --approve` with a temp file. Otherwise rely on the inbox LGTM plus a status-only PR comment.

Always add a PR comment:

```text
**LGTM** - codex

Quality gate: pass. Merge ready.
```

Print `STATUS: LGTM_SENT`.

### If result is `fail`

Send inbox feedback:

```bash
oacp send "${PROJECT}" \
  --oacp-dir "${OACP_ROOT}" \
  --from codex --to "${AUTHOR}" --type review_feedback \
  --subject "Review feedback: round ${CURRENT_ROUND} (#${PR_NUMBER})" \
  --body "findings_packet: packets/findings/<packet_filename>
round: ${CURRENT_ROUND}
blocking_count: <blocking_count>
task_id: ${TASK_ID:-}
review_round: ${CURRENT_ROUND}" \
  --related-pr "${PR_NUMBER}" \
  --priority P1
```

If `CURRENT_ROUND >= 2`, append:

```text
escalation: max_rounds_exceeded
```

Always add a status-only PR comment and print either:

- `STATUS: FEEDBACK_SENT_ROUND_<CURRENT_ROUND>`
- `STATUS: ESCALATED`

## 9. Round 2 handling

After non-escalated feedback:

- Keep polling local. Do not delegate inbox polling.
- Poll for `*_${AUTHOR}_review_addressed.yaml` every 30 seconds for up to 10 minutes.
- When it arrives, refresh the diff and comments, then either reuse the current delegated reviewer with `send_input` or run a fresh delegated/local analysis.

If the author never responds, print `STATUS: FEEDBACK_SENT_ROUND_<CURRENT_ROUND>` and stop.

## 10. Clean up

At terminal exit:

- Delete processed inbox messages only after the reply path succeeded.
- Close any still-open delegated reviewer with `close_agent`.

## Notes

- Prefer the PR's real `baseRefName`; do not hardcode `main`.
- Keep PR comments status-only. All detailed findings live in packets and inbox messages.
- Same-account repos may not want `gh pr review --approve`; inbox `review_lgtm` plus a status comment is acceptable there.
- Keep the packet-writing contract stable even when the analysis path changes.

## Learned from runs

- Codex reviewer delegation works best when the leader owns all protocol and shell state while the subagent only reasons over the diff and nearby files.
- Reusing a prior delegated reviewer with `send_input` is useful for focused round-2 re-reviews, but it is not worth carrying stale agent state across unrelated rounds.
- Tiny diffs often do not justify delegation; large or ambiguous diffs usually do.
