# doctor — Shared Intent

## What it does

Runs `oacp doctor` to check environment health, workspace structure, inbox health, YAML schema validity, autonomy configs, agent status, and signing trust roots. Parses the structured output, auto-fixes what it can, and reports blockers that need human intervention.

## Check categories

`oacp doctor` validates these areas (v0.4.x):

| Category | What it checks |
|----------|---------------|
| Environment | Required tools (git, python3, gh) and optional tools (ruff, shellcheck, pyyaml) |
| Workspace | workspace.json validity, agents/ directory presence, per-agent profile completeness (config, status, audit scaffold — not just a bare inbox directory) |
| Inbox Health | Per-agent inbox directories exist, message count and staleness (>24h) |
| Schemas | YAML validity of packets/ files and status.yaml field validation (runtime, status, capabilities, updated_at) |
| Autonomy | Receiver autonomy config blocks parse and validate; signed policy files verify (`policy_auth`) |
| Agent Status | status.yaml presence per agent, staleness (>1h since updated_at) |
| Trust (v0.4.1+) | Signing trust-root health: catalog-vs-pins drift, per-receiver pin-completeness gaps, enforce-readiness for `verify_mode: enforce` receivers |
| Memory Sync (`--memory`) | Advisory checks on the OACP home memory git sync |

## Severity levels

| Level | Symbol | Meaning |
|-------|--------|---------|
| ok | `[+]` | Check passed |
| warn | `[!]` | Non-blocking issue — should be addressed |
| error | `[x]` | Blocking issue — must be fixed |
| skip | `[-]` | Check skipped (missing dependency) |

## Auto-fixable issues

The CLI supports `oacp doctor --fix` which applies these fixes automatically:

- **Missing inbox directories** — creates the directory
- **Missing status.yaml** — creates from `templates/agent_status.template.yaml`
- **Stale status.yaml** — updates `updated_at` to current UTC timestamp

Skills should use `--fix` rather than implementing fix logic manually.

## Issues requiring human intervention

These should be reported as blockers:

- Missing required tools (git, python3, gh)
- Invalid workspace.json (malformed JSON)
- Invalid status.yaml schema (wrong runtime, invalid capabilities)
- Missing workspace.json or agents/ directory (requires `oacp init`)
- Stale inbox messages (>24h) — need manual triage

## Output contract

```
## Doctor Report

### Auto-Fixed
- <description of each auto-fix applied>

### Warnings
- [!] <category> — <description>

### Errors
- [x] <category> — <description> — <fix_hint>

### Summary
Environment: ok | Workspace: ok | Inbox: warn | Schemas: ok | Agent Status: warn
Auto-fixed: N issue(s) | Remaining: M warning(s), K error(s)
```

## Acceptance criteria

- `oacp doctor --project <name> --fix --json` runs successfully and output is parsed
- Auto-fixable issues are fixed by the `--fix` flag
- Non-fixable issues are reported with severity and fix hints
- Blockers requiring human action are clearly called out
- Exit cleanly even if `oacp doctor` itself returns a non-zero exit code
