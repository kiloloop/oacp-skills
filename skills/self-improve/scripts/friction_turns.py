#!/usr/bin/env python3
"""friction_turns.py — list a Claude Code session's GENUINE user turns for the /self-improve
session-friction pass (Step 4.5 Phase A).

Usage:
    python3 friction_turns.py <session.jsonl> [--after HH:MM | --after <ISO timestamp>]
                              [--tz <IANA zone>] [--width 110]

Why a script: the jsonl renders many machine rows as `type: "user"` — system reminders, task
notifications, injected skill bodies, MCP server instructions, compaction continuations — and an
event-driven session can carry more of them than real messages. An inflated count manufactures a
full friction pass out of machine text (it gates the ~10-turn skip threshold and the 2+ clustering
threshold); a deflated one scores a session with real corrections as having none. Extend SKIP when a
new wrapper shape appears — any row that reads like documentation rather than something a person
would type is a wrapper — and add the shape to ../tests/test_friction_turns.py, which runs this
script on one small transcript per shape.

Row shapes handled:
- `type == "user"`            — a typed turn (string content or text blocks); SKIP filters wrappers.
  A text block that is wholly a `<system-reminder>`, and a `!` command's output, are cut out first:
  the desktop app writes both into the row that carries the typed text.
- `type == "queue-operation"` — a message that went through the input queue. How it left the queue
  says whether a turn was running when it was typed:
  - an `enqueue` followed at once by a `dequeue`, with no `user` or `assistant` row between, was
    typed while the agent was idle. The desktop app queues every typed message this way, and the
    `user` row the dequeue delivers is the turn, so the enqueue is dropped (tagging it would make
    every turn of a desktop-app session read as `[mid-turn]`).
  - any other enqueue was typed while a turn ran, and is tagged `[mid-turn]`: one closed by a
    `remove` (`reason: absorbed_mid_turn`, folded into the running turn as an `attachment`), one
    closed by a `dequeue` after the running turn's rows, or one not closed yet. An absorbed message
    is NEVER written as a `user` row, so a user-only scan drops it silently — and mid-turn is exactly
    when a user interrupts to redirect ("no", "stop"), so the dropped rows skew toward the sharpest
    friction signal. Keep `operation == "enqueue"` only: the paired dequeue/remove row repeats or
    omits the text, and the separate `attachment` row (`attachment.type == "queued_command"`) is a
    third copy; counting all three scores one message as three.
- A queued message the harness later delivers as a plain `user` row is a fourth copy: a plain row
  identical to the preceding `[mid-turn]` row is dropped.
- A row whose `uuid` was already seen is a copy. When the session moves to another worktree (a
  `relocated` row), the desktop app appends the whole conversation again, with the same uuids and
  timestamps; a compaction re-writes a few attachment rows the same way. Counting the copies would
  list every earlier turn two or three times.
- Bare slash commands (`/compact`, `/wrap-up`) are not turns.
- A typed turn with no assistant row before the next genuine turn was cancelled (Esc before the model
  answered): it stays in the file but never reached the assistant. Tagged `[cancelled]` — intent
  history, not a correction the assistant missed; the turn that follows usually carries the redirect.
  A `!` command (`<bash-input>`) is a turn but never `[cancelled]`: the model never answers one.
- A compaction summary row ("This session is being continued …") is a wrapper, but its
  "All user messages:" list is the ONLY surviving record of the pre-compaction turns — it is
  printed separately and not counted.

Not covered: tool-layer rejections (a declined Bash command, a denied permission prompt, a rejected
AskUserQuestion) are friction evidence too and count toward the thresholds — add them by hand from
the transcript.

--after slices a multi-session-day file to the current arc: `HH:MM` is wall-clock in --tz (default:
this machine's local timezone), taken on the day of the file's last row, or the previous day when
that time is later than the last row. An ISO timestamp is accepted too (with Z/offset, or naive =
--tz). Prefer the ISO form: a bare HH:MM read off a clock in another zone slices the wrong span
without any error.
"""

import argparse
import datetime as dt
import json
import re
import sys
from zoneinfo import ZoneInfo

