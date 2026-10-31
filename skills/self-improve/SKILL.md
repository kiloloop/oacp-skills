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
- `--dry-run` — combines with any form above, and applies whenever `/wrap-up --dry-run` invokes this skill. Propose only: run Steps 1-7 and present the proposals without the approval ask — apply nothing, commit nothing, write no pass marker.

## Instructions

When the user runs `/self-improve`, execute these steps. `<skill-dir>` below is this skill's installed directory (e.g. `.claude/skills/self-improve`).

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
2. Global: `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/<name>/SKILL.md`
3. Shared skills repo (if your runtime stages skills from a separate checkout)

If the skill exists in multiple locations, note all copies (they may need syncing).

If `/self-improve <skill-name>` targets a specific skill, review it directly regardless of whether it ran this session.

#### Memory discovery

If scope includes memory, scan these locations and read whatever memory files exist (the set varies by project):

1. Project-level `memory/` directory relative to the repo root — use `command ls <memory-dir>/*.md` or `command find <memory-dir> -name '*.md' -type f`
2. Claude Code project memory at `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<current-project>/memory/`
3. OACP runtime project memory at `$OACP_HOME/projects/<project>/memory/` (`$OACP_HOME` defaults to `~/oacp`)

Print each file's age in whole days and its mtime in epoch seconds — Step 4's staleness tiers compare against the age, and the narrow scope below compares the epoch:

```bash
now=$(date +%s); for f in <memory-dir>/*.md; do m=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f"); echo "$(( (now - m) / 86400 ))d $m $f"; done
```

#### CLAUDE.md discovery

If scope includes claude-md:

- Global: `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md` (always included)
- Project: `./CLAUDE.md` in the current repo root (if it exists) — **check if it's a symlink** (`ls -la`) and note the target repo for commits
- Project settings: `.claude/settings.json`, `.claude/settings.local.json` (if present)

#### Same-day repeat — narrow scope

Before discovering files, check whether a prior self-improve already ran on this project today — multi-session days otherwise re-run the same static analysis against unchanged files. Run the check (and the Step 10 `append`) from inside the project's repository — its primary root or any of its worktrees: the script names the project from the cwd's repository, so a cwd drifted into a skill or memory dir reads and overwrites another project's marker.

```bash
bash <skill-dir>/scripts/pass_marker.sh check
```

It prints `PRIOR_PASS` if a completed pass already ran today — or yesterday when it is before 05:00 (a post-midnight session is still working the prior day), or yesterday within the last 12 hours (a pre-05:00 pass files under yesterday). "Today" is the user's day: dates follow `SELF_IMPROVE_TZ` (an IANA zone) when set, else the machine's local timezone — set it when the machine clock follows a travel location. The marker is written by Step 10 and is **machine-local** (`$OACP_HOME/state/` is not synced), so on a multi-machine day `NO_PRIOR_PASS` means no pass on *this* machine — check today's debriefs for a self-improve pass before running a full review.

If a prior pass exists, narrow the full-review scope to:

- **Skills**: only skills invoked since the prior debrief ended — its record's `ended_utc` in `$OACP_HOME/org-memory/debriefs/<project>/…` (the latest continuation segment, session id suffixed `2`, `3`, …, when there is one)
- **Memory**: only files with `mtime` newer than the prior debrief's `started_utc`. Compare epoch seconds, never an hour-only format, which makes prior-day files look same-day. A cluster of identical mtimes newer than that stamp is a prior pass's bulk write, not edits — the filter then passes every file, so fall back to the files this session read or edited
- **CLAUDE.md**: skip unless the session edited it
- **Friction**: always run (Step 4.5) — fresh signal each session

Skip the full memory sweep and the parallel subagents below. Note in the report header: "Narrow scope (same-day repeat — prior pass at HH:MM)."

### Parallel analysis subagents

For a full review (memory + claude-md, no same-day prior pass), fan out to parallel review subagents only when the surface is too large to read inline, because inline analysis of a large memory dir floods the main context. Measure first: `wc -c` the in-scope memory dirs — under ~25 KB total with no single file over ~8 KB, or a surface mostly read or edited already this session, stays inline. Split ~5-7 memory files per agent (a 14-file directory → 2-3 memory subagents plus 1 CLAUDE.md subagent). Each returns a structured findings report; the main agent compiles, deduplicates, and presents.

Before spawning, read [references/fanout-guards.md](references/fanout-guards.md) — briefing, collection, and verification guards that keep the fan-out from producing phantom findings.

