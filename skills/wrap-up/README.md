# wrap-up

End-of-session cleanup, debrief, significant org-memory events, delta-first self-improve, and bounded publication in one command.

## Prerequisites

- A git-tracked repo with optional `.oacp` project marker in the root
- `/self-improve` skill installed (hard dependency — see "Dependencies" below)

## Runtimes

- **Claude Code**: install to `.claude/skills/wrap-up/SKILL.md`
- **Codex**: install to `.agents/skills/wrap-up/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/wrap-up/scripts
cp skills/wrap-up/claude/SKILL.md .claude/skills/wrap-up/SKILL.md
cp skills/wrap-up/scripts/cleanup_branches.sh .claude/skills/wrap-up/scripts/

# Codex
mkdir -p .agents/skills/wrap-up/scripts
cp -R skills/wrap-up/codex/. .agents/skills/wrap-up/
cp skills/wrap-up/scripts/cleanup_branches.sh .agents/skills/wrap-up/scripts/
```

## Usage

```text
/wrap-up           # full sequence: cleanup, debrief, self-improve, commit, push
/wrap-up --dry-run # cleanup + debrief + self-improve only; skip commit, push, memory sync
```

## Dependencies

**Hard:**

- `/self-improve` skill (Step 4) — install from `skills/self-improve/` in this same repo. The skill fails with an install hint if `/self-improve` is missing.
- `oacp` CLI ≥ 0.4.2 — required for mode-aware inbox reporting, event writing, and memory publication.

**Optional:**

- `/debrief` skill — preferred Step 2 target when installed.

## Customization

Environment variables consulted by the skill:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OACP_HOME` | Root for inbox, org-memory, and memory-sync paths | `$HOME/oacp` |

## How it works

1. **Cleanup** — preview first; remove only verified local branches/worktrees; report pending and held inbox messages.
2. **Debrief** — invoke `/debrief`; failure is visible but non-fatal.
3. **Org-memory events** — `oacp write-event` for outcomes other agents care about.
4. **Self-improve** — session-delta audit, pause for approval, apply approved changes.
5. **Commit bounded repos** — explicit staging, unrelated and sensitive state excluded.
6. **OACP memory sync** — `oacp memory push` if the marker is present.
7. **Pull-rebase with autostash + push** — each authorized repository independently.
8. **Summary** — structured status block.

See [`shared/INTENT.md`](shared/INTENT.md) for the runtime-agnostic contract, [`claude/SKILL.md`](claude/SKILL.md) for Claude Code, and [`codex/SKILL.md`](codex/SKILL.md) for Codex.
