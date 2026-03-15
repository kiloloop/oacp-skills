---
name: self-improve
description: Review and improve the agent's operating system — skills, memory files, and CLAUDE.md configs. Identifies staleness, contradictions, gaps, and bloat, then proposes and applies fixes.
runtime: claude-code
---

# /self-improve — Agent Self-Improvement

Structured review of the agent's configuration and knowledge layer. Identifies staleness, contradictions, gaps, and improvement opportunities. Proposes changes, applies after approval, and commits to the correct repo.

## Arguments

- `/self-improve` — full review (session skills + memory + claude-md)
- `/self-improve skills` — review only skills that ran this session
- `/self-improve memory` — review memory files only
- `/self-improve claude-md` — review CLAUDE.md files only
- `/self-improve <skill-name>` — review a single specific skill (e.g., `/self-improve check-inbox`)

## Instructions

When the user runs `/self-improve`, execute these steps:

### 1. Parse target

Determine what to review based on the argument:

| Argument | Review scope |
|----------|-------------|
| (none) | skills + memory + claude-md |
| `skills` | Only skills that ran this session |
| `memory` | Only memory files |
| `claude-md` | Only CLAUDE.md files + settings |
| `<skill-name>` | That specific skill's SKILL.md |

### 2. Discover files

Build an inventory of all files to review based on the target scope.

#### Skills discovery

If scope includes skills:

**Session skills** — scan the conversation context for `/skill-name` invocations AND skills whose SKILL.md was edited this session. Both invoked and edited skills may need review.

**Locate each skill's SKILL.md** — check these paths in order:

1. Project-scoped: `./.claude/skills/<name>/SKILL.md`
2. Global: `~/.claude/skills/<name>/SKILL.md`
3. Shared skills repo (if configured)

If the skill exists in multiple locations, note all copies (they may need syncing).

If `/self-improve <skill-name>` targets a specific skill, review it directly regardless of whether it ran this session.

#### Memory discovery

If scope includes memory:

Scan for memory files in these locations:

1. Project-level `memory/` directory relative to the repo root
2. Claude Code project memory at `~/.claude/projects/<current-project>/memory/`
3. OACP runtime project memory at `$OACP_HOME/projects/<project>/memory/`

Read whatever memory files exist. The set varies by project.

Check modification dates:

```bash
stat -f "%m %N" <memory-dir>/*.md
```

#### CLAUDE.md discovery

If scope includes claude-md:

- Global: `~/.claude/CLAUDE.md` (always included)
- Project: `./CLAUDE.md` in the current repo root (if it exists) — **check if it's a symlink** (`ls -la`) and note the target repo for commits
- Project settings: `.claude/settings.json`, `.claude/settings.local.json` (if present)

### Parallel analysis (optional)

For full reviews with many files (10+), consider spawning parallel subagents to analyze different file groups rather than reading everything inline. This prevents context flooding.

**Scale by file count**: Split files across subagents (~5-7 files each). Each returns a structured findings report. The main agent compiles, deduplicates, and presents.

If your runtime does not support subagent spawning, analyze files sequentially — the workflow still works, just slower for large inventories.

### 3. Analyze — Skills

For each skill SKILL.md in scope, check:

- **Post-run lessons**: What worked vs what broke during the run this session. Add new entries to a "Learned from runs" or "Notes" section if the skill has one.
- **Contradiction with memory/config**: Instructions that contradict known patterns
- **Missing safety rules**: Edge cases exposed by the run (weekends, empty data, missing files)
- **Outdated references**: File paths, script names, argument flags, or repo URLs that no longer match the actual codebase
- **Multi-copy drift**: If the skill exists in multiple locations, diff them and flag divergence

#### 3b. Structural health gate

After surface checks, evaluate whether a skill needs **structural** work (not just patches):

**Pre-analysis triggers** (check during Step 3):

- **Output format drift** — the skill's format spec doesn't match the actual output it generates
- **Approaching 500 lines** — skill needs reference extraction before it can grow
- **Missing modes** — user manually does operations the skill should handle
- **"Learned from runs" > 5 entries** — lessons accumulating without being incorporated

**Post-analysis triggers** (check after Step 3 completes):

- **3+ findings on a single skill** — suggests systemic issues, not isolated bugs

If any structural trigger fires, tag the skill as `[STRUCTURAL]` in the report and recommend deeper analysis rather than surface patches.

**Skip this gate** if the skill is <100 lines (too small to have structural problems).

### 4. Analyze — Memory

For each memory file, check:

- **Staleness**: Use tiered thresholds based on file type (all use `stat` dates from discovery):
  - **2 days**: Derived/snapshot files (e.g., execution logs, dispatch records) — computed state that drifts quickly
  - **14 days**: Authored working files (e.g., priorities, tasks, agent lists) — updated by daily ops
  - **30 days**: Stable reference files (e.g., company info, repo lists) — rarely change, that's expected
  Flag with the file name and days since last update.
- **Contradictions**: Cross-reference between files — e.g., priorities say X is top priority but projects show it blocked; tasks have an item that decisions say was cancelled
- **Cross-file consistency**: Cross-reference issue numbers, agent names, and statuses across memory index, tasks, projects, priorities, and config files. An issue marked "Done" in one file but still listed as active in another is a `[CONFLICT]`.
- **Session context drift**: Check conversation history for user statements like "I removed X" or "we stopped using Y" and verify memory files reflect those changes
- **Memory index hygiene**: Count lines in the memory index file. If approaching platform truncation limits, flag and suggest content to move to topic files.