When the session touched only part of a large memory dir, or the dir was bulk-curated within the last week (an mtime cluster), narrow memory to the files this session read or edited — possibly none — and offer the full fan-out as opt-in. A harness or user directive against spawning agents outranks the fan-out. State the ground for an inline or narrowed pass in the report header, with the measured size where it applies, and never present a narrowed pass as a full review. If your runtime does not support subagent spawning, analyze files sequentially — the workflow still works, just slower.

### 3. Analyze — Skills

For each skill SKILL.md in scope, check:

- **Post-run lessons**: What worked vs what broke during the run this session. Add new entries to a "Learned from runs" or "Notes" section if the skill has one. **Also ask what almost went wrong and was caught** — a self-corrected near-miss leaves no failure trace, so "what broke?" cannot surface it, yet it is often the session's highest-value finding. Mine three shapes: a result you disbelieved and re-checked, a tool that silently answered a different question than you asked, and a finding you nearly filed against someone else before refuting it yourself.
- **First-run retrospective**: If a skill was **created AND executed in the same session**, walk through the actual execution and diff what the skill prescribed vs what happened: steps needing manual intervention the skill didn't cover, output format mismatches, external constraints discovered at runtime, unchecked data consistency issues, tooling surprises. First runs surface gaps that static review cannot — prioritize this over routine staleness/contradiction checks.
- **Contract/validator rejections outrank static review**: if a script, schema, or validator the skill invokes rejected the session's output — a missing required field, an unsatisfied gate, a malformed artifact — that is a skill gap by definition: the skill told you to produce something the contract refuses. These need no argument, only the error text. A skill can drift out of date with a contract it does not own without any of its own text becoming inconsistent.
- **Rule-shaped findings**: before a finding proposes or restates a rule, run the first section of [references/rule-checks.md](references/rule-checks.md) — count where the lesson already lives (restating a rule vs extending a catalogue), build a controlled fixture for any claim about tool behavior, and propose an executed check when the rule was already there and missed anyway.
- **Contradiction with MEMORY.md**: Instructions that contradict known project patterns
- **Missing safety rules**: Edge cases exposed by the run (weekends, empty data, missing files, sparse history)
- **Outdated references**: File paths, script names, argument flags, or repo URLs that no longer match the actual codebase
- **Multi-copy drift**: If the skill exists in multiple locations, diff them and flag divergence. When a runtime copy is meant to track a source checkout but is a plain copy, propose replacing it with a symlink to the source rather than syncing files one by one, and hand the user the removal of the copied directory instead of deleting it yourself. After fixing one, audit its siblings in the same parent directory — if one drifted, others likely did too. Test symlink-ness with `readlink <path>`: a directory listing follows the link and reads like a plain copy.
- **Verify quantitative claims**: When findings reference counts ("appeared N times"), durations ("X days stale"), or patterns ("recurring since"), verify against actual data (prior retros, git log, file timestamps) before including in the report. Don't estimate from memory.
- **Citation target classification**: before flagging a citation as dead, classify it — a local file path (verify by ls/grep) vs an external published document (spec, RFC, vendor page). Absence of a local match doesn't kill an external target; verify externally or report as "unverifiable, not necessarily dead".
- **Rendered-skill findings must be re-verified on disk**: the Skill tool substitutes positional arguments (`$1`, `$ARGUMENTS`) at render time, so in-context text can differ from the file. Before proposing an edit sourced from rendered text, grep the file for the quoted defect and check `git log --since=today` for same-day commits by other sessions — either can kill the finding. At apply time, also run `git status` on the file: dirty with a fresh mtime means another session is still writing it — skip the edit, keep the file out of your commit, and report the finding as covered by that session's in-progress work.

#### 3b. Structural health gate

After surface checks, evaluate whether a skill needs **structural** work (not just patches). This gate has two phases:

**Phase 1 (pre-analysis — check during Step 3)**:

- **Output format drift** — the skill's format spec doesn't match the actual output it generates (sections users manually added that a `--refresh` would blow away)
- **Approaching 500 lines or ~25 KB** — the skill needs reference extraction before it can grow. A line count alone misses skills written as long unwrapped paragraphs, so measure bytes on every pass and tag every hit:

  ```bash
  wc -c <skills-dir>/*/SKILL.md | awk '$1 > 25000 && $2 != "total"'
  ```

