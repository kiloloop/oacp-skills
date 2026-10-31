---
name: wrap-up
description: End-of-session cleanup, debrief, org-memory events, self-improve, commit, and push in one command.
---

# /wrap-up — Session Wrap-Up

Composes end-of-session steps into a single command: cleanup stale artifacts, optional debrief, org-memory events, self-improve (with approval pause), commit, and push.

## Arguments

- `/wrap-up` — full wrap-up sequence
- `/wrap-up --dry-run` — run cleanup + debrief + self-improve but skip commit and push

## Instructions

When the user runs `/wrap-up`, execute these steps in strict order:

### 1. Cleanup stale artifacts

Scope: merged branches and stale worktrees, plus an inbox report (1d) — in the primary repository, plus any repository where this session created a specific local worktree or branch. In such a sibling, clean only those named artifacts: no general branch cleanup, commits, pushes, or remote-branch deletion there. Ownership evidence is this session's own creation commands or recorded paths; a runtime prefix or a `.worktrees/` location alone is not.

> **Working-directory guard (run FIRST)**: verify `git rev-parse --show-toplevel` matches the session's primary repo before any cleanup command — a `cd` from earlier in the session persists in the shell, and cleanup silently runs against the wrong repo. If it doesn't match, `cd` back to the project root. Where the harness forbids `cd` to the root (a worktree-anchored session), run each cleanup command as `git -C <root> …`. A worktree-isolated session refuses `git -C <root>` too: run branch and worktree cleanup from the session's own worktree — it shares the repository's branches and worktree records — pass that path to `cleanup_branches.sh`, and leave any pull of the main clone to the user.
>
> **Memory home**: steps 1d, 2, 2b and 4b assume `$OACP_HOME`. A repo bound to its own agent-memory home (`agent-memory status` reports a binding as the source) uses that home instead: 1d has no inbox to check (say so), step 2 publishes with `--oacp-dir <home>`, 2b and 4b pass `--home <home>`, and 4b pushes only when `<home>/.oacp-memory-repo` exists — otherwise report the home as unsynced. A home outside the sandbox's write allowlist needs the step 2 and 2b writes run unsandboxed; sandboxed, they fail `Operation not permitted` and write nothing.

#### 1a. Just-merged PR worktrees

- If the session merged a PR from a dedicated worktree, finish its cleanup in this wrap-up — reporting the path is not the finish line. You cannot remove the worktree you are standing in, so move first: `cd <main-root>` → artifact check (below) → `git worktree remove <path>` → branch deletion (below) → `git pull --ff-only origin <base>`, so the main clone stops sitting behind its own merge. The fast-forward doesn't touch peer worktrees, which sit on their own branches. Skip the pull when the project's guidance makes pulling the main clone a deploy (live jobs run from it); report the clone as behind instead.
- **When the harness forbids `cd` to the root**, `git -C <main-root> worktree remove <path>` works from inside the worktree (add `--force` only after the artifact check — it also deletes untracked files). Sandboxed, the removal can fail `Operation not permitted` on the worktree and its `.git/worktrees/<name>` record; run it unsandboxed — from the main root too: a sandboxed `git worktree remove` can delete the worktree directory and then fail on the record, leaving a half-removed worktree that only an unsandboxed `git worktree prune` repairs. The shell's cwd is then a deleted directory, so make the removal the last step and use absolute paths for anything after it.
- **Harness-managed worktrees**: a worktree-isolated session is refused that `git -C` as well — leave it with `ExitWorktree` as the last step. `remove` deletes a worktree that `EnterWorktree` created; one entered by path is refused, so use `keep` (which returns to the starting directory), then run `git -C <main-root> worktree remove <path>`. A worktree the desktop app created for the session is the app's: archiving the session hands it back.
- **Gitignored artifacts don't block removal — check for irreplaceable ones first**: `git worktree remove` succeeds when the only remaining content is gitignored (build output like `release/`, `dist/`), silently deleting it. Before removing a build worktree, check those directories for non-reproducible or pending-publish artifacts (e.g., signed installers staged for a later upload); if any exist, surface them and let the user decide. Rebuildable-by-design outputs are fine to delete — say so in the report.
- After removing, try `git branch -d <branch>`. If it refuses because the repo is squash-only, verify the PR is `MERGED` and the local tip exactly equals its merged head (`gh pr view <n> --json state,headRefOid`); a full non-dry-run `/wrap-up` then authorizes `git branch -D` for that exact session-created branch. Pre-existing branches still need separate approval.

