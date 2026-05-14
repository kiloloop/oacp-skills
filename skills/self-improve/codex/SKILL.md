---
name: self-improve
description: "Review and improve the agent's operating system - skills, memory files, and AGENTS.md configs. Identifies staleness, contradictions, gaps, and bloat, then proposes and applies fixes."
---

# /self-improve - Agent Self-Improvement

Structured review of the agent's configuration and knowledge layer. Identifies
staleness, contradictions, gaps, and improvement opportunities. Proposes
changes, applies them after approval, and commits only when requested.

## Arguments

- `/self-improve` - full review (session skills + memory + AGENTS.md)
- `/self-improve skills` - review only skills that ran this session
- `/self-improve memory` - review memory files only
- `/self-improve agents-md` - review AGENTS.md files and settings only
- `/self-improve config` - alias for `agents-md`
- `/self-improve <skill-name>` - review a single specific skill

## Instructions

When the user runs `/self-improve`, execute these steps.

### 1. Parse Target

Determine what to review based on the argument:

| Argument | Review scope |
| --- | --- |
| (none) | skills + memory + AGENTS.md |
| `skills` | Only skills that ran this session |
| `memory` | Only memory files |
| `agents-md` or `config` | Only AGENTS.md files + settings |
| `<skill-name>` | That specific skill's SKILL.md |

If the target is ambiguous, confirm the intended scope before editing.

### 2. Discover Files

Build an inventory of all files to review based on the target scope. Prefer
`rg` and `rg --files` for discovery. When `find` is needed, use `command find`
so shell aliases do not interfere.

#### Skills Discovery

If scope includes skills:

- Session skills: scan the conversation context for `/skill-name` invocations.
  Only review skills that actually ran this session unless a specific
  `<skill-name>` was given.
- Specific skill: review it directly regardless of whether it ran this session.

Locate each skill's `SKILL.md` by checking these locations in order:

1. Project-scoped: `./.codex/skills/<name>/SKILL.md`
2. Global: `~/.codex/skills/<name>/SKILL.md`
3. Public skills repo shape: `skills/<name>/codex/SKILL.md`
4. Project-defined skill directories documented in the current repo's
   `AGENTS.md`

If the skill exists in multiple locations, note all copies and flag drift
instead of assuming they are synchronized.

#### Memory Discovery

If scope includes memory, first resolve the current OACP project from `.oacp`
or `workspace.json`:

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

Inspect whichever of these locations exist:

1. Project-level `memory/` directory relative to the repo root
2. OACP project memory at `$OACP_HOME/projects/<project>/memory/`
3. Codex project memory at `~/.codex/projects/<project>/memory/`

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

#### AGENTS.md Discovery

If scope includes AGENTS.md/config:

- Global: `~/.codex/AGENTS.md` if it exists
- Project: `./AGENTS.md` if it exists; check whether it is a symlink
- Project settings: `.codex/config.toml`, `.codex/settings.json`,
  `.codex/settings.local.json` if present

If an AGENTS.md file is a symlink, inspect the resolved target and note the
owning repo for any later commit.

### 3. Analyze Skills

For each skill in scope, check:

- Post-run lessons: what worked, what broke, and whether repeatable patterns
  should become durable instructions instead of another run note.
- Contradictions with memory or config.
- Missing safety rules for edge cases exposed by the run.
- Outdated references: file paths, script names, argument flags, or repo URLs
  that no longer match reality.
- Local-only metadata: workstation-specific versions, local registry state, and
  machine-local paths do not belong in general-purpose skill docs.
- Multi-copy drift: compare copies and flag divergence.
- Cross-runtime ownership: respect runtime namespaces. Do not edit another
  runtime's wrapper directly; route that drift to the owning runtime or record a
  follow-up.

### 4. Analyze Memory

For each memory file, check:

- Staleness:
  - 2 days for derived or snapshot files that drift quickly
  - 14 days for authored working files updated by daily operations
  - 30 days for stable reference files
- Contradictions across memory files, AGENTS.md, and current session context.
- Cross-file consistency for issue numbers, agent names, statuses, and active
  threads.
- Runtime split-brain: markers, AGENTS.md, skills, and memory should agree on
  the canonical runtime root.
