---
name: wrap-up
description: "End-of-session cleanup for Codex — inspect stale artifacts, run debrief, write significant org-memory events, run a delta-first self-improve pass, then publish bounded approved memory and repository changes."
---

# Wrap-up

Close a Codex session in one ordered workflow while keeping cleanup, memory
publication, repository publication, and external actions independently safe.

## Invocation

- `$wrap-up` runs the full sequence and authorizes the bounded local cleanup
  and publication described below.
- `$wrap-up --dry-run` performs only read-only cleanup inspection,
  `$debrief --dry-run`, event planning, and a read-only self-improve audit. It
  makes no file edits, cleanup mutations, event writes, commits, or pushes.
- An explicit `no-push` or `local-only` request runs the local sequence but
  performs no memory or repository commits or pushes.

Read the nearest `AGENTS.md` first. It owns repository identity, persistent
branch/worktree policy, validation, authentication, and publication rules.

Check the session project's `.no-org-memory` marker and applicable `AGENTS.md`
before org-memory work. An opt-out skips debrief, events, and memory publication,
including dry-run variants, with `skipped: project_opt_out`. An ambient store
or an additional cleanup repository cannot override it.

Set `WRAP_UP_SKILL` to the absolute directory containing this `SKILL.md` before
invoking bundled resources. Resolve the active memory home from project binding
or current runtime metadata; do not select a home from a repository basename.

## 1. Capture a read-only snapshot

Confirm the operational root and capture status before changing anything:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
CURRENT_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
git -C "$REPO_ROOT" status --short
git -C "$REPO_ROOT" worktree list --porcelain
git -C "$REPO_ROOT" worktree prune --dry-run --verbose
```

Resolve the base and persistent branches/worktrees from `AGENTS.md`.

First set `MEMORY_HOME` exactly as debrief does: use the main repository's
resolved `.agent-memory.json` home when bound, otherwise
`${OACP_HOME:-$HOME/oacp}`. Inspect the binding with
`env -u AGENT_MEMORY_HOME -u OACP_HOME agent-memory status`, or read the exact
binding and resolve a relative home against its directory. Stop on an invalid
binding. Pass this same value to the audit and subsequent debrief/publication;
an ambient `AGENT_MEMORY_HOME` must not redirect either step. Then run the
bundled advisory snapshot (read-only; Python standard library):

```bash
python3 "$WRAP_UP_SKILL/scripts/wrap_up_audit.py" --repo "$REPO_ROOT" --json \
  --memory-home "${MEMORY_HOME:?resolve it as debrief does}" \
  [--keep-branch <persistent-branch>]... [--keep-worktree <persistent-path>]... \
  [--keep-branch-prefix <peer-runtime/>]... \
  [--owned-branch <created-branch>]... [--owned-worktree <created-path>]...
