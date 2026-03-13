# check-inbox

Check the project inbox for new agent messages and process them.

## Overview

Single-pass inbox processor. Scans `$OACP_HOME/projects/$PROJECT/agents/$AGENT_NAME/inbox/` for pending messages, processes each one fully (read, act, reply, delete), then exits. Use with a loop for continuous monitoring.

## Prerequisites

- An [OACP](https://github.com/kiloloop/oacp) workspace initialized with `oacp init <project>`
- The `.oacp` project marker in the repo root (symlink or JSON file pointing to the OACP workspace)

## Runtimes

- **Claude Code**: Install to `.claude/skills/check-inbox/SKILL.md`
- **Codex**: Install to `.agents/skills/check-inbox/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/check-inbox
cp skills/check-inbox/claude/SKILL.md .claude/skills/check-inbox/SKILL.md

# Codex
mkdir -p .agents/skills/check-inbox
cp skills/check-inbox/codex/SKILL.md .agents/skills/check-inbox/SKILL.md
```

## Usage

```bash
# Claude Code
/check-inbox                        # single-pass scan
/check-inbox --project myproject    # explicit project name
/loop 2m /check-inbox               # continuous monitoring (every 2 min)

# Codex
# Invoke via AGENTS.md task dispatch or direct skill reference
```
