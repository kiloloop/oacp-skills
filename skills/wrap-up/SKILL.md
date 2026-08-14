---
name: wrap-up
description: End-of-session cleanup, optional debrief, self-improve, commit, and push in one command.
---

# /wrap-up — Session Wrap-Up

Composes end-of-session steps into a single command: cleanup stale artifacts, optional debrief, self-improve (with approval pause), commit, and push.

## Arguments

- `/wrap-up` — full wrap-up sequence
- `/wrap-up --dry-run` — run cleanup + debrief + self-improve but skip commit and push

## Instructions

When the user runs `/wrap-up`, execute these steps in strict order:

### 1. Cleanup stale artifacts

Scope: merged branches, stale worktrees, processed inbox messages.

> **Working-directory guard (run FIRST)**: verify `git rev-parse --show-toplevel` matches the session's primary repo before any cleanup command — a `cd` from earlier in the session persists in the shell, and cleanup silently runs against the wrong repo. If it doesn't match, `cd` back to the project root explicitly.

#### 1a. Just-merged PR worktrees

- If the session merged a PR from a dedicated worktree, remove that worktree immediately instead of waiting for the generic stale-worktree pass: `git worktree remove <path>`
- If the current shell is still inside that worktree, do not try to remove it in place. Report the path and rerun cleanup from the main clone or another surviving worktree.
- **Gitignored artifacts don't block removal — check for irreplaceable ones first**: `git worktree remove` succeeds when the only remaining content is gitignored (build output like `release/`, `dist/`), silently deleting it. Before removing a build worktree, check those directories for non-reproducible or pending-publish artifacts (e.g., signed installers staged for a later upload); if any exist, surface them and let the user decide. Rebuildable-by-design outputs are fine to delete — say so in the report.
- After removing the worktree, try `git branch -d <branch>`
- If `git branch -d <branch>` fails because the repo uses squash-only merges and the branch tip is not an ancestor of `main`, keep the branch and report it as a squash-merged local leftover instead of forcing `-D` — step 1b's PR-state pass handles it safely.

#### 1b. Merged branches

Squash merges leave branch tips that are never ancestors of `main`, so `git branch --merged` and `-d` are both blind to them — without a PR-state check, merged branches accumulate indefinitely while cleanup reports "nothing to clean". Run the two-pass cleanup (ancestry pass + PR-state pass), packaged as [`scripts/cleanup_branches.sh`](scripts/cleanup_branches.sh):

```bash
bash <skill-dir>/scripts/cleanup_branches.sh <repo-root>
```

