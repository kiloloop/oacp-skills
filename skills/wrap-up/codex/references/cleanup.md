# Cleanup reference

Load this reference only when wrap-up identifies cleanup candidates. The main
workflow and nearest `AGENTS.md` remain binding.

## Branches

Resolve the base branch from `origin/HEAD`, falling back to `main`, and
collect persistent branches from repository guidance. Establish the authorized
GitHub identity before querying PR state.

Preview ancestry candidates using `git branch --format='%(refname:short)'
--merged "$BASE_BRANCH"`. Exclude base, persistent, peer-owned, and checked-out
branches; use `git branch -d` for verified ancestry-merged candidates.

For remaining branches, query the repository-authorized GitHub identity for
merged PR `state` and `headRefOid`, then compare the exact local tip. A full
wrap-up authorizes `git branch -D` only for a recorded session-created branch
with state `MERGED` and an equal head. Pre-existing branches need separate
force-cleanup approval. The helper requires explicit recorded ownership and
checks `headRepository.nameWithOwner`, cross-repository status, branch, merged
state and exact head equality. Its JSON includes the PR head, local tip and
real checked-out path. Missing ownership, failed `git status`, failed PR reads,
fork/name collisions and divergent tips never recommend deletion. Always
read back the exact PR identity/head and local tip immediately before deletion. Keep missing PR
state, a mismatched tip, and unknown ownership. Never delete remote branches
without separate outward authority.

Exact head identity is mandatory because a `MERGED` branch can contain
unpublished commits made after the merge.

## Worktrees

Start read-only:

```bash
git worktree list --porcelain
git worktree prune --dry-run --verbose
```

Classify every candidate against this matrix:

| State | Action |
|---|---|
| Current or persistent | Keep. |
| Peer/runtime-owned | Keep. |
| Dirty or untracked | Keep and report paths. |
| Irreplaceable ignored artifacts | Keep and ask. |
| Clean, session-owned, branch proved merged | Remove, then rerun branch cleanup. |
| Only remote branch missing | Keep and ask. |
| Detached or unknown owner | Keep. |

`git worktree remove` can erase ignored output without warning. Inspect
ignored artifact directories before removing a worktree and distinguish
reproducible build output from signed or staged-for-publication material.

For missing-worktree administrative entries, capture
`git worktree prune --dry-run --verbose` twice. Only a full wrap-up may run
the mutating prune, and only when both snapshots name the same exact entries
and each was resolved as stale. Any race or new candidate aborts pruning.

## Inbox

Resolve the project from an explicit value, `.oacp`, or `workspace.json`.
Use:

```bash
oacp inbox "$PROJECT" --agent codex --oacp-dir "$OACP_ROOT" --json
```

Parse JSON from a temporary file, not a pipe into a heredoc. Report ordinary
pending and held-unverified enforce-mode rows separately. Held rows expose only
mechanism-owned metadata. Never delete, parse, or archive inbox messages during
wrap-up; terminal lifecycle belongs to `$check-inbox`.

Report candidates kept because they were current, persistent, peer-owned,
dirty, unverified, drifted, or awaiting approval.

## Live, local, and cached refs

Check live GitHub, local `refs/heads/<branch>`, and cached
`refs/remotes/origin/<branch>` separately. A deleted server branch does not
delete a local branch; a cached ref does not prove the server ref exists.
After verifying an exact live ref is absent, remove only that stale cached
ref with `git update-ref -d` when cleanup scope permits. Do not issue a
redundant server deletion or treat remote disappearance as merge evidence.
