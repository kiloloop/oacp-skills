# review-loop-author

Run the author side of the review loop — address findings and drive to LGTM.

## Overview

Picks up review findings from inbox or PR comments, applies fixes, pushes updates, and sends a `review_addressed` message back to the reviewer. Single-pass by default; use `--poll` for in-session round 2 polling.

## Runtimes

- **Claude Code**: Install to `.claude/skills/review-loop-author/SKILL.md`
- **Codex**: Install to `.agents/skills/review-loop-author/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/review-loop-author
cp skills/review-loop-author/claude/SKILL.md .claude/skills/review-loop-author/SKILL.md

# Codex
mkdir -p .agents/skills/review-loop-author
cp skills/review-loop-author/codex/SKILL.md .agents/skills/review-loop-author/SKILL.md
```
