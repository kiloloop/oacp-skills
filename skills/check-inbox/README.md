# check-inbox

Check the project inbox for new agent messages and process them.

## Overview

Single-pass inbox processor. Scans `$OACP_HOME/projects/$PROJECT/agents/$AGENT_NAME/inbox/` for pending messages, processes each one fully (verify, snapshot, act, reply, archive), then exits. Task requests pause for human confirmation unless the receiver's autonomy policy (`always_pause` / `auto_review`) auto-accepts them. Use a runtime heartbeat or watcher for recurring monitoring.

## Prerequisites

- [oacp-cli](https://github.com/kiloloop/oacp) `>=0.5.4` — install with the crypto extra for message signing and intake verification: `pip install 'oacp-cli[crypto]'`
- An OACP workspace initialized with `oacp init <project>`
- The `.oacp` project marker in the repo root (symlink or JSON file pointing to the OACP workspace)
- Peer signing identities pinned before their first message: `oacp trust import <kid>.pub.json --project <project> --agent <agent>`

## Runtimes

- **Claude Code**: Install to `.claude/skills/check-inbox/SKILL.md`
- **Codex**: Install to `.agents/skills/check-inbox/SKILL.md`

## Install

```bash
# Run from the catalog clone. Use a fresh destination for a clean install.
SKILL_SOURCE="$PWD/skills/check-inbox"

# Claude Code: instructions plus every bundled runtime dependency.
CLAUDE_DEST="$PWD/.claude/skills/check-inbox"
mkdir -p "$CLAUDE_DEST"
cp "$SKILL_SOURCE/SKILL.md" "$CLAUDE_DEST/SKILL.md"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CLAUDE_DEST/"
  fi
done

# Codex: common assets first, then the Codex instructions and helpers.
CODEX_DEST="$PWD/.agents/skills/check-inbox"
mkdir -p "$CODEX_DEST"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CODEX_DEST/"
  fi
done
cp -R "$SKILL_SOURCE/codex/." "$CODEX_DEST/"
```

## Usage

```bash
# Claude Code
/check-inbox                        # single-pass scan
/check-inbox --project myproject    # explicit project name
/check-inbox --autonomous           # skip confirmation for informational review-lifecycle messages
/loop 2m /check-inbox               # polling fallback when `oacp watch` is unavailable

# Codex
# Invoke via AGENTS.md task dispatch or direct skill reference
```

For continuous monitoring in Claude Code, run the `oacp watch` loop under the Monitor tool — empty scans cost no model turn. The command and re-arm rules are in [Recurring monitoring](SKILL.md#recurring-monitoring). Codex prefers a heartbeat that runs one project-scoped watch/inbox step per wake.
