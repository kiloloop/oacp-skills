# org-memory-synthesis — Shared Intent

## What it does

Synthesizes the cross-project org-memory layer that the OACP session-init hook auto-loads. Folds new events from `$OACP_HOME/org-memory/events/` into the curated SSOT files (`recent.md`, `decisions.md`, `rules.md`), then runs an audit pass that catches staleness, supersession asymmetry, chronological disorder, category drift, and migration leftovers.

Org-memory drifts if events accumulate unfolded and the curated files aren't audited. This skill is the canonical synthesis + audit pass.

## When to use

- The user asks whether org-memory is current ("is recent.md stale?", "synthesize org-memory", "fold events", "did we audit org-memory?")
- A wrap-up or housekeeping flow needs to fold recent events
- Cross-file inconsistency or stale entries surface during another task
- An upstream skill (e.g., a housekeeping orchestrator) hands off the org-memory pass

## Files & paths

| Path | Role |
|------|------|
| `$OACP_HOME/org-memory/recent.md` | Rolling current-state, target ≤150 lines, auto-loaded by the session-init hook |
| `$OACP_HOME/org-memory/decisions.md` | Architectural decisions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/rules.md` | Standing conventions (cross-repo, 3+ pattern threshold) |
| `$OACP_HOME/org-memory/events/YYYYMMDD-HHMMSS-<slug>.md` | Raw event files with YAML frontmatter (date, agent, project, type, related) |

`recent.md` carries a `<!-- Last event folded in: <filename> -->` header marker. The skill uses it to scope incremental synthesis — only events newer than the marker are read.

## Workflow

The skill walks through nine steps in strict order. Steps are runtime-agnostic in intent; runtime-specific shell and tool wiring lives in each runtime's `SKILL.md`.

1. **Scope the work** — list event filenames newer than the marker by parsing the `<!-- Last event folded in: -->` line from `recent.md`, then filtering the events directory with `awk '$0 > marker'` (filenames are lex-sortable on their `YYYYMMDD-HHMMSS-` prefix). Empty output ⇒ jump to Step 7 (audit-only pass). Missing marker ⇒ full pass; warn the user about read cost. Each runtime's `SKILL.md` carries the canonical inline shell for this step.
2. **Batch-read new event bodies** — one batched read across all new events. Skip YAML frontmatter; the body is what gets folded.
3. **Categorize each event** — the event's `type:` frontmatter drives placement:
   - `event` → `recent.md` Current State (rare promotions for cross-project milestones)
   - `rule` → `recent.md` Standing Rules; promote to `rules.md` if cross-repo (3+ repos in `related:`)
   - `decision` → `recent.md` Active Decisions; promote to `decisions.md` if architectural or cross-repo
4. **Propose a 3-file diff** — present `recent.md`, `decisions.md`, `rules.md` sections. One-line rationale per promotion. Note `recent.md` line-budget impact.
5. **Apply edits** — preserve newest-first order in `decisions.md` (new entries go at the top under a `## YYYY-MM-DD` heading).
6. **Update the markers** — two header lines in `recent.md`:
   - `<!-- Last event folded in: <newest event filename> -->`
   - `<!-- Last curated: YYYY-MM-DD by <who> -->`
   Dropping the marker forces the next pass to re-scan all events, defeating the incremental design.
7. **Audit pass — six checks, always run after synthesis**:
   - **A. Cross-file consistency** — items in both `recent.md` and a curated file must agree on key facts (paths, versions, pricing, structure).
   - **B. Supersession check** — for every `Supersedes X` in `decisions.md`, verify X also points back. Asymmetric supersession reads as if both entries are active.
   - **C. Stale-status check** — entries with status claims like "Filed #N", "Pending review", "Q1 target". For GitHub issue refs, verify via `gh issue view`. Annotate inline rather than removing.
   - **D. Chronological order in `decisions.md`** — section headers must run newest-first, top-to-bottom (new entries at the top). Run the mechanical check (don't self-report):

     ```bash
     command grep -nE '^## 20' $OACP_HOME/org-memory/decisions.md \
       | awk '{print $2}' | sort -rc
     # Exit 0 = correct (descending). Non-zero = re-sort needed.
     ```

     Re-sort with one Edit operation when `sort -rc` reports disorder.
   - **E. Category drift** — conventions filed under `decisions.md` move to `rules.md`, and vice versa.
   - **F. Migration leftovers** — content duplicated with another memory tree should be trimmed to a single pointer.
8. **Surface findings, apply, ask** — apply uncontroversial fixes directly (annotations, chronological re-sort, strict-duplicate removal). Pause and ask on judgment calls (pricing/status conflicts where local context can't resolve the truth).
9. **Suggest commit (don't auto-commit)** — give the user a ready-to-paste commit message; let them review and run it.

## Inputs

- `$OACP_HOME/org-memory/` (required) — initialized by `oacp org-memory init`.
- `OACP_HOME` env var (optional) — defaults to `$HOME/oacp` (matching the OACP CLI's documented fallback). Runtime SKILL.md files use the same precedence in their Step 1 inline shell.

## Hard dependency

- **Initialized org-memory tree**. If `$OACP_HOME/org-memory/` is missing, fail with an install hint: `oacp org-memory init`.

## Optional integrations

- **`oacp` CLI ≥ 0.4.0** — provides `oacp org-memory init` and event writers used elsewhere in the OACP stack.
- **`gh` CLI** — needed for Step 7C stale-status verification on GitHub issue refs.

## Acceptance criteria

- Marker line in `recent.md` is updated whenever events fold in. Never drop the marker.
- Audit Step 7D uses the mechanical `sort -rc` check — never self-report "chronological order looks fine".
- Superseded `decisions.md` entries are annotated (`**Superseded by YYYY-MM-DD <title>.**`), not deleted. History is load-bearing for understanding why a decision changed.
- Skill-specific rules (those that affect only one skill's flow) stay in `recent.md` Standing Rules and are never promoted to `rules.md`.
- Skill never auto-commits. The user reviews the diff and decides commit timing.
- Skill never edits sibling memory trees (e.g., project-scoped memory directories). Read-only from this skill's perspective.

## Outputs

- Edited `recent.md`, `decisions.md`, `rules.md` (in place under `$OACP_HOME/org-memory/`)
- Updated header markers in `recent.md`
- A findings summary covering: events folded, promotions made, audit findings (with file:line refs for conflicts), and any unresolved items deferred to the user
- A suggested commit message (no auto-commit)
