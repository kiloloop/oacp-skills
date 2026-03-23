---
name: doctor
description: Run environment and workspace diagnostics, auto-fix what it can, and report blockers. Use at session start or when something seems broken.
---

# /doctor — Environment & Workspace Diagnostics

Run `oacp doctor` to check environment health, workspace structure, inbox state, YAML schemas, and agent status. Auto-fixes safe issues and reports blockers that need human intervention.

## Arguments

```
/doctor [--project <name>]
```

- `--project <name>` — Which project to check. Auto-detected from `.oacp` project marker (may be a symlink to `workspace.json`) if omitted.

## Instructions

When the user runs `/doctor`, do the following:

### 1. Pre-flight: verify oacp CLI

Before anything else, check that the CLI is available:

```bash
command -v oacp >/dev/null 2>&1 || echo "NOT_FOUND"
```

If not found, report immediately: "oacp CLI not found. Install: `pip install oacp-cli`" and stop.

### 2. Resolve project name

If `--project` was provided, use it directly. Otherwise auto-detect:

```bash
PROJECT=$(python3 -c "import json; print(json.load(open('.oacp'))['project_name'])" 2>/dev/null || echo "")
```

If empty, ask the user which project to check. If the user only wants environment checks (no project), run without `--project`.

### 3. Run oacp doctor with --fix

Run the doctor command with `--fix` and `--json` for structured parsing:

```bash
oacp doctor --project "${PROJECT}" --fix --json 2>&1
```

If `--project` was not resolved, run without it and without `--fix` (fixes require a workspace target):

```bash
oacp doctor --json 2>&1
```

Capture both stdout (JSON) and the exit code. Exit code 1 means errors were found — this is expected, not a failure.

If the output is not valid JSON, the CLI may have crashed. Show the raw output to the user and report: "oacp doctor returned invalid output. Check CLI installation."

### 4. Parse the JSON output

The JSON output has this structure:

```json
{
  "has_errors": false,
  "fixed": [
    "Created claude/status.yaml",
    "Updated codex/status.yaml timestamp"
  ],
  "categories": [
    {
      "name": "Environment",
      "worst_severity": "ok",
      "results": [
        {
          "name": "git",
          "severity": "ok",
          "message": "git — git version 2.x.x"
        },
        {
          "name": "pyyaml",
          "severity": "warn",
          "message": "pyyaml — not importable",
          "fix_hint": "Install: pip install pyyaml"
        }
      ]
    }
  ]
}
```

Severity levels:

- `ok` — passed (or auto-fixed), no action needed
- `warn` — non-blocking issue, should be addressed
- `error` — blocking issue, must be fixed
- `skip` — check was skipped (missing dependency)

The `--fix` flag auto-fixes these safe issues:

| Issue | Fix applied |
|-------|------------|
| Missing inbox directory | Creates the directory |
| Missing status.yaml | Creates from template |
| Stale status.yaml | Updates `updated_at` timestamp |

Fixed results appear as `ok` in the output with updated messages. The `fixed` array lists what was changed — it will be empty on a healthy workspace where nothing needs fixing.

### 5. Report results

Present a structured report to the user:

```
## Doctor Report

### Auto-Fixed
- Created claude/status.yaml
- Updated codex/status.yaml timestamp

### Warnings
- [!] Environment — pyyaml not importable (Install: pip install pyyaml)
- [!] Inbox Health — claude/inbox has 3 messages, oldest 48h stale

### Errors
- [x] Workspace — workspace.json not found (Run: oacp init <project>)
- [x] Environment — gh not found (Install gh and ensure it is on PATH)

### Summary
Environment: ok | Workspace: error | Inbox: warn | Schemas: ok | Agent Status: ok
Auto-fixed: 2 issue(s) | Remaining: 1 warning(s), 2 error(s)
```

**Reporting rules:**

- List auto-fixes first (from the `fixed` array) so the user sees what changed
- Group remaining issues by category: Environment, Workspace, Inbox Health, Schemas, Agent Status
- Include `fix_hint` for all warn/error results that have one — note that `fix_hint` text comes from the CLI and may reference `make init` or `oacp init` depending on the context
- If no issues were found at all, report: "No issues found. Environment and workspace are healthy."
- `ok` and `skip` results are not shown individually — only the category summary

### 6. Recommend next steps

If there are remaining errors, suggest the most impactful fix first:

- Missing tools: installation commands
- Missing workspace: `oacp init <project>`
- Invalid YAML: which file to fix and what's wrong
- Stale inbox messages: suggest running `/check-inbox` to process them

If all checks pass (including after auto-fixes), confirm the environment is ready.

## Notes

- `oacp doctor` exit code 1 means errors were found — parse the output normally, do not treat it as a command failure
- The `--json` flag is required for structured parsing; without it, output is human-readable but harder to parse
- The CLI also supports `--oacp-dir <path>` to override the OACP home directory if `$OACP_HOME` is not set
- For recurring health checks, pair with `/check-inbox` at session start: run `/doctor` first to verify the environment, then `/check-inbox` to process pending messages
- Ensure your runtime has filesystem access to `$OACP_HOME` for reading workspace and agent directories
