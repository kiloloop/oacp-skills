# check-inbox

Check the project inbox for new agent messages and process them.

## Overview

Single-pass inbox processor. Scans `$OACP_HOME/projects/$PROJECT/agents/$AGENT_NAME/inbox/` for pending messages, processes each one fully (verify, snapshot, act, reply, archive), then exits. Use a runtime heartbeat or watcher for recurring monitoring.

## Prerequisites

- [oacp-cli](https://github.com/kiloloop/oacp) `>=0.4.3` — install with the crypto extra for message signing and intake verification: `pip install 'oacp-cli[crypto]'`
- An OACP workspace initialized with `oacp init <project>`
- The `.oacp` project marker in the repo root (symlink or JSON file pointing to the OACP workspace)
- Peer signing identities pinned before their first message: `oacp trust import <kid>.pub.json --project <project> --agent <agent>`

## Runtimes

- **Claude Code**: Install to `.claude/skills/check-inbox/SKILL.md`
- **Codex**: Install to `.agents/skills/check-inbox/SKILL.md`

## Install

```bash
# Claude Code
mkdir -p .claude/skills/check-inbox/references
cp skills/check-inbox/claude/SKILL.md .claude/skills/check-inbox/SKILL.md
cp skills/check-inbox/references/autonomy.md .claude/skills/check-inbox/references/

# Codex
mkdir -p .agents/skills/check-inbox
cp -R skills/check-inbox/codex/. .agents/skills/check-inbox/
```

## Usage

```bash
# Claude Code
/check-inbox                        # single-pass scan
/check-inbox --project myproject    # explicit project name
/loop 2m /check-inbox               # continuous monitoring (every 2 min)

# Codex
# Invoke via AGENTS.md task dispatch or direct skill reference
```
