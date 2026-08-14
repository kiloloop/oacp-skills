# review-loop-reviewer

Run the reviewer side of the review loop — review PR diffs, produce findings, and evaluate quality gate.

## Overview

Runs one stateless exact-head review round, enforces the findings contract, performs only declared GitHub effects, sends one terminal `review_feedback` or `review_lgtm`, and exits.

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
cp -R skills/review-loop-reviewer/codex/. .agents/skills/review-loop-reviewer/
```
