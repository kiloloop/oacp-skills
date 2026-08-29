# OACP Skills

Reusable skills for AI coding agents coordinating over the [Open Agent Coordination Protocol](https://github.com/kiloloop/oacp).

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OACP](https://img.shields.io/badge/OACP-%3E%3D0.4.2-orange.svg)](https://github.com/kiloloop/oacp)
[![Claude Code](https://img.shields.io/badge/Runtime-Claude_Code-6B4FBB.svg)](https://claude.ai/code)
[![Codex CLI](https://img.shields.io/badge/Runtime-Codex_CLI-74AA9C.svg)](https://github.com/openai/codex)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](https://github.com/kiloloop/oacp-skills/pulls)

## Skills

### [oacp](skills/oacp/)

The OACP protocol primer — teaches a runtime how to use the CLI and message protocol: version contract, workspace orientation, `oacp send` recipe with type taxonomy, message signing and trust pinning, `oacp inbox` vs `oacp watch` (per-subscriber cursors), review-loop semantics, and conventions. Auto-triggers when an agent works with OACP. Foundation for the workflow skills below.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code — auto-triggers based on context, or invoke explicitly
/oacp
```

---

### [check-inbox](skills/check-inbox/)

Single-pass inbox processor. Discovers pending OACP messages, verifies before parsing, binds handling to an immutable snapshot, replies when required, and archives only after terminal success. Use a runtime heartbeat with a stable watch cursor for recurring checks. It honors receiver autonomy and continuation grants; envelope enforcement is used only by runtimes with a verified adapter.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code / Codex
/check-inbox                        # single-pass scan
/check-inbox --project myproject    # explicit project
/loop 2m /check-inbox               # polling fallback (every 2 min)
```

---

### [review-loop-reviewer](skills/review-loop-reviewer/)

Runs one stateless exact-head PR review round, produces structured findings, performs only declared GitHub effects, sends one terminal LGTM or feedback message, and exits. The author/coordinator owns every later round.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code (triggered via check-inbox when a review_request arrives)
/review-loop-reviewer 42 --author claude
```

---

### [review-loop-author](skills/review-loop-author/)

Coordinates an exact-head review thread, routes verified feedback, applies authorized fixes, sends `review_addressed` plus a fresh bounded review request, and lands or parks only at an authorized terminal checkpoint.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code (triggered via check-inbox when review_feedback arrives)
/review-loop-author 42 --reviewer codex
```

---

### [self-improve](skills/self-improve/)

Audits authored skills, curated project memory, runtime config, and AGENTS.md or CLAUDE.md instructions for staleness, contradictions, gaps, and bloat. It proves source-to-runtime effective state, keeps generated memory read-only, and applies surgical fixes only with approval.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code / Codex
/self-improve                  # full review (skills + memory + runtime config)
/self-improve skills           # review only skills that ran this session
/self-improve memory           # review memory files only
/self-improve agents-md        # Codex: review AGENTS.md files + settings only
/self-improve claude-md        # Claude Code: review CLAUDE.md files + settings only
/self-improve friction         # Claude Code: review only session-friction patterns
/self-improve <skill-name>     # review a single specific skill
```

---

### [doctor](skills/doctor/)

Wraps `oacp doctor` for agent self-diagnostics. Runs checks across environment, workspace, inbox health, schemas, autonomy configs, agent status, and signing trust roots (pin completeness, enforce-readiness). Auto-fixes safe issues (missing inboxes, stale timestamps) and reports remaining blockers.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code
/doctor                        # auto-detect project, full diagnostics
/doctor --project myproject    # explicit project name

# CLI directly
oacp doctor --project myproject --fix        # auto-fix safe issues
oacp doctor --project myproject --fix --json # structured output
```

---

### [wrap-up](skills/wrap-up/)

End-of-session cleanup in one command: read-only cleanup preview → verified local cleanup → debrief → significant org-memory events → delta-first `/self-improve` → bounded memory/repository publication → complete or paused summary. Hard dependency on `/self-improve`; cleanup preserves persistent, peer-owned, dirty, and post-merge-diverged work.

**Runtimes:** Claude Code, Codex

```bash
# Command
/wrap-up            # full sequence
/wrap-up --dry-run  # cleanup + debrief + self-improve only; skip commit, push, memory sync
```

---

### [debrief](skills/debrief/)

Publish a structured session summary to the org-memory debrief store at `$OACP_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/`. One session produces one immutable, hash-verified record: the writer stages privately, publishes with an atomic no-replace link, and reads back to confirm, so the canonical path never holds a partial record. Append-only — identical content republishes idempotently, differing content at the same path fails rather than overwriting. Feeds `/wrap-up`'s debrief step.

**Runtimes:** Claude Code, Codex

```bash
/debrief            # generate the summary and publish it
/debrief --dry-run  # generate and display it; write nothing
```

---

### [org-memory-synthesis](skills/org-memory-synthesis/)

Synthesize the cross-project org-memory layer that the OACP session-init hook auto-loads. Folds new events from `$OACP_HOME/org-memory/events/` into the three curated SSOT files (`recent.md`, `decisions.md`, `rules.md`) via a marker-based incremental scan, then runs a 6-check audit (cross-file consistency, supersession asymmetry, stale-status, mechanical chronological order, category drift, migration leftovers). Pairs naturally with `/wrap-up`'s org-memory step.

**Runtimes:** Claude Code, Codex

```bash
/org-memory-synthesis    # full synthesis + audit pass
```

## How These Skills Work Together

The **oacp** skill teaches a runtime how to use the OACP CLI and protocol — it's the foundation the workflow skills build on. The next three form a complete agent-to-agent code review loop:

1. **check-inbox** monitors each agent's inbox for incoming messages (review requests, feedback, task assignments).
2. When a review request arrives, the reviewer agent runs **review-loop-reviewer** to analyze the PR diff and send structured findings back.
3. The author agent picks up findings via **review-loop-author**, applies authorized fixes, sends `review_addressed`, and creates a fresh exact-head request for the next stateless round.

The remaining skills are complementary maintenance tooling: **self-improve** audits skill instructions, memory files, and config drift; **doctor** verifies the OACP environment and workspace are healthy, especially useful at session start; and **org-memory-synthesis** keeps the cross-project SSOT layer (the one auto-loaded at session init) trustworthy by folding events and auditing for drift.

## Prerequisites

- [OACP CLI](https://github.com/kiloloop/oacp) >= 0.4.2 — install via `pip install 'oacp-cli[crypto]'` (the `[crypto]` extra enables message signing + verification; individual skills declare their own floor in `skill.yaml`)
- A supported runtime: [Claude Code](https://claude.ai/code) or [Codex CLI](https://github.com/openai/codex)
- An OACP workspace initialized with `oacp init <project>`

## Installation

### Option 1: skills.sh (Claude Code)

Install via [skills.sh](https://skills.sh) for Claude Code:

```bash
# Install all skills
npx skills add kiloloop/oacp-skills

# Install a single skill
npx skills add kiloloop/oacp-skills -s check-inbox

# Install globally (available across all projects)
npx skills add kiloloop/oacp-skills -g
```

> **Note:** skills.sh installs the Claude Code variant of each skill. For Codex or other runtimes, use Option 2 with the runtime-specific subdirectory.

### Option 2: Copy

Copy skill files directly into your project:

```bash
# Claude Code
mkdir -p .claude/skills/<skill-name>
cp skills/<skill-name>/SKILL.md .claude/skills/<skill-name>/SKILL.md

# Codex
mkdir -p .agents/skills/<skill-name>
cp skills/<skill-name>/codex/SKILL.md .agents/skills/<skill-name>/SKILL.md
```

### Option 3: Symlink (for skill developers)

Symlink skills from a local clone so updates pull through automatically:

```bash
git clone https://github.com/kiloloop/oacp-skills.git ~/oacp-skills

# Claude Code — symlink a single skill
mkdir -p .claude/skills/check-inbox
ln -s ~/oacp-skills/skills/check-inbox/SKILL.md \
      .claude/skills/check-inbox/SKILL.md

# Symlink all skills at once
for skill in check-inbox doctor oacp review-loop-author review-loop-reviewer self-improve; do
  mkdir -p .claude/skills/$skill
  ln -sf ~/oacp-skills/skills/$skill/SKILL.md \
         .claude/skills/$skill/SKILL.md
done
```

## Directory Structure

```
skills/
  <skill-name>/
    SKILL.md            # skill instructions (skills.sh compatible)
    skill.yaml          # machine-readable metadata (runtimes, category, OACP version)
    README.md           # human-readable docs
    shared/             # common intent, protocol refs
    claude/
      SKILL.md          # → symlink to ../SKILL.md
    codex/
      SKILL.md          # Codex-specific instructions
template/               # starter template for new skills
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the skill structure, schema reference, and submission guidelines.

## Related

- [kiloloop/oacp](https://github.com/kiloloop/oacp) — Open Agent Coordination Protocol CLI and spec

## License

[Apache-2.0](LICENSE)