### 5. Analyze — CLAUDE.md

For global and project CLAUDE.md files, check:

- **Duplication**: Rules or instructions that appear in both global and project CLAUDE.md. Project should only contain project-specific rules.
- **Contradictions**: Rules in one file that conflict with another
- **Missing rules**: Patterns manually enforced 3+ times in recent session history that aren't codified. Check conversation context for repeated manual corrections.
- **Bloat**: Unnecessary verbosity. Can sections be trimmed without losing meaning?
- **Outdated references**: Agent names, file paths, project lists, tool names that no longer exist
- **Settings drift**: Check settings files at different precedence levels. Lower-precedence files may be silently overridden — check for conflicts.

### 6. Report findings

Present findings grouped by category. Use these severity tags:

| Tag | Meaning |
|-----|---------|
| `[FIX]` | Clear bug or error — should be fixed |
| `[STALE]` | Data is outdated |
| `[GAP]` | Something is missing |
| `[CONFLICT]` | Contradiction between files |
| `[BLOAT]` | Unnecessary content, can be trimmed |
| `[STRUCTURAL]` | Skill needs architectural work — deeper analysis needed |

Format:

```
## Self-Improvement Report

### Skills
- [FIX] <skill>/SKILL.md:<line> — <description>
- [GAP] <skill>/SKILL.md — <description>

### Memory
- [STALE] <file>.md — last updated N days ago
- [CONFLICT] <file1> vs <file2> — <description>

### CLAUDE.md
- [BLOAT] <file> — <description>
- [GAP] <file> — <description>
```

**Sort findings by severity** within each category: `[FIX]` > `[CONFLICT]` > `[STRUCTURAL]` > `[GAP]` > `[STALE]` > `[BLOAT]`. Group clusters of routine findings under a single summary line to keep the report scannable.

If a category has no findings, say "No issues found" and move on.

### 7. Propose changes

For each finding, propose a specific edit:

```
### Proposed Changes

1. [FIX] <skill>/SKILL.md:<line>
   - File: <path>
   - Change: <description>

2. [STALE] <file>.md
   - File: <path>
   - Change: <description or flag for manual review>
```

For clusters of routine fixes (stale dates, obvious duplicates), group them under a single approval item to reduce cognitive overhead.

Ask: "Which changes should I apply? (all / list numbers / none)"

### 8. Apply approved changes

For each approved change:

1. Read the target file (if not already loaded)
2. Make the edit using the Edit tool
3. Confirm the change was applied

### 9. Commit changes

Group changes by repo and commit separately:

**Determine the correct repo for each file:**

- If CLAUDE.md is a symlink, commit to the **target repo**, not the symlink location
- OACP runtime memory files (`$OACP_HOME/projects/*/memory/`) are **not git-tracked** — skip commit, just apply edits
- Claude Code project memory (`~/.claude/projects/*/memory/`) are **not git-tracked** — skip commit, just apply edits
- Global `~/.claude/CLAUDE.md` is not version-controlled — skip commit, just apply the edit

**Git-tracked files** — commit per repo:

```bash
cd <repo-root>
git add <changed-files>
git commit -m "self-improve: <summary of changes>"
```

Do NOT push unless explicitly asked.

**Namespace discipline (shared skills repo):** Only edit files under your own runtime's namespace (e.g., `claude/`). Never directly edit files under another runtime's namespace. If multi-copy drift is found in another runtime's files, send an inbox message to that runtime's agent instead of editing directly.

**Memory file locking:** Before editing OACP runtime memory files, acquire an advisory lock to prevent concurrent writes:

```bash
LOCK_DIR="$OACP_HOME/projects/${PROJECT}/.memory-write.lock"
# Check for stale lock (>10 min old)
if [ -d "$LOCK_DIR" ]; then
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR") ))
  if [ "$LOCK_AGE" -gt 600 ]; then
    rmdir "$LOCK_DIR" 2>/dev/null
  fi
fi
# Acquire
if mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Lock acquired"
else
  echo "LOCKED — deferring memory edits"
fi
```

Release after all edits complete:

```bash
rmdir "$OACP_HOME/projects/${PROJECT}/.memory-write.lock" 2>/dev/null
```

### 9b. Handle deferred findings

If any findings were NOT applied (user said "none" or skipped them), decide where they go:

**Session debrief** (default for transient issues):

- Stale timestamps, tense fixes, formatting
- Routine memory hygiene (completed tasks not archived, missing dates)
- Anything the daily ops loop will naturally fix

**Issue tracker** (only for persistent structural problems):

- Skill bugs, config conflicts, missing capabilities
- Cross-repo inconsistencies that won't self-heal
- Changes requiring multi-session tracking

Never file issues for transient staleness findings — they become stale within 1-2 sessions as daily ops refreshes the same files.

### 10. Summary

```
Self-improvement complete:
- Reviewed: N skills, M memory files, K config files
- Findings: X total (N fixed, M flagged for manual review)
- Commits: [list repos + commit hashes]
```

## Notes

- This skill reviews, it does not rewrite. Changes should be surgical, not wholesale rewrites.
- For stale files flagged for manual review, note what looks outdated but don't invent new content — the user knows the current state better.
- Keep the report scannable. If there are 20+ findings, group by file rather than listing each individually.
- Memory files flagged `[STALE]` may be intentionally stable (e.g., company info rarely changes). Use the tiered thresholds as a signal, not a mandate.
- Ensure your runtime has filesystem access to `$OACP_HOME` for reading/writing memory files and inbox paths.
