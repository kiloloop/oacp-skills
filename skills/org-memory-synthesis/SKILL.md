---
name: org-memory-synthesis
description: Synthesize org-memory — fold new events into recent.md, promote cross-repo patterns to decisions.md and rules.md, and audit for staleness, cross-file conflicts, and drift. Invoke whenever the user asks "synthesize org-memory", "fold events", "is recent.md stale", "audit org-memory", or any phrasing like "did we synthesize org-memory" — even if they don't explicitly type the slash command.
---

# /org-memory-synthesis — Org-Memory Synthesis

Org-memory (`$OACP_HOME/org-memory/`) is the cross-project SSOT that the OACP session-init hook auto-loads. It drifts if events accumulate unfolded and topical files (`decisions.md`, `rules.md`) aren't curated. This skill does the full 3-file pass — synthesis then audit — so the curated layer stays trustworthy.

## When to use

Invoke this skill when:

- The user asks whether org-memory is current
- A wrap-up / housekeeping flow needs to fold recent events
- Cross-file inconsistency or stale entries surface during another task
- An upstream skill hands off the org-memory pass

## Files & paths

| Path | Role |
|------|------|
| `$OACP_HOME/org-memory/recent.md` | Rolling current-state, target ≤150 lines, auto-loaded by session-init hook |
| `$OACP_HOME/org-memory/decisions.md` | Architectural decisions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/rules.md` | Standing conventions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/events/YYYYMMDD-HHMMSS-<slug>.md` | Raw event files with YAML frontmatter (date, agent, project, type, related) |

`recent.md` header carries `<!-- Last event folded in: <filename> -->` — use it to scope incremental synthesis cheaply. `OACP_HOME` defaults to `$HOME/oacp` per the OACP CLI; check the workspace marker if unsure.

## Setup

Resolve the workspace and fail fast if org-memory isn't initialized:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
test -d "$OACP_ROOT/org-memory" || {
  echo "ERROR: org-memory not found. Run: oacp org-memory init" >&2
  exit 1
}
```

## Synthesis flow

### 1. Scope the work

List event filenames newer than the marker in `recent.md`. Filenames are lex-sortable (`YYYYMMDD-HHMMSS-` prefix), so `awk '$0 > m'` is the comparison:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
RECENT="$OACP_ROOT/org-memory/recent.md"
EVENTS_DIR="$OACP_ROOT/org-memory/events"

MARKER=$(command grep -m1 "Last event folded in:" "$RECENT" \
  | sed -E 's/.*Last event folded in:[[:space:]]+([^[:space:]]+).*/\1/')

if [ -z "$MARKER" ]; then
  echo "WARN: no marker in $RECENT header; listing ALL events (full pass)" >&2
  command ls "$EVENTS_DIR" | sort
else
  command ls "$EVENTS_DIR" | sort | awk -v m="$MARKER" '$0 > m'
fi
```

- Empty output → org-memory is current; jump to Step 7 (audit-only pass).
- Missing marker (older `recent.md`) → script lists all events and warns; do a full pass and tell the user the read cost.

### 2. Batch-read new event bodies

One Bash call. Read each event's body so you have enough context to categorize:

```bash
cd $OACP_HOME/org-memory/events && for f in <newline-separated names from step 1>; do echo "=== $f ==="; command tail -n +9 "$f"; echo; done
```

(`tail -n +9` skips the YAML frontmatter — frontmatter is for routing, the body is what gets folded. Adjust if your event files use a different frontmatter length.)

### 3. Categorize each event

The event's `type:` frontmatter field drives placement:

| `type` | Default placement in `recent.md` | Promotion candidate? |
|--------|----------------------------------|----------------------|
| `event` | Current State | Rarely — only milestones with durable cross-project bearing |
| `rule` | Standing Rules | Promote to `rules.md` if cross-repo (3+ repos in `related:`) or generalizable convention |
| `decision` | Active Decisions | Promote to `decisions.md` if architectural or cross-repo |

Cross-repo signal: count distinct repos in the event's `related:` field. 3+ is the promotion threshold. Skill-specific rules (those that only affect one skill's flow) stay in `recent.md` Standing Rules only — promoting them adds `rules.md` noise without cross-repo benefit.

### 4. Propose a 3-file diff to the user

Present as three sections — `recent.md`, `decisions.md`, `rules.md`. For each promotion, give a one-line rationale tying it to the 3+ pattern threshold, cross-repo signal, or convention class. Note `recent.md` line-budget impact so it stays under 150.

