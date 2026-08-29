# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-08-28

### Added

- `debrief` — new skill publishing a session summary to the org-memory debrief store as one immutable, hash-verified record per session.
- `debrief` — Claude and Codex wrappers over a shared writer that publishes failure-atomically and republishes identical content idempotently.

### Changed

- `validate` workflow — `public_status` is checked against the documented vocabulary (`staging | public | internal-only`) instead of presence alone.

## [0.6.0] - 2026-08-14

### Changed

- All skills (Claude Code, Codex, and shared surfaces) — ported to the OACP 0.4.x protocol line. `requires_oacp` floors are `>=0.4.0` minimum, `>=0.4.2` where signing or held-message reporting is required, and `>=0.4.3` for intake/review-loop continuation semantics; install lines copy required runtime packages and use the `oacp-cli[crypto]` extra where signing is in scope.
- `check-inbox` — verify-first intake, immutable accepted snapshots, current-schema validation, enforce-posture `dead_letter/` disposition through the canonical receive boundary, stable watch cursors with one epoch replay, terminal no-clobber archival, and a `follow_up` handling row. The 0.4.3 autonomy adapters preserve evaluator-owned completion state and thread-scoped continuation grants; enforcement envelopes remain adapter-dependent rather than a cross-runtime assumption.
- `oacp` — new "Message signing & trust" section (`oacp key gen`, `oacp trust import|list|sign-policy`, `oacp send --sign`, `oacp verify --attach-audit`), watch cursor flags, signing lifecycle in `shared/INTENT.md` (auth trailer field + Verify lifecycle step), continuation-grant note in the review-loop section, and an unverified-message failure mode.
- `doctor` — documents the 0.4.x check inventory: agent-profile completeness, Autonomy category (config validation + signed-policy verification), Trust category (catalog-vs-pins drift, pin completeness, enforce-readiness), and the `--memory` advisory checks; trust-gap and policy-signature fix recommendations.
- `review-loop-author` / `review-loop-reviewer` — verified intake for review messages, head binding via record-and-resolve (`declared_head` is advisory sender context; the reviewer binds verdicts to the live `rev-parse` head), `validated_head` + structured `nits` in LGTM/feedback reply bodies, author-side stale-head guard before merge, and declared/granted side-effect bounds on GitHub actions (v0.4.3 continuation grants).
- `wrap-up` — inbox reporting distinguishes held-unverified messages; cleanup begins with read-only previews, preserves persistent/peer/dirty worktrees and irreplaceable ignored artifacts, and uses exact merged-head identity before squash-branch force deletion. Publication is bounded, delta-first, and uses `pull --rebase --autostash`.
- `self-improve` — Codex now classifies authored, installed, cross-runtime, and generated state; proves the source-to-runtime chain; captures before/after probes; treats generated Codex memory as read-only; and uses explicit lock ownership across multi-call OACP memory edits.
- `check-inbox` / `self-improve` / `wrap-up` — install blocks now copy `references/` and `scripts/` alongside SKILL.md so in-skill links resolve after install.
- Processed-message lifecycle across `oacp`, `check-inbox`, and both `review-loop` skills now follows the protocol's terminal archival: fully-processed messages move atomically (no-clobber, byte-preserving, original filename) to `inbox/archive/` instead of being deleted, so receiver-side signed evidence survives. The archival block is a fail-closed guard chain — digest drift against the accepted snapshot, destination collision, and a missing or symlinked `archive/` each stop before moving and retain the source; move failures and post-move identity checks (source pathname absent even as a symlink, archived copy a regular file with the accepted digest) are reported as errors, never as success (`archive/` is provisioned by workspace init/migration, never created during message processing; the author skill defines the helper during setup so the LGTM-first path has it before any routing). Intake verification runs before any message field is parsed and fails closed on every non-verified outcome under `verify_mode: enforce`.
- Reviewer dispatch authorization tightened to the v0.4.3 contract: every `review_request` round requires a current human confirmation unless the canonical gate verdict is `review_continuation_accepted`; `--autonomous` no longer confers reviewer-dispatch authority and implied same-PR re-authorization is removed. Author-side review messages establish a schema-valid explicit `conversation_id` (`conv-<YYYYMMDD>-<agent>-<seq>`) at round 1 and carry it unchanged through the loop for continuation-grant matching, thread via `--in-reply-to`, and declare `repo` + canonical `round` for fail-closed grant matching; the reviewer re-checks the live PR head immediately before terminal sends and after GitHub actions.
- Codex review-loop packages now include their runtime metadata, references, tested helpers, explicit conversation propagation, stateless reviewer termination, declared GitHub review effects, and an author terminal gate that requires any mandated formal approval at the validated head in addition to OACP LGTM and green checks.
- `org-memory-synthesis` (Codex) now inserts new dated decisions at the top and mechanically verifies descending newest-first order with `sort -rc`.
- `wrap-up` `scripts/cleanup_branches.sh` deletes a squash-merged branch only when its local tip exactly equals the merged PR's head SHA, preserving unpublished post-merge commits; the reviewer retains the `review_request` until the terminal verdict is delivered.
- Top-level README — OACP badge and prerequisites raised to `>=0.4.2`, skill descriptions refreshed for signing/trust/grants; `template/` scaffold floor raised to `>=0.4.0`.

