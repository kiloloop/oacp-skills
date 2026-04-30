# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-04-30

### Added

- `oacp` skill — protocol primer that teaches a runtime how to use the OACP CLI and message protocol: version contract (`>=0.3.0`), workspace orientation, `oacp send` recipe with full type taxonomy, `oacp inbox` vs `oacp watch`, review-loop semantics (Author → Reviewer direct dispatch), and conventions. Includes `shared/INTENT.md` runtime-agnostic protocol primer and runtime-specific `claude/SKILL.md` (symlinked) and `codex/SKILL.md`.
- Top-level README "oacp" entry as the protocol primer that the workflow skills build on.

### Changed

- OACP version floor bumped from `>=0.1.0` to `>=0.3.0` for the bundle (driven by the new `oacp` skill's contract). Other skills retain their individual `requires_oacp` declarations.
- "How These Skills Work Together" section reframed to position `oacp` as the foundation for the workflow skills.

## [0.2.0] - 2026-03-22

### Added

- `doctor` skill — environment and workspace diagnostics with auto-fix
- [skills.sh](https://skills.sh) compatibility — top-level `SKILL.md` files for standard discovery, `claude/SKILL.md` symlinks to top level
- Promote workflow for staging → public sync

### Changed

- README rewritten with per-skill sections, usage examples, and install guide
- Installation options reordered: skills.sh (Claude Code) → copy → symlink (devs only)
- Removed `runtime` frontmatter field from skill SKILL.md files
- Cleaned stale AHS references before public launch

## [0.1.0] - 2026-03-16

### Added

- `check-inbox` skill — scan OACP inbox for agent messages and auto-act on them
- `review-loop-reviewer` skill — review PR diffs, produce structured findings, emit verdict
- `review-loop-author` skill — address review findings, push fixes, drive to LGTM
- `self-improve` skill — audit skills, memory, and config for drift, gaps, and contradictions
- Cross-runtime support (Claude Code + Codex CLI) for all skills
- Skill template for contributing new skills
- CI validation workflow (skill.yaml schema, SKILL.md frontmatter, absolute path check)

[0.3.0]: https://github.com/kiloloop/oacp-skills/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/kiloloop/oacp-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kiloloop/oacp-skills/releases/tag/v0.1.0