- **Missing modes** — user manually does operations the skill should handle (detected from session context)
- **Denormalization without validation** — skill generates redundant data across sections with no consistency check
- **"Learned from runs" > 5 entries** — lessons accumulating without being incorporated; the fix is folding them into the numbered steps

**Phase 2 (post-analysis — check after Step 3 completes, before Step 6)**:

- **3+ findings on a single skill** — suggests systemic issues, not isolated bugs

If any structural trigger fires (either phase), tag the skill as `[STRUCTURAL]` in the report (Step 6) and:

1. Invoke a skill-architecture subagent (e.g., `skill-creator` in analysis-only mode) with a prompt focused on architecture, output-format consistency, missing modes, and reference-extraction opportunities. No evals or test cases — analysis only.
2. Include the subagent's findings in the Step 6 report under a `[STRUCTURAL]` section
3. Save the analysis to `<project>/drafts/<skill-name>-structural-review.md` for follow-up
4. **File an issue** (per Step 9b criteria — structural problems are persistent, not transient)

This avoids spending time on surface patches when the skill needs a redesign. The subagent runs in isolation to avoid flooding the main context.

**Skip this gate** if the skill is under ~5 KB (too small to have structural problems), if a `drafts/<skill-name>-structural-review.md` already exists and is <7 days old, or if an open issue already tracks the restructure, for this skill alone or with its siblings — name it in the report, and comment the measured size and an extraction candidate there instead of running a separate analysis. Read the issue's body and comments before proposing that comment: a skill the issue already lists gets no new comment, and a growth note repeated every pass is noise, not tracking.

### 4. Analyze — Memory

For each memory file, check:

- **Staleness**: Use tiered thresholds based on file type (all use `stat` dates from discovery):
  - **2 days**: Derived/snapshot files (e.g., execution logs, dispatch records) — computed state that drifts quickly
  - **14 days**: Authored working files (e.g., priorities, tasks, agent lists) — updated by routine sessions
  - **30 days**: Stable reference files (e.g., company info, repo lists) — rarely change, that's expected

  Flag with the file name and days since last update. If mtimes cluster suspiciously (several files sharing one timestamp) or the directory lives on a synced machine, verify via `git log -1 --format=%ad -- <file>` where the directory is git-tracked — a bulk filesystem touch resets mtimes independent of edits.
- **Re-read before asserting staleness**: on multi-agent projects another runtime can rewrite the same memory dir mid-session, so an early-session read is stale evidence by the time this step runs. Never source a `[STALE]` or `[GAP]` finding from an in-context read taken more than a few tool calls ago — re-read the file and `stat` its mtime at analysis time.
- **Contradictions**: Cross-reference between files — e.g., priorities say X is top priority but projects show it blocked; tasks have an item that decisions say was cancelled
- **Cross-file consistency**: Explicitly cross-reference issue numbers, agent names, and statuses across the memory index, tasks, dispatches, projects, priorities, and config files. An issue marked "Done" in one file but still listed as active in another is a `[CONFLICT]`.
- **Session context drift**: Check conversation history for user statements like "I removed X" or "we stopped using Y" and verify memory files reflect those changes.
- **Memory index line count**: Count lines in the memory index file. If approaching the platform's truncation limit (Claude Code truncates after line 200), flag and suggest content to move to topic files.
- **tasks file hygiene** (if present): overdue items, time-bound items missing due dates, items in the wrong section, completed items not yet archived
- **decisions file hygiene** (if present): decisions without dates or rationale; decisions older than 90 days — still relevant?
- **30-day untouched files**: Any memory file not modified in 30+ days — flag for review or deletion

### 4.5 Analyze — Session Friction

Steps 3-5 review static artifacts and miss behavioral friction — moments where the user had to correct the agent's approach mid-session. Friction recurs across sessions; codifying the rule once prevents the same correction next time.

**Phase A — flag (inline, no subagent)**:

Friction evidence is what the human did: typed turns, mid-turn interrupts, and decisions delivered through the tool layer (a declined Bash command, a denied permission prompt, a rejected `AskUserQuestion`). Tool-layer rejections count toward the thresholds like typed turns and are often the sharpest signal — the user rejected the framing before spending a turn explaining why. Machine rows — `<system-reminder>` blocks, Monitor/task notifications, injected skill bodies, MCP instructions, hook output — are not evidence and never count.

List the genuine turns mechanically:

```bash
python3 <skill-dir>/scripts/friction_turns.py ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<project-slug>/<session-uuid>.jsonl [--after <ISO timestamp> | --after HH:MM [--tz <zone>]]
```

