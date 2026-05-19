---
name: review-loop-reviewer
description: Run the reviewer side of the review loop — review PR diffs, produce findings, and evaluate quality gate. Single-pass by default (exits after verdict); use --poll for in-session round 2 polling. Hybrid split — leader handles Bash I/O, subagent does analysis only.
---

# /review-loop-reviewer -- Reviewer-Side Review Loop

Hybrid architecture: the **leader** pre-gathers all data via Bash (git, gh, inbox), spawns a **`code-reviewer` subagent** (Read + Bash-for-search only — `command rg`/`command fd`/`command ls`), then the **leader** post-processes the verdict (writes findings packet, sends inbox messages, PR comments/approvals).

This works around runtime restrictions where the subagent's shell permissions can't be widened to match the leader's — the split keeps state-changing operations on the leader, where runtime permissions are configured.

## Arguments

- `/review-loop-reviewer <PR_NUMBER> --author <name>` -- required. The PR and the author agent name.
- `/review-loop-reviewer <PR_NUMBER> --author <name> --project <name>` -- override auto-detected project.
- `/review-loop-reviewer <PR_NUMBER> --author <name> --task-id <id>` -- optional task context when no review_request metadata is available.
- `/review-loop-reviewer <PR_NUMBER> --author <name> --model sonnet` -- model for the subagent (default: `sonnet`).
- `/review-loop-reviewer <PR_NUMBER> --author <name> --dry-run` -- show what the subagent would do without spawning it.
- `/review-loop-reviewer <PR_NUMBER> --author <name> --poll` -- enable in-session polling for `review_addressed` (Step 8). Without this flag, the skill exits after sending the verdict (single-pass mode for event-driven dispatch via `/check-inbox`).

## Instructions

When the user runs `/review-loop-reviewer`, do the following:

### 1. Parse arguments

Extract:

- `PR_NUMBER` -- required, first positional arg. Error if missing.
- `AUTHOR` -- required `--author` flag. Error if missing: "Error: --author is required. Specify the author agent name (e.g., --author claude)."
- `PROJECT` -- optional `--project` flag, auto-detected if omitted.
- `TASK_ID` -- optional `--task-id` flag (default empty).
- `MODEL` -- optional `--model` flag, default `sonnet`.
- `DRY_RUN` -- optional `--dry-run` flag.
- `POLL` -- optional `--poll` flag.

### 2. Gather context

Detect the branch from the PR:

```bash
BRANCH=$(gh pr view <PR_NUMBER> --json headRefName -q .headRefName)
REPO=$(gh pr view <PR_NUMBER> --json headRepositoryOwner,headRepository -q '"\(.headRepositoryOwner.login)/\(.headRepository.name)"' 2>/dev/null || gh repo view --json nameWithOwner -q .nameWithOwner)
```

Detect the project name (from `--project` flag or `.oacp`):

```bash
PROJECT=${PROJECT_FLAG:-$(python3 -c "import json; print(json.load(open('.oacp'))['project_name'])" 2>/dev/null || basename $(git rev-parse --show-toplevel))}
```

Detect the repo path:

```bash
REPO_PATH=$(git rev-parse --show-toplevel)
```

Set derived paths:

```bash
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
INBOX_DIR="${OACP_HOME}/projects/${PROJECT}/agents/claude/inbox"
PACKETS_DIR="${OACP_HOME}/projects/${PROJECT}/packets/findings"
```

### 3. Check preconditions

Verify:

- PR exists: `gh pr view <PR_NUMBER>`
- `--author` was provided (not empty)
- Inbox directory exists: `test -d "${INBOX_DIR}"`
- `oacp send` is available: `oacp send --help` succeeds
- `gh` is authenticated: `gh auth status`

Pre-create the findings packets directory if it does not exist:

```bash
mkdir -p "${PACKETS_DIR}"
```

Report any failures and stop.

### 4. Pre-gather data (leader collects everything the subagent needs)

This is the critical step: the leader fetches ALL external data so the subagent never needs Bash.

#### 4a. Read project memory files

Use the Read tool to read:

- `${OACP_HOME}/projects/<PROJECT>/memory/project_facts.md`
- `${OACP_HOME}/projects/<PROJECT>/memory/open_threads.md`

