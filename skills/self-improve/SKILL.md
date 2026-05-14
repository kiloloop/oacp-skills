---
name: self-improve
description: Review and improve the agent's operating system — skills, memory files, CLAUDE.md configs, and session-friction patterns. Identifies staleness, contradictions, gaps, bloat, and behavioral patterns the user had to correct mid-session, then proposes and applies fixes.
---

# /self-improve — Agent Self-Improvement

Structured review of the agent's configuration and knowledge layer. Identifies staleness, contradictions, gaps, and improvement opportunities. Proposes changes, applies after approval, and commits to the correct repo.

## Arguments

- `/self-improve` — full review (session skills + memory + claude-md + friction)
- `/self-improve skills` — review only skills that ran this session
- `/self-improve memory` — review memory files only
- `/self-improve claude-md` — review CLAUDE.md files only
- `/self-improve friction` — review only session-friction patterns
- `/self-improve <skill-name>` — review a single specific skill (e.g., `/self-improve check-inbox`)

## Instructions

When the user runs `/self-improve`, execute these steps:

### 1. Parse target

Determine what to review based on the argument:

| Argument | Review scope |
|----------|-------------|
| (none) | skills + memory + claude-md + friction |
| `skills` | Only skills that ran this session |
| `memory` | Only memory files |
| `claude-md` | Only CLAUDE.md files + settings |
| `friction` | Only session-friction patterns (Step 4.5) |
| `<skill-name>` | That specific skill's SKILL.md |

### 2. Discover files

Build an inventory of all files to review based on the target scope.

#### Skills discovery

If scope includes skills:

**Session skills** — scan the conversation context for `/skill-name` invocations AND skills whose SKILL.md was edited this session. Both invoked and edited skills may need review.

**Locate each skill's SKILL.md** — check these paths in order:

1. Project-scoped: `./.claude/skills/<name>/SKILL.md`
2. Global: `~/.claude/skills/<name>/SKILL.md`
3. Shared skills repo (if your runtime stages skills from a separate checkout)

If the skill exists in multiple locations, note all copies (they may need syncing).

If `/self-improve <skill-name>` targets a specific skill, review it directly regardless of whether it ran this session.

#### Memory discovery

If scope includes memory:

Scan for memory files in these locations:

1. Project-level `memory/` directory relative to the repo root — use `command ls <memory-dir>/*.md` or `command find <memory-dir> -name '*.md' -type f`
2. Claude Code project memory at `~/.claude/projects/<current-project>/memory/`
3. OACP runtime project memory at `$OACP_HOME/projects/<project>/memory/` (defaults to `~/oacp/projects/<project>/memory/` when `$OACP_HOME` is unset)

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

#### Same-day repeat — narrow scope

Before discovering files, check whether a prior self-improve already ran on this project today. Multi-session days re-run the same static-file analysis against unchanged thresholds — wasteful subagent tokens for findings that already got cleared hours earlier.

```bash
PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
DATE=$(date +%Y%m%d)
DEBRIEF="<your debrief dir>/$PROJECT/$DATE/<runtime>.md"   # adjust path to your debrief layout
[ -f "$DEBRIEF" ] && command grep -q "## Self-Improvement Report" "$DEBRIEF" && echo "PRIOR_PASS"
```

If a prior pass exists, narrow the full-review scope to:

- **Skills**: only skills invoked since the last debrief session header
- **Memory**: only files with `mtime` newer than the prior debrief's session-start timestamp
- **CLAUDE.md**: skip unless the session edited it
- **Friction**: always run (Step 4.5) — fresh signal each session

Skip the full memory sweep and the parallel subagents below. Inline analysis is sanctioned in this mode, not a deviation. Note in the report header: "Narrow scope (same-day repeat — prior pass at HH:MM)."

### Parallel analysis subagents

For full reviews (memory + claude-md) **without a prior same-day pass**, spawn parallel review subagents rather than reading all files inline. With 10+ memory files, inline analysis floods the main context.

**Scale subagents by file count**: Split memory files across multiple agents (~5-7 files per agent). For a 14-file memory directory, spawn 2-3 memory subagents plus 1 CLAUDE.md subagent.

Each subagent returns a structured findings report. The main agent compiles, deduplicates, and presents.