The script keeps typed `user` rows and mid-turn queue enqueues (tagged `[mid-turn]` — an interrupt redirects a running turn, so these skew toward corrections), drops known wrapper shapes (the list lives in the script; extend it, with a fixture in `tests/`, when a new one appears), dedups copies, and prints the compaction summary's pre-compaction user messages separately. Then:

- Read the list before trusting the count — an unseen wrapper can survive, and the count gates the thresholds below.
- Under narrow scope, slice to this arc (a resumed transcript can span several): pass the prior debrief record's `ended_utc` as it stands. A bare `HH:MM` is read in `--tz` (default: local), so a time read off another zone's clock slices the wrong span without error. The closing count line prints the resolved cut-off — check it.
- After a compaction, scan the printed pre-compaction list too; those turns exist nowhere else.
- A `[cancelled]` row (Esc before the model answered) never reached the assistant: read it as intent history, not a correction the agent missed — the turn that follows usually carries the redirect. Confirm with the user before it enters a finding.
- Add tool-layer rejections by hand from the transcript.

Then flag correction signals — negation/redirect openers ("no", "actually", "wait", "stop", "hold on"), explicit corrections ("that's wrong", "you misunderstood", "not Y, X"), mode disambiguation ("I'm asking, not telling you to", "exploring"), reverts ("undo", "revert", "remove that"), and factual corrections ("should be X", especially dates, timezones, names). For each flagged event, capture the trigger (verbatim excerpt), the action immediately preceding it, and a brief root-cause hypothesis (date/time, framing, scope, decision-vs-exploration, fabricated data, wrong-product framing, etc.).

**Phase B — cluster + cross-reference (LLM judgment)**: cluster flagged events by root cause. For each cluster with **2+ events this session**, cross-reference existing rules (global `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`, project `./CLAUDE.md`, in-scope SKILL.md files) and classify:

- **Covered + working** — rule exists, friction was a momentary slip. No action; mention it so the user knows the rule is doing its job.
- **Covered but not enforced** — rule exists but friction recurred. Propose tightening (sharper triggers, earlier placement, escalated severity) or an executed check ([references/rule-checks.md](references/rule-checks.md)).
- **Partial** — an adjacent rule doesn't cover this exact case. Propose extending it.
- **Missing** — propose specific rule text + target file: cross-project behavior → global `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`; project-specific (memory writes, dispatch flow, framing) → project `./CLAUDE.md`; fires only inside one skill → that SKILL.md.

**False-positive guards**: skip corrections about tool/system failures ("no, the build failed differently") and mid-task scope additions ("actually let's also do X"); single events go to debrief Next Actions (Step 9b), not rule proposals — require **2+ in the same session**; if the user already supplied the fix in-session ("add this rule: ..."), credit it as resolved.

**Skip this step entirely** when scope targets a single skill or a non-friction flag (`skills` / `memory` / `claude-md`), or the session has fewer than ~10 genuine user turns — **unless** ≥2 of them are `[mid-turn]`, ≥2 typed corrections share one root cause, or ≥2 tool-layer rejections share one root cause. Rejections are not in the script's count, so scan the transcript for them before letting the count skip this step.

**Output**: feed into Step 6 with `[FRICTION]` tag. Include 1-2 verbatim evidence excerpts per cluster so the user can verify the pattern before approving a rule write.

### 4.6 Analyze — Standing-rule compliance

Steps 3-4.5 ask whether the *files* are right. This step asks whether **what the session did** complied with rules that already existed — a violation leaves no trace in any file: nothing reads wrong and nobody typed a correction.

For each domain the session acted in (released, promoted, merged, published, dispatched, changed a shared contract), grep for a governing rule *before* concluding the session was clean — in every rule source [references/rule-checks.md](references/rule-checks.md) lists (org memory and the installed skills):

```bash
command grep -n -A3 '^### ' "$OACP_HOME/org-memory/rules.md" "$OACP_HOME/org-memory/decisions.md" | command grep -iE -A3 '<domain keyword>'
command grep -rniE '<domain keyword>' "$OACP_HOME/org-memory/events/" --include='<YYYYMMDD>-*' --include='<YYYYMMDD>-*'   # today's and yesterday's UTC dates
command grep -rn '<domain keyword>' <skills-dir>/
```

