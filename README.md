# OACP Skills

Reusable skills for AI coding agents coordinating over the [Open Agent Coordination Protocol](https://github.com/kiloloop/oacp).

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OACP](https://img.shields.io/badge/OACP-%3E%3D0.1.0-orange.svg)](https://github.com/kiloloop/oacp)
[![Claude Code](https://img.shields.io/badge/Runtime-Claude_Code-6B4FBB.svg)](https://claude.ai/code)
[![Codex CLI](https://img.shields.io/badge/Runtime-Codex_CLI-74AA9C.svg)](https://github.com/openai/codex)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](https://github.com/kiloloop/oacp-skills/pulls)

## Skills

| Skill | What it does | When to use it |
|-------|-------------|----------------|
| [check-inbox](skills/check-inbox/) | Scan OACP inbox for agent messages and auto-act on them | Continuous or on-demand inbox polling in multi-agent workflows |
| [review-loop-reviewer](skills/review-loop-reviewer/) | Review PR diffs, produce structured findings, emit verdict | Agent acting as code reviewer on a PR |
| [review-loop-author](skills/review-loop-author/) | Address review findings, push fixes, drive to LGTM | Agent authoring a PR that is under review |

## Prerequisites

- [OACP](https://github.com/kiloloop/oacp) >= 0.1.0 — install via `pip install oacp-cli`
- A supported runtime: [Claude Code](https://claude.ai/code) or [Codex CLI](https://github.com/openai/codex)
- An OACP workspace initialized with `oacp init <project>`

## Quick Install

Copy the skill file for your runtime into your project:

```bash
# Claude Code
mkdir -p .claude/skills/<skill-name>
cp skills/<skill-name>/claude/SKILL.md .claude/skills/<skill-name>/SKILL.md

# Codex
mkdir -p .agents/skills/<skill-name>
cp skills/<skill-name>/codex/SKILL.md .agents/skills/<skill-name>/SKILL.md
```

## How These Skills Work Together

These three skills form a complete agent-to-agent code review loop over OACP:

1. **check-inbox** monitors each agent's inbox for incoming messages (review requests, feedback, task assignments).
2. When a review request arrives, the reviewer agent runs **review-loop-reviewer** to analyze the PR diff and send structured findings back.
3. The author agent picks up the findings via **review-loop-author**, applies fixes, and sends a `review_addressed` message — closing the loop.

Each skill is independent and useful on its own, but together they enable fully autonomous multi-round code review between agents.

## Directory Structure

```
skills/
  <skill-name>/
    skill.yaml          # machine-readable metadata
    README.md           # human-readable docs
    shared/             # common intent, protocol refs
    claude/
      SKILL.md          # Claude Code native instructions
    codex/
      SKILL.md          # Codex native instructions
template/               # starter template for new skills
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the skill structure, schema reference, and submission guidelines.

## Related

- [kiloloop/oacp](https://github.com/kiloloop/oacp) — Open Agent Coordination Protocol

## License

[Apache-2.0](LICENSE)
