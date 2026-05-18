# org-memory-synthesis

Synthesize org-memory — fold new events into `recent.md`, promote cross-repo patterns to `decisions.md` and `rules.md`, and audit the curated layer for staleness, conflicts, and drift.

## Overview

Org-memory (`$OACP_HOME/org-memory/`) is the cross-project SSOT that the session-init hook auto-loads into every session. It drifts when events accumulate unfolded and when topical files (`decisions.md`, `rules.md`) aren't curated. This skill does the full 3-file synthesis pass plus a six-check audit, so the curated layer stays trustworthy.

See [`shared/INTENT.md`](shared/INTENT.md) for the runtime-agnostic contract, acceptance criteria, and the full workflow.

## Prerequisites

- An [OACP](https://github.com/kiloloop/oacp) workspace with org-memory initialized (`oacp org-memory init`).
- `OACP_HOME` env var pointing at the workspace (defaults to `$HOME/oacp` per the OACP CLI fallback).
- `gh` CLI — used by audit Step 7C to verify GitHub issue status references. Optional but recommended.

## Runtimes

- **Claude Code**: install to `.claude/skills/org-memory-synthesis/SKILL.md`
- **Codex**: install to `.agents/skills/org-memory-synthesis/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/org-memory-synthesis
cp skills/org-memory-synthesis/SKILL.md .claude/skills/org-memory-synthesis/SKILL.md

# Codex
mkdir -p .agents/skills/org-memory-synthesis
cp skills/org-memory-synthesis/codex/SKILL.md .agents/skills/org-memory-synthesis/SKILL.md
```

## Usage

```text
# Claude Code
/org-memory-synthesis          # full synthesis + audit pass

# Codex
/org-memory-synthesis          # full synthesis + audit pass
```

Invoke any time the user asks whether org-memory is current, asks to fold events, or asks for an audit. A wrap-up / housekeeping skill may also hand off to it.

## What it produces

- Edits in place: `$OACP_HOME/org-memory/recent.md`, `decisions.md`, `rules.md`
- Updated `recent.md` header markers (`Last event folded in:`, `Last curated:`)
- A findings summary covering folded events, promotions, audit findings, and any unresolved items deferred to the user
- A suggested commit message — **the skill does not auto-commit**

## How it works

1. **Scope the work** — Step 1's inline shell lists events newer than the marker line in `recent.md`; empty output means jump to the audit-only pass.
2. **Batch-read new event bodies** — one read across all new events, skipping YAML frontmatter.
3. **Categorize** — `type:` frontmatter routes events into `recent.md` (default) or curated files (cross-repo promotions).
4. **Propose 3-file diff** — `recent.md`, `decisions.md`, `rules.md` sections with one-line rationale per promotion.
5. **Apply edits** — preserve chronological order in `decisions.md` (append at the bottom).
6. **Update markers** — never drop the marker; it's the cheapest performance optimization in this flow.
7. **Audit pass** — six checks: cross-file consistency, supersession asymmetry, stale-status (with `gh issue view`), chronological order (mechanical `sort -c` check), category drift, migration leftovers.
8. **Surface findings, apply, ask** — uncontroversial fixes applied directly; judgment calls deferred to the user.
9. **Suggest commit** — ready-to-paste message; user decides timing.

See [`shared/INTENT.md`](shared/INTENT.md) for the full contract, [`SKILL.md`](SKILL.md) for the canonical Claude Code runtime instructions (also surfaced via `claude/SKILL.md` symlink), and [`codex/SKILL.md`](codex/SKILL.md) for the Codex runtime instructions.

## Notes

- Audit Step 7D **must** use the mechanical `sort -c` check on `## YYYY-MM-DD` headers — self-reported "chronological order looks fine" misses real false-cleans. This is the canonical version; ship it verbatim.
- Superseded `decisions.md` entries are annotated (`**Superseded by …**`), never deleted. History is load-bearing.
- Skill-specific rules stay in `recent.md` Standing Rules only — promoting them adds `rules.md` noise without cross-repo benefit.
- Skill never auto-commits and never edits sibling memory trees.
