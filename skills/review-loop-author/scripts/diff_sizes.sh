#!/usr/bin/env bash
# diff_sizes — the size figures a review_request quotes, measured rather than typed.
#
# Prints the per-file `git diff --histogram --numstat` rows and the `--shortstat`
# totals between two refs, in the form Step 4 asks to paste into the request's
# diff_summary. Three-dot range: the diff runs from the merge base of the two refs
# to the head, so `main` as the base measures the PR against the branch point even
# after main has moved, and two commits on one branch measure the fix delta.
#
# Usage:
#   bash diff_sizes.sh <repo-dir> <base-ref> <head-ref>
#   bash diff_sizes.sh "$REPO_PATH" main "$REQUESTED_HEAD"        # round 1: the PR against its base
#   bash diff_sizes.sh "$REPO_PATH" <reviewed-head> <new-head>    # round N+1: the fix delta
#
# Output is the figures only, so it can be pasted whole; exit code is git's.
set -u
if [ "$#" -ne 3 ]; then
  echo "usage: diff_sizes.sh <repo-dir> <base-ref> <head-ref>" >&2
  exit 2
fi
repo="$1"; base="$2"; head="$3"
echo "numstat ${base}...${head} (added deleted path):"
git -C "$repo" diff --histogram --numstat "${base}...${head}" || exit $?
echo "shortstat ${base}...${head}:"
git -C "$repo" diff --histogram --shortstat "${base}...${head}"
