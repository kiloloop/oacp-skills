---
name: org-memory-synthesis
description: Synthesize org-memory — fold new events into recent.md, promote cross-repo patterns to decisions.md and rules.md, and audit for staleness, cross-file conflicts, and drift. Invoke whenever the user asks "synthesize org-memory", "fold events", "is recent.md stale", "audit org-memory", or any phrasing like "did we synthesize org-memory" — even if they do not explicitly type the slash command.
---

# /org-memory-synthesis — Org-Memory Synthesis

Org-memory (`$OACP_HOME/org-memory/`) is the cross-project SSOT that the OACP
session-init hook auto-loads. It drifts if events accumulate unfolded and
topical files (`decisions.md`, `rules.md`) are not curated. This skill does the
full 3-file pass — synthesis then audit — so the curated layer stays
trustworthy.

## When to use

Use this skill when:

- The user asks whether org-memory is current
- A wrap-up or housekeeping flow needs to fold recent events
- Cross-file inconsistency or stale entries surface during another task
- An upstream skill hands off the org-memory pass

## Files & paths

| Path | Role |
|------|------|
| `$OACP_HOME/org-memory/recent.md` | Rolling current-state, target ≤150 lines, auto-loaded by session-init hook |
| `$OACP_HOME/org-memory/decisions.md` | Architectural decisions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/rules.md` | Standing conventions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/events/YYYYMMDD-HHMMSS-<slug>.md` | Raw event files with YAML frontmatter (date, agent, project, type, related) |

`recent.md` header carries `<!-- Last event folded in: <filename> -->`. Use it
to scope incremental synthesis cheaply. `OACP_HOME` defaults to `$HOME/oacp`
per the OACP CLI; check the workspace marker if unsure.

## Setup

Resolve the workspace and helper before reading event bodies:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
test -d "$OACP_ROOT/org-memory" || {
  echo "ERROR: org-memory not found. Run: oacp org-memory init" >&2
  exit 1
}
```

## Synthesis flow

### 1. Scope the work

List event filenames newer than the marker in `recent.md`. Filenames are
lex-sortable on the `YYYYMMDD-HHMMSS-` prefix, so an `awk '$0 > m'` filter is
the comparison:

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

- Empty output means org-memory is current; jump to Step 7 for the audit-only
  pass.
- Missing marker in older `recent.md` means the inline shell lists all events
  and warns; do a full pass and tell the user the read cost.

### 2. Batch-read new event bodies

Use one shell read across the listed event files:

```bash
cd $OACP_HOME/org-memory/events && for f in <newline-separated names from step 1>; do echo "=== $f ==="; command tail -n +9 "$f"; echo; done
```

`tail -n +9` skips the YAML frontmatter. Use the frontmatter for routing; fold
the body into the curated files.

### 3. Categorize each event

The event's `type:` frontmatter field drives placement:

| `type` | Default placement in `recent.md` | Promotion candidate? |
|--------|----------------------------------|----------------------|
| `event` | Current State | Rarely — only milestones with durable cross-project bearing |
| `rule` | Standing Rules | Promote to `rules.md` if cross-repo (3+ repos in `related:`) or generalizable convention |
| `decision` | Active Decisions | Promote to `decisions.md` if architectural or cross-repo |

Cross-repo signal: count distinct repos in the event's `related:` field. 3+ is
the promotion threshold. Skill-specific rules that affect only one skill's flow
stay in `recent.md` Standing Rules; promoting them adds `rules.md` noise without
cross-repo benefit.

### 4. Propose a 3-file diff to the user

Present the intended changes as three sections: `recent.md`, `decisions.md`,
and `rules.md`. For each promotion, include a one-line rationale tied to the 3+
pattern threshold, cross-repo signal, or convention class. Note `recent.md`
line-budget impact so it stays under 150 lines.

If all edits are mechanical and uncontroversial, proceed after the proposal.
Pause for judgment calls where local context cannot resolve the truth.

### 5. Apply edits

Use Codex's normal file-editing flow (`apply_patch` for manual edits) and keep
the change set limited to:

- `$OACP_HOME/org-memory/recent.md`
- `$OACP_HOME/org-memory/decisions.md`
- `$OACP_HOME/org-memory/rules.md`

Place new `decisions.md` entries at the **top** of the file under the correct
`## YYYY-MM-DD` heading so newest-first order is preserved. Step 7D will
mechanically verify order.

