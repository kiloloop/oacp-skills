# self-improve

Review and improve the agent's operating system — skills, memory files, and config. Identifies staleness, contradictions, gaps, and bloat, then proposes and applies fixes.

## Overview

Agents accumulate configuration drift over time: skill instructions go stale, memory files contradict each other, config rules become outdated. `/self-improve` runs a structured audit across the agent's knowledge layer and proposes surgical fixes.

It reviews three target categories:

- **Skills** — SKILL.md files that ran during the session (or a specific skill by name)
- **Memory** — project memory files across all configured memory locations
- **Config** — agent config files (e.g., CLAUDE.md) and settings

Findings are tagged by severity (`[FIX]`, `[STALE]`, `[GAP]`, `[CONFLICT]`, `[BLOAT]`, `[STRUCTURAL]`) and presented for approval before any changes are applied.

## Prerequisites

- OACP workspace (`.oacp` project marker in repo root)
- Project memory directory at `$OACP_HOME/projects/<project>/memory/`
- Git-tracked skills and config files

## Runtimes

- **Claude Code**: Install to `.claude/skills/self-improve/SKILL.md`
- **Codex**: Install to `.agents/skills/self-improve/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/self-improve
cp skills/self-improve/claude/SKILL.md .claude/skills/self-improve/SKILL.md

# Codex
mkdir -p .agents/skills/self-improve
cp skills/self-improve/codex/SKILL.md .agents/skills/self-improve/SKILL.md
```

## Usage

```
/self-improve                  # Full review (skills + memory + config)
/self-improve skills           # Review only skills that ran this session
/self-improve memory           # Review memory files only
/self-improve config           # Codex: review config files only
/self-improve claude-md        # Claude Code and Codex alias for config review
/self-improve <skill-name>     # Review a single specific skill
```

## How it works

1. **Discover** — builds an inventory of files to review based on scope
2. **Analyze** — checks each file for staleness, contradictions, gaps, bloat, and structural issues
3. **Report** — presents findings grouped by category with severity tags
4. **Propose** — suggests specific edits for each finding
5. **Apply** — makes approved changes using the Edit tool
6. **Commit** — groups changes by repo and commits separately
