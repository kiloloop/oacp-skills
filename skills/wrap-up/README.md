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
# Run from the catalog clone. Use a fresh destination for a clean install.
SKILL_SOURCE="$PWD/skills/wrap-up"

# Claude Code: instructions plus every bundled runtime dependency.
CLAUDE_DEST="$PWD/.claude/skills/wrap-up"
mkdir -p "$CLAUDE_DEST"
cp "$SKILL_SOURCE/SKILL.md" "$CLAUDE_DEST/SKILL.md"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CLAUDE_DEST/"
  fi
done

# Codex: common assets first, then the Codex instructions and helpers.
CODEX_DEST="$PWD/.agents/skills/wrap-up"
mkdir -p "$CODEX_DEST"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CODEX_DEST/"
  fi
done
cp -R "$SKILL_SOURCE/codex/." "$CODEX_DEST/"
```

## Usage

```text
/wrap-up           # full sequence: cleanup, debrief, org-memory events, self-improve, commit, memory sync, push
$wrap-up --dry-run # Codex: read-only previews and proposals; no writes
/wrap-up --dry-run # Claude: local stages may run; skip commit/push
```

## Dependencies

**Hard:**

- `/self-improve` skill (Step 4) — install from `skills/self-improve/` in this same repo. If `/self-improve` is missing, the skill reports the gap rather than improvising a fallback.
- `oacp` CLI ≥ 0.5.3 when reporting an OACP inbox; memory operations use the separate `agent-memory-cli` package.

**Optional:**

- `/debrief` skill — Step 2 writer; report a missing installation without inventing a fallback store.
- `agent-memory-cli` ≥ 0.1.1 for `agent-memory event write`, layout checks and configured memory publication.

## Customization

Environment variables consulted by the skill:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OACP_HOME` | OACP inbox root; compatibility memory-home override | `$HOME/oacp` for the inbox |
| `AGENT_MEMORY_HOME` | Memory-home override, ahead of `OACP_HOME` | Nearest binding/marker, then `$HOME/agent-memory` |

Codex's audit helper also accepts explicit `--memory-home`, ahead of those
environment variables. Otherwise it reads the nearest valid
`.agent-memory.json` or canonical workspace marker; an invalid binding is
reported without silently choosing another store. Memory and inbox homes are
independent.

The Codex cleanup snapshot requires recorded `--owned-branch` and
`--owned-worktree` evidence for deletion suggestions; peer namespaces can be
reserved with `--keep-branch-prefix`. Unknown status or ownership, divergent
heads, and fork PRs with the same branch name remain keep outcomes.

## How it works

1. **Cleanup** — preview first; remove only verified local branches/worktrees; report pending and held inbox messages.
2. **Debrief** — invoke `/debrief`; failure is visible but non-fatal.
3. **Org-memory events** — `agent-memory event write --home <resolved-home>` for outcomes other agents care about.
4. **Self-improve** — session-delta audit, reuse existing scope approval, apply approved changes.
5. **Commit bounded repos** — explicit staging, unrelated and sensitive state excluded.
6. **OACP memory sync** — `agent-memory push --home <resolved-home> --agent <registered-agent>` if the marker is present.
7. **Pull-rebase with autostash + push** — each authorized repository independently.
8. **Summary** — structured status block.

See [`shared/INTENT.md`](shared/INTENT.md) for the runtime-agnostic contract, [`claude/SKILL.md`](claude/SKILL.md) for Claude Code, and [`codex/SKILL.md`](codex/SKILL.md) for Codex.