# Machine rows that render as `type: "user"`. Substring match against the row text.
SKIP = (
    "<system-reminder>",
    "SYSTEM NOTIFICATION",
    "<task-notification>",
    "<command-name>",
    "<command-message>",
    "local-command",
    "This session is being continued from a previous conversation",   # compaction summary (see below)
    "Base directory for this skill",
    "(Re-invocation of ",                                             # compaction re-injects truncated skill bodies
    "[Image: original ",
    "[Image: source: ",
    "was loaded earlier (see the invoked-skills reminder",            # Skill re-invocation wrapper
    "[Request interrupted by user]",                                  # interrupt marker, not typed text
    "browser automation\n\nYou have access to",                       # MCP server instructions injected as a user row
    "Another Claude session sent a message:",                         # subagent/teammate idle notification
    "<teammate-message",                                              # same shape, tag-first variant
    "<agent-message from=",                                           # subagent hand-back injected as a user row
    "<bash-stdout>",                                                  # output of a `!` command; the `<bash-input>` row before it is the typed action
    "<side-sessions-event>",                                          # desktop app: side sessions finished, written after a <system-reminder>
)

COMPACTION_MARKER = "This session is being continued from a previous conversation"
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
# The desktop app writes harness text into the row that carries what the user typed: hook context and
# session notices as a `<system-reminder>` text block ahead of the typed block, and a `!` command's
# output right after its `<bash-input>`. Those parts are cut out, so the SKIP test sees the typed part
# instead of dropping the whole row.
BASH_OUTPUT_RE = re.compile(r"<(bash-stdout|bash-stderr)>.*?</\1>", re.S)


def is_reminder_block(s):
    s = s.strip()
    return s.startswith("<system-reminder>") and s.endswith("</system-reminder>")


def row_text(d):
    """Return (text, tag) for a user or queue-operation row, or (None, None) for anything else."""
    t = d.get("type")
    if t == "queue-operation":
        if d.get("operation") != "enqueue":
            return None, None
        return (d.get("content") or "").strip(), "  [mid-turn]"
    if t == "user":
        c = (d.get("message") or {}).get("content")
        if isinstance(c, str):
            txt = c
        else:
            txt = " ".join(
                b.get("text", "") for b in c or []
                if isinstance(b, dict) and b.get("type") == "text" and not is_reminder_block(b.get("text", ""))
            )
        return BASH_OUTPUT_RE.sub("", txt).strip(), ""
    return None, None


def idle_enqueues(raw):
    """Indices of the `enqueue` rows that a `dequeue` closed before any user or assistant row:
    messages typed while the agent was idle (see the docstring)."""
    idle = set()
    for i, d in enumerate(raw):
        if d.get("type") != "queue-operation" or d.get("operation") != "enqueue":
            continue
        for e in raw[i + 1:]:
            if e.get("type") in ("user", "assistant"):   # the turn moved before the queue let go
                break
            if e.get("type") == "queue-operation" and e.get("operation") in ("dequeue", "remove"):
                if e.get("operation") == "dequeue":
                    idle.add(i)
                break
    return idle


def parse_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_after(arg, tz, last_ts):
    """Turn --after into an aware datetime. HH:MM = wall-clock in tz on the last row's day.
    tz None means this machine's local timezone."""
    if TIME_RE.match(arg):
        if last_ts is None:
            sys.exit("--after HH:MM needs at least one timestamped row to anchor the day")
        hh, mm = (int(x) for x in arg.split(":"))
        local_last = last_ts.astimezone(tz)
        cand = local_last.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > local_last:
            cand -= dt.timedelta(days=1)
        return cand
    try:
        cand = dt.datetime.fromisoformat(arg.replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"--after: expected HH:MM or an ISO timestamp, got {arg!r}")
    if cand.tzinfo is None:
        cand = cand.replace(tzinfo=tz) if tz is not None else cand.astimezone()
    return cand


