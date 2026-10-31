# self-improve

Review and improve the agent's operating system — skills, memory files, and config. Identifies staleness, contradictions, gaps, and bloat, then applies fixes within the approved scope.

## Overview

Agents accumulate configuration drift over time: skill instructions go stale, memory files contradict each other, config rules become outdated. `/self-improve` runs a structured audit across the agent's knowledge layer and proposes surgical fixes.

It reviews these target categories:

- **Skills** — SKILL.md files that ran during the session (or a specific skill by name)
- **Memory** — hand-maintained project memory; generated runtime memory remains read-only
- **Config** — AGENTS.md or CLAUDE.md plus explicitly relevant settings
- **Friction** (Claude Code) — patterns the user had to correct mid-session

Findings are tagged by severity (`[FIX]`, `[STALE]`, `[GAP]`, `[CONFLICT]`, `[BLOAT]`, `[STRUCTURAL]`) and presented with concrete edits and acceptance probes. Existing matching approval
is reused; expanded scope needs a new decision.

## Prerequisites

- OACP workspace and authored project memory when auditing OACP-specific state;
  standalone skills/config audits do not require a memory workspace.
- Git-tracked skills and config files

## Runtimes

- **Claude Code**: Install to `.claude/skills/self-improve/SKILL.md`
- **Codex**: Install to `.agents/skills/self-improve/SKILL.md`

## Install

```bash
# Run from the catalog clone. Use a fresh destination for a clean install.
SKILL_SOURCE="$PWD/skills/self-improve"

# Claude Code: instructions plus every bundled runtime dependency.
CLAUDE_DEST="$PWD/.claude/skills/self-improve"
mkdir -p "$CLAUDE_DEST"
cp "$SKILL_SOURCE/SKILL.md" "$CLAUDE_DEST/SKILL.md"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CLAUDE_DEST/"
  fi
done

# Codex: common assets first, then the Codex instructions and helpers.
CODEX_DEST="$PWD/.agents/skills/self-improve"
mkdir -p "$CODEX_DEST"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CODEX_DEST/"
  fi
done
cp -R "$SKILL_SOURCE/codex/." "$CODEX_DEST/"
```

## Usage

```
/self-improve                  # Full review (skills + memory + config; Claude Code adds friction)
/self-improve skills           # Review only skills that ran this session
/self-improve memory           # Review memory files only
/self-improve config           # Codex: review config files only
/self-improve claude-md        # Claude Code and Codex alias for config review
/self-improve friction         # Claude Code: review session-friction patterns only
/self-improve <skill-name>     # Review a single specific skill
/self-improve --dry-run        # Combines with any form: propose only, apply nothing
```

## How it works

1. **Resolve** — classifies authored sources, symlinks, installed artifacts, and owners
2. **Prove** — checks source → discovery → caller → observed behavior
3. **Audit** — captures findings and a before/after acceptance probe
4. **Propose** — requests approval for exact local edits and external effects
5. **Apply** — patches only approved authored sources and reruns the probes
6. **Publish** — commits or pushes only within explicit publication authority
