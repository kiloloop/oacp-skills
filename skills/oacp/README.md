# oacp

Use the OACP CLI and protocol to coordinate multi-agent work.

## Overview

Teaches a runtime how to operate within the [Open Agent Coordination Protocol](https://github.com/kiloloop/oacp) — verify the environment, send protocol-compliant messages, watch inboxes for incoming work, and follow review-loop semantics. Pair with the companion skills (`check-inbox`, `doctor`, `review-loop-*`) for a complete agent coordination loop.

## Prerequisites

- [OACP CLI](https://github.com/kiloloop/oacp) >= 0.3.0 — install with `pip install 'oacp-cli>=0.3.0'`
- An OACP workspace initialized with `oacp init <project>`
- A `.oacp` project marker in the repo root (created by `oacp setup <runtime> --project <project>`)

## Runtimes

- **Claude Code**: install to `.claude/skills/oacp/SKILL.md`
- **Codex**: install to `.agents/skills/oacp/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/oacp
cp skills/oacp/SKILL.md .claude/skills/oacp/SKILL.md

# Codex
mkdir -p .agents/skills/oacp
cp skills/oacp/codex/SKILL.md .agents/skills/oacp/SKILL.md
```

Or via skills.sh (Claude Code only):

```bash
npx skills add kiloloop/oacp-skills -s oacp
```

## Usage

The skill auto-triggers based on its description whenever you work with OACP — running `oacp` commands, sending inbox messages, dispatching reviews, or referencing `.oacp` workspace markers. You can also invoke it explicitly:

```bash
# Claude Code
/oacp
```

## What it teaches

- The version contract (`oacp --version`) and why to verify it first
- Workspace layout (`$OACP_HOME`, `.oacp` marker, agent inboxes)
- The full `oacp send` recipe and which `--type` to pick
- `oacp inbox` vs `oacp watch` — one-shot vs event-driven
- Review-loop dispatch (Author → Reviewer direct, not coordinator-mediated)
- `oacp doctor`, `oacp validate`, `oacp write-event` — supporting commands

See `SKILL.md` for the Claude Code-native instructions and `shared/INTENT.md` for runtime-agnostic protocol concepts.
