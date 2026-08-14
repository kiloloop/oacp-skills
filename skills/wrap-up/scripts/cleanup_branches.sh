#!/usr/bin/env bash
# Two-pass local branch cleanup for regular and squash-only repositories.
#
# A squash merge creates a new base-branch commit, so ancestry alone cannot
# prove that a topic branch is disposable. Pass 2 deletes only when the local
# tip exactly equals a merged PR's headRefOid. MERGED state alone is not enough:
# a branch may contain unpublished post-merge commits.
#
# Usage:
#   bash cleanup_branches.sh [repo-root] [--base <branch>] [--keep <branch>]...
#   bash cleanup_branches.sh [repo-root] --dry-run [other options]
#
# The caller must establish the repository-authorized GitHub identity before
# running the script. Remote branches are never deleted.

set -u

REPO_ROOT="."
BASE_BRANCH=""
DRY_RUN=0
KEEP_BRANCHES=()
POSITIONAL_SEEN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base)
      [ "$#" -ge 2 ] || { echo "ERROR: --base requires a branch" >&2; exit 2; }
      BASE_BRANCH="$2"
      shift 2
      ;;
    --keep)
      [ "$#" -ge 2 ] || { echo "ERROR: --keep requires a branch" >&2; exit 2; }
      KEEP_BRANCHES+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
    *)
      [ "$POSITIONAL_SEEN" -eq 0 ] || {
        echo "ERROR: only one repo-root positional argument is allowed" >&2
        exit 2
      }
      REPO_ROOT="$1"
      POSITIONAL_SEEN=1
      shift
      ;;
  esac
done

cd "$REPO_ROOT" || exit 1
REPO_ROOT="$(git rev-parse --show-toplevel)" || exit 1
cd "$REPO_ROOT" || exit 1

if [ -z "$BASE_BRANCH" ]; then
  BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
  BASE_BRANCH="${BASE_BRANCH:-main}"
fi
BASE_REF="$BASE_BRANCH"
git show-ref --verify --quiet "refs/heads/$BASE_BRANCH" ||
  BASE_REF="origin/$BASE_BRANCH"
git rev-parse --verify "$BASE_REF^{commit}" >/dev/null 2>&1 || {
  echo "ERROR: base branch is not resolvable: $BASE_BRANCH" >&2
  exit 1
}

should_keep() {
  local candidate="$1"
  local kept
  [ "$candidate" = "$BASE_BRANCH" ] && return 0
  [ "${#KEEP_BRANCHES[@]}" -eq 0 ] && return 1
  for kept in "${KEEP_BRANCHES[@]}"; do
    [ "$candidate" = "$kept" ] && return 0
  done
  return 1
}

checked_out_path() {
  git for-each-ref --format='%(worktreepath)' "refs/heads/$1"
}

delete_or_preview() {
  local branch="$1"
  local kind="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "WOULD prune ($kind): $branch"
    return 0
  fi
  if [ "$kind" = "ancestry" ]; then
    git branch -d "$branch" && echo "pruned (ancestry): $branch"
  else
    git branch -D "$branch" &&
      echo "pruned (squash-merged, tip == merged PR head): $branch"
  fi
}

# Pass 1 — regular / fast-forward ancestry.
while IFS= read -r branch; do
  [ -n "$branch" ] || continue
  if should_keep "$branch"; then
    echo "KEEP $branch — base or persistent branch"
    continue
  fi
  worktree_path="$(checked_out_path "$branch")"
  if [ -n "$worktree_path" ]; then
    echo "KEEP $branch — checked out at $worktree_path"
    continue
  fi
  delete_or_preview "$branch" "ancestry"
done < <(git branch --format='%(refname:short)' --merged "$BASE_REF")

# Pass 2 — squash merges, guarded by exact merged PR head identity.
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)"
if [ -z "$REPO" ]; then
  echo "SKIP pass 2 — gh cannot resolve this repository with the authorized identity"
  echo "cleanup_branches: complete"
  exit 0
fi

while IFS= read -r branch; do
  [ -n "$branch" ] || continue
  if should_keep "$branch"; then
    continue
  fi
  worktree_path="$(checked_out_path "$branch")"
  [ -z "$worktree_path" ] || continue

  merged_head="$(gh pr list --repo "$REPO" --head "$branch" --state merged --limit 1     --json headRefOid --jq '.[0].headRefOid' 2>/dev/null)"
  if [ -z "$merged_head" ]; then
    echo "KEEP $branch — no merged PR found"
    continue
  fi
  local_tip="$(git rev-parse "refs/heads/$branch" 2>/dev/null)"
  if [ "$local_tip" = "$merged_head" ]; then
    delete_or_preview "$branch" "squash"
  else
    echo "KEEP $branch — local tip $local_tip != merged PR head $merged_head"
  fi
done < <(git for-each-ref --format='%(refname:short)' refs/heads/)

echo "cleanup_branches: complete"