def compaction_turns(txt):
    """Extract the bullet list under 'All user messages:' from a compaction summary."""
    i = txt.find("All user messages")
    if i < 0:
        return []
    out = []
    for line in txt[i:].splitlines()[1:]:
        s = line.strip()
        if s.startswith("- "):
            out.append(s[2:].strip().strip('"'))
        elif s and out:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("jsonl", help="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<project-slug>/<session-uuid>.jsonl")
    ap.add_argument("--after", help="HH:MM (wall-clock in --tz) or ISO timestamp; keep rows at/after it")
    ap.add_argument("--tz", default=None, help="IANA zone for HH:MM and naive timestamps (default: local)")
    ap.add_argument("--width", type=int, default=110, help="chars of each turn to print")
    args = ap.parse_args()

    tz = ZoneInfo(args.tz) if args.tz else None
    raw = []
    seen = set()
    with open(args.jsonl) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            uid = d.get("uuid")
            if uid in seen:                               # a re-written copy (see the docstring)
                continue
            if uid:
                seen.add(uid)
            raw.append(d)
    idle = idle_enqueues(raw)

    rows = []
    last_ts = None
    for i, d in enumerate(raw):
        ts = parse_ts(d.get("timestamp"))
        if ts is not None:
            last_ts = ts
        if d.get("type") == "assistant":          # boundary marker for the cancelled-turn check
            rows.append((ts, None, "assistant"))
            continue
        if i in idle:                             # its dequeue delivers it as the `user` row that follows
            continue
        txt, tag = row_text(d)
        if txt is None:
            continue
        if d.get("isMeta") and COMPACTION_MARKER not in txt:   # harness-injected row: a built-in skill's body has no "Base directory" line to match
            continue
        rows.append((ts, txt, tag))

    after = resolve_after(args.after, tz, last_ts) if args.after else None

    # pass 1 — the genuine turns (wrapper / slash / --after / duplicate filters)
    genuine = []      # indices into rows
    pending_mid = []  # [mid-turn] texts whose queue-delivery copy may still arrive as the next plain user row
    pre_compaction = []
    for i, (ts, txt, tag) in enumerate(rows):
        if tag == "assistant" or not txt:
            continue
        if COMPACTION_MARKER in txt:
            pre_compaction = compaction_turns(txt) or pre_compaction
            continue
        if any(m in txt for m in SKIP):
            continue
        if txt.startswith("/") and len(txt.split()) == 1:   # bare slash command
            continue
        if after is not None and ts is not None and ts < after:
            continue
        if not tag:
            if txt in pending_mid:     # the queued message delivered again as a plain user row
                pending_mid.remove(txt)
                continue
            pending_mid.clear()        # another typed turn came first: a later repeat is a new message
        else:
            pending_mid.append(txt)
        genuine.append(i)

    # pass 2 — a plain typed turn with no assistant row before the NEXT PLAIN typed turn was cancelled
    # (Esc before the model answered). [mid-turn] rows are neither candidates nor boundaries: one can be
    # enqueued before the running turn's first assistant row, and would otherwise mark the turn that
    # started it as cancelled. A `!` command is neither: the model never answers one, so it would
    # always read as cancelled.
    plain = [i for i in genuine if not rows[i][2] and not rows[i][1].startswith("<bash-input>")]
    cancelled = set()
    for k, i in enumerate(plain[:-1]):
        nxt = plain[k + 1]
        if not any(rows[x][2] == "assistant" for x in range(i + 1, nxt)):
            cancelled.add(i)

    n = mid = canc = 0
    for i in genuine:
        ts, txt, tag = rows[i]
        if tag:
            mid += 1
        if i in cancelled:
            tag = "  [cancelled]"
            canc += 1
        n += 1
        flat = " ".join(txt.split())
        nots = "  [no-ts]" if (after is not None and ts is None) else ""
        print(f"{n:3d}. {flat[:args.width]}{tag}{nots}")

    if pre_compaction:
        print(f"\n-- pre-compaction turns from the compaction summary ({len(pre_compaction)}; not counted above; "
              f"scan them too — they exist nowhere else):")
        for i, t in enumerate(pre_compaction, 1):
            print(f"  c{i}. {t[:args.width]}")

    slice_note = f" after {after.astimezone(tz).strftime('%Y-%m-%d %H:%M %Z')}" if after else ""
    print(f"-- {n} genuine turn(s), {mid} mid-turn, {canc} cancelled{slice_note}", file=sys.stderr)


if __name__ == "__main__":
    main()
