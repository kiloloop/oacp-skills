#!/usr/bin/env bash
# send_done_and_finalize — the Done reply and the terminal finalize as ONE step, so the work
# clock quoted in Done is the number the audit record stamps.
#
# Why: `oacp autonomy finalize --dry-run` prints no minutes, the real finalize needs the Done
# reply's message id, and a Done body is signed at send — so a clock computed by hand a few tool
# calls before the finalize can land a minute off the record. This script fills the body's
# placeholders, sends, and finalizes back to back, then compares the quoted figure with
# `result.actual_minutes` and prints MATCH or MISMATCH.
#
# {{MINUTES}} = ceil((now - started_at) / 60), the finalizer's own rounding — and ONLY when the
# record carries nothing the finalizer would subtract (no threshold_checkpoint.paused_at_utc, no
# pause_intervals, no clock_adjustments). Pause arithmetic is the finalizer's: on such a record
# this script REFUSES a body that uses {{MINUTES}} — write the clock as start → {{END}} and point
# at `result.actual_minutes` instead.
# {{END}} = the send time, except on a terminal-time checkpoint (`terminal_time: true`): the
# finalizer pins completion at the checkpoint, so {{END}} fills with that pinned
# `completed_at_utc` — the send time would contradict the record the reply points at.
# After the finalize it reports the active envelope (completion ordering: reply → terminal
# finalize → clear): when it is this task's, it prints the standalone `oacp envelope clear` to
# run next; another task's envelope, or unreadable state, is named and left in place. It never
# clears itself — the CLI's clear is not conditional on the task, so a clear from here could
# remove a successor's envelope. A leftover envelope denies the session's later work.
#
# Exit: 0 sent + finalized + MATCH (or no minutes quoted) · 1 refused/failed before the send ·
# 3 sent but the finalize failed (4 = checkpoint → the human clears it, then run
# finalize_done.sh --commit -- <same args> --reply-message-id <printed id>) · 5 MISMATCH (send a
# threaded correction quoting the record).
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat >&2 <<'EOF'
usage: send_done_and_finalize.sh <audit_file> <project> <to> <in_reply_to_msg_id> \
         <conversation_id> <subject> <body_file> \
         [--type <type>] [--from <agent>] [--priority <P0-P3>] [--print-only] -- <finalize args…>
  <body_file>      may carry {{END}} (UTC completion stamp) and {{MINUTES}} (the work clock)
  <finalize args>  finalize_done.sh's: --started-at <utc> --actual-files-touched N
                   [--artifact '<repo> <sha>' …] [--realized <effect> …] — one flag per value;
                   never --reply-message-id (this script supplies it)
  --type           reply type (default notification; answer a brainstorm_request with
                   brainstorm_followup)
  --from           sender agent (default claude)
  --print-only     fill the body and run the dry-run; send nothing, finalize nothing
EOF
  exit 1
}

[ "$#" -ge 8 ] || usage
audit="$1"; project="$2"; to="$3"; parent="$4"; conv="$5"; subject="$6"; body="$7"; shift 7
print_only=0
done_type="notification"
sender="claude"
priority=""
while :; do
  case "${1:-}" in
    --print-only) print_only=1; shift ;;
    --type|--from|--priority)
      [ -n "${2:-}" ] || { echo "REFUSED: $1 needs a value" >&2; exit 1; }
      case "$1" in
        --type) done_type="$2" ;;
        --from) sender="$2" ;;
        --priority) priority="$2" ;;
      esac
      shift 2 ;;
    *) break ;;
  esac
done
[ "${1:-}" = "--" ] && shift
[ -f "$audit" ] || { echo "REFUSED: audit record not found: $audit" >&2; exit 1; }
[ -f "$body" ] || { echo "REFUSED: body file not found: $body" >&2; exit 1; }
started=""; prev=""
for a in "$@"; do
  [ "$prev" = "--started-at" ] && started="$a"
  case "$a" in
    --started-at=*) started="${a#--started-at=}" ;;
    --reply-message-id|--reply-message-id=*)
      echo "REFUSED: --reply-message-id is supplied by this script" >&2; exit 1 ;;
  esac
  prev="$a"
