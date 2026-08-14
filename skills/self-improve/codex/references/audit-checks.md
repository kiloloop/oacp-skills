# Self-improve audit checks

Load only the section required by the selected audit scope.

## Skills

Load this reference only when skills are in scope.

### Resolve and inventory

Resolve each skill in this order:

1. Active session Skills catalog and exact source locator, preserving
   plugin-qualified names.
2. Canonical authoring locations: `.agents/skills` from the working directory
   to repo root, `$HOME/.agents/skills`, then `/etc/codex/skills` when readable.
3. Explicit environment-owned authoring roots documented by the current
   repository, such as `$WORKSPACE_ROOT/<skills-repo>/codex/skills`.
4. `${CODEX_HOME:-$HOME/.codex}/skills` only as a compatibility fallback.

Inventory the target's `SKILL.md`, frontmatter, auxiliary metadata such as
`agents/openai.yaml` or `skill.yaml`, directly linked references, scripts,
tests, discovery links, setup/install generators, and direct callers. Do not
load unrelated resources.

### Audit checklist

- Frontmatter name matches the folder; description states behavior, triggers,
  and important exclusions.
- Representative natural-language, `$skill`, negative, and plugin-qualified
  prompts route correctly where applicable.
- Inputs, outputs, stopping conditions, approval boundaries, and validation are
  explicit without narrating obvious model behavior.
- Paths, commands, flags, tools, config keys, and capability claims match live
  behavior.
- Authored source, symlink target, installed artifact, and cross-runtime fork
  are classified correctly.
- External, destructive, costly, credential-sensitive, and scope-expanding
  actions have one clear boundary.
- Rules already owned by AGENTS.md or protocol are not duplicated.
- Conditional detail lives in a directly linked reference; repeated fragile
  mechanics live in a tested script.
- Repeatable run learnings are consolidated into the owning instruction,
  reference, script, test, or metadata rather than appended as a log.
- The folder passes its validator and project-native tests.

When a skill is absent from the active catalog but present in an authored root,
record a discovery gap and verify the canonical installation or symlink after
any approved fix.

## Curated memory

Load this reference only when hand-maintained project memory is in scope.

### Select memory

Use the repo-local memory directory defined by the project, or OACP project
memory under `$OACP_HOME/projects/<project>/memory/` when `.oacp`,
`workspace.json`, AGENTS guidance, or the CLI identifies the project.

Treat `${CODEX_HOME:-$HOME/.codex}/memories/` as generated state. Inventory only
explicit top-level files when the user asks to troubleshoot generation; never
broadly scan rollout/session evidence or recommend hand-trimming generated
files.

### Audit checklist

- Verify time-sensitive facts, dates, current status, issue/PR identifiers,
  agent names, and runtime roots against live evidence.
- Cross-check the project's actual set of `MEMORY.md`, `project_facts.md`,
  `decision_log.md`, `open_threads.md`, `known_debt.md`, and AGENTS.md. Do not
  create missing files merely for symmetry.
- Keep current facts, dated decisions, active threads, and known debt in their
  defined homes; flag duplication and contradictions.
- Treat age as a review signal, not proof of staleness.
- Apply line or context budgets only to hand-maintained memory.
- Flag OACP split-brain when markers, guidance, skills, and runtime memory
  disagree about `$OACP_HOME` or project identity.

Before an approved OACP memory edit, use the project memory lock required by
the main workflow.

## AGENTS and configuration

Load this reference only when AGENTS.md, hooks, plugins, or Codex configuration
are in scope.

### Select surfaces

Inspect only applicable sources:

- Global `${CODEX_HOME:-$HOME/.codex}/AGENTS.md`.
- Repo-root and applicable nested `AGENTS.md` files.
- A tracked shared source documented by the current repository, such as
  `$WORKSPACE_ROOT/<skills-repo>/codex/projects/<project>/AGENTS.md`.
- Allowlisted keys from user or trusted-project `config.toml`, selected profile
  config, and surfaced admin `requirements.toml`.
- Relevant plugin manifests, hook definitions, and their setup generators only
  when the finding touches those surfaces.

Resolve symlinks and identify the owning repo. An intentional runtime-wiring
symlink is not drift.

### Audit checklist

- Keep global guidance cross-project and project guidance repo-specific.
- Flag duplicated, conflicting, misplaced, or obsolete rules.
- Verify commands, paths, markers, config keys, hooks, permissions, and
  capability claims against authored config and observed runtime state.
- Check both the generator and generated/discovered form when setup owns a
  hook, manifest, symlink, or config entry.
- Keep repo/account/App routing and branch/worktree policy in active AGENTS or
  repository policy rather than copying it into skills.
- Inspect remotes and credential guidance without printing secrets. Flag
  persisted tokens, token-bearing remotes, private-key defaults, or unredacted
  environment values.

Use an explicit key allowlist for config inspection. Never dump entire home,
browser, keychain, shell-history, token, or cloud-CLI trees.
