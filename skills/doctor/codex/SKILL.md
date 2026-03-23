---
name: doctor
description: Run environment and workspace diagnostics, auto-fix what it can, and report blockers. Use at session start or when something seems broken.
---

# /doctor

Run `oacp doctor` to check environment health, workspace structure, inbox
state, YAML schemas, and agent status. Auto-fix safe issues and report
blockers that still need human intervention.

## Interface

```bash
/doctor [--project <name>]
```

- `--project <name>` — optional project override

## Workflow

### 1. Resolve project name

If `--project` was provided, use it directly. Otherwise auto-detect:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os

project = ""
for marker in (".oacp", "workspace.json"):
    if not os.path.exists(marker):
        continue
    path = os.path.realpath(marker) if os.path.islink(marker) else marker
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        project = data.get("project_name", "") or ""
    except Exception:
        project = ""
    if project:
        break
print(project)
PY
)"
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
```

If `PROJECT` is empty, run environment-only checks unless the user explicitly
asked for a specific project audit.

### 2. Run oacp doctor with --fix

With a project:

```bash
oacp doctor --project "${PROJECT}" --fix --json 2>/dev/null
```

Without a project:

```bash
oacp doctor --json 2>/dev/null
```

Capture stdout JSON and the exit code. Exit code `1` means doctor found
blocking errors, not that the command itself failed.

### 3. Parse JSON output

Parse:

- `has_errors`
- `fixed[]`
- each category's `name` and `worst_severity`
- `categories[]`
- each result's `name`, `severity`, `message`, and optional `fix_hint`

The `fixed` array lists safe changes already applied by `oacp doctor --fix`.
Do not reimplement those fixes in the skill.

### 4. Report findings

```text
## Doctor Report

### Auto-Fixed
- <list of fixes applied>

### Warnings
- [!] <category> — <description>

### Errors
- [x] <category> — <description> — <fix_hint>

### Summary
<category>: <severity> | ...
Auto-fixed: N issue(s) | Remaining: M warning(s), K error(s)
```

Reporting rules:

- List auto-fixes first, directly from `fixed[]`
- Group remaining issues by category
- Include `fix_hint` for `warn` and `error` results when present
- Do not surface `ok` results individually
- If there are no remaining issues, report that the environment is healthy
- Build the summary from the parsed category severities after `--fix`, not from
  a stale pre-fix snapshot

### 5. Recommend next steps

Prioritize the most impactful remaining fix:

- Missing tools: installation commands
- Missing workspace: `oacp init <project>`
- Invalid YAML: file path and error details
- Stale inbox: suggest processing with `/check-inbox`

## Notes

- Do not invent checks beyond the categories returned by `oacp doctor`.
- `--fix` already handles missing inbox directories, missing `status.yaml`, and
  stale status timestamps. Do not add manual fix scripts for those cases.
- `shared/INTENT.md` is a repo-side reference, not an installed runtime
  dependency for Codex.
- Prefer concise reporting over restating every successful check.
