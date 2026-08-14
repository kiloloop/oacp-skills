---
name: doctor
description: Run environment and workspace diagnostics, auto-fix what it can, and report blockers. Use at session start or when something seems broken.
---

# /doctor

Run `oacp doctor` to check environment health, workspace structure, inbox
state, YAML schemas, autonomy configs, agent status, and signing trust roots.
Auto-fix safe issues and report blockers that still need human intervention.

## Interface

```bash
/doctor [--project <name>]
```

- `--project <name>` — optional project override

## Workflow

### 1. Verify the CLI version

Before anything else, require the signing-capable OACP version declared by this
package (`>=0.4.2`):

```bash
command -v oacp >/dev/null 2>&1 || {
  echo "oacp CLI not found; install 'oacp-cli[crypto]>=0.4.2'" >&2
  exit 1
}
OACP_VERSION="$(oacp --version 2>&1)" || {
  printf '%s\n' "$OACP_VERSION" >&2
  exit 1
}
printf '%s\n' "$OACP_VERSION"
python3 - "$OACP_VERSION" <<'PY'
import re
import sys

version = sys.argv[1].strip()
match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
if not match:
    raise SystemExit(f"could not parse oacp version: {version}")
if tuple(int(part) for part in match.groups()) < (0, 4, 2):
    raise SystemExit(f"oacp {version} is older than required 0.4.2")
PY
```

If the reported version is older than `0.4.2`, stop and ask the user to install
or upgrade with `pip install --upgrade 'oacp-cli[crypto]>=0.4.2'`. The base
install can run ordinary checks, but the `[crypto]` extra is required for the
signing and trust inventory described below.

### 2. Resolve project name

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

### 3. Run oacp doctor with --fix

Capture stdout, stderr, and the exit code separately so malformed JSON or an
operational crash cannot be mistaken for a diagnostic finding. With a project:

```bash
DOCTOR_JSON="$(mktemp)"
DOCTOR_STDERR="$(mktemp)"
DOCTOR_RC=0
oacp doctor --project "${PROJECT}" --oacp-dir "${OACP_ROOT}" \
  --fix --json >"${DOCTOR_JSON}" 2>"${DOCTOR_STDERR}" || DOCTOR_RC=$?
```

Without a project:

```bash
DOCTOR_JSON="$(mktemp)"
DOCTOR_STDERR="$(mktemp)"
DOCTOR_RC=0
oacp doctor --oacp-dir "${OACP_ROOT}" --json \
  >"${DOCTOR_JSON}" 2>"${DOCTOR_STDERR}" || DOCTOR_RC=$?
```

Exit code `1` means doctor found blocking errors, not that the command itself
failed. Require `$DOCTOR_JSON` to parse as a JSON object. On invalid JSON or an
unexpected exit code, report the captured stderr and stop instead of
fabricating a report. Remove both private temp files after parsing/reporting.

### 4. Parse JSON output

Parse:

- `has_errors`
- `fixed[]`
- each category's `name` and `worst_severity`
- `categories[]`
- each result's `name`, `severity`, `message`, and optional `fix_hint`

The `fixed` array lists safe changes already applied by `oacp doctor --fix`.
Do not reimplement those fixes in the skill.

The OACP 0.4.x inventory includes:

- **Environment** — required tools and Python packages
- **Workspace** — `workspace.json`, agent directories, and per-agent profile
  completeness (config, status, and audit scaffold)
- **Inbox Health** — message counts and oldest-message staleness
- **Schemas** — inbox/outbox message validation
- **Autonomy** — receiver policy parsing and signed-policy verification
  (`policy_auth`)
- **Agent Status** — `status.yaml` presence and freshness
- **Trust** (v0.4.1+) — catalog/pin drift, receiver pin completeness, and
  enforce-readiness
- **Memory Sync** (with `--memory`) — advisory checks for the OACP memory repo

### 5. Report findings

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

### 6. Recommend next steps

Prioritize the most impactful remaining fix:

- Missing tools: installation commands
- Missing workspace: `oacp init <project>`
- Invalid YAML: file path and error details
- Stale inbox: suggest processing with `/check-inbox`
- Trust-pin gaps on an enforce receiver: import each missing peer with
  `oacp trust import <kid>.pub.json --project <project> --agent <receiver>`
- Invalid policy signature (`policy_auth: invalid`): confirm the policy change,
  then re-sign it with `oacp trust sign-policy`

## Notes

- Do not invent checks beyond the categories returned by `oacp doctor`.
- `--fix` already handles missing inbox directories, missing `status.yaml`, and
  stale status timestamps. Do not add manual fix scripts for those cases.
- `shared/INTENT.md` is a repo-side reference, not an installed runtime
  dependency for Codex.
- Prefer concise reporting over restating every successful check.