done
[ -n "$started" ] || { echo "REFUSED: finalize args must carry --started-at <utc>" >&2; exit 1; }

# 1 — fill the body first, so a refusal surfaces before anything runs. Python reads the record
# only to decide whether a clock may be computed and which {{END}} applies.
final="$(mktemp "${TMPDIR:-/tmp}/done-body.XXXXXX")" || { echo "REFUSED: no temp file" >&2; exit 1; }
quoted=$(python3 - "$audit" "$body" "$final" "$started" <<'PY'
import datetime as dt, math, re, sys, time
audit, body_path, final_path, started = sys.argv[1:5]
text = open(audit, encoding="utf-8").read()
body = open(body_path, encoding="utf-8").read()

def has_value(key):
    # any occurrence of the key with a non-empty scalar, or a block list under it
    for m in re.finditer(rf"^\s*{key}:[ \t]*(.*)$", text, re.M):
        v = m.group(1).strip()
        if v == "":
            nxt = text[m.end():].lstrip("\n").split("\n", 1)[0]
            if nxt.lstrip().startswith("- "):
                return True
        elif v not in ("null", "~", "[]", "{}"):
            return True
    return False

subtracts = [k for k in ("paused_at_utc", "pause_intervals", "clock_adjustments") if has_value(k)]
try:
    start = dt.datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
except ValueError:
    sys.stderr.write("REFUSED: --started-at must be YYYY-MM-DDTHH:MM:SSZ\n"); sys.exit(1)
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
minutes = ""
if "{{MINUTES}}" in body:
    if subtracts:
        sys.stderr.write(
            "REFUSED: the record carries " + ", ".join(subtracts) + " — the finalizer subtracts "
            "those and this script does no pause arithmetic. Drop {{MINUTES}} from the body: quote "
            "start → {{END}} and point at result.actual_minutes.\n")
        sys.exit(1)
    elapsed = (now - start).total_seconds()
    if elapsed < 0:
        sys.stderr.write("REFUSED: --started-at is in the future\n"); sys.exit(1)
    # keep clear of a minute boundary: the finalize stamps a few seconds after the send
    if elapsed % 60 != 0 and 60 - (elapsed % 60) < 20:
        time.sleep(60 - (elapsed % 60) + 1)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        elapsed = (now - start).total_seconds()
    minutes = str(int(math.ceil(elapsed / 60.0)))
end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
if "{{END}}" in body and re.search(r"^\s*terminal_time:\s*true\s*$", text, re.M):
    pinned = re.findall(r"^\s*completed_at_utc:\s*['\"]?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)['\"]?\s*$", text, re.M)
    if not pinned:
        sys.stderr.write("REFUSED: terminal_time checkpoint carries no pinned completed_at_utc for {{END}}\n")
        sys.exit(1)
    end = pinned[0]
body = body.replace("{{END}}", end).replace("{{MINUTES}}", minutes)
if "{{" in body:
    sys.stderr.write("REFUSED: unfilled placeholder left in the body\n"); sys.exit(1)
open(final_path, "w", encoding="utf-8").write(body)
print(minutes)
PY
) || exit 1

# 2 — the dry-run gate (finalize_done.sh owns its guards; nothing is written).
bash "$here/finalize_done.sh" "$audit" -- "$@" || { echo "dry-run did not pass — nothing sent" >&2; exit 1; }

if [ "$print_only" -eq 1 ]; then
  echo "── print-only: body as it would be sent (quoted minutes: ${quoted:-none}) ──"
  cat "$final"
  exit 0
fi