If your runtime does not support subagent spawning, analyze files sequentially — the workflow still works, just slower.

### 3. Analyze — Skills

For each skill SKILL.md in scope, check:

- **Post-run lessons**: What worked vs what broke during the run this session. Add new entries to a "Learned from runs" or "Notes" section if the skill has one.
- **First-run retrospective**: If a skill was **created AND executed in the same session**, do a thorough execution retrospective — don't just check the SKILL.md as a static document. Walk through the actual execution in conversation context and diff what the skill prescribed vs what actually happened. Look for:
  - Steps that required manual intervention not covered by the skill
  - Output format mismatches
  - External constraints discovered at runtime
  - Data consistency issues the skill didn't check for
  - Tooling surprises
  First runs surface gaps that static review cannot. Prioritize this over routine staleness/contradiction checks.
- **Contradiction with MEMORY.md**: Instructions that contradict known project patterns
- **Missing safety rules**: Edge cases exposed by the run (weekends, empty data, missing files, sparse history)
- **Outdated references**: File paths, script names, argument flags, or repo URLs that no longer match the actual codebase
- **Multi-copy drift**: If the skill exists in multiple locations, diff them and flag divergence. **Structural fix preferred**: When drift is found between a repo copy and a runtime copy at `~/.claude/skills/<name>`, check whether the directory is a plain copy rather than a symlink to the source. Prefer the structural fix:

  ```bash
  rm -rf ~/.claude/skills/<name>
  ln -s <source-repo>/<name> ~/.claude/skills/<name>
  ```

  over per-file sync. After fixing one, audit ALL siblings in the same parent directory — if one drifted, others likely did too.
- **Verify quantitative claims**: When findings reference counts ("appeared N times"), durations ("X days stale"), or patterns ("recurring since"), verify against actual data (prior retros, git log, file timestamps) before including in the report. Don't estimate from memory.

#### 3b. Structural health gate

After surface checks, evaluate whether a skill needs **structural** work (not just patches). This gate has two phases:

**Phase 1 (pre-analysis — check during Step 3)**:

- **Output format drift** — the skill's format spec doesn't match the actual output it generates (sections users manually added that a `--refresh` would blow away)
- **Approaching 500 lines** — skill needs reference extraction before it can grow
- **Missing modes** — user manually does operations the skill should handle (detected from session context)
- **Denormalization without validation** — skill generates redundant data across sections with no consistency check
- **"Learned from runs" > 5 entries** — lessons accumulating without being incorporated

**Phase 2 (post-analysis — check after Step 3 completes, before Step 6)**:

- **3+ findings on a single skill** — suggests systemic issues, not isolated bugs

If any structural trigger fires (either phase), tag the skill as `[STRUCTURAL]` in the report (Step 6) and:

1. Invoke a skill-architecture subagent (e.g., `skill-creator` in analysis-only mode) with a prompt focused on architecture, output-format consistency, missing modes, and reference-extraction opportunities. No evals or test cases — analysis only.
2. Include the subagent's findings in the Step 6 report under a `[STRUCTURAL]` section
3. Save the analysis to `<project>/drafts/<skill-name>-structural-review.md` for follow-up
4. **File an issue** (per Step 9b GH issue criteria — structural problems are persistent, not transient)

This avoids spending time on surface patches when the skill needs a redesign. The subagent runs in isolation to avoid flooding the main context.

**Skip this gate** if the skill is <100 lines (too small to have structural problems) or if a `drafts/<skill-name>-structural-review.md` already exists and is <7 days old (analysis already done recently).

### 4. Analyze — Memory

For each memory file, check:

- **Staleness**: Use tiered thresholds based on file type (all use `stat` dates from discovery):
  - **2 days**: Derived/snapshot files (e.g., execution logs, dispatch records) — computed state that drifts quickly
  - **14 days**: Authored working files (e.g., priorities, tasks, agent lists) — updated by daily ops
  - **30 days**: Stable reference files (e.g., company info, repo lists) — rarely change, that's expected
  Flag with the file name and days since last update.