Store the contents as `MEMORY_CONTEXT` (summarize to key points if very long).

#### 4b. Parse review_request from inbox

```bash
command ls -1 "${INBOX_DIR}/" 2>/dev/null | command grep '\.yaml$'
```

Look for files matching `*_<AUTHOR>_review_request.yaml`. If found, read the matching file with the Read tool and extract: PR number, branch, diff_summary, task_id, review_round. Then delete it:

```bash
rm "${INBOX_DIR}/<filename>"
```

Set `CURRENT_ROUND` from the review_request `review_round` field (default 1).
Set `TASK_ID` from the review_request `task_id` field if present (fallback to CLI `--task-id`).

If no review_request is found, proceed with `CURRENT_ROUND=1` and the CLI-provided context.

#### 4c. Check existing GitHub comments

Fetch all 3 comment APIs to avoid duplicate findings:

```bash
# 1. PR review comments (inline on diff)
INLINE_COMMENTS=$(gh api repos/<REPO>/pulls/<PR_NUMBER>/comments --jq '.[].body' 2>/dev/null || echo "")

# 2. PR reviews (approve/request-changes with body)
REVIEW_COMMENTS=$(gh api repos/<REPO>/pulls/<PR_NUMBER>/reviews --jq '.[] | "\(.state): \(.body)"' 2>/dev/null || echo "")

# 3. Conversation tab / issue comments
ISSUE_COMMENTS=$(gh api repos/<REPO>/issues/<PR_NUMBER>/comments --jq '.[].body' 2>/dev/null || echo "")
```

Combine into `EXISTING_COMMENTS`.

#### 4d. Fetch full diff

```bash
cd <REPO_PATH>
git fetch origin <BRANCH>
DIFF_TEXT=$(git diff main...origin/<BRANCH>)
```

Store the full diff as `DIFF_TEXT`.

#### 4e. Fetch PR title and body

```bash
PR_INFO=$(gh pr view <PR_NUMBER> --json title,body)
```

Store as `PR_TITLE` and `PR_BODY`.

#### 4f. Incremental delta (re-review rounds only)

If `CURRENT_ROUND > 1`, also capture the incremental delta between the previous round's HEAD and the current HEAD. The author's `review_addressed` message carries `head_sha` for the current round; the previous round's HEAD is the `commit_sha` from the prior round's `review_addressed` (or, for the first re-review, the original PR HEAD captured in round 1).

```bash
git diff <PREV_ROUND_HEAD>..<CURRENT_HEAD> > "/tmp/claude/pr<PR_NUMBER>_round<PREV>_to_round<CURRENT>_delta.txt"
```

Pass BOTH paths to the subagent in Step 6: `CUMULATIVE_DIFF_PATH` (full main → current HEAD) and `INCREMENTAL_DIFF_PATH` (delta since last review). The incremental delta is usually small (single-digit KB even when cumulative is large) and gives the subagent a focused "what changed since last review" view alongside the full picture. This matters for re-review rounds (verifying previous findings are addressed) and for catching new issues introduced by fixes.

For round 1, skip this step — `INCREMENTAL_DIFF_PATH` is the same as `CUMULATIVE_DIFF_PATH`.

### 5. Show plan

Display to the user:

```
Review Loop -- Reviewer Side (Hybrid Split)
  PR:          #<PR_NUMBER> (<REPO>)
  Branch:      <BRANCH>
  Author:      <AUTHOR>
  Project:     <PROJECT>
  Task ID:     <TASK_ID or empty>
  Round:       <CURRENT_ROUND>
  Model:       <MODEL>
  Inbox:       <INBOX_DIR>
  Packets dir: <PACKETS_DIR>
  Diff size:   <line count of DIFF_TEXT> lines
  Existing comments: <count> found
```

If `--dry-run`, stop here.

### 6. Spawn analysis-only subagent

Use the Task tool to spawn a `code-reviewer` subagent with `run_in_background: true`. Use the model from `--model` flag (default `sonnet`).

**IMPORTANT**: The subagent is analysis-only (Read + Bash restricted to search — `command rg`, `command fd`, `command ls`; no Write, no git/gh). All external data is passed in the prompt. The subagent outputs the findings YAML in its verdict block; the **leader** writes the findings packet file.