## [0.5.2] - 2026-05-19

### Changed

- `review-loop-author` skill (Claude Code runtime) — refreshed SKILL.md content. Hybrid split clarified as leader-handles-Bash-I/O + fix-only subagent (works around CC sandbox-in-Task breakage). Adds a mergeable precondition check; `task_id` review-state updates (`review_round`, `review_status`, `findings_packets`); `--body-file` + tempfile for all PR comments; generic GitHub-App auth note (per-command `http.extraheader` push pattern). Migrates from `python3 scripts/send_inbox_message.py` to `oacp send`.
- `review-loop-reviewer` skill (Claude Code runtime) — refreshed SKILL.md content. Hybrid split clarified (leader Bash I/O + analysis-only `code-reviewer` subagent with Read + search-only Bash). Adds incremental round-to-round diff path for re-review focus; fork-aware `REPO` detection via `headRepositoryOwner`/`headRepository`; self-review guard for App-authored PRs; supplemental-context channel for external spec / design-doc / prior-findings paths. Migrates from `python3 scripts/send_inbox_message.py` to `oacp send`.
- `review-loop-author` skill (Codex runtime) — refreshed SKILL.md content. Codex-native delegation idioms (`spawn_agent` / `send_input` / `wait_agent` / `close_agent`); `BASE_BRANCH` dynamically resolved from the PR rather than hardcoded; `repo_gh` wrapper with App-token-preferred + human-auth fallback; `workspace.json` marker fallback alongside `.oacp`. Migrates from `python3 scripts/send_inbox_message.py` to `oacp send`.
- `review-loop-reviewer` skill (Codex runtime) — refreshed SKILL.md content. Mirrors the Claude slice: identical findings-packet contract (P0..P3, blocking, status, area, file, line, repro/expected/evidence/recommendation); three GitHub comment surfaces fetched (inline + reviews + issue); concise/status-only PR comments with sensitive-data exclusion rule. Migrates from `python3 scripts/send_inbox_message.py` to `oacp send`.

## [0.5.1] - 2026-05-18

### Added

- `org-memory-synthesis` skill — synthesize the cross-project org-memory layer that the OACP session-init hook auto-loads. Folds new events from `$OACP_HOME/org-memory/events/` into the three curated SSOT files (`recent.md`, `decisions.md`, `rules.md`) via a marker-based incremental scan, then runs a 6-check audit (cross-file consistency, supersession asymmetry, stale-status, mechanical chronological order, category drift, migration leftovers). Both Claude Code and Codex runtimes. Pairs naturally with `/wrap-up`'s org-memory step.
- Top-level README `org-memory-synthesis` entry between `wrap-up` and "How These Skills Work Together".

## [0.5.0] - 2026-05-14

### Changed

- `check-inbox` skill — refreshed SKILL.md content. Adds OACP Phase 1 receiver autonomy (`always_pause` / `auto_review`) with a 4-gate evaluator, audit events, and a post-acceptance threshold checkpoint. New `references/autonomy.md` sub-doc carries the evaluator detail. Event-driven `oacp watch` is now the preferred recurring-monitoring path, with `/loop` as the fallback. Manifest bumps `requires_oacp` to `>=0.3.1`.
- `self-improve` skill — refreshed SKILL.md content. Adds session-friction analysis (Step 4.5) — scans the current conversation for user corrections, clusters by root cause, and proposes new or extended rules. New `friction` scope flag for the dedicated pass. Adds same-day repeat narrowing (skip full scan when a prior pass ran today), first-run retrospective for skills created+executed in the same session, structural-health gate with optional skill-architecture subagent escalation, tiered memory-staleness thresholds (2/14/30 days), namespace discipline for shared skill repos, and advisory file locking for concurrent runtime writes to OACP memory.
- `wrap-up` skill — refreshed SKILL.md content. Flow: cleanup → optional `/debrief` → org-memory events → `/self-improve` → commit → optional memory sync → push.

## [0.4.0] - 2026-05-01

### Added

- `wrap-up` skill — end-of-session cleanup, optional debrief, self-improve, commit, and push in one command. 8-step sequence: cleanup → debrief → org-memory → self-improve → commit → memory-sync → push → summary. Hard dependency on `/self-improve` skill; optional integrations with `/debrief` and the `oacp` CLI (≥0.3.0). Both Claude Code and Codex runtimes.
- Top-level README "wrap-up" entry under the Skills section.

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

[0.7.0]: https://github.com/kiloloop/oacp-skills/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/kiloloop/oacp-skills/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/kiloloop/oacp-skills/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/kiloloop/oacp-skills/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/kiloloop/oacp-skills/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/kiloloop/oacp-skills/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/kiloloop/oacp-skills/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/kiloloop/oacp-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kiloloop/oacp-skills/releases/tag/v0.1.0