- Session context drift: recent user statements should be reflected when they
  change durable operating context.
- Large memory/index files that are approaching platform truncation limits.
- Task/decision hygiene when task or decision files exist: overdue items,
  missing dates, completed items not archived, or decisions without rationale.

Use staleness thresholds as signals, not automatic rewrite mandates.

### 5. Analyze AGENTS.md

For global and project AGENTS.md files, check:

- Duplication between global and project instructions.
- Contradictions between global, project, and settings files.
- Runtime-root alignment with `.oacp`, `workspace.json`, and OACP memory paths.
- Missing rules for patterns manually enforced multiple times in the session.
- Bloat that can be trimmed without losing meaning.
- Outdated references to agents, paths, tools, or commands.
- Settings drift in `.codex/*` files.
- Git credential hygiene: flag embedded credentials in remotes and prefer
  per-command authentication according to the consuming repo's policy.

### 6. Report Findings

Present findings grouped by category. Use these severity tags:

| Tag | Meaning |
| --- | --- |
| `[FIX]` | Clear bug or error that should be fixed |
| `[STALE]` | Data is outdated |
| `[GAP]` | Something is missing |
| `[CONFLICT]` | Contradiction between files |
| `[BLOAT]` | Unnecessary content that can be trimmed |
| `[STRUCTURAL]` | Skill needs architectural work, not just a patch |

Sort findings within each category in this order:

`[FIX]` > `[CONFLICT]` > `[STRUCTURAL]` > `[GAP]` > `[STALE]` > `[BLOAT]`

If a category has no findings, say so explicitly. Keep the report scannable by
grouping obvious routine findings when separate bullets would not change the
approval decision.

### 7. Propose Changes

For each finding, propose a specific edit:

```text
1. [FIX] example-skill/SKILL.md:52
   File: ~/.codex/skills/example-skill/SKILL.md
   Change: Replace the stale command with the current command from AGENTS.md.
```

Ask:

```text
Which changes should I apply? (all / list numbers / none)
```

The approval prompt must be self-contained. Include:

- Recommended choice when one is clear
- Every proposed change number
- The target file or repo for each change
- The exact outcome the user is approving
- Allowed replies: `all`, `none`, or specific numbers

For routine cleanup, group related edits into one approval item when that makes
the decision easier.

### 8. Apply Approved Changes

For each approved change:

1. Read the target file if it is not already loaded.
2. Respect runtime namespaces; edit only files owned by Codex or shared files
   whose ownership is clear.
3. Before editing OACP runtime memory, acquire an advisory lock:

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

Then continue:

1. If the lock cannot be acquired, skip memory edits and report them as
   deferred.
2. Make the edit with a precise patch.
3. Confirm the change was applied.
4. Release the memory lock after memory edits:

```bash
rmdir "$LOCK_DIR" 2>/dev/null
```

### 9. Commit Changes Only When Requested

Commit only when the user explicitly asks for commits. Otherwise, apply edits
and report what changed.

Determine the correct repo for each file:

- If AGENTS.md is a symlink, commit to the target repo, not the symlink path.
- Runtime memory under `$OACP_HOME/projects/*/memory/` is usually not
  git-tracked; edit in place and report it separately.
- `~/.codex/projects/*/memory/` is usually not git-tracked; edit in place and
  report it separately.
- In a shared skills repo, keep commits scoped to the files owned by this
  runtime or clearly shared files approved by the user.

When commits are requested, group changes by repo and commit separately:

```bash
cd <repo-root>
git status -sb
git add <changed-files>
git commit -m "self-improve: <summary of changes>"
```

Do not push unless explicitly asked.

### 10. Summarize

End with a concise summary:

```text
Self-improvement complete:
- Reviewed: N skills, M memory files, K config files
- Findings: X total (N fixed, M flagged for manual review)
- Commits: [repo + commit hashes, or none]
```

## Notes

- This skill reviews and applies surgical fixes; it does not wholesale rewrite
  the operating system.
- For stale files flagged for manual review, describe what looks outdated
  without inventing current content.
- Keep the report scannable. If there are many findings, group by file.
- For repeated self-improve run lessons, promote durable guidance into the
  relevant section instead of growing a second procedure log.
