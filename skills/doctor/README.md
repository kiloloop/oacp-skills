# doctor

Run environment and workspace diagnostics, auto-fix what it can, and report blockers.

## Overview

Wraps `oacp doctor` for agent self-diagnostics. Runs five check categories
(environment, workspace, inbox health, schemas, agent status), parses the
structured JSON output, uses the native `--fix` path for safe fixes, and
reports remaining warnings and errors with fix hints.

Use at session start to verify the OACP environment is healthy, or on-demand
when something seems broken.

## Prerequisites

- [OACP](https://github.com/kiloloop/oacp) >= 0.1.2 — install via `pip install oacp-cli`
- An OACP workspace initialized with `oacp init <project>` (for workspace checks)

## Runtimes

- **Claude Code**: Install to `.claude/skills/doctor/SKILL.md`
- **Codex**: Install to `.agents/skills/doctor/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/doctor
cp skills/doctor/claude/SKILL.md .claude/skills/doctor/SKILL.md

# Codex
mkdir -p .agents/skills/doctor
cp skills/doctor/codex/SKILL.md .agents/skills/doctor/SKILL.md
```

## Usage

```bash
# Claude Code
/doctor                        # auto-detect project, full diagnostics + auto-fix
/doctor --project myproject    # explicit project name

# Codex
# Invoke via AGENTS.md task dispatch or direct skill reference

# CLI directly
oacp doctor --project myproject --fix        # auto-fix safe issues
oacp doctor --project myproject --fix --json # structured output with fixes
```

## What it checks

| Category | Checks |
| -------- | ------ |
| Environment | Required tools plus optional `ruff`, `shellcheck`, `pyyaml` |
| Workspace | workspace.json validity, agents/ directory |
| Inbox Health | Per-agent inbox dirs, message count and staleness |
| Schemas | YAML validity of packets/ and status.yaml field validation |
| Agent Status | status.yaml presence and timestamp freshness |

## What it auto-fixes

When run with `--fix` (skills pass this automatically):

- Missing inbox directories (creates them)
- Missing status.yaml (creates from template)
- Stale status.yaml timestamps (updates `updated_at` to current UTC)

`skills/doctor/shared/INTENT.md` remains in the repo as reference material for
skill authors, but it does not need to be installed for Codex runtime use.
