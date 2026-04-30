# OACP Skills

Reusable skills for AI coding agents coordinating over the [Open Agent Coordination Protocol](https://github.com/kiloloop/oacp).

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OACP](https://img.shields.io/badge/OACP-%3E%3D0.3.0-orange.svg)](https://github.com/kiloloop/oacp)
[![Claude Code](https://img.shields.io/badge/Runtime-Claude_Code-6B4FBB.svg)](https://claude.ai/code)
[![Codex CLI](https://img.shields.io/badge/Runtime-Codex_CLI-74AA9C.svg)](https://github.com/openai/codex)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](https://github.com/kiloloop/oacp-skills/pulls)

## Skills

### [oacp](skills/oacp/)

The OACP protocol primer — teaches a runtime how to use the CLI and message protocol: version contract, workspace orientation, `oacp send` recipe with type taxonomy, `oacp inbox` vs `oacp watch`, review-loop semantics, and conventions. Auto-triggers when an agent works with OACP. Foundation for the workflow skills below.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code — auto-triggers based on context, or invoke explicitly
/oacp
```

---

### [check-inbox](skills/check-inbox/)

Single-pass inbox processor. Scans for pending OACP messages, processes each one (read, act, reply, delete), then exits. Pair with a loop for continuous monitoring.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code
/check-inbox                        # single-pass scan
/check-inbox --project myproject    # explicit project
/loop 2m /check-inbox               # continuous polling every 2 min
```

---

### [review-loop-reviewer](skills/review-loop-reviewer/)

Reads a PR diff, produces structured findings (blocking / non-blocking), renders a verdict (LGTM or REQUEST_CHANGES), and sends feedback to the author's OACP inbox. Supports multi-round reviews with `--poll`.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code (triggered via check-inbox when a review_request arrives)
/review-loop-reviewer 42 --author claude
/review-loop-reviewer 42 --author claude --poll   # wait for author's next push
```

---

### [review-loop-author](skills/review-loop-author/)

Picks up review findings from inbox or PR comments, applies fixes, pushes updates, and sends a `review_addressed` message back to the reviewer. Closes the review loop.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code (triggered via check-inbox when review_feedback arrives)
/review-loop-author 42 --reviewer codex
/review-loop-author 42 --reviewer codex --poll     # wait for reviewer's next round
```

---

### [self-improve](skills/self-improve/)

Audits the agent's knowledge layer — skills, memory files, and config — for staleness, contradictions, gaps, and bloat. Proposes and applies surgical fixes with approval.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code
/self-improve                  # full review (skills + memory + config)
/self-improve skills           # review only skills that ran this session
/self-improve memory           # review memory files only
/self-improve <skill-name>     # review a single specific skill
```

---

### [doctor](skills/doctor/)

Wraps `oacp doctor` for agent self-diagnostics. Runs checks across environment, workspace, inbox health, schemas, and agent status. Auto-fixes safe issues (missing inboxes, stale timestamps) and reports remaining blockers.

**Runtimes:** Claude Code, Codex

```bash
# Claude Code
/doctor                        # auto-detect project, full diagnostics
/doctor --project myproject    # explicit project name

# CLI directly
oacp doctor --project myproject --fix        # auto-fix safe issues
oacp doctor --project myproject --fix --json # structured output
```

## How These Skills Work Together

The **oacp** skill teaches a runtime how to use the OACP CLI and protocol — it's the foundation the workflow skills build on. The next three form a complete agent-to-agent code review loop:

1. **check-inbox** monitors each agent's inbox for incoming messages (review requests, feedback, task assignments).
2. When a review request arrives, the reviewer agent runs **review-loop-reviewer** to analyze the PR diff and send structured findings back.
3. The author agent picks up the findings via **review-loop-author**, applies fixes, and sends a `review_addressed` message — closing the loop.

The remaining skills are complementary maintenance tooling: **self-improve** audits skill instructions, memory files, and config drift, while **doctor** can verify the OACP environment and workspace are healthy, especially useful at session start.

## Prerequisites

- [OACP CLI](https://github.com/kiloloop/oacp) >= 0.3.0 — install via `pip install 'oacp-cli>=0.3.0'`
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
