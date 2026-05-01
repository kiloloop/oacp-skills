---
name: wrap-up
description: End-of-session cleanup for Codex - cleanup, optional debrief, self-improve, commit, memory sync, and push in one command.
---

# /wrap-up - Codex Session Wrap-Up

Run end-of-session hygiene in one ordered sequence: cleanup, optional debrief,
org-memory events, self-improve, commit, OACP memory sync, pull-rebase + push,
and a final summary.

## Interface

```bash
/wrap-up
/wrap-up --dry-run
```

- `/wrap-up`: run the full sequence.
- `/wrap-up --dry-run`: run Steps 1-4, then report what Steps 5-7 would do
  without committing, memory-syncing, or pushing.

## Workflow

When the user runs `/wrap-up`, execute these steps in order.

### 1. Cleanup stale artifacts

Scope: just-merged PR worktrees, merged local branches, stale worktrees, and
pending inbox messages. Use safe cleanup only; never force-delete a branch.

Start with repo and base-branch context:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
BASE_BRANCH="${BASE_BRANCH:-main}"
BASE_REF="$BASE_BRANCH"
git show-ref --verify --quiet "refs/heads/$BASE_BRANCH" || BASE_REF="origin/$BASE_BRANCH"
CURRENT_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
```

#### 1a. Just-merged PR worktrees

If this session merged a PR from a dedicated worktree under
`<repo-root>/.worktrees/`, remove that worktree immediately from a surviving
checkout:

```bash
git worktree remove <path>
git branch -d <branch>
```

- Do not remove the worktree if the current shell is inside it. Report the path
  and rerun cleanup from the main clone or another worktree.
- If `git branch -d` fails after a squash merge, keep the branch and report it
  as a squash-merged local leftover. Do not use `git branch -D`.

#### 1b. Merged branches

List local branches merged into the base branch:

```bash
MERGED_BRANCHES="$(git branch --merged "$BASE_REF" | command grep -v '^\*\|^[[:space:]]*'"$BASE_BRANCH"'$' || true)"
printf '%s\n' "$MERGED_BRANCHES"
```

Delete each listed branch with safe delete only:

```bash
git branch -d <branch>
```

Report either `Deleted N merged branches: ...` or
`No merged branches to clean`.

#### 1c. Stale worktrees

Prune missing worktree admin entries, then inspect repo-local worktrees:

```bash
git worktree prune
git worktree list --porcelain
```

For worktrees under `<repo-root>/.worktrees/`:

- If the worktree is the current checkout, keep it and report that cleanup must
  run elsewhere.
- If its branch is merged into `$BASE_REF` and the worktree is clean, remove
  it with `git worktree remove <path>`, then try `git branch -d <branch>`.
- If it has modified or untracked files, keep it and report it as dirty.
- If it is not merged, keep it and report it as still active.
- If the only stale signal is a missing remote branch, ask before removal.

Report either `Pruned N worktrees` or `No stale worktrees`.

#### 1d. Inbox status

Resolve the project from OACP markers:

```bash
PROJECT="$(python3 - <<'PY'
import json
import os

def project_from_marker(path: str) -> str:
    if not (os.path.isfile(path) or os.path.islink(path)):
        return ""
    try:
        resolved = os.path.realpath(path) if os.path.islink(path) else path
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("project_name", "") or ""
    except Exception:
        return ""

for marker in (".oacp", "workspace.json"):
    project = project_from_marker(marker)
    if project:
        print(project)
        break
else:
    print("")
PY
)"
```

If the project is empty, report `Inbox skipped (no OACP project marker)`.
Otherwise, use the OACP CLI snapshot as the source of truth:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
INBOX_JSON_FILE="$(mktemp)"
trap 'rm -f "$INBOX_JSON_FILE"' EXIT
oacp inbox "$PROJECT" --agent codex --oacp-dir "$OACP_ROOT" --json >"$INBOX_JSON_FILE"
python3 - "$INBOX_JSON_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)
for agent in report.get("agents", []):
    for message in agent.get("messages", []):
        path = str(message.get("path", "")).strip()
        if path.endswith(".yaml"):
            print(path)
PY
```

- If `oacp` is unavailable or the project is absent from `$OACP_ROOT`, warn and
  continue.
- If files exist, report them to the user. Do not auto-delete inbox messages.
- If none exist, report `Inbox clean`.

### 2. Debrief

Debrief is non-fatal. Use the first available target:

1. If a `/debrief` skill is installed, run it and let it write to its
   configured location.
2. Else if `$CORTEX_HOME` points at a clone of `kiloloop/cortex`, write the
   debrief there following that repo's inbox layout.
