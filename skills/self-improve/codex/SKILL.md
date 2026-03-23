---
name: self-improve
description: Review and improve the agent's operating system — skills, memory files, and AGENTS.md configs. Identifies staleness, contradictions, gaps, and bloat, then proposes and applies fixes.
---

# /self-improve

Review and improve the agent's configuration and knowledge layer in a Codex
and OACP workspace.

## Interface

```bash
/self-improve [skills|memory|config|claude-md|<skill-name>]
```

- No argument: review skills, memory, and config
- `skills`: review only skills used in this session
- `memory`: review only memory files
- `config` or `claude-md`: review only AGENTS/settings files
- `<skill-name>`: review one specific skill

## Workflow

### 1. Load the shared intent

Read `../shared/INTENT.md` before analysis. Use it as the source of truth for:

- review targets
- severity tags
- findings report format
- acceptance criteria

### 2. Parse the target

Map the argument to one of four scopes:

- full review
- `skills`
- `memory`
- `config` or `claude-md`
- a specific skill name

If the request is ambiguous, confirm the intended scope before editing.

### 3. Discover files

Prefer `rg` and `rg --files` for discovery. When you need `find`, use
`command find` so shell aliases do not interfere.

Resolve the current OACP project when memory is in scope:

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

#### Skills

If the scope includes skills:

- When a specific `<skill-name>` was provided, review that skill directly.
- Otherwise, review skills that were actually used in this session.
- Check these locations in order:
  1. `./.agents/skills/<name>/SKILL.md`
  2. `~/.codex/skills/<name>/SKILL.md`
  3. `skills/<name>/codex/SKILL.md` when working inside a skills repo

If you find multiple copies, call out any drift instead of assuming they are in
sync.

#### Memory

If the scope includes memory, inspect whichever of these locations exist:

1. `./memory/`
2. `$OACP_HOME/projects/<project>/memory/`
3. `~/.codex/projects/<project>/memory/`

List files with:

```bash
command find "<memory-dir>" -maxdepth 1 -type f -name '*.md' | sort
```

Check modification dates with:

```bash
command find "<memory-dir>" -maxdepth 1 -type f -name '*.md' | sort | while read -r f; do
  python3 -c "import os,sys; st=os.stat(sys.argv[1]); print(int(st.st_mtime), sys.argv[1])" "$f"
done
```

If a directory does not exist, note that and continue.

#### Config

If the scope includes config, review:

- `./AGENTS.md` (check whether it is a symlink)
- `~/.codex/AGENTS.md`
- `.codex/settings.json`
- `.codex/settings.local.json`

### 4. Analyze

Apply the shared checklist from `../shared/INTENT.md`, plus these Codex-specific
checks:

- **Skills**: compare the actual wrapper behavior against the repo's current
  commands, paths, and runtime expectations
- **Memory**: flag stale, contradictory, or drifted files across the discovered
  memory locations
- **Config**: look for duplicated or conflicting rules between global and
  project `AGENTS.md`, plus mismatches between `AGENTS.md` and `.codex`
  settings

Escalate a skill as `[STRUCTURAL]` when the shared trigger conditions are met,
such as output-format drift, missing modes, or 3+ findings on one skill.

### 5. Report findings

Use the findings format from `../shared/INTENT.md`. Sort findings within each
category in this order:

`[FIX]` > `[CONFLICT]` > `[STRUCTURAL]` > `[GAP]` > `[STALE]` > `[BLOAT]`

If a category has no findings, say so explicitly.

### 6. Propose changes

For each finding, propose a specific edit and then ask:

```text
Which changes should I apply? (all / list numbers / none)
```

Group obvious routine cleanup into one approval item when it makes the report
easier to scan.

### 7. Apply approved changes

Make surgical edits. Prefer editing existing files over creating new ones
unless the finding specifically requires a new file.

Before editing shared OACP runtime memory, acquire an advisory lock:

```bash
LOCK_DIR="$OACP_ROOT/projects/${PROJECT}/.memory-write.lock"
if [ -d "$LOCK_DIR" ]; then
  LOCK_MTIME="$(python3 -c "import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))" "$LOCK_DIR")"
  LOCK_AGE=$(( $(date +%s) - LOCK_MTIME ))
  if [ "$LOCK_AGE" -gt 600 ]; then
    rmdir "$LOCK_DIR" 2>/dev/null
  fi
fi
if mkdir "$LOCK_DIR" 2>/dev/null; then
  trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT
else
  echo "Memory files locked by another runtime - defer those edits"
fi
```

Memory files under `$OACP_HOME/projects/*/memory/` and
`~/.codex/projects/*/memory/` are not git-tracked. Edit them in place and
report them separately from repo commits.

After memory edits are complete, release the advisory lock explicitly:

```bash
rmdir "$LOCK_DIR" 2>/dev/null
```

### 8. Commit changes

**Namespace discipline:** Only edit files under the `codex/` namespace. If
drift is found in `claude/SKILL.md` or other runtimes' files, do not edit them
directly; send an inbox message to that runtime's agent instead.

Group git-tracked changes by repo and commit separately. If `AGENTS.md` is a
symlink, commit the source file in the owning repo rather than the symlink
stub.

Do not push unless the user asks for it.

### 9. Summarize

End with a concise summary:

```text
Self-improvement complete:
- Reviewed: N skills, M memory files, K config files
- Findings: X total (N fixed, M flagged)
- Commits: [repo + commit summary]
```