The subagent prompt MUST be exactly the template below with variables substituted:

````
You are the analysis subagent for reviewing PR #<PR_NUMBER> on repo <REPO>.

Your ONLY job: analyze the diff and output a structured verdict with findings YAML. You receive all data pre-gathered — you do NOT need git, gh, or any Bash commands. The leader will write the findings packet file.

CRITICAL: You are an analysis-only code-reviewer. Use Read for file examination and Bash only for search (`command rg`, `command fd`, `command ls`). Do NOT use Write, and do NOT use Bash for git, gh, or any state-changing operation. Output the findings YAML in your verdict block — the leader writes it to disk. (Glob and Grep tools no longer exist on native Claude Code builds since v2.1.117.)

## Context

- PR number: <PR_NUMBER>
- Branch: <BRANCH>
- Repo: <REPO>
- Author: <AUTHOR>
- Project: <PROJECT>
- Task ID: <TASK_ID>
- Round: <CURRENT_ROUND>
- Findings packet path: <PACKETS_DIR>/<YYYYMMDD>_<topic>_claude_r<CURRENT_ROUND>.yaml

## PR Title

<PR_TITLE>

## PR Body

<PR_BODY>

## Project Context (Memory)

<MEMORY_CONTEXT>

## Supplemental Context

<SUPPLEMENTAL_CONTEXT or "None.">

(The leader populates this with any external spec, design-doc, or RFC file paths the review_request body references — including locked specs the implementation should match, prior findings packets, or design rationale docs. Read each referenced path via the Read tool if relevant to a finding.)

## Existing PR Comments (do not duplicate these)

<EXISTING_COMMENTS or "None.">

## Full Diff

For round 1: `<CUMULATIVE_DIFF_PATH>` (the full main → HEAD diff).
For re-review rounds: `<INCREMENTAL_DIFF_PATH>` is the focused round-to-round delta; `<CUMULATIVE_DIFF_PATH>` is the full cumulative diff. Read the incremental delta first to verify each previous finding was addressed, then consult the cumulative diff if you need broader context.

```diff
<DIFF_TEXT>
```

(If the diff was passed inline above. Otherwise read the paths via the Read tool.)

## Reviewer Heuristics

Follow these heuristics during review:

- R1: Only review issues in the diff — do not review entire files. Pre-existing issues belong in separate tickets.
- R2: Compare actual diff against the PR title/body description — flag discrepancies.
- R3: Mark blocking only for bugs, security issues, or protocol violations. Style nits are non-blocking (P2/P3).
- R4: Include a concrete recommendation for every finding.
- R5: (Handled by leader — skip.)
- R6: On re-review rounds, check if previous findings were addressed. Check for new issues introduced by fixes.
- R7: Verify breaking changes are called out in PR description.
- R8: Verify prerequisites/dependencies are accurately documented as required vs optional.

## Instructions

### Step 1: Analyze the diff

Read the diff carefully. Note:
- What changed and why (compare against PR title/body)
- Potential bugs, security issues, protocol violations
- Style issues, documentation gaps
- Any discrepancies between stated purpose and actual changes

If you need additional context about existing source files, use the Read tool to examine them in the repo.

### Step 2: Produce findings

Compose the findings YAML (the leader will write it to disk). Use this exact format:
```yaml
packet_id: "<YYYYMMDD>_<topic>_claude_r<round>"
source_review_packet: ""
reviewer: "claude"
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
```

For each finding, assign severity using these guidelines:
- P0: Critical — data loss, security vulnerability, crash
- P1: Major — incorrect behavior, protocol violation, missing required functionality
- P2: Minor — style issues, suboptimal patterns, documentation gaps
- P3: Nit — cosmetic, naming preferences, optional improvements

### Step 3: Evaluate quality gate

The gate PASSES when ALL of:
- Zero unresolved P0 findings (severity=P0, status=open)
- Zero unresolved blocking findings (blocking=true, status=open)

### Step 4: Output verdict

As the LAST part of your output, print a structured verdict block exactly like this:

```
---VERDICT---
result: pass|fail
blocking_count: <N>
non_blocking_count: <N>
packet_path: <full path where the leader should write the findings YAML>
summary: <1-2 sentence summary of key findings or "No blocking issues found.">
---FINDINGS_YAML---
<the complete findings YAML content from Step 2>
---END_VERDICT---
```

This block is parsed by the leader. The leader extracts the YAML between `---FINDINGS_YAML---` and `---END_VERDICT---` and writes it to disk. Do not deviate from the format.
````

### 7. Post-process (leader handles all messaging)

After the subagent completes, the leader:

1. **Parse the verdict** from the subagent's output text. Look for the `---VERDICT---` block and extract `result`, `blocking_count`, `non_blocking_count`, `packet_path`, `summary`, and the findings YAML content between `---FINDINGS_YAML---` and `---END_VERDICT---`.

2. **Write the findings packet** — the leader writes the extracted YAML to `packet_path` using the Write tool. Verify the file was written correctly by reading it back.

3. **Authenticate for PR interactions** (approval, comments). If the repo requires GitHub App auth (e.g., to attribute the review to a bot identity), generate and use the short-lived app token exactly as that repo specifies. Export `GH_TOKEN` for `gh` commands. Fall back to verified human auth only after a concrete app failure.

   **Self-review guard**: Check if the PR was authored by the same identity that would post the review:

   ```bash
   PR_AUTHOR=$(gh pr view <PR_NUMBER> --json author -q .author.login)
   ```

   If `PR_AUTHOR` matches the reviewer identity (e.g., the same bot or the same user), `gh pr review --approve` will fail ("Can not approve your own pull request"). In this case, skip the GitHub approval and post an informational comment instead. The inbox LGTM message should still be sent regardless.

4. **Branch on result**:

#### If gate PASSES (result=pass) → send LGTM

Send inbox LGTM message:

```bash
oacp send <PROJECT> \
  --from claude --to <AUTHOR> --type review_lgtm \
  --subject "LGTM: PR #<PR_NUMBER>" \
  --body "quality_gate_result: pass\nmerge_ready: true\nmerge_method: squash\ntask_id: <TASK_ID>\nreview_round: <CURRENT_ROUND>" \
  --related-pr <PR_NUMBER> --priority P1 \
  --oacp-dir "${OACP_HOME}"
```

Submit PR review approval using the configured GitHub token (so the approval is attributed correctly):

```bash
APPROVE_FILE="$(mktemp)"
cat > "${APPROVE_FILE}" <<EOF
LGTM - claude

Quality gate: pass. Merge ready.
EOF
GH_TOKEN="${TOKEN}" gh pr review <PR_NUMBER> --approve --body-file "${APPROVE_FILE}"
rm -f "${APPROVE_FILE}"
```

Print: `STATUS: LGTM_SENT`

#### If gate FAILS (result=fail) → send feedback

Check if `CURRENT_ROUND >= 2` (max rounds). If so, add escalation.

Send inbox feedback message:

```bash
oacp send <PROJECT> \
  --from claude --to <AUTHOR> --type review_feedback \
  --subject "Review feedback: round <CURRENT_ROUND> (#<PR_NUMBER>)" \
  --body "findings_packet: packets/findings/<packet_filename>\nround: <CURRENT_ROUND>\nblocking_count: <blocking_count>\ntask_id: <TASK_ID>\nreview_round: <CURRENT_ROUND>" \
  --related-pr <PR_NUMBER> --priority P1 \
  --oacp-dir "${OACP_HOME}"
```

If `CURRENT_ROUND >= 2`, append `\nescalation: max_rounds_exceeded` to the body.

Post PR comment for human visibility (status only — no paths, logs, or details):

```bash
COMMENT_FILE="$(mktemp)"
cat > "${COMMENT_FILE}" <<EOF
**Review feedback (round <CURRENT_ROUND>)** - claude

Status: changes requested.
Blocking findings: <blocking_count>
Total findings: <total>
Details delivered via inbox review_feedback message.
EOF
GH_TOKEN="${TOKEN}" gh pr comment <PR_NUMBER> --body-file "${COMMENT_FILE}"
rm -f "${COMMENT_FILE}"
```

If escalated: print `STATUS: ESCALATED` and stop.
Otherwise: print `STATUS: FEEDBACK_SENT_ROUND_<CURRENT_ROUND>`