- **Contradictions**: Cross-reference between files — e.g., priorities say X is top priority but projects show it blocked; tasks have an item that decisions say was cancelled
- **Cross-file consistency**: Explicitly cross-reference issue numbers, agent names, and statuses across the memory index, tasks, dispatches, projects, priorities, and config files. An issue marked "Done" in one file but still listed as active in another is a `[CONFLICT]`.
- **Session context drift**: Check conversation history for user statements like "I removed X" or "we stopped using Y" and verify memory files reflect those changes.
- **Memory index line count**: Count lines in the memory index file. If approaching the platform's truncation limit (Claude Code truncates after line 200), flag and suggest content to move to topic files.
- **tasks file hygiene** (if present):
  - Overdue items (past due date, not archived)
  - Items missing due dates that seem time-bound
  - Items in the wrong section
  - Completed items not yet archived
- **decisions file hygiene** (if present):
  - Decisions without dates
  - Decisions without rationale
  - Decisions older than 90 days — still relevant?
- **30-day untouched files**: Any memory file not modified in 30+ days — flag for review or deletion

### 4.5 Analyze — Session Friction

Behavioral patterns are easy to miss when only static files are reviewed. This pass scans the **current conversation** for friction signals (user corrections, redirects, reverts) and proposes rules when a pattern recurs without being covered by existing rules.

**Why this exists**: Steps 3-5 review static artifacts (skill files, memory files, CLAUDE.md). They miss behavioral friction — moments where the user had to correct the agent's approach mid-session. Friction recurs across sessions; codifying the rule once prevents the same correction next time.

**Phase A — Heuristic flag (inline, no subagent)**:

Scan user messages in the current session for correction patterns:

- **Negation/redirect openers**: "no", "actually", "wait", "stop", "hold on"
- **Explicit correction**: "that's wrong", "you misunderstood", "wrong [X]", "not [Y], [X]"
- **Mode disambiguation**: "I'm asking, not telling you to", "exploring", "decision or"
- **Reverts**: "undo", "revert", "remove that"
- **Factual corrections**: "X not Y", "should be X" (especially for dates, timezones, names)

For each flagged message, capture:

- The trigger phrase (verbatim user message excerpt)
- The action immediately preceding it (what behavior triggered the correction)
- Brief root-cause hypothesis (date/time, framing, sanitization, scope, decision-vs-exploration, fabricated data, wrong-product framing, etc.)

**Phase B — Cluster + cross-reference (LLM judgment)**:

1. Cluster flagged events by root cause.
2. For each cluster with **2+ events** in this session, cross-reference against existing rules in:
   - Global `~/.claude/CLAUDE.md`
   - Project `./CLAUDE.md` (if exists)
   - Skill SKILL.md files in scope
