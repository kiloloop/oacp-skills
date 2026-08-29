---
name: debrief
description: Capture a structured session summary and publish it to the OACP org-memory debrief store as an immutable record. Run at the end of any session.
---

# /debrief — Session Debrief

Publish a structured summary of this session to the central org-memory debrief store:

```text
$OACP_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/<YYYYMMDD>-<agent>-<session>.md
```

One session produces exactly one file, written once at session end and never rewritten. The store is the full-fidelity session record; curated outcomes reach other agents through `oacp write-event` instead (see "Curation guard" below).

## Arguments

- `/debrief` — generate the summary and publish it
- `/debrief --dry-run` — generate and display the summary without writing anything

## Instructions

### 1. Identify the project

Resolve the project name with this fallback chain:

1. The `project_name` field in the workspace marker. The marker is gitignored and lives only at the repository's main root, so resolve that root first rather than reading it from the working directory — a linked worktree has no marker of its own:

   ```bash
   ROOT=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
   python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['project_name'])" "$ROOT/.oacp"
   ```

2. `basename "$ROOT"` — not `git rev-parse --show-toplevel`, which returns the worktree directory when the session is running inside one
3. The working directory basename, when not in a git repo

The name must match the workspace directory under `$OACP_HOME/projects/` byte-for-byte — the store path segment is case-sensitive and is validated against that same rule.

### 2. Collect the session identity

The writer needs five identity values. Gather them before composing the body:

- **`--project`** — from step 1
- **`--agent`** — your registered agent name (the `agents/<name>/` directory under the project workspace)
- **`--runtime`** — the runtime family running the session
- **`--session`** — a short stable session id: **1-32 lowercase letters and digits, never hyphens**. Use the first 8 characters of the harness session UUID with hyphens stripped. This is what distinguishes multiple sessions by the same agent on the same day. If the session keeps working after a debrief has already landed, the continuation segment takes a derived id rather than this one — see step 8.
- **`--started-utc` / `--ended-utc`** — session bounds as ISO 8601 UTC, e.g. `2026-08-25T20:04:11Z`. Take these from the clock, never from an estimate; `ended_utc` must not precede `started_utc`, and the date of `started_utc` determines the filename and directory segments.

> **UTC, not local time.** The store path and the `<YYYYMMDD>` filename prefix are derived from `started_utc` in UTC. On a machine whose OS timezone is ahead of or behind UTC, a locally-stamped date lands the record in the wrong month directory. Generate both stamps with `date -u +%Y-%m-%dT%H:%M:%SZ`.
>
> **Clock, don't estimate — and read the start rather than recalling it.** `--ended-utc` is the clock at publish time. `--started-utc` is the harder one: by the end of a session its start is hours behind you, so the honest options are a guess or a hunt. Read it off the session log instead — the first timestamped entry your harness recorded *is* the session start, already in UTC. In Claude Code that is the first line carrying a `timestamp` field in the session's `.jsonl` transcript; other runtimes expose an equivalent session log. Break on the first entry that actually has the field rather than reading line 1, since not every line carries one. Do **not** substitute the file's creation stat — that is local time, and it reads a full timezone offset away from the UTC stamp the store expects.

### 3. Review the session

Gather what actually happened:

- **Accomplishments** — what was built, fixed, reviewed, or decided
- **Decisions** — key choices and their rationale
- **Issues** — tickets created, closed, or updated. If other agents collaborated (parallel runs, review loops), include their closures and PR activity; local `git log` alone misses them.
- **Files changed** — `git diff --name-only HEAD~5..HEAD 2>/dev/null` or `git status --short`
- **Git activity** — `git log --oneline --since="8 hours ago"`, in each repo touched for cross-project sessions
- **Next actions** — carry-forward items, open threads, blockers. **Before writing them, check today's org-memory events and decisions for a ruling that already supersedes a plan you are about to restate.** A debrief that carries a paused or superseded plan forward as a next action re-opens it for whatever consumes the store next, and the record is immutable once published.

Your conversation context is the primary source. Git activity supplements it; it does not replace what you remember of the session.

### 4. Compose the body

Write the body to a scratch file, then hand that file to the writer. The body is everything after the frontmatter — the writer generates the frontmatter itself, so do not write a `---` block at the top.

```markdown
# Session Summary: <project> — YYYY-MM-DD

**Runtime**: <runtime>
**Duration**: ~X minutes

## What Changed

- bullet points of accomplishments

## Decisions Made

- key decisions with rationale

## Tickets / Issues

- created/closed/updated references (or "None")

## Files Modified

- key files changed

## Next Actions

- [ ] carry-forward items

## Notes

- anything notable (omit the section if nothing)
```

