# review-loop-author

Run the author side of the review loop — address findings and drive to LGTM.

## Overview

Coordinates an exact-head OACP review thread, routes verified findings, applies authorized fixes, requests bounded re-review rounds, and lands or parks only at an authorized terminal checkpoint. On Claude Code each invocation is single-pass: it sends the round's messages and exits, and `/check-inbox` re-invokes it when the reviewer's reply lands.

## Prerequisites

- OACP CLI `>=0.5.3` with signing support (`oacp-cli[crypto]`), an initialized
  project and registered/trusted author and reviewer identities.
- Python 3 with PyYAML, Git, and GitHub CLI authenticated under the consuming
  repository's policy.
- The `check-inbox` skill for verified intake, admission and terminal archival.

A passing OACP verdict is terminal even when a required formal GitHub approval
was not in the accepted scope: `withheld_side_effects` records it, and the
author arranges a separately authorized eligible approver before landing.
An accepted formal approval whose submission/readback fails holds the
composite approval-and-LGTM path until corrected.

## Runtimes

- **Claude Code**: Install to `.claude/skills/review-loop-author/SKILL.md`
- **Codex**: Install to `.agents/skills/review-loop-author/SKILL.md`

## Install

```bash
# Run from the catalog clone. Use a fresh destination for a clean install.
SKILL_SOURCE="$PWD/skills/review-loop-author"

# Claude Code: instructions plus every bundled runtime dependency.
CLAUDE_DEST="$PWD/.claude/skills/review-loop-author"
mkdir -p "$CLAUDE_DEST"
cp "$SKILL_SOURCE/SKILL.md" "$CLAUDE_DEST/SKILL.md"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CLAUDE_DEST/"
  fi
done

# Codex: common assets first, then the Codex instructions and helpers.
CODEX_DEST="$PWD/.agents/skills/review-loop-author"
mkdir -p "$CODEX_DEST"
for resource in scripts references shared agents; do
  if [ -d "$SKILL_SOURCE/$resource" ]; then
    cp -R "$SKILL_SOURCE/$resource" "$CODEX_DEST/"
  fi
done
cp -R "$SKILL_SOURCE/codex/." "$CODEX_DEST/"
```