### 6. Update the markers

Two header lines in `recent.md` must stay present:

- `<!-- Last event folded in: <newest event filename from step 1> -->`
- `<!-- Last curated: YYYY-MM-DD by <who> -->`

A dropped marker forces the next pass to re-scan all events, defeating the
incremental design.

### 7. Audit pass — ALWAYS run after synthesis

Six checks, in order. The audit catches what synthesis alone misses.

**A. Cross-file consistency.** For items appearing in both `recent.md` and a
curated file, compare key facts such as product structure, paths, versions, and
status claims. Surface mismatches with file references.

**B. Supersession check.** Scan `decisions.md` for `Supersedes X` annotations.
For each X, verify X is also marked as superseded with a pointer back.
Asymmetric supersession reads as if both entries are active.

**C. Stale-status check.** Find entries with status claims like "Filed #N",
"Pending review", or "Q1 target". For GitHub issue refs where the repo can be
inferred, verify state:

```bash
gh issue view <N> --repo <owner>/<repo> --json state,closedAt,updatedAt
```

Annotate stale claims inline rather than removing them, for example:
`Status: #15 still OPEN P3, not actioned`.

**D. Chronological order in `decisions.md`.** Section headers must run
**newest-first, top-to-bottom** so the freshest decisions are read first. Run
the mechanical check — do not self-report:

```bash
DECISION_HEADERS="$(mktemp)"
command grep -nE '^## 20' "$OACP_HOME/org-memory/decisions.md" \
  | awk '{print $2}' >"$DECISION_HEADERS" || true
if [ ! -s "$DECISION_HEADERS" ]; then
  echo "No dated decision headers found" >&2
  command rm -f -- "$DECISION_HEADERS"
  exit 1
fi
ORDER_RC=0
LC_ALL=C sort -rc "$DECISION_HEADERS" || ORDER_RC=$?
command rm -f -- "$DECISION_HEADERS"
test "$ORDER_RC" -eq 0
```

Exit zero means descending order is correct. If `sort -rc` reports disorder or
no dated headers exist, repair with one edit operation. The mechanical check is
the verification; never substitute self-reporting.

**E. Category drift.** Conventions filed under `decisions.md` should move to
`rules.md`, and architectural decisions filed under `rules.md` should move to
`decisions.md`. If unclear, leave the item where the historical event-author
put it and mention the ambiguity.

**F. Migration leftovers.** Content duplicated with another memory tree, such
as a domain-specific memory store, should be trimmed to a single pointer.

### 8. Surface findings, apply, ask

Apply uncontroversial fixes directly: annotations, chronological re-sort, and
strict duplicate removal. Pause and ask on judgment calls such as
pricing/status conflicts or ownership ambiguity.

### 9. Suggest commit; do not auto-commit

Typical commit message:

```text
org-memory: synthesize <N> events + audit pass

- <N> events folded into recent.md (<M> to decisions.md, <K> to rules.md)
- <audit findings summary>
```

Let the user decide commit timing. The skill never commits automatically.

## Anti-patterns

- Do not delete superseded entries; annotate them. History is load-bearing.
- Do not promote skill-specific rules to `rules.md`.
- Do not auto-commit.
- Do not edit sibling memory trees or project-scoped memory directories.
- Do not drop the marker in `recent.md`.
- Do not replace the Step 7D `sort -rc` check with a prose claim.

## Workarounds

- Use `command ls`, `command grep`, and `command tail` to bypass shell aliases.
- `gh issue view` in Step 7C may need authenticated GitHub CLI access; if auth
  is missing, report the unchecked refs instead of inventing status.
- `recent.md` target is ≤150 lines; `decisions.md` and `rules.md` grow over
  time. Trim by annotation or consolidation, not by deleting history.

## Notes

- The skill operates on `$OACP_HOME/org-memory/` only.
- Step 1's scope-the-work shell is inlined directly in this file (and in the
  Claude top-level `SKILL.md`) — there is no separate helper script.
- `shared/INTENT.md` is the source of truth for runtime-agnostic behavior.

## Learned from runs

<!-- Add post-run lessons here once /org-memory-synthesis has shipped and accumulated real-world feedback. -->