> **Use a file-writing tool, never a shell heredoc.** Shell expansion corrupts debrief bodies — backticks in a double-quoted heredoc execute as command substitution, and the mangling is silent. Write the body with your runtime's file-writing tool and pass the path.

### 5. Resolve the writer

The writer ships inside this skill, so its path depends on where the skill is
installed, never on the current working directory — a debrief is written from
whatever project the session was in.

```bash
# Claude Code states the skill's base directory when it loads this file; use
# that value. For runtimes that do not, fall back to the install locations.
SKILL_DIR="<base directory for this skill>"
if [ ! -f "$SKILL_DIR/scripts/write_debrief.py" ]; then
  for d in "$PWD/.claude/skills/debrief" "$HOME/.claude/skills/debrief"; do
    [ -f "$d/scripts/write_debrief.py" ] && SKILL_DIR="$d" && break
  done
fi
test -f "$SKILL_DIR/scripts/write_debrief.py" \
  || { echo "debrief writer not found; re-install the skill" >&2; exit 1; }
```

Stop here if the writer cannot be resolved. Do not hand-compose a record into
the store — the frontmatter, the content hash, and the publication primitive
are the writer's contract, and a hand-written file satisfies none of them.

### 6. Dry run

`/debrief --dry-run` stops here. Run the step 7 command with `--dry-run`
appended: the writer validates the identity and body, composes the exact
record it would publish, prints it, and touches nothing — no directories
created, no files written. Status is reported as `dry-run`.

Show the composed record and the target path, then **stop**. Do not continue
to step 7, and do not report the session as debriefed.

### 7. Publish

```bash
python3 "$SKILL_DIR/scripts/write_debrief.py" \
  --project "<project>" \
  --agent "<agent>" \
  --runtime "<runtime>" \
  --session "<session>" \
  --started-utc "<started>" \
  --ended-utc "<ended>" \
  --body-file "<path-to-body>" \
  --json
```

The writer validates the schema, computes the content hash, stages the record privately, publishes it with an atomic no-replace link, and reads it back to confirm. Exit codes: `0` published (or an idempotent re-publish of a byte-identical record), `1` validation error, `2` publication failure.

Publication is failure-atomic — the canonical path only ever holds a complete, verified record. On any failure the path stays absent; at worst a private `.stage.*` file remains, and a later successful publication of the same record sweeps it. The writer only ever publishes an inode it created itself, so a `.stage.*` file that appears from anywhere else is never adopted — `oacp doctor` reports it and it is safe to delete by hand.

### 8. Handle a collision

`--session` collisions are the one failure that needs a judgment call:

- **Byte-identical record already published** → reported as `idempotent`. Nothing to do; the run already landed.
- **Different record at the same path** → hard failure. A published debrief is never replaced. Re-publish under a **new session identifier**; the existing record stays as it is.

Corrections and follow-ups are new artifacts too — a later debrief, or an event referencing the original — never an edit to a landed file.

> **A session that keeps working after its own debrief.** "One session, one file" assumes the session ends when the debrief is written. When work continues past that point — a second wrap-up, a dispatch that lands later, a resumed session — the published record is immutable and now materially incomplete, and re-running with the same identity collides by construction. Publish a **continuation segment**: same project, agent, and runtime; the session id suffixed with the segment number (`b31ffdea` → `b31ffdea2`, then `b31ffdea3`); `started_utc` set to the previous record's `ended_utc`; `ended_utc` set to now. The suffixed form stays inside the 1-32 alphanumeric session grammar, so it needs no separate allowance. Open the body by naming the parent record and the span it covers, so the two read as one session rather than two unrelated ones. Do not backfill the earlier record, and do not skip the write — skipping is how a session's most consequential stretch goes unrecorded.

### 9. Confirm

Print the canonical path, the status, and the content hash from the writer's JSON output.

## Curation guard

Raw debriefs never enter `recent.md` or `events/`. Only curated folds do. If the session produced an outcome other agents or projects need, write it as a separate event:

```bash
oacp write-event --type decision --project "<project>" --agent "<agent>" ...
```

Set the event's `source_ref` to the debrief filename stem (`<YYYYMMDD>-<agent>-<session>`) so the two can be reconciled later.

## Notes

- Keep it concise — 2-6 bullets per section. If the session was trivial, say so rather than padding.
- Facts over narrative: the store is read by curation tooling, not for prose.
- Debrief files are never auto-loaded at session start; they are permanent history, not context.
- The store does **not** have to exist first — the writer provisions its own tree, verified by publishing into a directory with no `org-memory/` at all. `oacp org-memory init` is a convenience, never a precondition.
- `oacp doctor` validates store *setup* — layout, staging artifacts, symlinks. It never opens debrief files; schema and hash correctness are the writer's contract, verified at publication.

## Learned from runs

<!-- Section kept as an anchor for future entries. -->