# 3 — send, then finalize at once with the reply id.
send_args=(--from "$sender" --to "$to" --type "$done_type" --subject "$subject"
  --body-file "$final" --in-reply-to "$parent" --conversation-id "$conv" --json)
[ -n "$priority" ] && send_args+=(--priority "$priority")
[ -n "${OACP_HOME:-}" ] && send_args+=(--oacp-dir "$OACP_HOME")
out=$(oacp send "$project" "${send_args[@]}" 2>&1) \
  || { printf '%s\n' "$out" >&2; echo "send failed — nothing finalized" >&2; exit 1; }
mid=$(printf '%s' "$out" | python3 -c "import json,re,sys; m=re.search(r'\{.*\}', sys.stdin.read(), re.S); print(json.loads(m.group(0))['message_id'])") \
  || { printf '%s\n' "$out" >&2; echo "sent, but no message_id could be read — finalize by hand" >&2; exit 3; }
# The recipient's inbox path is what the post-send check needs; the message id cannot stand in
# for it (the filename carries a different short hash than the id).
inbox_path=$(printf '%s' "$out" | python3 -c "import json,re,sys; m=re.search(r'\{.*\}', sys.stdin.read(), re.S); d=json.loads(m.group(0)); print(d.get('inbox_path') or ' '.join(d.get('inbox_paths', [])))" 2>/dev/null)
echo "Done sent: $mid (quoted minutes: ${quoted:-none})"
echo "inbox: ${inbox_path:-?}  (post-send check: test -f, then oacp verify --receiver $to)"
bash "$here/finalize_done.sh" "$audit" --commit -- "$@" --reply-message-id "$mid"; rc=$?
if [ "$rc" -ne 0 ]; then
  echo "finalize exit $rc AFTER the send — Done id $mid. 4 = checkpoint: the human clears it via \`oacp autonomy outcome\`, then run finalize_done.sh --commit -- <same args> --reply-message-id $mid" >&2
  exit 3
fi

# 4 — the record is terminal: say whose envelope is active and hand over the clear. Read only:
# `oacp envelope clear` removes whatever envelope is active, so a clear issued from here could
# remove a task compiled after this comparison. The operator runs it as a standalone command.
home="${OACP_HOME:-$HOME/oacp}"
env_file="$home/projects/$project/agents/$sender/state/active_envelope.json"
if [ -f "$env_file" ]; then
  env_mid=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("message_id",""))' "$env_file" 2>/dev/null)
  rec_mid=$(python3 -c 'import re,sys; m=re.search(r"^message_id:\s*(\S+)", open(sys.argv[1], encoding="utf-8").read(), re.M); print(m.group(1) if m else "")' "$audit")
  if [ -z "$env_mid" ]; then
    echo "envelope: unreadable state at $env_file — left in place; inspect it before any clear" >&2
  elif [ "$env_mid" = "$rec_mid" ]; then
    echo "envelope: still active for this task ($rec_mid) — clear it now, as a standalone command:"
    echo "  oacp envelope clear --project $project --receiver $sender${OACP_HOME:+ --oacp-dir $OACP_HOME}"
  else
    echo "envelope: the active one belongs to $env_mid, not ${rec_mid:-?} — left in place; clear it at that task's completion" >&2
  fi
else
  echo "envelope: none active"
fi

# 5 — the record is the authority: compare.
recorded=$(python3 - "$audit" <<'PY'
import re, sys
m = re.search(r"^  actual_minutes:\s*(\S+)", open(sys.argv[1], encoding="utf-8").read(), re.M)
print(m.group(1) if m else "")
PY
)
if [ -z "${quoted:-}" ]; then
  echo "record actual_minutes: ${recorded:-?} (no figure was quoted in Done)"
elif [ "$quoted" = "$recorded" ]; then
  echo "MATCH: Done quotes $quoted min = result.actual_minutes"
else
  echo "MISMATCH: Done quotes $quoted min, the record says ${recorded:-?} — send a threaded correction quoting the record" >&2
  exit 5
fi