3. Else write a concise session summary to `./.oacp/debriefs/YYYY-MM-DD.md`
   inside the current repo, creating the directory if needed.

If a configured debrief target fails, warn and continue to Step 3.

### 3. Org-memory events

Write org-memory events only for outcomes that matter to other agents or
projects. Skip routine completions, inbox messages processed, minor doc edits,
and self-improve findings.

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
test -d "$OACP_ROOT/org-memory/events" || { echo "Skipped (org-memory not initialized)"; exit 0; }
```

Use `oacp write-event` with the Codex agent name:

```bash
oacp write-event --agent codex --project <project> \
  --type <decision|event|rule> --slug <short-slug> \
  --body "<one-line description>" \
  [--related "PR #N,..."] \
  [--oacp-dir "$OACP_ROOT"]
```

Guidance:

- Write at most 3-5 events.
- Use lowercase alphanumeric slugs with hyphens only.
- Convert version dots in slugs to hyphens, such as `cli-0-3-0-released`.
- Report `Wrote N org-memory events`, `Skipped (org-memory not initialized)`,
  or `No org-memory events (routine session)`.

### 4. Run /self-improve

`/self-improve` is a hard dependency.

- Invoke `/self-improve` with full scope: skills, memory, and config.
- If the skill is not installed, stop with this install hint:

  ```bash
  mkdir -p .agents/skills/self-improve
  cp skills/self-improve/codex/SKILL.md .agents/skills/self-improve/SKILL.md
  ```

- Pause when `/self-improve` asks which changes to apply.
- Apply only approved changes.
- If no findings are reported, continue.

Optional follow-up: if Step 4 produced findings or the user corrected the
process, run `/self-improve self-improve` and apply only approved changes.

### 5. Commit current repo

Skip this step in `--dry-run`.

Check the current repo:

```bash
git status --short
```

If there are no changes, report `Commit: no changes` and continue.

Rules:

- Commit only the current repo. Other repos are out of scope unless the user
  explicitly opts in.
- Do not commit unrelated pre-existing user work. If the tree is already dirty
  with unrelated changes, report the skipped paths and leave them unstaged.
- Stage files explicitly; do not use `git add -A` or `git add .`.
- Exclude `.env`, credentials, private keys, `settings.json`, and
  `settings.local.json` unless the user explicitly asks.
- Exclude ephemeral runtime artifacts such as live lockfiles and local
  permission files.
- Commit message: `wrap-up: <brief summary>`.

### 6. OACP memory sync

Skip this step in `--dry-run`.

Sync memory through the OACP CLI instead of manual git commands:

```bash
OACP_ROOT="${OACP_HOME:-$HOME/oacp}"
test -f "$OACP_ROOT/.oacp-memory-repo" || { echo "memory: skipped (sync not active)"; exit 0; }
oacp memory push --oacp-dir "$OACP_ROOT"
```

Rules:

- Memory sync is independent of the current-repo commit and push.
- If `oacp memory push` fails, report the failure and continue to Step 7.
- Do not force-push or manually edit memory repo git state.
- SSH signing or agent socket access requirements must be described in prose
  and handled by the active runtime configuration, not by inline bypass flags.

Report the memory result: pushed commit SHA, clean/no changes, skipped, or
failed.

### 7. Pull-rebase and push current repo

Skip this step in `--dry-run`.

Before pushing:

- Inspect `git remote -v`. If a remote contains an embedded credential, reset it
  to a plain GitHub URL before continuing.
- Follow the active repo's `AGENTS.md` for authentication requirements.
- Pull with rebase before pushing the current branch:

  ```bash
  BRANCH="$(git branch --show-current)"
  git pull --rebase origin "$BRANCH"
  git push origin "$BRANCH"
  ```

- If the branch is detached, report that push is skipped.
- If rebase conflicts, run `git rebase --abort`, report the conflict, and skip
  push.

Report branch, commit SHA, and remote URL with any credential redacted.

### 8. Summary

Print a final status block:

```text
Wrap-up complete:
- Cleanup: N branches, M worktrees pruned, inbox <status>
- Debrief: <mode> - <path or "skipped">
- Org-memory: N events written (or "skipped" or "routine session")
- Self-improve: N findings (M applied)
- Commit: <sha> on <branch> (or "no changes" / "skipped")
- OACP memory: <sha> (or "clean" / "skipped" / "failed")
- Push: <branch> -> origin (or "skipped")
```

## Guardrails

- Use safe branch deletion only: `git branch -d`, never `-D`.
- Never auto-delete inbox messages.
- Debrief and memory-sync failures are non-fatal.
- Keep commits scoped to the current repo unless the user explicitly expands
  scope.
- Do not inline runtime-specific sandbox bypass flags.
- Preserve unrelated user changes.