3. Classify each cluster:
   - **Covered + working** — rule exists, friction was a momentary slip. No action; mention so user knows the rule is doing its job.
   - **Covered but not enforced** — rule exists but friction recurred. Propose tightening (sharper trigger phrasing, moved earlier in the rule list, or escalated severity).
   - **Partial** — adjacent rule exists but doesn't cover this exact case. Propose extending it.
   - **Missing** — no rule covers this. Propose specific rule text + target file. Default targeting:
     - Cross-project behavioral pattern → global `~/.claude/CLAUDE.md`
     - Project-specific (memory writes, dispatch flow, project-specific framing) → project `./CLAUDE.md`
     - Skill-specific (only fires inside one skill's execution) → that skill's SKILL.md

**False-positive guards**:

- Skip if the correction is about a tool/system failure, not behavior ("no, the build failed differently")
- Skip mid-task refinements ("actually let's also do X") — these are scope additions, not corrections
- Single events go to debrief Next Actions (Step 9b), not propose-rule. Require **2+ in same session** for a `[FRICTION]` finding worth a rule proposal.
- If the user already pasted a fix during the session (e.g., "add this rule: ..."), credit it as resolved — don't re-propose.

**Skip this step entirely** when:

- `/self-improve <skill-name>` targets a single skill (focused review, not behavioral)
- `/self-improve skills` / `memory` / `claude-md` (scope flags exclude friction; only `(none)` or `friction` includes it)
- Session has fewer than ~10 user messages (not enough signal)

**Output**: feed into Step 6 with `[FRICTION]` tag. Include 1-2 verbatim evidence excerpts per cluster so the user can verify the pattern before approving a rule write.

### 5. Analyze — CLAUDE.md

For global and project CLAUDE.md files, check:

- **Duplication**: Rules or instructions that appear in both global and project CLAUDE.md. Project should only contain project-specific rules.
- **Contradictions**: Rules in one file that conflict with another.
- **Missing rules**: Friction-driven rule proposals come from Step 4.5 (Session Friction). Step 5 only flags rules that are *referenced but not defined* (e.g., a skill cites "Rule X" that doesn't exist in CLAUDE.md).
- **Bloat**: Unnecessary verbosity. Can sections be trimmed without losing meaning?
- **Outdated references**: Agent names, file paths, project lists, tool names that no longer exist.
- **Settings drift**: Check both `.claude/settings.json` and `.claude/settings.local.json` if they exist. `settings.local.json` overrides `settings.json` (precedence: local > project > global), so conflicts between the two are silent — the local file wins without warning. Check for sandbox settings vs CLAUDE.md rules, env var overrides (e.g., model aliases) that contradict documented defaults, and hook configurations that duplicate or conflict.

### 6. Report findings

Present findings grouped by category. Use these severity tags:

| Tag | Meaning |
|-----|---------|
| `[FIX]` | Clear bug or error — should be fixed |
| `[STALE]` | Data is outdated |
| `[GAP]` | Something is missing |
| `[CONFLICT]` | Contradiction between files |
| `[BLOAT]` | Unnecessary content, can be trimmed |
| `[STRUCTURAL]` | Skill needs architectural work — deeper analysis attached |
| `[FRICTION]` | Recurring behavioral pattern (2+ user corrections this session) not covered by existing rules — propose new or extended rule |

Format:

```text
## Self-Improvement Report

### Skills
- [FIX] <skill>/SKILL.md:<line> — <description>
- [GAP] <skill>/SKILL.md — <description>

### Memory
- [STALE] <file>.md — last updated N days ago
- [CONFLICT] <file1> vs <file2> — <description>
- [BLOAT] memory index at 195 lines — approaching 200-line truncation limit

### CLAUDE.md
- [BLOAT] Global CLAUDE.md repeats <rule> that's also in project CLAUDE.md
- [GAP] No rule for handling <pattern> despite N incidents in memory

### Friction
- [FRICTION] <root cause>: 2 events this session
  Evidence: <quote 1>, <quote 2>
  Existing rule: <rule reference> — covers, but agent skipped the prompt twice
  Proposed: <specific change>
- [FRICTION] No friction patterns detected for <category> this session
```

**Sort findings by severity** within each category: `[FIX]` → `[CONFLICT]` → `[STRUCTURAL]` → `[FRICTION]` → `[GAP]` → `[STALE]` → `[BLOAT]`. This ensures actionable bugs surface first and routine staleness sinks to the bottom. Group clusters of routine findings (multiple `[STALE]` dates, formatting fixes) under a single line like "Routine: 5 stale timestamps" to keep the report scannable.

If a category has no findings, say "No issues found" and move on.

### 7. Propose changes

For each finding, propose a specific edit:

```text
### Proposed Changes

1. [FIX] <skill>/SKILL.md:<line>
   - File: <path>
   - Change: <description>

2. [STALE] <file>.md
   - File: <path>
   - Change: <description or flag for manual review>

3. [BLOAT] <memory-index>.md
   - File: <path>
   - Change: Move <section> to a separate file, keep only summary references
```

For clusters of routine fixes (stale dates, obvious duplicates, baked-in lessons), group them under a single 'routine cleanup' approval item to reduce cognitive overhead.

Ask: "Which changes should I apply? (all / list numbers / none)"

### 8. Apply approved changes

For each approved change:

1. Read the target file (if not already loaded)
2. Make the edit using the Edit tool
3. Confirm the change was applied

### 9. Commit changes

Group changes by repo and commit separately.

**Determine the correct repo for each file**:

- If CLAUDE.md is a symlink, commit to the **target repo**, not the symlink location.
- OACP runtime memory files (`$OACP_HOME/projects/*/memory/`) are **not git-tracked** — skip commit, just apply edits.
- Claude Code project memory (`~/.claude/projects/*/memory/`) are **not git-tracked** — skip commit, just apply edits.

**Namespace discipline (shared skills repo)**: Only edit files under your own runtime's namespace (e.g., `claude/` and `shared/`). Never directly edit files under another runtime's namespace (`codex/`, `gemini/`, etc.). If multi-copy drift is found in another runtime's files, send an inbox `task_request` to that runtime instead of editing directly. This prevents merge conflicts when both runtimes run self-improve concurrently.

**Git-tracked files** — commit per repo:

```bash
cd <repo-root>
git stash --include-untracked                                  # stash applied edits — pull --rebase fails on a dirty worktree
git pull --rebase origin $(git rev-parse --abbrev-ref HEAD)    # sync before committing — prevents push conflicts with other runtimes
git stash pop                                                  # restore edits on top of updated base
git add <changed-files>
git commit -m "self-improve: <summary of changes>"
```

If pull-rebase fails (merge conflict), abort with `git rebase --abort`, pop the stash (`git stash pop`), warn the user, and skip commit for that repo. If stash pop conflicts, warn and leave changes in stash for manual resolution.

**Global `~/.claude/CLAUDE.md`**: Resolve the symlink before editing (the Edit tool refuses to write through symlinks; use `readlink` to find the real path). If the target is version-controlled, commit + push to that repo. Same pattern for `~/.claude/agents/*`, `~/.claude/hooks/*`, and other symlinked global config.

Do NOT push unless explicitly asked.

**Memory file locking**: Before editing OACP runtime memory files (`$OACP_HOME/projects/*/memory/`), acquire an advisory lock to prevent concurrent writes from other runtimes.

The lock spans multiple tool calls (Edit tool, not Bash), so `trap` cleanup doesn't work — each Bash invocation is a separate process. Use explicit acquire/release:

**Acquire** (before first Edit):

```bash
LOCK_DIR="$OACP_HOME/projects/${PROJECT}/.memory-write.lock"
# Check for stale lock (>10 min old)
if [ -d "$LOCK_DIR" ]; then
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR") ))
  if [ "$LOCK_AGE" -gt 600 ]; then
    rmdir "$LOCK_DIR" 2>/dev/null
  fi
fi
# Acquire lock
if mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Lock acquired"
else
  echo "LOCKED — deferring edits to debrief carry-over"
fi
```

If locked, skip all OACP runtime memory edits and note them as deferred in Step 9b.

**Release** (after all Edits complete — always run, even if edits fail):

```bash
rmdir "$OACP_HOME/projects/${PROJECT}/.memory-write.lock" 2>/dev/null && echo "Lock released" || echo "No lock to release"
```

### 9b. Handle deferred findings

If any findings from Step 6 were NOT applied (user said "none" or skipped them), decide where they go:

**Session debrief / next-actions** (default for transient issues):

- Stale timestamps, tense fixes, formatting cleanup
- Routine memory hygiene (completed tasks not archived, missing dates)
- Anything that the daily ops loop will naturally fix on the next pass

Write these to the session debrief's "Next Actions" section so the next daily-ops pass picks them up — no issue tracker entry needed.

**Issue tracker** (only for persistent structural problems):

- Skill bugs, config conflicts, missing capabilities
- Cross-repo inconsistencies that won't self-heal
- Changes requiring multi-session tracking or coordination

**Never file issues for transient staleness findings.** They become stale within 1-2 sessions as daily ops naturally refreshes the same files. If in doubt, use the debrief — it's cheaper to re-discover a finding than to manage a throwaway issue.

### 10. Summary

```text
Self-improvement complete:
- Reviewed: N skills, M memory files, K config files
- Findings: X total (N fixed, M flagged for manual review)
- Commits: [list repos + commit hashes]
```

## Notes

- This skill reviews, it does not rewrite. Changes should be surgical, not wholesale rewrites.
- For stale files flagged for manual review, note what looks outdated but don't invent new content — the user knows the current state better.
- `command find` for shell operations (some shells alias `find` to `fd`).
- `gh` and `git` commands may require `dangerouslyDisableSandbox: true` depending on your runtime's sandbox configuration.
- Keep the report scannable. If there are 20+ findings, group by file rather than listing each individually.
- Memory files flagged `[STALE]` may be intentionally stable (e.g., company info rarely changes). Use the 30-day threshold as a signal, not a mandate.
