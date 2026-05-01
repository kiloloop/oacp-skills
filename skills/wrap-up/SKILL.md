---
name: wrap-up
description: End-of-session cleanup — cleanup, optional debrief, self-improve, commit, and push in one command.
---

# /wrap-up — Session Wrap-Up

Composes end-of-session steps into a single command: cleanup stale artifacts, optional debrief, self-improve (with approval pause), commit, and push.

## Arguments

- `/wrap-up` — full wrap-up sequence
- `/wrap-up --dry-run` — run cleanup + debrief + self-improve but skip commit, push, and memory sync

## Instructions

When the user runs `/wrap-up`, execute these steps in strict order:

### 1. Cleanup stale artifacts

Scope: merged branches, stale worktrees, processed inbox messages.

#### 1a. Just-merged PR worktrees

- If the session merged a PR from a dedicated worktree, remove that worktree immediately instead of waiting for the generic stale-worktree pass: `git worktree remove <path>`
- If the current shell is still inside that worktree, do not try to remove it in place. Report the path and rerun cleanup from the main clone or another surviving worktree.
- After removing the worktree, try `git branch -d <branch>`
- If `git branch -d <branch>` fails because the repo uses squash-only merges and the branch tip is not an ancestor of `main`, keep the branch and report it as a squash-merged local leftover instead of forcing `-D`

#### 1b. Merged branches

- List local branches merged into main:

  ```bash
  git branch --merged main | command grep -v '^\*\|main'
  ```

- Delete each with `git branch -d <branch>` (safe delete only — never `-D`)
- Report: "Deleted N merged branches: list" or "No merged branches to clean"

#### 1c. Stale worktrees

- Run `git worktree prune` to clean up missing worktrees
- List remaining: `git worktree list`
- For entries under `.worktrees/`:
  - If the worktree's branch is merged into main: `git worktree remove <path>`
  - In squash-only repos, merged PR evidence also counts as stale even when branch ancestry does not show merged. Use session context or PR metadata before removing.
  - If the only signal is that the remote branch disappeared, ask before removing; the branch may be intentionally local-only.
  - If not merged: leave in place, warn user
  - After removing a stale worktree, try `git branch -d <branch>` only when Git reports the branch as merged. Never force-delete a leftover local branch during wrap-up.
- Report: "Pruned N worktrees" or "No stale worktrees"

#### 1d. Processed inbox messages

- Resolve project from the `.oacp` marker in the repo root:

  ```bash
  [ -f ".oacp" ] && python3 -c "import json; print(json.load(open('.oacp'))['project_name'])"
  ```

- If no marker found, skip inbox cleanup
- Inbox dir: `${OACP_HOME:-$HOME/oacp}/projects/<project>/agents/claude/inbox/`
- List YAML files with `command ls -1 <dir> | command grep '\.yaml$'` (not `*.yaml` glob — zsh `nomatch` errors when empty; `command ls` in case `ls` is aliased to `eza`; `-1` required — without it, multi-column output breaks grep)
- If files exist: report them to the user but do NOT auto-delete (they may be unprocessed)
- If inbox is empty: report "Inbox clean"

### 2. Debrief (optional)

Three modes, all non-fatal — debrief failure does not block remaining steps:

1. **If a `/debrief` skill is installed**, invoke it and let it write to its configured location.
2. **Else if `$CORTEX_HOME` is set** and points at a clone of `kiloloop/cortex`, write a debrief there following that repo's inbox layout.
3. **Else**, write a 20-line summary to `./.oacp/debriefs/YYYY-MM-DD.md` (create the directory if missing).

Public cortex repo: <https://github.com/kiloloop/cortex>.

If a debrief target is configured but the write fails (e.g., `$CORTEX_HOME` set but path missing), warn and continue to the next step.

### 3. Org-memory events

Write events for the session's significant outcomes to the org-level memory log. This feeds the cross-project knowledge layer that other agents read for org context.

**Skip this step** if `${OACP_HOME:-$HOME/oacp}/org-memory/events/` does not exist (org-memory not initialized — run `oacp org-memory init` to set up).

```bash
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
[ -d "$OACP_HOME/org-memory/events" ] && echo "org-memory active" || echo "SKIP"
```

**What to write**: only events that matter to other agents and projects — not routine task completion.

| Write an event for | Type | Example |
|--------------------|------|---------|
| PR merged | `event` | "PR #N merged: <short public outcome>" |
| Architecture/design decision | `decision` | "Standardized on REST for public APIs" |
| New standing rule or convention | `rule` | "All repos require GitHub App tokens for gh CLI" |
| Release or deployment | `event` | "v0.2.0 published to PyPI" |

**Do NOT write events for**: routine code fixes, test additions, doc typos, inbox messages processed, self-improve findings.

**How**: use `oacp write-event`. Auto-detect project from git repo basename. Use the debrief (Step 2) as source material — the key accomplishments and decisions are already captured there.

```bash
oacp write-event --agent claude --project <project> \
  --type <decision|event|rule> --slug <short-slug> \
  --body "<one-line description>" \
  [--related "PR #N,..."] \
  [--oacp-dir "$OACP_HOME"]
```

