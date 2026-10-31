# Fix-subagent spawn contract (review-loop-author Step 7)

Load this only when spawning the fix subagent for a larger fix set. For small
fix sets the leader edits directly — see SKILL.md Step 7.

## Spawn parameters

Agent tool, `subagent_type: general-purpose`, `model: sonnet` (sufficient for
scoped code fixes).

The subagent gets Read, Edit, Write, and Bash **for search only** (`command
rg`, `command fd`, `command ls`). It must not run git, gh, `oacp send`, or any
state-changing command — the leader owns commits, pushes, and messages.

## Prompt template

Substitute every `<...>` variable, then send exactly:

````
You are the fix subagent for PR #<PR_NUMBER> on repo <REPO>.

Your ONLY job: read the review findings, edit source files to address them,
and output a summary of what you did. You receive all findings data
pre-gathered.

Use Read to examine source, Edit to fix code, Write for new files if needed,
and Bash only for search (`command rg`, `command fd`, `command ls`). Don't run
git, gh, or message sends: the leader owns commits, pushes, and every other
state change.

## Context

- PR number: <PR_NUMBER>
- Branch: <BRANCH>
- Repo: <REPO>
- Repo path: <REPO_PATH>
- Round: <current_round>

## Findings to Address

```yaml
<FINDINGS_CONTENT>
```

## Instructions

Address every finding with `status: open`, blocking findings first (P0, P1,
then blocking P2), then non-blocking P2/P3. Each one ends in one of three
outcomes:

- **Fix** — the finding is valid and the fix is clear: make a minimal, focused
  edit that addresses it without introducing new issues.
- **Push back** — the finding is incorrect or rests on a misunderstanding:
  record why (the leader sends the reviewer a question).
- **Defer** — out of scope for this PR: record why.

### Output fix summary

As the LAST part of your output, print exactly this structure (parsed by the
leader — do not deviate; use empty lists when a section has no items):

```
---FIX_SUMMARY---
fixed:
  - id: "F-001"
    description: "<what was changed>"
    files: ["<path/to/file>"]
deferred:
  - id: "F-002"
    reason: "<why deferred>"
pushed_back:
  - id: "F-004"
    reason: "<why this finding is incorrect>"
files_modified:
  - "<path/to/file1>"
---END_FIX_SUMMARY---
```
````

## Leader parse contract

Extract the `---FIX_SUMMARY---` … `---END_FIX_SUMMARY---` block: `fixed`,
`deferred`, `pushed_back`, `files_modified`. Review the actual `git diff`
before committing — the block is the subagent's claim, the diff is the truth.
If the block is missing or malformed, do not guess: inspect the diff, ask the
subagent (SendMessage) for a corrected block, or fall back to leader-direct
verification of each finding.
