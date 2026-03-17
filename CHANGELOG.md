# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-03-16

### Added

- `check-inbox` skill — scan OACP inbox for agent messages and auto-act on them
- `review-loop-reviewer` skill — review PR diffs, produce structured findings, emit verdict
- `review-loop-author` skill — address review findings, push fixes, drive to LGTM
- `self-improve` skill — audit skills, memory, and config for drift, gaps, and contradictions
- Cross-runtime support (Claude Code + Codex CLI) for all skills
- Skill template for contributing new skills
- CI validation workflow (skill.yaml schema, SKILL.md frontmatter, absolute path check)

[Unreleased]: https://github.com/kiloloop/oacp-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kiloloop/oacp-skills/releases/tag/v0.1.0
