#!/usr/bin/env bash
# oacp_archive.sh — terminal archival of a processed inbox message (OACP inbox_outbox spec):
# digest-checked, no-clobber move to <inbox>/archive/<filename>, byte-preserving so signed
# evidence survives. Every guard fails closed. A RETAINED line means nothing moved and the
# message stays pending in inbox/; an ERROR line means the move ran but a post-move identity
# check failed — inspect before any retry. archive/ is provisioned by workspace
# init/migration — never mkdir -p it here; a missing or symlinked archive/ is a degraded
# workspace.
#
# Usage: bash oacp_archive.sh <inbox_dir> <filename> <accepted_sha256>
# <accepted_sha256> is the digest captured at intake; the live file is re-hashed and must
# match, so a message that changed since it was read is retained, not moved.
# Exit 0 only on ARCHIVED; 1 on any RETAINED/ERROR line; 2 on usage error.

set -u

if [ "$#" -ne 3 ]; then
  echo "usage: oacp_archive.sh <inbox_dir> <filename> <accepted_sha256>" >&2
  exit 2
fi

d="$1"; f="$2"; want="$3"

sha() { shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1; }

case "$f" in
  ""|*/*|.|..) echo "RETAINED: filename must be a bare inbox entry name"; exit 1 ;;
esac
[ -d "$d/archive" ] && [ ! -L "$d/archive" ] \
  || { echo "RETAINED: archive/ missing or symlinked — provision via workspace migration"; exit 1; }
[ -f "$d/$f" ] && [ ! -L "$d/$f" ] \
  || { echo "RETAINED: source missing or not a regular file"; exit 1; }
live=$(sha "$d/$f")
[ -n "$live" ] || { echo "RETAINED: digest read failed"; exit 1; }
[ "$live" = "$want" ] \
  || { echo "RETAINED: digest drift — re-verify before any further processing"; exit 1; }
[ ! -e "$d/archive/$f" ] && [ ! -L "$d/archive/$f" ] \
  || { echo "RETAINED: destination exists — never overwrite history"; exit 1; }
mv -n "$d/$f" "$d/archive/$f" \
  || { echo "RETAINED: move failed"; exit 1; }
[ ! -e "$d/$f" ] && [ ! -L "$d/$f" ] \
  || { echo "ERROR: source path still present after move (skipped move or concurrent re-creation) — inspect before retry"; exit 1; }
arch=$(sha "$d/archive/$f")
[ -f "$d/archive/$f" ] && [ ! -L "$d/archive/$f" ] && [ "$arch" = "$want" ] \
  || { echo "ERROR: archived copy missing or digest mismatch — inspect before retry"; exit 1; }
echo "ARCHIVED: $d/archive/$f"
