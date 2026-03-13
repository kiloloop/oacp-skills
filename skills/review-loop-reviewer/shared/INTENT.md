# review-loop-reviewer — Shared Intent

## What it does

Runs the reviewer side of an asynchronous code review loop. Pre-gathers PR diff and context, spawns an analysis subagent to review the code, then processes the verdict — writing a findings packet and sending feedback or LGTM to the author via inbox.

## Architecture

Hybrid leader/subagent split:

- **Leader**: handles all external I/O — git fetch, GitHub API calls, inbox reads/deletes, findings packet writes, message sending
- **Analysis subagent**: read-only — examines the diff (passed in via prompt), reads source files for context, produces a structured verdict with findings YAML. No shell access, no file writes.

This separation ensures the subagent cannot accidentally modify the repository or interact with external services.

## Message types

| Direction | Type | Purpose |
|-----------|------|---------|
| Receives | `review_request` | Trigger to review a PR (includes round number) |
| Receives | `review_addressed` | Author has pushed fixes (poll mode only) |
| Sends | `review_feedback` | Findings packet reference with blocking count |
| Sends | `review_lgtm` | Approval — quality gate passed |

## Protocol references

- **Findings packet format**: YAML stored at `$OACP_HOME/projects/<project>/packets/findings/`

  ```yaml
  packet_id: "<date>_<topic>_<agent>_r<round>"
  reviewer: "<agent>"
  round: <N>
  summary:
    verdict: "pass|fail"
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
      recommendation: "<suggested fix>"
  ```

- **Quality gate**: Passes when zero P0 and zero blocking findings are open
- **Severity scale**: P0 (critical) → P1 (major) → P2 (minor) → P3 (nit)

## Reviewer heuristics

1. Only review issues in the diff — pre-existing issues belong in separate tickets
2. Compare diff against PR description — flag discrepancies
3. Mark blocking only for bugs, security issues, or protocol violations
4. Include a concrete recommendation for every finding
5. On re-review rounds, verify previous findings were addressed
6. Verify breaking changes are documented

## Acceptance criteria

- Full diff analyzed against PR description
- Findings packet written with correct format
- Quality gate evaluated (pass/fail)
- Appropriate message sent: `review_lgtm` (pass) or `review_feedback` (fail)
- PR comment posted for human visibility (status only)
- Self-review guard: skip GitHub approval if reviewer authored the PR