### 8. Round 2 handling (leader polls and re-invokes)

> **Single-pass mode (default)**: If `--poll` was NOT provided, skip this step entirely. The skill exits after Step 7 (post-process verdict). When `/check-inbox` receives the `review_addressed` message (informational) followed by a new `review_request` (round N+1), it will dispatch a new `/review-loop-reviewer` invocation for the next round.

If `--poll` was provided, poll for the author's response after sending feedback (non-escalated):

```bash
command ls -1 "${INBOX_DIR}/" 2>/dev/null | command grep '\.yaml$'
```

Look for files matching `*_<AUTHOR>_review_addressed.yaml`. Poll every 30 seconds for up to 10 minutes (20 polls). When found:

1. Read the message with the Read tool to extract: `commit_sha`, `changes_summary`, `round`.
2. Delete the message:

   ```bash
   rm "${INBOX_DIR}/<filename>"
   ```

3. Fetch the updated diff:

   ```bash
   cd <REPO_PATH>
   git fetch origin <BRANCH>
   DIFF_TEXT=$(git diff main...origin/<BRANCH>)
   ```

4. (Optional) If `eval_fix.py` is available locally, run a quick heuristic check on the findings packet.
5. Increment `CURRENT_ROUND` and re-execute Steps 4c through 7 (re-gather comments, spawn new subagent with updated diff, post-process verdict).

If timeout (no message after 20 polls), print `STATUS: FEEDBACK_SENT_ROUND_<CURRENT_ROUND>` and stop.

### 9. Clean up

After the review loop completes (LGTM sent, escalated, or timed out):

- Delete all processed inbox messages (review_request, review_addressed) if not already deleted.

## Notes

- The subagent is a `code-reviewer` (Read + Bash-for-search only — `command rg`/`command fd`/`command ls`) — no Write calls, no git/gh/commits. All state-changing I/O is pre-gathered or done by the leader. The leader writes the findings packet from the subagent's verdict output.
- Default model is sonnet (sufficient for review — reading + analysis).
- Pre-creates `packets/findings/` directory in preconditions so the leader can write findings immediately.
- Configure runtime permissions according to local policy; the leader owns all state-changing shell operations (inbox ops, gh commands, git).
- **Failure state tracking**: If the leader crashes after sending `review_feedback` but before the review loop completes, the next invocation should check the outbox/reviewer inbox for an already-sent `review_feedback` for this PR+round before re-sending.
- The reviewer does not need a separate worktree — it reads diffs from the existing repo.
- **Single-pass is the default**: The skill exits after sending feedback (Step 7). When the author sends `review_addressed` + a new `review_request` (round N+1), `/check-inbox` dispatches a fresh `/review-loop-reviewer` invocation. Use `--poll` to revert to in-session polling (Step 8) if needed.
- **Diff size guard**: If the diff exceeds ~3000 lines, warn the user that the subagent prompt will be very large. Consider splitting into multiple reviews or summarizing unchanged context.
- **Large diff file-path pattern**: For diffs >100KB, do NOT embed the full diff in the subagent prompt. Instead, save `DIFF_TEXT` to a Bash tool-results file (it auto-persists large outputs) or a temp file, then include the file path in the subagent prompt and instruct the subagent to use the Read tool to load it. This avoids context overflow while preserving full diff coverage.
- **Approval auto-dismissal between rounds**: After a reviewer LGTM, any subsequent author push triggers the org's `dismiss-stale-reviews` rule (if enabled), stripping the approval and returning the PR to REVIEW_REQUIRED. The author must send a fresh `review_request` for round N+1; the reviewer re-reviews the incremental diff. Don't treat a previously-LGTM'd PR showing as unapproved as a regression — it's the dismissal policy.

## PR Comment Data-Minimization Rule

- PR comments must be status-only summaries for humans.
- Keep details in inbox protocol messages and findings packets; do not paste them into PR comments.
- Never include command output, logs, stack traces, credentials, environment values, or local-only paths in PR comments.
- Always use `--body-file` with a temp file for PR comments and approvals — avoids shell expansion leaking sensitive data to `ps` output.

## Learned from runs

<!-- All prior lessons incorporated into main instructions. Section kept as anchor for future entries. -->
