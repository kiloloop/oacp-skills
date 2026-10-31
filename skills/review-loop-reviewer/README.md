# review-loop-reviewer

Run the reviewer side of the review loop — review PR diffs, produce findings, and evaluate quality gate.

## Overview

Runs one stateless exact-head review round, enforces the findings contract, performs only declared GitHub effects, sends one terminal `review_feedback` or `review_lgtm`, and exits.

## Prerequisites

- OACP CLI `>=0.5.3` with signing support (`oacp-cli[crypto]`), an initialized
  project and registered/trusted author and reviewer identities.
- Python 3.10+ with PyYAML, Git, and GitHub CLI authenticated under the consuming
  repository's policy.
- The `check-inbox` skill for verified intake, admission and terminal archival.

## Runtimes

- **Claude Code**: Install to `.claude/skills/review-loop-reviewer/SKILL.md`
- **Codex**: Install to `.agents/skills/review-loop-reviewer/SKILL.md`

## Install

```bash
# Run from the catalog clone. Use a fresh destination for a clean install.
SKILL_SOURCE="$PWD/skills/review-loop-reviewer"

# Claude Code: instructions plus every bundled runtime dependency.
CLAUDE_DEST="$PWD/.claude/skills/review-loop-reviewer"
mkdir -p "$CLAUDE_DEST"
cp "$SKILL_SOURCE/SKILL.md" "$CLAUDE_DEST/SKILL.md"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CLAUDE_DEST/"
  fi
done

# Codex: common assets first, then the Codex instructions and helpers.
CODEX_DEST="$PWD/.agents/skills/review-loop-reviewer"
mkdir -p "$CODEX_DEST"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CODEX_DEST/"
  fi
done
cp -R "$SKILL_SOURCE/codex/." "$CODEX_DEST/"
```
