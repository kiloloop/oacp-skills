# self-improve

Review and improve the agent's operating system — skills, memory files, and config. Identifies staleness, contradictions, gaps, and bloat, then proposes and applies fixes.

## Overview

Agents accumulate configuration drift over time: skill instructions go stale, memory files contradict each other, config rules become outdated. `/self-improve` runs a structured audit across the agent's knowledge layer and proposes surgical fixes.

It reviews three target categories:

- **Skills** — SKILL.md files that ran during the session (or a specific skill by name)
- **Memory** — hand-maintained project memory; generated runtime memory remains read-only
- **Config** — AGENTS.md or CLAUDE.md plus explicitly relevant settings

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
mkdir -p .claude/skills/self-improve/references
cp skills/self-improve/claude/SKILL.md .claude/skills/self-improve/SKILL.md
cp skills/self-improve/references/*.md .claude/skills/self-improve/references/

# Codex
mkdir -p .agents/skills/self-improve
cp -R skills/self-improve/codex/. .agents/skills/self-improve/
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

1. **Resolve** — classifies authored sources, symlinks, installed artifacts, and owners
2. **Prove** — checks source → discovery → caller → observed behavior
3. **Audit** — captures findings and a before/after acceptance probe
4. **Propose** — requests approval for exact local edits and external effects
5. **Apply** — patches only approved authored sources and reruns the probes
6. **Publish** — commits or pushes only when separately requested