#### 1b. Merged branches

Squash merges leave branch tips that are never ancestors of `main`, so `git branch --merged` and `-d` are both blind to them — without a PR-state check, merged branches accumulate indefinitely while cleanup reports "nothing to clean". Run the two-pass cleanup (ancestry pass + PR-state pass), packaged as [`scripts/cleanup_branches.sh`](scripts/cleanup_branches.sh):

```bash
bash <skill-dir>/scripts/cleanup_branches.sh <repo-root> [--keep <branch>]... [--keep-prefix <prefix>]...
```

Pass `--keep` for each persistent branch the project names, and `--keep-prefix <runtime>/` for each peer runtime working in the repo (e.g. `codex/`) — a peer's merged branch is still its own to clean up. `--dry-run` previews; `--base` overrides the base (default `origin/HEAD`, else `main`). Ensure `gh` is authenticated for the repo first. Under a network-filtering sandbox, run the script unsandboxed: a `gh` nested in a script can fail TLS through the proxy even when the same `gh` typed directly works. Don't trust a probe either — `gh pr list --repo <owner>/<name>` can succeed on a repo the script still can't resolve (it resolves from the local remote) — so the `SKIP pass 2` line, which quotes gh's error, is the only signal: fix auth or the sandbox and re-run. The script's contract:

