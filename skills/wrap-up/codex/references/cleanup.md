# Cleanup reference

Load this reference only when wrap-up identifies cleanup candidates. The main
workflow and nearest `AGENTS.md` remain binding.

## Branches

Resolve the base branch from `origin/HEAD`, falling back to `main`, and
collect persistent branches from repository guidance. Establish the authorized
GitHub identity before querying PR state.

Use the packaged helper for both preview and execution:

```bash
bash "$SKILL_DIR/scripts/cleanup_branches.sh" "$REPO_ROOT" --dry-run \
  --base "$BASE_BRANCH" [--keep <persistent-branch>]...
bash "$SKILL_DIR/scripts/cleanup_branches.sh" "$REPO_ROOT" \
  --base "$BASE_BRANCH" [--keep <persistent-branch>]...
```

The full second command is allowed only outside dry-run. The helper:

- safe-deletes ancestry-merged branches with `git branch -d`;
- skips base, persistent, and worktree-checked-out branches;
- queries merged PRs for remaining local branches;
- force-deletes a squash-merged local branch only when its current tip exactly
  equals the merged PR's `headRefOid`;
- keeps branches with no merged PR, a mismatched tip, or unavailable authorized
  GitHub state;
- never deletes remote branches.

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
