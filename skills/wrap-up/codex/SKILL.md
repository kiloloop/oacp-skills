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

## 1. Capture a read-only snapshot

Confirm the operational root and capture status before changing anything:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
CURRENT_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
git -C "$REPO_ROOT" status --short
git -C "$REPO_ROOT" worktree list --porcelain
git -C "$REPO_ROOT" worktree prune --dry-run --verbose
```

Resolve the base branch and every persistent branch/worktree from
`AGENTS.md`. Establish the repository-authorized GitHub identity when the
squash-merge pass is needed, then preview branch cleanup:

```bash
bash "$SKILL_DIR/scripts/cleanup_branches.sh" "$REPO_ROOT" --dry-run \
  --base "$BASE_BRANCH" [--keep <persistent-branch>]...
```

Use `oacp inbox --json` for the current Codex project. Distinguish ordinary
pending messages from held-unverified enforce-mode rows. Never parse held
fields, and never treat either class as processed cleanup.

Read [references/cleanup.md](references/cleanup.md) only when a candidate
exists or a snapshot command fails.

## 2. Clean stale artifacts

Skip all mutations in dry-run mode. In a full run, the invocation authorizes
only the local candidates that satisfy every guard below.

Run the packaged two-pass branch helper after passing all persistent branches
as `--keep`. Its ancestry pass uses safe `git branch -d`; its squash pass
uses `-D` only when the local tip exactly equals a merged PR's
`headRefOid`. A `MERGED` state alone, a missing remote branch, or a
post-merge local tip never authorizes deletion.

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

Invoke `$debrief` using project auto-detection. This attempt is required, but
failure is non-fatal: report it and continue. Do not fabricate a debrief when
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

Dry-run keeps this audit read-only. If changes are proposed, pause and relay
the complete approval menu: recommendation, numbered items, target files and
repos, exact outcomes, and allowed replies. Apply only approved edits. After
the user resolves the menu, continue without a second publication question
unless the user narrowed or disabled publication.

A pause must report all state gathered so far and every deferred cleanup,
event, memory, commit, and push action. Use
`Wrap-up paused — self-improve approval required`, never the completion
report.

## 6. Publish memory and repository changes

A full wrap-up publishes OACP memory once and commits/pushes only bounded
approved repository changes. Skip publication for dry-run, `no-push`,
`local-only`, narrower scope, or unavailable required authentication.

`oacp memory push` is the sole memory publication path. Never substitute
manual memory-repository staging, commits, repair, or force push. Handle each
source repository independently and stage explicit paths only. Exclude
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
