# review-loop-reviewer

Run the reviewer side of the review loop — review PR diffs, produce findings, and evaluate quality gate.

## Overview

Reads a PR diff, produces structured findings (blocking/non-blocking), renders a verdict (LGTM or REQUEST_CHANGES), and sends `review_feedback` or `review_lgtm` to the author's inbox. Single-pass by default; use `--poll` for in-session round 2 polling.

## Runtimes

- **Claude Code**: Install to `.claude/skills/review-loop-reviewer/SKILL.md`
- **Codex**: Install to `.agents/skills/review-loop-reviewer/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/review-loop-reviewer
cp skills/review-loop-reviewer/claude/SKILL.md .claude/skills/review-loop-reviewer/SKILL.md

# Codex
mkdir -p .agents/skills/review-loop-reviewer
cp skills/review-loop-reviewer/codex/SKILL.md .agents/skills/review-loop-reviewer/SKILL.md
```