Ensure `gh` is authenticated for the repo first (pass 2 is skipped, and nothing deleted, if `gh` can't resolve it). The script's contract:

- **Pass 1 (ancestry)**: `git branch --merged main` → `git branch -d` (regular/fast-forward merges).
- **Pass 2 (PR head)**: for each remaining local branch not checked out in any worktree, look up its merged PR and delete ONLY when the local tip exactly equals that PR's merged `headRefOid` — a `MERGED` state alone is not enough, since the branch may carry unpublished commits made after the merge, and deleting it would orphan them. The exact-head verification is the safety, not the `-D` flag. `main`, worktree-checked-out branches (including other agents'), branches with no merged PR, and branches whose tip diverged from the merged head are never deleted; they print as `KEEP` for manual review — never `-D` those by hand either.
- **Remote counterparts**: deleting merged remote refs on a shared repo is outward-facing — list candidates and let the user authorize `git push --delete`. Assess from `git ls-remote --heads origin` after `git remote prune origin` (`git branch -a`'s remote-tracking refs go stale and inflate the list).
- Report: "Deleted N merged branches (K ancestry + M squash); kept P unmerged" or "No merged branches to clean"

#### 1c. Stale worktrees

- Run `git worktree prune` to clean up missing worktrees
- List remaining: `git worktree list`
- **Peer-agent ownership guard**: a worktree whose path or branch names another agent or runtime belongs to that agent — report it, never remove it, even when its PR is merged. Peer worktrees don't always self-identify by name: another agent's PR-review checkout may appear as a detached-HEAD worktree under a temp path with no branch name. Treat any worktree this session didn't create, in a tmp path or detached at a reviewed PR's head, as peer-owned.
- For entries this session owns:
  - If the worktree's branch is merged into main: `git worktree remove <path>`
  - In squash-only repos, merged PR evidence also counts as stale even when branch ancestry does not show merged. Use session context or PR metadata before removing.
  - If the only signal is that the remote branch disappeared, ask before removing; the branch may be intentionally local-only.
  - If not merged: leave in place, warn user
  - After removing a stale worktree, try `git branch -d <branch>` only when Git reports the branch as merged. Never force-delete a leftover local branch during wrap-up.
- Report: "Pruned N worktrees" or "No stale worktrees"

#### 1d. Processed inbox messages

- Resolve project from `.oacp` marker in repo root:

  ```bash
  [ -f ".oacp" ] && python3 -c "import json, sys; print(json.load(open('.oacp'))['project_name'])"
  ```

- If no marker found, skip inbox cleanup
- Inbox dir: `$OACP_HOME/projects/<project>/agents/<agent>/inbox/`
- List YAML files with `command ls -1 <dir> | command grep '\.yaml$'` (not `*.yaml` glob — zsh `nomatch` errors when empty; `command ls` because `ls` may be aliased to `eza`; `-1` required — without it, multi-column output breaks grep)
- If files exist: report them to the user but do NOT auto-delete — they may be unprocessed, or held-unverified under an OACP enforce posture (oacp-cli v0.4.2+: a message that failed or lacked signature verification is surfaced explicitly, never treated as ordinary backlog)
- If inbox is empty: report "Inbox clean"

### 2. Run debrief (optional)

- If a `/debrief` skill is installed, invoke it. Otherwise, skip with a one-line note.
- If debrief fails, warn and continue to the next step — debrief is non-fatal.

### 2b. Write org-memory events

Write events for the session's significant outcomes to the org-level memory log. This feeds the cross-project knowledge layer that other agents read for org context.

**Skip this step** if `$OACP_HOME/org-memory/events/` does not exist (org-memory not initialized — run `oacp org-memory init` to set up).

```bash
[ -d "$OACP_HOME/org-memory/events" ] && echo "org-memory active" || echo "SKIP"
```

**What to write**: Only events that matter to other agents and projects — not routine task completion.

| Write an event for | Type | Example |
|--------------------|------|---------|
| PR merged | `event` | "PR #44 merged: org-level memory spec + CLI" |
| Architecture/design decision | `decision` | "Standardized on REST for public APIs" |
| New standing rule or convention | `rule` | "All repos in this org require signed commits" |
| Release or deployment | `event` | "v0.2.0 published" |

**Do NOT write events for**: routine code fixes, test additions, doc typos, inbox messages processed, self-improve findings.

**How**: Use `oacp write-event`. Auto-detect project from git repo basename. Use the debrief (step 2) as source material if available.

```bash
oacp write-event --agent <agent> --project <project> \
  --type <decision|event|rule> --slug <short-slug> \
  --body "<one-line description>" \
  [--related "PR #N,..."] \
  [--oacp-dir "$OACP_HOME"]
```

> **Slug constraint**: lowercase alphanumeric + hyphens only, 1-64 chars, must start and end with alphanumeric. **No dots** — convert version segments to hyphens (e.g., `release-0-2-3` not `release-0.2.3`).

**Keep it lightweight**: 3-5 events max per session. If the session was trivial (only reading files, answering questions), write zero events and report "No org-memory events (routine session)."

Report: "Wrote N org-memory events" or "Skipped (org-memory not initialized)" or "No org-memory events (routine session)".

### 3. Run /self-improve

- Invoke the `/self-improve` skill
- The skill will present findings and ask "Which changes should I apply?"
- **Pause here** — wait for user approval before continuing
- Apply approved changes
- If no findings, report "No issues found" and continue

### 3b. Self-improve the self-improve skill

After step 3 completes, run `/self-improve self-improve` — a targeted review of the self-improve skill itself. This catches issues with the review process that only surface during execution (e.g., missed edge cases, incorrect analysis patterns, user corrections during step 3).

- **Skip if step 3 had no findings and no user corrections** — nothing to learn from a clean run
- If findings exist, apply with approval and commit alongside step 4

### 4. Commit changes

- Run `git status` to check for uncommitted changes
- If no changes, skip to step 5
- Stage changed files explicitly (no `git add -A` or `git add .`)
- Exclude from staging: `.env`, credentials, secrets, `settings.json`
- Commit message: `wrap-up: <brief summary of changes>`
- If `--dry-run`: show what would be committed but do not commit

### 4b. OACP memory sync (optional)

Push the cross-machine memory snapshot if memory sync is active. Captures new `org-memory/events/` entries from step 2b plus any session memory edits.

```bash
test -f "$OACP_HOME/.oacp-memory-repo" || { echo "memory sync: not active (skip)"; exit 0; }
oacp memory push
```

- **Skip silently** if `.oacp-memory-repo` marker absent — memory sync not initialized on this machine. Run `oacp memory init` (or `oacp memory clone --remote <url>` for second+ machines) to opt in.
- `oacp memory push` is idempotent: stages allowlisted files (`org-memory/**`, `projects/*/memory/**`), commits with `memory: <agent>@<host> <date> (N files)` format, pushes to origin/main. No-op if no changes.
- Independent of step 5 — failure here does not block the current-repo push. Wrap-up should report the memory-push outcome separately.
- If `--dry-run`: run `oacp memory push --dry-run` if supported; otherwise skip the push and report what would be staged.
- Report: commit SHA + file count, or "memory: clean (no changes)", or "memory: skipped (sync not active)".

### 5. Push to remote

- **Pull-rebase before push** to avoid conflicts with parallel runtimes that may have pushed:

  ```bash
  git pull --rebase --autostash origin <branch>
  ```

  (`--autostash` carries uncommitted files over the rebase.) If the rebase conflicts, abort with `git rebase --abort`, warn the user, and skip push; if the autostash pop conflicts, git keeps the stash — warn and resolve before pushing.
- Push current branch to origin: `git push origin <branch>`
- If `--dry-run`: skip push
- Report: branch, commit SHA, remote URL

### 6. Summary

Print a final status block:

```
Wrap-up complete:
- Cleanup: N branches, M worktrees pruned, inbox <status>
- Debrief: <status>
- Org-memory: N events written (or "skipped" or "routine session")
- Self-improve: N findings (M applied)
- Commit: <sha> on <branch> (or "no changes")
- OACP memory: <sha> (or "clean" or "skipped (sync not active)" or "skipped (dry-run)")
- Push: <branch> -> origin (or "skipped (dry-run)")
```

## Notes

- **Mid-wrap-up dispatches (OACP v0.4.1+ envelopes)**: if a new task auto-accepts during wrap-up, its compiled scope envelope can deny wrap-up's own later side effects (steps 4-5 commits/pushes are outside a reply-only task's envelope). Run the dispatched task's lifecycle to terminal — reply, audit update, `oacp envelope clear` — then resume wrap-up where it paused. Don't interleave the two.
- Cleanup deletes are verification-gated: ancestry-merged, or PR confirmed `MERGED` (`git branch -d` for the former; pass 2's `-D` fires only on the PR-state verification). Unmerged branches are never force-deleted.
- Inbox messages are reported but never auto-deleted — user must confirm deletion.
- Debrief failure is non-fatal. The remaining steps still run.
- Use `command grep` / `command ls` / `command find` in shell commands if your shell aliases these to other tools.
- `OACP_HOME` defaults: see `oacp doctor` for the active path.