### 5. Apply edits

Use the `Edit` tool. Place new `decisions.md` entries under the correct `## YYYY-MM-DD` heading so chronological order is preserved (Step 7D will re-sort if not).

### 6. Update the markers

Two header lines in `recent.md`:

- `<!-- Last event folded in: <newest event filename from step 1> -->`
- `<!-- Last curated: YYYY-MM-DD by <who> -->`

A dropped marker forces the next pass to re-scan all events, defeating the incremental design.

### 7. Audit pass — ALWAYS run after synthesis

Six checks, in order. The audit catches what synthesis alone misses.

**A. Cross-file consistency.** For items appearing in both `recent.md` and a curated file (e.g., product structure, pricing, paths, version numbers), compare key facts. Surface mismatches — they usually mean one file fell behind.

**B. Supersession check.** Scan `decisions.md` for `Supersedes X` annotations. For each X, verify X is also marked as superseded with a pointer back. Asymmetric supersession reads as if both are active.

**C. Stale-status check.** Find entries with status claims like "Filed #N", "Pending review", "Q1 target". For GitHub issue refs where the repo can be inferred, verify state:

```bash
gh issue view <N> --repo <owner>/<repo> --json state,closedAt,updatedAt
```

(Runtimes that sandbox the shell may need to allow `gh` for this step — configure that in your runtime's permissions, not in the skill body. If `gh` auth is missing, report the unchecked refs rather than inventing status.) Annotate stale claims inline rather than removing them, e.g. `Status: #15 still OPEN P3, not actioned`.

**D. Chronological order in `decisions.md`.** Section headers must run **oldest-first, top-to-bottom** (new entries append at the bottom). Run the mechanical check — don't self-report:

```bash
command grep -nE '^## 20' $OACP_HOME/org-memory/decisions.md \
  | awk '{print $2}' | sort -c
# Exit 0 = order is correct. Non-zero = re-sort needed.
```

If `sort -c` reports a disorder, re-sort with one Edit operation. The mechanical check is the verification — never substitute self-reporting. (A real false-clean was caught with this exact check when a newly-folded section had been prepended at the top while the rest of the file ran oldest-first.)

**E. Category drift.** Conventions filed under `decisions.md` should move to `rules.md`, and vice versa. Decisions are architectural calls; rules are standing conventions. If unclear, default to leaving where the historical event-author put it.

**F. Migration leftovers.** Content duplicated with another memory tree (e.g., content owned by a domain-specific memory store) should be trimmed to a single pointer.

### 8. Surface findings, apply, ask

Apply uncontroversial fixes directly (annotations, chronological re-sort, removing strict duplications). Pause and ask on judgment calls — pricing/status conflicts where the truth isn't obvious from local context.

### 9. Suggest commit (don't auto-commit)

Typical commit message:

```
org-memory: synthesize <N> events + audit pass

- <N> events folded into recent.md (<M> to decisions.md, <K> to rules.md)
- <audit findings summary>
```

Let the user run the commit; the skill never commits automatically.

## Anti-patterns

- **Don't delete superseded entries — annotate.** History is load-bearing for understanding why a decision changed. Add `**Superseded by YYYY-MM-DD <title>.**` inline.
- **Don't promote skill-specific rules** to `rules.md`. Keep them in `recent.md` Standing Rules.
- **Don't auto-commit.** The user reviews and decides commit timing.
- **Don't touch sibling memory trees** (project-scoped memory directories). Read-only from this skill's perspective.
- **Don't drop the marker.** It's the cheapest performance optimization in this flow.
- **Don't replace the Step 7D `sort -c` check with a prose claim.** Self-reported "chronological order looks fine" misses real false-cleans. Run the mechanical check.

## Workarounds

- Use `command ls`, `command grep`, `command tail` to bypass shell aliases (`ls` → `eza`, `grep` → `rg`).
- `gh issue view` in Step 7C may need a runtime sandbox bypass — configure in the runtime, not inline.
- `recent.md` target ≤150 lines; `decisions.md` and `rules.md` grow over time — trim via annotation, not deletion.

## Notes

- The skill operates on `$OACP_HOME/org-memory/` only. It never edits sibling project-scoped memory.
- `shared/INTENT.md` is the source of truth for runtime-agnostic behavior.

## Learned from runs

<!-- Add post-run lessons here once /org-memory-synthesis has shipped and accumulated real-world feedback. -->