- **Pass 1 (ancestry)**: `git branch --merged <base>` → `git branch -D` (the listing already proves the tip is in the base; `-d` would also demand HEAD or upstream containment, which fails from a worktree on another branch).
- **Pass 2 (PR head)**: for each remaining local branch not checked out in any worktree, look up its merged PR and delete ONLY when the local tip exactly equals that PR's merged `headRefOid` — a `MERGED` state alone is not enough, since the branch may carry unpublished commits made after the merge, and deleting it would orphan them. The exact-head verification is the safety, not the `-D` flag. The base, `--keep`/`--keep-prefix` branches, worktree-checked-out branches (including other agents'), branches with no merged PR, and branches whose tip diverged from the merged head are never deleted. Pass 2 prints `KEEP <branch> — <reason>` for the no-merged-PR and diverged-tip cases; reserved and checked-out branches print `KEEP` only when pass 1 lists them as merged and are otherwise skipped silently. Review the `KEEP` lines by hand — never `-D` those branches either.
- Run this broad pass only in the primary repo or a repo the user fully opted into. In a sibling included only for this session's artifacts, delete just the recorded branches.
- **Remote counterparts**: deleting merged remote refs on a shared repo is outward-facing — list candidates and let the user authorize `git push --delete`. Assess from `git ls-remote --heads origin` after `git remote prune origin` (`git branch -a`'s remote-tracking refs go stale and inflate the list). Repos that auto-delete head branches have already removed a merged PR's ref; `push --delete` there fails `remote ref does not exist` and breaks any `&&` chain, so let the prune be the cleanup.
- Report: "Deleted N merged branches (K ancestry + M squash); kept P unmerged" or "No merged branches to clean"

#### 1c. Stale worktrees

- Run `git worktree prune`, then list remaining: `git worktree list`
- **Leftover directories that are not worktrees**: a `.worktrees/<name>/` directory absent from `git worktree list` is residue (often just a `.claude/` inside, left when a worktree was removed without `--force`, or recreated by the harness when the removed worktree was the session's own cwd). A runtime's parent directory whose children are listed worktrees (`.worktrees/<runtime>/`) is not residue — compare leaf paths. Never count it as a stale worktree; report each with its contents and hand the user the removal command (`! rm -rf <repo>/.worktrees/<name>`) rather than deleting it yourself.
- **Peer-agent ownership guard**: a worktree whose path or branch names another agent or runtime belongs to that agent — report it, never remove it, even when its PR is merged. Peer worktrees don't always self-identify by name: another agent's PR-review checkout may appear as a detached-HEAD worktree under a temp path with no branch name. Treat any worktree this session didn't create, in a tmp path or detached at a reviewed PR's head, as peer-owned.
- For entries this session owns, remove a worktree only when its branch is merged — in squash-only repos, merged-PR evidence counts even when ancestry doesn't show it. If the only signal is a vanished remote branch, ask first (it may be intentionally local-only). Not merged → leave in place, warn.
- After removal, `git branch -d <branch>` when Git reports it merged. Never force-delete an unverified branch: `-D` only under 1a's or 1b's verification (ancestry-merged into the base, or a local tip exactly equal to its merged PR's head).
- Report: "Pruned N worktrees" or "No stale worktrees"

#### 1d. Inbox report

- Resolve the project from the `.oacp` marker at the **main** repo root — a linked worktree has no marker of its own, so a cwd read inside one silently skips this step. Pass the session's root with `git -C` so a drifted cwd can't resolve a different project:

  ```bash
  ROOT=$(dirname "$(git -C <root> rev-parse --path-format=absolute --git-common-dir)")
  [ -f "$ROOT/.oacp" ] && python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['project_name'])" "$ROOT/.oacp"
  ```

- No marker → use `basename "$ROOT"` only if `$OACP_HOME/projects/<basename>/` exists; otherwise skip the inbox report. A resolved name that isn't the session's project is a cwd bug, not an unregistered project.
- Inbox dir: `$OACP_HOME/projects/<project>/agents/<agent>/inbox/`
- List YAML files with `command ls -1 <dir> | command grep '\.yaml$'` (not a `*.yaml` glob — zsh `nomatch` errors when empty; `command` bypasses aliases; `-1` keeps the output grep-able)
- Files present → report them; never delete or archive them (OACP archives messages, and archival belongs to `/check-inbox`). Held-unverified or INVALID messages under an OACP enforce posture are surfaced explicitly, never treated as ordinary backlog. **A fresh message that verifies is unprocessed work, not a report item**: process it with `/check-inbox` now, before step 2, so the debrief covers it.
- Empty → report "Inbox clean". **A missing directory is not clean**: the agent has no workspace in that project on this machine — report "no <agent> inbox for <project> on this machine".

### 2. Run debrief (optional)

- If a `/debrief` skill is installed, invoke it — it auto-detects the project and publishes one immutable record per session to the org-memory debrief store (`$OACP_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/`). Otherwise, skip with a one-line note.
- Let `/debrief` own the record's dates: the store keys its directory and filename on the session's UTC start, not on a project's local-timezone convention.
- **Second wrap-up in one session**: if this session already has a record, neither skip the step nor re-run with the same identity (that collides by construction) — publish a continuation segment per `/debrief`'s collision handling. The test is coverage: when the latest segment's `ended_utc` is only minutes old and nothing material has happened since (bookkeeping, a memory push, this wrap-up), report that segment's path instead of publishing an empty one. Read its `ended_utc` before deciding; recall is not the check.
- If debrief fails, warn and continue — debrief is non-fatal. A missing store is not a failure; the writer provisions its own tree.

### 2b. Write org-memory events

Write events for the session's significant outcomes to the org-level memory log, which other agents read for cross-project context.

**Skip this step** if `$OACP_HOME/org-memory/events/` does not exist (org-memory not initialized — run `agent-memory org init` to set up).

**What to write**: only outcomes that matter to other agents and projects — not routine task completion.

| Write an event for | Type | Example |
|--------------------|------|---------|
| PR merged | `event` | "PR #44 merged: org-level memory spec + CLI" |
| Architecture/design decision | `decision` | "Standardized on REST for public APIs" |
| New standing rule or convention | `rule` | "All repos in this org require signed commits" |
| Release or deployment | `event` | "v0.2.0 published" |

**Do NOT write events for**: routine code fixes, test additions, doc typos, inbox messages processed, self-improve findings.

> **Existing-rule check**: before writing a `rule` or `decision`, grep the topic in `org-memory/rules.md` and `decisions.md` (headings via `command grep -n '^### '`, then keywords), in today's and yesterday's `org-memory/events/` (UTC-dated filenames — a peer's same-day event isn't folded into `decisions.md` until synthesis), and in the installed skills. Hit in org-memory → write nothing, or write only the genuine delta as a refinement pointing at the rule. Hit in a skill → the session broke a standing rule; an honest event names that rule and the delta it lacks (often a recovery path), not a rediscovery.

**How**: use `agent-memory event write`, with the step 2 debrief as source material:

```bash
agent-memory event write --home "$OACP_HOME" --agent claude --project "<project>" \
  --type <decision|event|rule> --slug <short-slug> \
  --body "<one-line description>" \
  [--source-ref <debrief-filename-stem>] [--related "PR #N,..."]
```

`--source-ref` names the debrief the event was folded from. Under `/wrap-up --dry-run`, add `--dry-run`: it validates and prints the record without writing.

> **Slug constraint**: lowercase alphanumeric + hyphens only, 1-64 chars, must start and end with alphanumeric. **No dots** — convert version segments to hyphens (e.g., `release-0-2-3` not `release-0.2.3`). Requires `agent-memory` on PATH; if it is unavailable, report the missing `agent-memory-cli` prerequisite and skip event writing. Success prints `published:` or `idempotent:`.
>
> **Under an active envelope the event body is command text to the hook**: a destructive token quoted inside `--body` (a recursive-force remove, a forced push flag, a verify-skipping flag) denies the write when the envelope declares `destructive_ops: false`, data or not. Spell the action in words — "a forced push", "the recursive remove" — never quote the flag.

**Keep it lightweight**: write events only for the outcomes in the table above — most sessions warrant none or a few. If the session was trivial (only reading files, answering questions), write zero events and report "No org-memory events (routine session)."

Report: "Wrote N org-memory events" or "Skipped (org-memory not initialized)" or "No org-memory events (routine session)".

### 3. Run /self-improve

- Invoke the `/self-improve` skill
- The skill will present findings and ask "Which changes should I apply?"
- **Pause here** — wait for user approval before continuing
- **The user has said they are away** ("stepping out", "just run wrap-up"): the pause cannot resolve, so don't hold the wrap-up on it — present the findings, apply none, record them where the user will find them on return (the project's status memory, `$OACP_HOME/projects/<project>/memory/open_threads.md`), and continue.
- Apply approved changes
- If no findings, report "No issues found" and continue

### 3b. Self-improve the self-improve skill

After step 3 completes, run `/self-improve self-improve` — a targeted review of the self-improve skill itself. This catches issues with the review process that only surface during execution (e.g., missed edge cases, incorrect analysis patterns, user corrections during step 3).

- **Skip if step 3 had no findings and no user corrections** — nothing to learn from a clean run
- If findings exist, apply with approval and commit alongside step 4

### 4. Commit changes

- Run `git status` to check for uncommitted changes
- If no changes, skip to step 4b
- Stage changed files explicitly (no `git add -A` or `git add .`)
- Exclude from staging: `.env`, credentials, secrets, `settings.json`
- Commit message: `wrap-up: <brief summary of changes>` for wrap-up's own housekeeping edits
- **Other repos step 3 edited**: self-improve can edit skills or instruction files that live in a separate repo. Commit and push those there only when this session made the edits, staging explicit paths and leaving other runtimes' files alone. Check `git -C <repo> rev-list --count origin/<branch>..HEAD` too — self-improve may commit without pushing, so a clean `status` is not "nothing to do".
- **Paused mid-dispatch on a feature branch**: commit the task's own work with its conventional message (referencing its issue), push the branch so the work survives the pause, and leave the dispatch message in the inbox — it stays unprocessed until its completion reply. The PR, review request, and merge wait for the resumed session.
- **Paused with a review round in flight**: the work is already pushed at the declared head, so there is nothing to commit, and step 5 must NOT push that branch — any push voids the reviewer's round. Write the owed close-out (what to do on feedback vs. LGTM, the message ids, the task's start time — naming only commands whose contract you checked against the script's usage header, since a hand-off can name a script that cannot do the step) to the project's status memory (`$OACP_HOME/projects/<project>/memory/open_threads.md`, read at the next session's start) and report the round as in flight.
- If `--dry-run`: show what would be committed but do not commit

### 4b. OACP memory sync (optional)

Push the cross-machine memory snapshot if memory sync is active. Captures new `org-memory/events/` entries from step 2b, debriefs from step 2, and any session memory edits.

```bash
test -f "$OACP_HOME/.oacp-memory-repo" || { echo "memory sync: not active (skip)"; exit 0; }
agent-memory push --home "$OACP_HOME" --agent claude
```

- **Skip silently** if the `.oacp-memory-repo` marker is absent — memory sync is not initialized on this machine (`agent-memory enable` to opt in, or `agent-memory clone` on a second machine). Requires `agent-memory` on PATH; if it is missing, warn and skip.
- `agent-memory push` is idempotent: it stages allowlisted files (`org-memory/**`, `projects/*/memory/**`), commits, and pushes when a remote exists. No-op if no changes.
- **Pass `--agent`**: without it the commit author falls back to `$AGENT_MEMORY_AGENT`, then `$AGENT_NAME`, then `$USER`, publishing agent-authored commits under the human's name. Name the agent actually running the session.
- **Another session's fresh uncommitted files → skip the push and say so.** Run `git -C "$OACP_HOME" status --short` first: a dirty or untracked path you did not write, modified within the last ~30 minutes, belongs to a peer session still mid-wrap-up. The push stages every allowlisted file, so pushing now would publish their in-flight edits under your commit. Report "memory: push skipped — N in-flight files from another session" and let the next push carry yours. Hours-old leftovers with no live session are the opposite case: carry them.
- If commit signing or the git credential helper needs access the sandbox blocks, run the push unsandboxed.
- Independent of step 5 — failure here does not block the current-repo push. Report the memory-push outcome separately.
- If `--dry-run`: the push has no dry-run flag — show `git -C "$OACP_HOME" status --short` and skip.
- Report: commit SHA + file count, or "memory: clean (no changes)", or "memory: skipped (sync not active)", or the skip line above.

### 5. Push to remote

- **Pull-rebase before push** to avoid conflicts with parallel runtimes that may have pushed:

  ```bash
  git pull --rebase --autostash origin <branch>
  ```

  (`--autostash` carries uncommitted files over the rebase.) If the rebase conflicts, abort with `git rebase --abort`, warn the user, and skip push; if the autostash pop conflicts, git keeps the stash — warn and resolve before pushing.
- Push current branch to origin: `git push origin <branch>` — never a branch with a review round in flight (step 4)
- If `--dry-run`: skip push
- Report: branch, commit SHA, remote URL

### 6. Summary

Print a final status block:

```
Wrap-up complete:
- Cleanup: N branches, M worktrees pruned, inbox <status>
- Debrief: <status> $OACP_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/<file>.md
- Org-memory: N events written (or "skipped" or "routine session")
- Self-improve: N findings (M applied)
- Commit: <sha> on <branch> (or "no changes" or "review round in flight")
- Other repos: <repo>@<sha> (or "none")
- OACP memory: <sha> (or "clean" or "skipped (sync not active)" or "skipped (dry-run)")
- Push: <branch> -> origin (or "skipped (dry-run)")
```

## Notes

- **Mid-wrap-up dispatches (OACP v0.4.1+ envelopes)**: if a new task auto-accepts during wrap-up, its compiled scope envelope can deny wrap-up's own later side effects (steps 4-5 commits/pushes are outside a reply-only task's envelope). Run the dispatched task's lifecycle to terminal — reply, audit update, `oacp envelope clear` — then resume wrap-up where it paused. Don't interleave the two.
- Cleanup deletes are verification-gated: ancestry-merged into the base, or a local tip exactly equal to a merged PR's head. Unverified branches are never force-deleted.
- Wrap-up reports inbox messages and never deletes or archives them: OACP archives messages rather than deleting them, and processing and archival belong to `/check-inbox`.
- Debrief failure is non-fatal. The remaining steps still run.
- Commit scope: the current repo, repos step 3 edited (both step 4), and the memory repo (4b, if the marker is present). Other repos are touched only to clean exact local worktrees or branches this session created. The debrief store is not committed separately — 4b's `agent-memory push` carries `org-memory/**`.
- Under a network-filtering sandbox, signed commits, SSH pushes, and nested `gh` calls can fail with TLS errors (e.g. `x509: OSStatus -26276`) while credentials are fine — retry unsandboxed rather than debugging the call or the token.
- Use `command grep` / `command ls` / `command find` in shell commands if your shell aliases these to other tools.
- `OACP_HOME` defaults: see `oacp doctor` for the active path.
