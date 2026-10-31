---
name: debrief
description: Capture a structured session summary and publish it to the OACP org-memory debrief store as an immutable record. Run at the end of any session.
---

# /debrief — Session Debrief

Publish a structured summary of this session to the central org-memory debrief store:

```text
$MEMORY_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/<YYYYMMDD>-<agent>-<session>.md
```

`$MEMORY_HOME` is the memory home step 1 resolves — the OACP home unless the repo is bound to its own.

One session produces exactly one file, written once at session end and never rewritten. The store is the full-fidelity session record; curated outcomes reach other agents through `agent-memory event write` instead (see "Curation guard" below).

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

The name must match the workspace directory under `$OACP_HOME/projects/` byte-for-byte — the store path segment is case-sensitive. If no workspace directory matches the candidate, confirm the project name with the user before publishing: the writer validates only the segment's shape, never that the workspace exists.

**A repo bound to its own memory home.** An `.agent-memory.json` binding at the main repo root ties the repo to an agent-memory home other than the OACP home, so such a repo usually has no OACP workspace and the chain above finds no match. Take the binding's `project` — no confirmation needed, the binding already names it — and publish into its `home` with `--oacp-dir "<home>"` (step 7). `agent-memory status` prints `source: binding:<path>` with the resolved `home:` and `project:`, but an exported `$AGENT_MEMORY_HOME` or `$OACP_HOME` outranks the binding, so run it as `env -u AGENT_MEMORY_HOME -u OACP_HOME agent-memory status` or read the file directly. If your runtime sandboxes file writes, the bound home must be writable from the session; otherwise the writer fails `Operation not permitted` on its stage file and writes nothing.

**Resolve the memory home once.** Set `MEMORY_HOME` to the binding's `home` for a bound repo, otherwise to `${OACP_HOME:-$HOME/oacp}` (the writer's own default). Every later step that touches memory uses this one value — the ruling lookup in step 3, publication in step 7, the curation event, `org init`, and `doctor` — so the debrief, the rulings it checks, and the event it curates all land in the same home.

### 2. Collect the session identity

The writer needs five identity values. Gather them before composing the body:

- **`--project`** — from step 1
- **`--agent`** — your registered agent name (the `agents/<name>/` directory under the project workspace)
- **`--runtime`** — the runtime family running the session (`claude` for Claude Code)
- **`--session`** — a short stable session id: **1-32 lowercase letters and digits, never hyphens**. Use the first 8 characters of the harness session UUID with hyphens stripped, copied from the `session=` line the snippet below prints — never retyped. The store parses the session id as the substring after the final hyphen, so a hyphen corrupts the filename grammar. If the session keeps working after a debrief has already landed, the continuation segment takes a derived id rather than this one — see step 8.
- **`--started-utc` / `--ended-utc`** — session bounds as ISO 8601 UTC with whole seconds, e.g. `2026-08-25T20:04:11Z`. `ended_utc` must not precede `started_utc`, and the date of `started_utc` determines the filename and directory segments.

> **UTC, not local time.** The store path and the `<YYYYMMDD>` filename prefix are derived from `started_utc` in UTC. On a machine whose OS timezone is ahead of or behind UTC, a locally-stamped date lands the record in the wrong month directory. Generate both stamps with `date -u +%Y-%m-%dT%H:%M:%SZ`.
>
> **Clock, don't estimate — and read the start rather than recalling it.** `--ended-utc` is the clock at publish time. `--started-utc` is the harder one: by the end of a session its start is hours behind you, so read it off the session transcript. The first timestamped entry *is* the session start, already in UTC, and the transcript's filename is the session UUID, so one command yields both values:
>
> ```bash
> python3 -c "
> import json, os, sys
> p = sys.argv[1]
> print('session=' + os.path.basename(p).split('.')[0].replace('-', '')[:8])
> for line in open(p):
>     d = json.loads(line)
>     if d.get('timestamp'): print('started_utc=' + d['timestamp'][:19] + 'Z'); break
> " "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$CLAUDE_CODE_SESSION_ID".jsonl
> ```
>
> Claude Code exports the session UUID to Bash as `$CLAUDE_CODE_SESSION_ID`, so no identifier is typed by hand (substitute the UUID only on a version that does not export it). The transcript directory is keyed by the directory the session was launched from, so the glob finds it without deriving that name. Not every line carries a `timestamp`, so break on the first that does rather than reading line 1. Transcript stamps carry milliseconds, and the writer parses whole seconds strictly — hence the `[:19]` truncation. Do **not** substitute the file's creation stat: that is local time, a full timezone offset away from the UTC stamp the store expects.

### 3. Review the session

Gather what actually happened:

- **Accomplishments** — what was built, fixed, reviewed, or decided
- **Decisions** — key choices and their rationale
- **Issues** — tickets created, closed, or updated. If other agents collaborated (parallel runs, review loops), include their closures and PR activity; local `git log` alone misses them.
- **Files changed** — `git log --name-only --format= --since="<started_utc>"` plus `git status --short`
- **Git activity** — `git log --oneline --since="<started_utc>"`, in each repo touched for cross-project sessions
- **Next actions** — carry-forward items, open threads, blockers. **Before writing them, check today's entries in `$MEMORY_HOME/org-memory/events/` and `decisions.md` for a ruling that already supersedes a plan you are about to restate.** A debrief that carries a paused or superseded plan forward as a next action re-opens it for whatever consumes the store next, and the record is immutable once published.

Your conversation context is the primary source. Git activity supplements it; it does not replace what you remember of the session.

### 4. Compose the body

Write the body to a scratch file, then hand that file to the writer. The body is everything after the frontmatter — the writer generates the frontmatter itself, so do not write a `---` block at the top.

```markdown
# Session Summary: <project> — YYYY-MM-DD

**Runtime**: <runtime>
**Duration**: ~{{DURATION}} minutes

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

Leave `{{DURATION}}` literal. The writer replaces it at publish time with the minutes between `--started-utc` and `--ended-utc`, rounded up, before hashing — a figure written by hand is a projection made before the end stamp exists. It is the only placeholder the writer fills.

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
  for d in "$PWD/.claude/skills/debrief" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/debrief"; do
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
  --oacp-dir "${MEMORY_HOME:?resolve it in step 1}" \
  --json
```

`--oacp-dir` takes the home step 1 resolved; passing it every time keeps a bound repo's debrief out of the ambient OACP home, and an unset `MEMORY_HOME` stops the command instead of falling back to that home.

The writer validates the schema, fills `{{DURATION}}`, computes the content hash, stages the record privately, publishes it with an atomic no-replace link, and reads it back to confirm. Exit codes: `0` published (or an idempotent re-publish of a byte-identical record), `1` validation error, `2` publication failure.

Publication is failure-atomic — the canonical path only ever holds a complete, verified record. On any failure the path stays absent; at worst a private `.stage.*` file remains, and a later successful publication of the same record sweeps it. The writer only ever publishes an inode it created itself, so a `.stage.*` file that appears from anywhere else is never adopted — `agent-memory doctor` reports it and it is safe to delete by hand.

### 8. Handle a collision

`--session` collisions are the one failure that needs a judgment call:

- **Byte-identical record already published** → reported as `idempotent`. Nothing to do; the run already landed.
- **Different record at the same path** → hard failure. A published debrief is never replaced. Re-publish under a **new session identifier**; the existing record stays as it is.

Corrections and follow-ups are new artifacts too — a later debrief, or an event referencing the original — never an edit to a landed file.

> **A session that keeps working after its own debrief.** "One session, one file" assumes the session ends when the debrief is written. When work continues past that point — a second wrap-up, a dispatch that lands later, a resumed session — the published record is immutable and now materially incomplete, and re-running with the same identity collides by construction. Publish a **continuation segment**: same project, agent, and runtime; the session id suffixed with the segment number (`b31ffdea` → `b31ffdea2`, then `b31ffdea3`); `started_utc` set to the previous record's `ended_utc`; `ended_utc` set to now. The suffixed form stays inside the 1-32 alphanumeric session grammar, so it needs no separate allowance. Open the body by naming the parent record and the span it covers, so the two read as one session rather than two unrelated ones. When the session sat idle between the two (a resumed session days later), `{{DURATION}}` measures that whole wall span: keep the placeholder, say on the Duration line that it is the wall span, and give the active span from command timestamps. Do not backfill the earlier record, and do not skip the write — skipping is how a session's most consequential stretch goes unrecorded.

### 9. Confirm

Print the canonical path, the status, and the content hash from the writer's JSON output.

## Curation guard

Raw debriefs never enter `recent.md` or `events/`. Only curated folds do. If the session produced an outcome other agents or projects need, write it as a separate event, with `--source-ref` set to the debrief filename stem so the two can be reconciled later (`/wrap-up` step 2b covers this when that skill is installed):

```bash
agent-memory event write --home "${MEMORY_HOME:?resolve it in step 1}" \
  --type decision --project "<project>" --agent "<agent>" --slug "<slug>" \
  --source-ref "<YYYYMMDD>-<agent>-<session>" --body-file "<path-to-event-body>"
```

## Notes

- Keep each section to the facts a later reader needs. If the session was trivial, say so rather than padding.
- Facts over narrative: the store is read by curation tooling, not for prose.
- Debrief files are never auto-loaded at session start; they are permanent history, not context.
- The store does **not** have to exist first — the writer provisions its own tree. `agent-memory org init --home "$MEMORY_HOME"` is optional setup, never a precondition.
- `agent-memory doctor --home "$MEMORY_HOME"` validates store *setup* — layout, staging artifacts, symlinks. It never opens debrief files; schema and hash correctness are the writer's contract, verified at publication.
