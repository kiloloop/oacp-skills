#!/bin/bash
# Advisory lock for OACP runtime memory edits ($OACP_HOME/projects/<project>/memory/),
# preventing concurrent writes from other runtimes.
#
# The lock must span multiple tool calls (Edit tool, not Bash), so `trap` cleanup can't
# work — each Bash invocation is a separate process. Explicit acquire/release instead.
#
# Usage:
#   memory_lock.sh acquire <project>   -> "Lock acquired" or "LOCKED" (defer edits)
#   memory_lock.sh release <project>   -> always run after edits complete, even on failure
#
# Stale locks (>10 min old) are auto-broken on acquire.

set -u
OACP_HOME="${OACP_HOME:-$HOME/oacp}"
CMD="${1:-}"
PROJECT="${2:-}"
[ -n "$PROJECT" ] || { echo "usage: memory_lock.sh acquire|release <project>" >&2; exit 2; }
LOCK_DIR="$OACP_HOME/projects/$PROJECT/.memory-write.lock"

# GNU stat first: GNU `stat -f` is filesystem mode and would print to stdout before failing.
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }

case "$CMD" in
  acquire)
    # A missing project dir would make mkdir fail and masquerade as LOCKED — fail loud instead
    [ -d "$(dirname "$LOCK_DIR")" ] || { echo "NO_SUCH_PROJECT: $(dirname "$LOCK_DIR")" >&2; exit 2; }
    if [ -d "$LOCK_DIR" ]; then
      LOCK_AGE=$(( $(date +%s) - $(mtime "$LOCK_DIR") ))
      [ "$LOCK_AGE" -gt 600 ] && rmdir "$LOCK_DIR" 2>/dev/null
    fi
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo "Lock acquired"
    else
      echo "LOCKED — deferring edits to debrief carry-over"
    fi
    ;;
  release)
    rmdir "$LOCK_DIR" 2>/dev/null && echo "Lock released" || echo "No lock to release"
    ;;
  *)
    echo "usage: memory_lock.sh acquire|release <project>" >&2
    exit 2
    ;;
esac
