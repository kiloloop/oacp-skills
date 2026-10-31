#!/bin/bash
# self-improve pass marker — check for / write the same-day-repeat detection marker.
#
# Usage (run from the primary repo root — the project name comes from the cwd):
#   pass_marker.sh check            -> prints PRIOR_PASS / NO_PRIOR_PASS
#   pass_marker.sh append <scope>   -> records a completed pass for today
#
# The marker is a sidecar state file, NOT a line inside the debrief:
#
#   $OACP_HOME/state/self-improve/<project>-<YYYYMMDD>.marker
#
# Debrief records in the OACP org-memory store are immutable and carry a
# content_sha256 over their exact body bytes, so appending a marker to one
# silently corrupts the hash of the artifact built to be tamper-evident. A
# sidecar also survives whatever consumes or rotates the debrief. `state/` is
# machine-local (never synced), so the marker answers "did a pass run on THIS
# machine today".
#
# Mechanics:
# - "Today" is the user's day, not UTC's: dates are taken in $SELF_IMPROVE_TZ
#   (an IANA zone, e.g. America/New_York) or, when unset, the machine's local
#   timezone. Pin it if the machine's clock follows a travel location.
# - A post-midnight marathon is still working the PRIOR day: before 05:00
#   `check` also accepts yesterday's marker, and `append` records against
#   yesterday when that marker already exists.
# - After 05:00 a yesterday marker still counts when it was written within the
#   last 12 hours, so a pre-05:00 pass (filed under yesterday) is seen by a
#   check later that morning.
# - One marker per project per day; `append` overwrites, latest pass wins.
# - PASS_MARKER_NOW (epoch seconds) pins the clock for tests/test_pass_marker.py.

set -u

# $HOME can be empty or unset in some sandboxed or automation shells, which
# would silently resolve every path under / and report NO_PRIOR_PASS.
if [ -z "${HOME:-}" ]; then
  HOME=$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)')
  export HOME
fi

OACP_HOME="${OACP_HOME:-$HOME/oacp}"
STATE_DIR="$OACP_HOME/state/self-improve"

# Main repo root even inside a worktree checkout: --show-toplevel returns the
# worktree dir there, which would file the marker under the worktree's name.
COMMON=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
if [ -n "$COMMON" ]; then PROJECT=$(basename "$(dirname "$COMMON")"); else PROJECT=$(basename "$(pwd)"); fi

NOW="${PASS_MARKER_NOW:-$(date +%s)}"

# fmt <epoch> <strftime format> — in the user's zone; BSD date, then GNU date.
fmt() {
  if [ -n "${SELF_IMPROVE_TZ:-}" ]; then
    TZ="$SELF_IMPROVE_TZ" date -r "$1" "+$2" 2>/dev/null || TZ="$SELF_IMPROVE_TZ" date -d "@$1" "+$2"
  else
    date -r "$1" "+$2" 2>/dev/null || date -d "@$1" "+$2"
  fi
}
# GNU stat first: GNU `stat -f` is filesystem mode and would print to stdout before failing.
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }

HOUR=$(( 10#$(fmt "$NOW" %H) ))
# Yesterday's date without day-length arithmetic: step back to around midnight,
# then 12 more hours — lands mid-yesterday even across a DST change.
YESTERDAY_EPOCH=$(( NOW - HOUR * 3600 - 43200 ))

marker_for_date() { echo "$STATE_DIR/${PROJECT}-$1.marker"; }
MARKER=$(marker_for_date "$(fmt "$NOW" %Y%m%d)")
YMARKER=$(marker_for_date "$(fmt "$YESTERDAY_EPOCH" %Y%m%d)")

case "${1:-}" in
  check)
    [ -f "$MARKER" ] && { echo "PRIOR_PASS"; exit 0; }
    if [ -f "$YMARKER" ]; then
      [ "$HOUR" -lt 5 ] && { echo "PRIOR_PASS"; exit 0; }
      AGE=$(( NOW - $(mtime "$YMARKER") ))
      [ "$AGE" -lt 43200 ] && { echo "PRIOR_PASS"; exit 0; }
    fi
    echo "NO_PRIOR_PASS"
    ;;
  append)
    SCOPE="${2:-full}"
    TS=$(fmt "$NOW" %H:%M)
    if [ ! -f "$MARKER" ] && [ "$HOUR" -lt 5 ] && [ -f "$YMARKER" ]; then
      MARKER="$YMARKER"
    fi
    if ! mkdir -p "$STATE_DIR" 2>/dev/null; then
      echo "cannot create $STATE_DIR — marker skipped (next run does a full pass)" >&2
      exit 0
    fi
    printf '%s scope=%s\n' "$TS" "$SCOPE" > "$MARKER"
    # Print the resolved path: a cwd drifted into another repo resolves to the
    # wrong project, and this line is where that shows.
    echo "marker recorded: $MARKER ($TS scope=$SCOPE)"
    ;;
  *)
    echo "usage: pass_marker.sh check | append <scope>" >&2
    exit 2
    ;;
esac
