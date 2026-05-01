# wrap-up

End-of-session cleanup, optional debrief, self-improve, commit, and push in one command. Run `/wrap-up` once at the end of a working session to leave a clean tree, durable memory, and an up-to-date remote.

## Prerequisites

- A git-tracked repo with optional `.oacp` project marker in the root
- `/self-improve` skill installed (hard dependency — see "Dependencies" below)

## Runtimes

- **Claude Code**: install to `.claude/skills/wrap-up/SKILL.md`
- **Codex**: install to `.agents/skills/wrap-up/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/wrap-up
cp skills/wrap-up/claude/SKILL.md .claude/skills/wrap-up/SKILL.md

# Codex
mkdir -p .agents/skills/wrap-up
cp skills/wrap-up/codex/SKILL.md .agents/skills/wrap-up/SKILL.md
```

## Usage

```text
/wrap-up           # full sequence: cleanup, debrief, self-improve, commit, push
/wrap-up --dry-run # cleanup + debrief + self-improve only; skip commit, push, memory sync
```

## Dependencies

**Hard:**

- `/self-improve` skill (Step 4) — install from `skills/self-improve/` in this same repo. The skill fails with an install hint if `/self-improve` is missing.

**Optional:**

- `oacp` CLI ≥ 0.3.0 — needed for Step 3 (`oacp write-event`) and Step 6 (`oacp memory push`). Without it, those steps are skipped.
- `/debrief` skill — preferred Step 2 target when installed.
- Cloned `kiloloop/cortex` (set `$CORTEX_HOME`) — second-tier Step 2 target. Public repo: <https://github.com/kiloloop/cortex>.

## Customization

Environment variables consulted by the skill:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OACP_HOME` | Root for inbox, org-memory, and memory-sync paths | `$HOME/oacp` |
| `CORTEX_HOME` | Clone of `kiloloop/cortex` for Step 2 fallback | unset |

## How it works

1. **Cleanup** — remove just-merged PR worktrees; delete merged local branches (safe `-d` only); prune stale worktrees; report processed inbox messages.
2. **Debrief (optional)** — `/debrief` skill, else `$CORTEX_HOME`, else `./.oacp/debriefs/YYYY-MM-DD.md`. Non-fatal.
3. **Org-memory events** — `oacp write-event` for outcomes other agents care about.
4. **Self-improve** — full review, pause for approval, apply approved changes.
5. **Commit current repo** — explicit staging, secrets excluded.
6. **OACP memory sync** — `oacp memory push` if the marker is present.
7. **Pull-rebase + push** — current branch.
8. **Summary** — structured status block.

See [`shared/INTENT.md`](shared/INTENT.md) for the runtime-agnostic contract and acceptance criteria, and [`claude/SKILL.md`](claude/SKILL.md) for the Claude Code runtime instructions.