> **Slug constraint**: lowercase alphanumeric + hyphens only, 1–64 chars, must start and end with alphanumeric. **No dots** — convert version segments to hyphens (e.g., `cli-0-2-3-released`, not `cli-0.2.3-released`).

**Keep it lightweight**: 3–5 events max per session. If the session was trivial (only reading files, answering questions), write zero events and report "No org-memory events (routine session)."

Report: "Wrote N org-memory events" or "Skipped (org-memory not initialized)" or "No org-memory events (routine session)".

### 4. Run /self-improve (hard dependency)

- Invoke the `/self-improve` skill (full scope: skills + memory + claude-md)
- **If `/self-improve` is not installed**, fail with a clear install hint — install it from this same repo:

  ```bash
  mkdir -p .claude/skills/self-improve
  cp <repo>/skills/self-improve/claude/SKILL.md .claude/skills/self-improve/SKILL.md
  ```

- The skill will present findings and ask "Which changes should I apply?"
- **Pause here** — wait for user approval before continuing
- Apply approved changes
- If no findings, report "No issues found" and continue

#### 4b. Self-improve the self-improve skill (optional)

After Step 4 completes, optionally run `/self-improve self-improve` — a targeted review of the self-improve skill itself. This catches issues with the review process that only surface during execution (missed edge cases, incorrect analysis patterns, user corrections during Step 4).

- **Skip if Step 4 had no findings and no user corrections** — nothing to learn from a clean run
- If findings exist, apply with approval and commit alongside Step 5

### 5. Commit changes (current repo)

- Run `git status` to check for uncommitted changes in the current repo
- If no changes, skip to Step 6
- Stage changed files explicitly (no `git add -A` or `git add .`)
- Exclude from staging: `.env`, credentials, secrets, `settings.json`
- Commit message: `wrap-up: <brief summary of changes>`
- If `--dry-run`: show what would be committed but do not commit

### 6. OACP memory sync

Push the cross-machine memory snapshot if memory sync is active. Captures new `org-memory/events/` entries from Step 3 plus any session memory edits (decisions, recent state, project facts, etc.).

```bash
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
test -f "$OACP_HOME/.oacp-memory-repo" || { echo "memory sync: not active (skip)"; exit 0; }
oacp memory push
```

- **Skip silently** if `.oacp-memory-repo` marker is absent — memory sync is not initialized on this machine. Run `oacp memory init` (or `oacp memory clone --remote <url>` for second-and-beyond machines) to opt in.
- `oacp memory push` is idempotent: stages allowlisted files (`org-memory/**`, `projects/*/memory/**`), commits with `memory: <agent>@<host> <date> (N files)` format, pushes to `origin/main`. No-op if no changes.
- Independent of Step 7 — failure here does not block the current-repo push. Wrap-up reports the memory-push outcome separately.
- **SSH commit signing**: this step performs a signed commit, which on macOS typically requires an SSH agent (e.g., the 1Password agent) reachable over a Unix socket. Sandboxed runtimes commonly block agent sockets — if your runtime sandboxes shell commands, allow this step to run unsandboxed or pre-approve socket access for the SSH agent. Configure that in your runtime's permissions; do not inline runtime-specific bypass flags here.
- If `--dry-run`: run `oacp memory push --dry-run` if supported; otherwise report what would be staged via `git -C "$OACP_HOME" status --short` and skip the actual push.
- Report: commit SHA + file count, or "memory: clean (no changes)", or "memory: skipped (sync not active)".

### 7. Push current repo

- **Pull-rebase before push** to avoid conflicts with other runtimes that may have pushed:

  ```bash
  git pull --rebase origin <branch>
  ```

  If rebase fails (merge conflict), abort with `git rebase --abort`, warn the user, and skip push.
- Push the current branch to origin: `git push origin <branch>`
- If `--dry-run`: skip push
- Report: branch, commit SHA, remote URL

### 8. Summary

Print a final status block:

```text
Wrap-up complete:
- Cleanup: N branches, M worktrees pruned, inbox <status>
- Debrief: <mode> — <path or "skipped">
- Org-memory: N events written (or "skipped" or "routine session")
- Self-improve: N findings (M applied)
- Commit: <sha> on <branch> (or "no changes")
- OACP memory: <sha> (or "clean" or "skipped (sync not active)" or "skipped (dry-run)")
- Push: <branch> -> origin (or "skipped (dry-run)")
```

## Notes

- Cleanup uses only safe deletes (`git branch -d`, never `-D`). Unmerged branches are never force-deleted.
- Inbox messages are reported but never auto-deleted — the user must confirm deletion.
- Debrief failure is non-fatal. Remaining steps still run.
- Commit scope is the current repo plus the cross-machine memory repo (Step 6, if marker present). Other repos are not touched.
- Use `command grep` and `command ls` in shell commands when those names may be aliased on the host (`grep` aliased to `rg`, `ls` aliased to `eza` are common setups).
- Memory snapshot pushes (Step 6) require the runtime to allow access to the SSH signing agent's socket — describe this in your runtime's permissions config.

## Learned from runs

<!-- Add post-run lessons here once /wrap-up has shipped and accumulated real-world feedback. -->
