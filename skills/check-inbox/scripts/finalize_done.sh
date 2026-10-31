#!/usr/bin/env bash
# finalize_done — the terminal `oacp autonomy finalize --final-state done` with the guards
# that references/autonomy.md §D–§E states:
#   1. Realized effects pass through to the canonical finalizer, which decides coverage: a
#      `--realized sends_oacp_reply` is within the envelope when the profile declares
#      `sends_oacp_reply: true` or `sends_oacp_reply_only: true` (or a grant permits it), and
#      is refused as an uncovered grant-only effect (exit 2) otherwise; an undeclared boundary
#      action (e.g. `merges_pr`) breaches into a checkpoint pause (exit 4). The Done reply's id
#      still rides `--reply-message-id` either way.
#   2. A dry-run always runs FIRST, so a clock or files overrun (exit 4) surfaces before the
#      Done reply is composed. The dry-run prints the final state and checkpoint action but NO
#      minutes — `result.actual_minutes` exists only after the real write. To quote a clock in
#      Done that equals the record's, use send_done_and_finalize.sh beside this script.
#   3. The real write happens only with `--commit`, and exactly once.
#   4. The finalize stamps `result.runtime` from OACP_RUNTIME_MODEL/OACP_RUNTIME_EFFORT or
#      --model/--effort; with neither, the record lands model and effort null (autonomy.md,
#      "Run the canonical evaluator"). When the caller supplies neither, this script reads them
#      from the Claude Code session transcript (the latest assistant row's message.model and
#      perTurnEffort, located by CLAUDE_CONFIG_DIR and CLAUDE_CODE_SESSION_ID) and refuses if
#      it cannot.
#
# Usage:  bash finalize_done.sh <audit_file> [--commit] -- <finalize args…>
#   e.g.  bash finalize_done.sh agents/claude/audit/autonomy_decisions/<rec>.yaml -- \
#           --started-at 2026-01-15T19:13:55Z --actual-files-touched 4 \
#           --realized creates_or_updates_pr --realized commits_changes
#         (dry-run only: nothing is written)
#         bash finalize_done.sh <rec> --commit -- <same args> --reply-message-id <done-msg-id>
# Exit: the finalizer's exit code (0 written/validated · 2 usage or refusal · 4 checkpoint
# breached at the dry-run — nothing written: record the pause with one bare
# `oacp autonomy finalize <rec> --final-state done` (this wrapper never does), the human clears
# it with `oacp autonomy outcome --decision approved --actor <handle> <rec>` (no --replace),
# then re-run this wrapper).
set -u
audit="${1:?usage: finalize_done.sh <audit_file> [--commit] -- <finalize args…>}"; shift
commit=0
if [ "${1:-}" = "--commit" ]; then commit=1; shift; fi
[ "${1:-}" = "--" ] && shift
for a in "$@"; do
  case "$a" in
    --completed-at|--completed-at=*)
      echo "REFUSED: --completed-at — the Done finalize stamps completion itself (a terminal-time checkpoint pins it); let the finalizer derive it (autonomy.md §E)" >&2
      exit 2 ;;
    --final-state|--final-state=*|--checkpoint|--dry-run|--commit)
      echo "REFUSED: $a — this wrapper owns --final-state done and the dry-run/commit split" >&2
      exit 2 ;;
  esac
done
has_model=0; has_effort=0
[ -n "${OACP_RUNTIME_MODEL:-}" ] && has_model=1
[ -n "${OACP_RUNTIME_EFFORT:-}" ] && has_effort=1
for a in "$@"; do
  case "$a" in --model|--model=*) has_model=1 ;; --effort|--effort=*) has_effort=1 ;; esac
done
if [ "$has_model" -eq 0 ] || [ "$has_effort" -eq 0 ]; then
  derived=$(python3 - "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" "${CLAUDE_CODE_SESSION_ID:-}" <<'PY'
import glob, json, sys
cfg, sid = sys.argv[1], sys.argv[2]
model = effort = ""
for p in (glob.glob(f"{cfg}/projects/*/{sid}.jsonl") if sid else [])[:1]:
    for line in open(p, encoding="utf-8"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant":
            continue
        m = (d.get("message") or {}).get("model") or ""
        if m and not m.startswith("<"):
            model = m
        effort = d.get("perTurnEffort") or effort
print(model or "-", effort or "-")
PY
)
  read -r d_model d_effort <<<"$derived"
  got=""
  if [ "$has_model" -eq 0 ]; then
    [ "${d_model:--}" != "-" ] || { echo "REFUSED: no runtime model — export OACP_RUNTIME_MODEL or pass --model; the session transcript gave none" >&2; exit 2; }
    export OACP_RUNTIME_MODEL="$d_model"; got="model=$d_model"
  fi
  if [ "$has_effort" -eq 0 ]; then
    [ "${d_effort:--}" != "-" ] || { echo "REFUSED: no runtime effort — export OACP_RUNTIME_EFFORT or pass --effort; the session transcript gave none" >&2; exit 2; }
    export OACP_RUNTIME_EFFORT="$d_effort"; got="${got:+$got }effort=$d_effort"
  fi
  echo "runtime from session transcript: $got" >&2
fi
echo "── dry-run (nothing written) ──"
out=$(oacp autonomy finalize "$audit" --final-state done --dry-run --json "$@" 2>&1); rc=$?
printf '%s\n' "$out"
if [ "$rc" -ne 0 ]; then
  echo "dry-run exit $rc — resolve before composing Done. 4 = the checkpoint would pause: for a terminal-time breach, record it with the bare \`oacp autonomy finalize <rec> --final-state done\` (no --dry-run; exits 4 and stamps paused_at_utc), have the human clear it with \`oacp autonomy outcome --decision approved --actor <handle> <rec>\` (no --replace), then re-run this wrapper; otherwise fix the actuals" >&2
  if [ "$rc" -eq 4 ]; then
    # A full record path wraps when pasted as one `!` line; hand the clear over as cd + glob.
    stamp=$(basename "$audit"); stamp=${stamp%%_*}
    echo "hand the human the clear as two lines (the cd persists for the next):" >&2
    echo "  ! cd $(cd "$(dirname "$audit")" && pwd)" >&2
    echo "  ! oacp autonomy outcome --decision approved --actor <handle> ${stamp}_*.yaml" >&2
  fi
  exit "$rc"
fi
if [ "$commit" -ne 1 ]; then
  echo "dry-run passed. The derived actual_minutes is ceil(active seconds / 60) and is stamped only by the real write."
  echo "Compose Done, then re-run with --commit -- <same args> --reply-message-id <done-msg-id>."
  exit 0
fi
echo "── real finalize (once) ──"
oacp autonomy finalize "$audit" --final-state done --json "$@"
