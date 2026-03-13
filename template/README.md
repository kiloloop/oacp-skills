# <skill-name>

<one-line description>

## Overview

<Explain what the skill does, when to use it, and how it fits into OACP workflows.>

## Runtimes

- **Claude Code**: Install to `.claude/skills/<skill-name>/SKILL.md`
- **Codex**: Install to `.agents/skills/<skill-name>/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/<skill-name>
cp skills/<skill-name>/claude/SKILL.md .claude/skills/<skill-name>/SKILL.md

# Codex
mkdir -p .agents/skills/<skill-name>
cp skills/<skill-name>/codex/SKILL.md .agents/skills/<skill-name>/SKILL.md
```