```

Supply authorized `GH_TOKEN`/`GITHUB_TOKEN` only when PR reads are needed, or
`--allow-ambient-gh` only after repository policy permits the verified human
identity. Otherwise accept skipped PR state. Helper recommendations never
authorize removal: independently apply every guard in step 2 and the cleanup
reference, including session ownership and exact merged head. Pass ownership
flags only from this session's recorded creation evidence; absent ownership,
failed status, unknown repository identity, or diverged tips are keep outcomes.
The snapshot includes `local_tip`, `pr_head_oid`, and the actual worktree path.
Ancestry candidates use safe deletion; same-repository squash evidence permits
a force-delete suggestion only after full head equality.

For standalone callers, the helper's CLI-compatible fallback order is
`--memory-home`, `AGENT_MEMORY_HOME`, `OACP_HOME`,
nearest valid `.agent-memory.json` binding, canonical workspace marker, then
`~/agent-memory`. A malformed nearest binding is an error, never a fallback.
The wrap-up workflow always passes the debrief-resolved home explicitly instead.
The inbox home remains separate (`OACP_HOME`, otherwise `~/oacp`); a memory
binding does not imply an OACP inbox. No workspace directory convention
selects a memory store.

If this session created an exact branch or worktree in a sibling repository,
audit that repository under its own instructions and auth policy. Cleanup
scope covers only those recorded artifacts; a runtime prefix or `.worktrees/`
location is not ownership. General sibling cleanup and publication require
separate scope. Keep each repository's candidates and decisions separate.

Use `oacp inbox --json` for the current Codex project. Distinguish ordinary
pending messages from held-unverified enforce-mode rows. Never parse held
fields, and never treat either class as processed cleanup.

Read [references/cleanup.md](references/cleanup.md) only when a candidate
exists or a snapshot command fails.

## 2. Clean stale artifacts

Skip all mutations in dry-run mode. In a full run, the invocation authorizes
only the local candidates that satisfy every guard below.

Use the cleanup reference's ancestry and squash passes. Safe-delete ancestry
branches with `git branch -d`; a full wrap-up authorizes force deletion only of
an exact session-created squash-merged branch after confirming `MERGED` and
local tip equality with the merged PR's `headRefOid`. Pre-existing branches
need separate force-cleanup authority. A vanished remote is not merge evidence.

For worktrees:

- never remove the current, persistent, peer-owned, dirty, or untracked
  worktree;
- before removal, inspect ignored content and retain irreplaceable signed,
  staged-for-publication, or otherwise non-reproducible artifacts;
- remove only a clean session-owned worktree whose branch is already proved
  merged;
- begin administrative pruning with `git worktree prune --dry-run --verbose`;
  in full mode, rerun immediately and mutate only when the exact candidate set
  is unchanged and every entry was resolved as stale;
- keep detached or runtime-managed worktrees this session did not create.

Remote branch deletion is a separate outward-facing approval. Inbox lifecycle
is not wrap-up cleanup: report queued paths and leave them for
`$check-inbox` to verify, process, reply, and archive terminally.

## 3. Run debrief

Unless the project opted out, invoke `$debrief` using project auto-detection.
This attempt is required, but failure is non-fatal: report it and continue. Do not fabricate a debrief when
the skill fails. In dry-run mode invoke `$debrief --dry-run`.

## 4. Write significant org-memory events

Use a successful debrief as source material. Skip when debrief failed,
org-memory is not initialized, or the session produced no cross-project
outcome.

Deduplicate against tracked and untracked events. Write at most 3–5 entries and
write zero for routine fixes, tests, documentation cleanup, inbox processing,
self-improve findings, or read-only work. Read
[references/publication.md](references/publication.md) only when an
event is plausibly eligible. In dry-run mode, report proposed events without
writing them.

## 5. Run delta-first self-improve

Invoke `$self-improve` in session-delta mode. Start with:

- skills actually used this session;
- guidance, curated memory, or config changed this session;
- observed failures, workarounds, conflicts, stale claims, or discovery gaps.

Expand only when evidence indicates drift. Route release-wide migrations,
multi-skill capability changes, and context-budget audits to
`$audit-oacp-skills`.

Dry-run keeps this audit read-only. Match findings against the user's existing
approved files and outcomes first; apply already approved changes without
asking again. Pause only for new scope and relay the complete approval menu:
recommendation, numbered items, target files and repositories, exact outcomes,
and allowed replies. After the user resolves it, continue without a second
publication question unless publication was narrowed or disabled.

A pause must report all state gathered so far and every deferred cleanup,
event, memory, commit, and push action. Use
`Wrap-up paused — self-improve approval required`, never the completion
report.

## 6. Publish memory and repository changes

A full wrap-up commits/pushes only bounded approved repository changes.
It publishes OACP memory once unless the session project opted out. Skip publication for dry-run, `no-push`,
`local-only`, narrower scope, or unavailable required authentication.

`agent-memory push --home <resolved-memory-home> --agent codex` is the sole memory
publication path. Never substitute manual memory-repository staging, commits,
repair, or force push. Handle each source repository independently and stage explicit paths only. Exclude
unrelated or pre-existing changes, credentials, private keys, `.env`, local
settings, generated caches, and live runtime state.

Before a repository push, follow its nearest `AGENTS.md`, inspect token-free
remotes, and synchronize with:

```bash
git pull --rebase --autostash origin "$CURRENT_BRANCH"
```

If rebase or autostash restoration conflicts, abort/stop, preserve the work,
and report that repository as unpublished. Read
[references/publication.md](references/publication.md) only when publication is
actionable.

## 7. Summarize

```text
Wrap-up complete:
- Cleanup: N branches, M worktrees, inbox <clean / pending / held>
- Debrief: <saved path or failure>
- Org-memory events: N written / planned / skipped
- Self-improve: N findings (M applied)
- Memory: <pushed SHA / no changes / skipped / failed>
- Commits: <repo>@<sha> on <branch>; ... (or "no changes")
- Pushes: <repo>: <branch> -> origin; ... (or "skipped")
- Deferred: <remaining dirty, held, or approval-gated work>
```

A successful debrief or edit does not imply that its repository was committed
or pushed.

## Durable rules

- Keep OACP memory, the current repository, and every sibling repository as
  separate Git scopes.
- Exact sibling branches/worktrees created by this session are cleanup-only
  scope unless their publication was separately approved.
- Default publication is bounded to OACP memory, the current repository, and
  another repository only when this wrap-up created or explicitly approved
  changes there. Other repositories require opt-in.
- PR creation, merge, release/promotion, deployment, remote-branch deletion,
  and unrelated existing changes always require separate authority.
- Preserve unrelated user and concurrent-runtime work.
- Codex does not compile, extend, or clear the Claude-only OACP enforcement
  envelope.
- Consolidate repeatable lessons into their owning guidance; do not append a
  second procedure or learned log.