- **Skill hit** — rules learned by doing the work live in the skill that runs it, so an org-memory-only grep passes clean on exactly the rules the session most likely executed past. A skill-rule hit is a compliance failure, not a discovery.
- **Org-memory-only hit** — the rule exists but the skill that owns the work has no guard for it: record the deviation *and* propose the guard.
- **Project records** — when the session executed a dispatched or tracked item, also grep `$OACP_HOME/projects/<project>/memory/known_debt.md` and `open_threads.md` for its subject; an earlier fix plan can name parts of the fix the brief did not.

Under `/wrap-up`, step 2b's existing-rule check runs first, while the session's claims are in hand, and is the primary detector; this step is the backstop for sessions that write no events. When 2b already surfaced a deviation, carry it into the report with 2b named as the source.

Read the rule's rationale against what you did. Complied, or no rule reaches the case → record nothing. **Contradicted a standing rule** → a finding of the highest-value kind, because it is the class that ships: report it against the session and against the skill that should have gated it. Never resolve it by editing the rule to match what happened (the opposite-prescription check in [references/rule-checks.md](references/rule-checks.md)) — surface the deviation, propose the guard, and let the user rule on both; typically the rule stands and the shipped artifact stands as a recorded deviation.

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

Before writing the approval ask:

- **Group routine fixes** (stale dates, obvious duplicates, baked-in lessons) under a single "routine cleanup" approval item.
- **Verify a `[BLOAT]` deletion** justified as "duplicated in X": read X and diff item-by-item — don't delete without verifying full coverage. When copying content to an archive before trimming, count items on both sides after the copy.
- **Verify a proposed destination before naming it**: when an option moves content to a target file, check the target's section headings (`command grep -n '^## '`) and confirm a fitting section exists. An issue you offer to file is a destination too — search the tracker's open issues first (`gh issue list --repo <repo> --search '<keywords>'`); another session may have filed it minutes earlier. A skill you name as the fix is a destination too — confirm it is in this session's skill listing, and dispatch the work to its owning agent when it belongs to another one.
- **Run the rule checks** in [references/rule-checks.md](references/rule-checks.md) on every finding that adds or changes a rule: the existing-rule grep (including whether the target already prescribes the *opposite* of what you did — a deviation to record, not a gap to ratify), collapsing findings that share a root cause, and tree-wide scoping of a stale external fact so the ask states the true site count.

Ask: "Which changes should I apply? (all / list numbers / none)"

"all" approves edits; it cannot pick between options. An item that needs a ruling — option (a) vs (b), or whether to record a deviation — goes in its own question, separate from the numbered edits, and names the option taken if left unanswered.

**Under an active envelope** (an admitted OACP task still running in this session), offer **defer to the resumed session** as the default apply option and name it as the one taken if left unanswered: skill and memory edits count against the task's `files_touched` budget, the hook denies a destructive token quoted in an edit, and an approval given mid-task lands the changes inside another task's audit trail. Carry the deferred findings in the project's `open_threads.md` so the next session applies them once the envelope clears.

### 8. Apply approved changes

**Memory file locking**: before the first edit to shared OACP runtime memory (`$OACP_HOME/projects/<project>/memory/`), acquire the advisory lock, and hold it through Step 9b, whose carry-over can write `open_threads.md` — release on abort too. The lock spans several tool calls, so it is explicit rather than `trap`-based; locks older than 10 minutes are broken automatically.

```bash
bash <skill-dir>/scripts/memory_lock.sh acquire <project>
bash <skill-dir>/scripts/memory_lock.sh release <project>
```

If acquire prints `LOCKED`, skip all OACP runtime memory edits, `open_threads.md` included, and list the deferred edits in the Step 10 summary instead.

For each approved change:

1. Read the target region if its text is not already in context — an anchor composed from memory misses — and never write through a symlink: `readlink` and edit the real target
2. Make the edit using the Edit tool — before any insertion or scripted assert-replace batch, follow [references/apply-mechanics.md](references/apply-mechanics.md), which also covers sandbox-denied paths and executable edits
3. **An edit to an executable — a script, hook, or guard — is not applied until you run it**, on both the path you fixed and the path that already worked (details in the reference)
4. **A stale claim usually lives in more than one place** — after editing the body, grep the whole file for restatements. Memory files carry a claim three-plus times: the frontmatter `description:` (the field recall matches on), a summary or "How to apply" line, and a one-line hook in the memory index. Skills restate rules between a step body and `## Notes`. Grep the skill's whole directory, not just SKILL.md, when the edited rule is a contract someone downstream must satisfy — a `references/` file is read by a different consumer (a subagent prompt, an extracted recipe) that never sees the corrected text
5. **Write the rule in present tense and keep its provenance out of the step body** — dates, PR numbers, and recurrence tallies go in the commit message, not beside the rule: step bodies load on every trigger, and a dated parenthetical keeps reading as current state after it stops being true. Keep a concrete case inline only when it teaches something the rule's wording cannot, as a short example without IDs

