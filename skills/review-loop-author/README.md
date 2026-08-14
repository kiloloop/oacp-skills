# review-loop-author

Run the author side of the review loop — address findings and drive to LGTM.

## Overview

Coordinates an exact-head OACP review thread, routes verified findings, applies authorized fixes, requests bounded re-review rounds, and lands or parks only at an authorized terminal checkpoint.

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
cp -R skills/review-loop-author/codex/. .agents/skills/review-loop-author/
```
