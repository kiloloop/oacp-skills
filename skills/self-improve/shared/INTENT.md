# self-improve — Shared Intent

## What it does

Structured review of the agent's configuration and knowledge layer. Identifies staleness, contradictions, gaps, and improvement opportunities across skills, memory files, and agent config. Proposes changes, applies after approval, and commits to the correct repo.

## Review targets

| Target | What gets reviewed |
|--------|--------------------|
| Skills | SKILL.md files that ran during the session, or a named skill |
| Memory | Project memory files across all configured locations |
| Config | Agent config files and settings |

## Severity tags

| Tag | Meaning |
|-----|---------|
| `[FIX]` | Clear bug or error — should be fixed |
| `[STALE]` | Data is outdated |
| `[GAP]` | Something is missing |
| `[CONFLICT]` | Contradiction between files |
| `[BLOAT]` | Unnecessary content, can be trimmed |
| `[STRUCTURAL]` | Skill needs architectural work — deeper analysis needed |

## Workflow

1. **Parse target** — determine scope from argument (all, skills, memory, config, or a specific skill name)
2. **Discover files** — build inventory of all files to review based on scope
3. **Analyze** — check each file against the analysis checklist for its category
4. **Report findings** — present findings grouped by category, sorted by severity
5. **Propose changes** — suggest specific edits for each finding
6. **Apply approved changes** — make edits after user approval
7. **Commit** — group changes by repo and commit separately

## Analysis checklist — Skills

For each skill SKILL.md in scope, check:

- **Post-run lessons**: What worked vs what broke during the session. Are there patterns worth codifying?
- **Contradiction with memory/config**: Instructions that contradict known project patterns
- **Missing safety rules**: Edge cases exposed by the run (empty data, missing files, auth failures)
- **Outdated references**: File paths, script names, argument flags, or URLs that no longer match the codebase
- **Multi-copy drift**: If the skill exists in multiple locations, diff them and flag divergence

### Structural health gate

After surface checks, evaluate whether a skill needs structural work (not just patches). Triggers:

- Output format drift — format spec doesn't match actual output
- Approaching 500 lines — needs reference extraction before it can grow
- Missing modes — user manually does operations the skill should handle
- 3+ findings on a single skill — suggests systemic issues
- "Learned from runs" > 5 entries — lessons accumulating without being incorporated

If any trigger fires, tag as `[STRUCTURAL]` and recommend deeper analysis.

## Analysis checklist — Memory

For each memory file, check:

- **Staleness** (tiered thresholds):
  - 2 days: derived/snapshot files (computed state that drifts quickly)
  - 14 days: authored working files (updated by daily ops)
  - 30 days: stable reference files (rarely change, expected)
- **Contradictions**: Cross-reference between files — statuses, issue numbers, agent names
- **Session context drift**: Verify memory reflects recent user statements ("I removed X", "we stopped using Y")
- **Index file hygiene**: Check if the memory index is approaching any platform truncation limits

## Analysis checklist — Config

For agent config files, check:

- **Duplication**: Rules that appear in both global and project config
- **Contradictions**: Rules in one file that conflict with another
- **Missing rules**: Patterns manually enforced 3+ times in session history that aren't codified
- **Bloat**: Unnecessary verbosity — can sections be trimmed without losing meaning?
- **Outdated references**: Agent names, file paths, project lists, tool names that no longer exist
- **Settings drift**: Check for silent overrides between settings files at different precedence levels

## Output contract — Findings report

```
## Self-Improvement Report

### Skills
- [FIX] <skill>/SKILL.md:<line> — <description>
- [GAP] <skill>/SKILL.md — <description>

### Memory
- [STALE] <file>.md — last updated N days ago
- [CONFLICT] <file1> vs <file2> — <description>

### Config
- [BLOAT] <file> — <description>
- [GAP] <file> — <description>
```

Sort findings by severity within each category: `[FIX]` > `[CONFLICT]` > `[STRUCTURAL]` > `[GAP]` > `[STALE]` > `[BLOAT]`.

Group clusters of routine findings under a single summary line to keep the report scannable.

## Acceptance criteria

- All targets in scope are reviewed
- Findings reported with severity tags and specific file/line references
- Changes gated on user approval — no edits without consent
- Commits grouped by repo (not mixed across repos)
- Non-git-tracked files (runtime memory) are edited in place, not committed
- Deferred findings routed to appropriate follow-up (session debrief or issue tracker)