### 9. Commit changes

Skip under a dry run ([Arguments](#arguments)). Group changes by repo and commit separately.

**Determine the correct repo for each file**:

- If CLAUDE.md is a symlink, commit to the **target repo**, not the symlink location.
- OACP runtime memory (`$OACP_HOME/projects/*/memory/`) and Claude Code project memory (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/*/memory/`) are **not git-tracked** by this flow — skip commit, just apply edits.

**Namespace discipline (shared skills repo)**: Only edit files under your own runtime's namespace (e.g., `claude/` and `shared/`). Never directly edit files under another runtime's namespace (`codex/`, `gemini/`, etc.). If multi-copy drift is found in another runtime's files, send an inbox `task_request` to that runtime instead of editing directly. This prevents merge conflicts when both runtimes run self-improve concurrently.

**Git-tracked files** — commit per repo:

```bash
git -C <repo-root> pull --rebase --autostash origin "$(git -C <repo-root> rev-parse --abbrev-ref HEAD)"   # sync first; autostash carries dirty files over the rebase
git -C <repo-root> add <changed-files>
git -C <repo-root> commit -m "self-improve: <summary of changes>"
```

If the rebase conflicts, run `git -C <repo-root> rebase --abort`, warn the user, and skip commit for that repo. If the autostash re-apply conflicts, git keeps the stash entry — warn and leave it for manual resolution.

**Global `CLAUDE.md`** in your Claude Code config dir (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}`): Resolve the symlink before editing (`readlink` finds the real path). If the target is version-controlled, commit to that repo. Same pattern for the config dir's `agents/*`, `hooks/*`, and other symlinked global config.

Do NOT push unless explicitly asked.

### 9b. Handle deferred findings

If any findings from Step 6 were NOT applied (user said "none" or skipped them), decide where they go:

- **Session debrief "Next Actions"** (default, for transient issues): stale timestamps, tense or formatting fixes, routine memory hygiene — anything later sessions naturally refresh. **Under `/wrap-up` the debrief is already published** (it runs before this pass, and the record is immutable), so that destination does not exist: put the carry-over in the project memory's `open_threads.md` (or the project's status notes) and name it in the wrap-up summary. A continuation debrief segment is for material new work, not deferred hygiene.
- **Issue tracker** (only for persistent structural problems): skill bugs, config conflicts, missing capabilities, cross-repo inconsistencies that won't self-heal, changes needing multi-session coordination.

**Never file issues for transient staleness findings.** They become stale within 1-2 sessions as routine work refreshes the same files. If in doubt, use the debrief — it's cheaper to re-discover a finding than to manage a throwaway issue.

Then release the memory lock if Step 8 took it.

### 10. Summary

```text
Self-improvement complete:
- Reviewed: N skills, M memory files, K config files
- Findings: X total (N fixed, M flagged for manual review)
- Commits: [list repos + commit hashes]
```

After printing the summary, record the pass marker the **Same-day repeat** check reads (from inside the project's repository, as there) — never under a dry run ([Arguments](#arguments)):

```bash
bash <skill-dir>/scripts/pass_marker.sh append "<scope>"
```

The marker is a sidecar state file under `$OACP_HOME/state/self-improve/`, independent of the debrief — record it on standalone passes too. Never write it into a debrief record: records are immutable and carry a `content_sha256` over their body, so an append silently breaks the hash. Marker filenames follow the user's day while debrief filenames are UTC-dated, so the two can legitimately differ by a day — that is not drift.

## Notes

- This skill reviews, it does not rewrite. Changes should be surgical, not wholesale rewrites.
- For stale files flagged for manual review, note what looks outdated but don't invent new content — the user knows the current state better.
- `command find` for shell operations (some shells alias `find` to `fd`).
- `gh` and `git` commands may need sandbox exceptions depending on your runtime's configuration.
- Keep the report scannable. If there are 20+ findings, group by file rather than listing each individually.
- Memory files flagged `[STALE]` may be intentionally stable (e.g., company info rarely changes). Use the 30-day threshold as a signal, not a mandate.
