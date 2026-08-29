# debrief — Shared Intent

## What it does

Turns the end of a working session into one durable, immutable record in the OACP org-memory debrief store. The skill collects what happened, composes a structured Markdown body, and publishes it through a writer that guarantees the canonical path only ever holds a complete, hash-verified record.

Debriefs are the full-fidelity session history. They are deliberately *not* the channel other agents read: curated outcomes travel as org-memory events, and the raw session narrative stays in the store.

## Workflow

1. **Identify the project** — workspace marker at the repository's main root, then that root's basename, then working directory basename. Must match the workspace directory name byte-for-byte. The marker is resolved through the git common directory, not the working tree, so a session running inside a linked worktree resolves the same project as one at the main root.
2. **Collect session identity** — project, agent, runtime, session id, and UTC start/end stamps.
3. **Review the session** — accomplishments, decisions, ticket activity (including collaborating agents'), files changed, git activity, next actions.
4. **Compose the body** — structured Markdown, written with a file-writing tool rather than a shell heredoc.
5. **Resolve the writer** — `scripts/write_debrief.py` from the installed skill directory, never a cwd-relative path.
6. **Publish** — the writer validates, stages, links, and verifies. `--dry-run` stops after composition.
7. **Handle collisions** — identical content is idempotent; different content at an existing path is a hard failure that recovers under a new session id.
8. **Confirm** — report path, status, and content hash.

## Inputs

- Session context (required) — the agent's own record of what happened
- `$OACP_HOME` (optional) — defaults to `$HOME/oacp`, matching the OACP CLI's documented fallback
- `--dry-run` (optional) — compose and display without writing

## Boundaries

- **Append-only.** One session, one file. Never an append, never a rewrite. Corrections are new artifacts.
- **A session that outlives its own debrief writes a continuation segment.** "One session, one file" assumes the session ends when the record is written. Work that continues past it — a resumed session, a late-landing dispatch — is published under the same project, agent, and runtime with the session id suffixed by the segment number, `started_utc` set to the previous record's `ended_utc`. The landed record is never backfilled, and the continuation is never skipped.
- **Next actions carry only live intent.** Before writing them, check the day's org-memory events and decisions for a ruling that already supersedes a plan being restated. A record is immutable once published, so a superseded plan carried forward as a next action cannot be retracted, and it re-opens the question for whatever reads the store next.
- **UTC governs the path.** The `<YYYY>/<MM>` segments and `<YYYYMMDD>` prefix derive from `started_utc` in UTC, not local time.
- **Curation guard.** The skill never writes to `recent.md` or `events/`. Promoting an outcome is a separate, explicit `oacp write-event` call.
- **The kernel owns layout and schema; the writer owns correctness.** `oacp doctor` checks store setup only and never opens debrief files, so schema completeness and hash integrity are verified by the writer at publication time. The composed frontmatter is re-parsed and asserted to round-trip before the store is touched — nothing downstream can catch a serializer that changes a record's identity.

## Design notes

Two properties drive the writer's shape:

- **Failure-atomic publication.** Staging privately and publishing with a no-replace `link()` means a crash can never expose a partial record at the canonical path. `O_CREAT|O_EXCL` on the canonical path is explicitly insufficient — it reserves the name atomically but writes content non-atomically.
- **The writer only publishes an inode it created itself.** The staging nonce is unpredictable, the staging file is created `O_CREAT|O_EXCL|O_NOFOLLOW`, its bytes are verified through that same descriptor, and the published name is confirmed to resolve to that same `(st_dev, st_ino)`. A pre-existing staging path is never read, adopted, or linked: adopting one would let an outside file become the canonical record and stay mutable through the shared inode, which defeats immutability entirely.
- **Stale staging artifacts are swept after publication, not before.** Once the record is landed, no writer of it can still need a stage — a concurrent publisher resolves against the canonical record instead. That ordering makes the sweep safe to run unconditionally, so a crashed run's partial stage does not accumulate. The sweep only removes plain single-linked files owned by this writer; anything else is left for `oacp doctor` to report.

## Acceptance criteria

- A published record validates under `oacp doctor`'s debrief-store check (canonical layout, no staging leftovers, no symlinks).
- Frontmatter carries every required field, and `content_sha256` matches the exact body bytes.
- Republishing identical content is idempotent; differing content at the same path fails without altering the landed record.
- Every identity value the protocol grammars accept survives a real YAML parser as the same string, and a body that is not valid UTF-8 is refused before the store is touched.
- `--dry-run` composes the exact record that would be published and creates nothing.
- The seven protocol-mandated writer-conformance cases pass.

## Dependencies

- `oacp` CLI ≥ 0.4.4 for the `oacp doctor` store check. The writer itself has no `oacp` dependency and provisions its own tree, so `oacp org-memory init` is a convenience rather than a precondition.
- Python 3.9+ standard library only
