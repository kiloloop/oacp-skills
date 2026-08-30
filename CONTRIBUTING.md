# Contributing to OACP Skills

## Skill Structure

Each skill lives in `skills/<skill-name>/` with the following layout:

```
skills/<skill-name>/
  skill.yaml          # machine-readable metadata (required)
  README.md           # human-readable docs (required)
  shared/             # common intent, protocol refs, examples
  claude/
    SKILL.md           # Claude Code native instructions
  codex/
    SKILL.md           # Codex native instructions
```

## skill.yaml Schema

Every skill must have a `skill.yaml` with these fields:

```yaml
id: <skill-name>           # must match directory name
name: <Human Name>         # display name
category: coordination     # coordination | development | ops
summary: <one-line>        # what the skill does
license: Apache-2.0
compatible_runtimes:       # which runtimes have SKILL.md files
  - claude-code
  - codex
requires_oacp: ">=0.1.0"  # minimum OACP version
public_status: staging     # staging | public | internal-only
owners:
  - kiloloop
```

## SKILL.md Format

Each runtime-specific `SKILL.md` must have YAML frontmatter:

```yaml
---
name: <skill-name>
description: <one-line description>
---
```

The `name` field should match the slash command users will type (e.g., `check-inbox` maps to `/check-inbox`).

## Scrub Checklist

Before submitting a skill for public promotion:

- [ ] No absolute paths (`/Users/...`) — use `$OACP_HOME`, `$HOME`, or `$PROJECT`
- [ ] No personal names, emails, or proprietary project names
- [ ] No `dangerouslyDisableSandbox` config blobs — describe requirements in prose
- [ ] No cost telemetry, internal PR numbers, or commit SHAs
- [ ] `skill.yaml` present with all required fields
- [ ] SKILL.md frontmatter present and accurate for each runtime
- [ ] Apache-2.0 compatible (no embedded internal IP)

## Workflow

1. Fork or branch from `main`
2. Add/modify skill in `skills/<skill-name>/`
3. Validate: CI runs YAML frontmatter lint + markdownlint automatically on PR
4. Open a PR — one skill per PR for review clarity
5. Reviewer checks scrub checklist above

## Versioning

This collection follows [Semantic Versioning](https://semver.org/), with one
deliberate narrowing of the usual "new feature → MINOR" reading:

| Bump | When |
|------|------|
| **PATCH** (`0.7.0` → `0.7.1`) | Any non-breaking change — fixes, doc corrections, skill updates, **and new skills entering the catalog**. This is the default; most releases are patches. |
| **MINOR** (`0.7.0` → `0.8.0`) | A breaking interface or schema change (e.g. a `skill.yaml` field removed or repurposed), or a raise to the collection's `requires_oacp` ceiling. |
| **MAJOR** (`1.0.0`) | First stable release; thereafter, incompatible changes to the skill packaging contract. |

Adding a skill is an addition, not a new interface — the catalog grows without
changing anything an existing consumer depends on, so it is a PATCH.

**Recorded deviation:** v0.7.0 was cut as a MINOR bump for a skill addition
(`debrief`). It stands as released — no re-cut — and is the one exception on the
books. The next skill-adding release is v0.7.1.

The OACP badge in `README.md` is a **ceiling**: it reads `max(requires_oacp)`
across `skills/*/skill.yaml` and is refreshed at each cut, so installing it
satisfies every skill. Individual skills declare their own floor in `skill.yaml`
and many run on less.
