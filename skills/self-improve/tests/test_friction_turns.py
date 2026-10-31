"""Fixtures for friction_turns.py, one per transcript shape the script handles.

Each case writes a small session jsonl and runs the script's real entry point, so a
change to its reading, filtering or tagging shows up here. The row shapes are real
Claude Code transcript shapes (CLI and desktop app); the message texts are synthetic.

    python3 -m unittest discover -s skills/self-improve/tests   (pytest runs it too)
"""

import datetime as dt
import itertools
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "friction_turns.py"
T0 = dt.datetime(2026, 1, 15, 22, 0, tzinfo=dt.timezone.utc)
_tick = itertools.count()


def _stamp(row, uuid=True):
    k = next(_tick)
    row["timestamp"] = (T0 + dt.timedelta(seconds=k)).isoformat().replace("+00:00", "Z")
    if uuid:
        row.setdefault("uuid", f"u{k}")
    return row


def user(content):
    """A user row: a string, or a list of text blocks (see blocks())."""
    return _stamp({"type": "user", "message": {"role": "user", "content": content}})


def blocks(*texts):
    return [{"type": "text", "text": t} for t in texts]


def tool_result():
    return _stamp({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_x", "content": "ok"}]}})


def assistant():
    return _stamp({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "working"}]}})


def queue(op, content=None, **kw):
    row = {"type": "queue-operation", "operation": op, **kw}
    if content is not None:
        row["content"] = content
    return _stamp(row, uuid=False)


def absorbed(text):
    """How the desktop app folds a message into the running turn: attachment, then remove."""
    return [
        _stamp({"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}}),
        queue("remove", reason="absorbed_mid_turn"),
    ]


def typed_idle(text):
    """How the desktop app delivers a message typed while the agent is idle."""
    return [queue("enqueue", text), queue("dequeue"), user(text)]


class FrictionTurns(unittest.TestCase):

    def scan(self, rows, *extra):
        """Run the script on rows; return (turn lines, the stderr count line)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            out = subprocess.run([sys.executable, str(SCRIPT), str(path), *extra],
                                 capture_output=True, text=True, check=True)
        turns = [m.group(1) for m in map(re.compile(r"^\s*\d+\. (.*)$").match, out.stdout.splitlines()) if m]
        return turns, out.stderr.strip()

    # --- the input queue ---------------------------------------------------------------

    def test_message_typed_while_idle_is_a_plain_turn(self):
        turns, count = self.scan([*typed_idle("hello"), assistant()])
        self.assertEqual(turns, ["hello"])
        self.assertEqual(count, "-- 1 genuine turn(s), 0 mid-turn, 0 cancelled")

    def test_absorbed_message_is_mid_turn(self):
        rows = [*typed_idle("do X"), assistant(),
                queue("enqueue", "stop, do Y"), tool_result(), *absorbed("stop, do Y"), assistant()]
        turns, count = self.scan(rows)
        self.assertEqual(turns, ["do X", "stop, do Y  [mid-turn]"])
        self.assertEqual(count, "-- 2 genuine turn(s), 1 mid-turn, 0 cancelled")

    def test_message_that_waited_for_the_turn_is_mid_turn_once(self):
        # CLI shape: dequeued after the running turn's rows, then delivered as a plain user row.
        rows = [user("do X"), assistant(),
                queue("enqueue", "also Z"), assistant(), queue("dequeue"), user("also Z"), assistant()]
        turns, _ = self.scan(rows)
        self.assertEqual(turns, ["do X", "also Z  [mid-turn]"])

    def test_message_typed_during_a_tool_call_is_mid_turn(self):
        # Only a tool result lies between the enqueue and the dequeue: a turn was still running.
        rows = [user("run it"), assistant(),
                queue("enqueue", "no wait"), tool_result(), queue("dequeue"), user("no wait"), assistant()]
        turns, _ = self.scan(rows)
        self.assertEqual(turns, ["run it", "no wait  [mid-turn]"])

    def test_requeued_message_counts_once(self):
        # Desktop app: dequeued at once, put back, then absorbed by the running turn.
        rows = [*typed_idle("A"), assistant(),
                queue("enqueue", "B"), queue("dequeue"), queue("enqueue", "B"), tool_result(),
                *absorbed("B"), assistant()]
        turns, _ = self.scan(rows)
        self.assertEqual(turns, ["A", "B  [mid-turn]"])

    def test_message_still_queued_is_mid_turn(self):
        turns, _ = self.scan([*typed_idle("A"), assistant(), queue("enqueue", "B")])
        self.assertEqual(turns, ["A", "B  [mid-turn]"])

    def test_same_text_typed_again_after_another_turn_counts_twice(self):
        # The delivery copy is the next plain row only: once another typed turn has come
        # in between, the same correction typed again is a second correction.
        rows = [*typed_idle("task A"), assistant(),
                queue("enqueue", "stop, ask first"), tool_result(), *absorbed("stop, ask first"), assistant(),
                *typed_idle("task B"), assistant(),
                *typed_idle("stop, ask first"), assistant()]
        turns, count = self.scan(rows)
        self.assertEqual(turns, ["task A", "stop, ask first  [mid-turn]", "task B", "stop, ask first"])
        self.assertEqual(count, "-- 4 genuine turn(s), 1 mid-turn, 0 cancelled")

    # --- rows the desktop app writes again ---------------------------------------------

    def test_copies_after_a_relocation_count_once(self):
        first = [*typed_idle("A"), assistant(), *typed_idle("B"), assistant()]
        copies = [dict(r) for r in first if r.get("uuid")]           # same uuids and timestamps
        rows = [*first, {"type": "relocated", "relocatedCwd": "/tmp/wt"}, *copies,
                *typed_idle("C"), assistant()]
        turns, count = self.scan(rows)
        self.assertEqual(turns, ["A", "B", "C"])
        self.assertEqual(count, "-- 3 genuine turn(s), 0 mid-turn, 0 cancelled")

    # --- harness text in the typed row -------------------------------------------------

    def test_reminder_block_does_not_hide_the_typed_text(self):
        reminder = "<system-reminder>\nYou are operating in a git worktree.\n</system-reminder>\n\n"
        turns, _ = self.scan([user(blocks(reminder, "let's continue the migration")), assistant()])
        self.assertEqual(turns, ["let's continue the migration"])

    def test_reminder_rows_without_typed_text_are_dropped(self):
        event = "<side-sessions-event>None of the sessions you started is working now.</side-sessions-event>"
        rows = [user("<system-reminder>\nThe session finished.\n</system-reminder>\n" + event),
                user(blocks("<system-reminder>\nThe session finished.\n</system-reminder>", event)),
                user(blocks("<system-reminder>\nhook context\n</system-reminder>")),
                assistant()]
        turns, count = self.scan(rows)
        self.assertEqual(turns, [])
        self.assertEqual(count, "-- 0 genuine turn(s), 0 mid-turn, 0 cancelled")

    def test_bang_command_counts_and_is_never_cancelled(self):
        app = "<bash-input>ls</bash-input><bash-stdout>a\nb</bash-stdout><bash-stderr></bash-stderr>"
        cli = [user("<bash-input>pwd</bash-input>"), user("<bash-stdout>/x</bash-stdout><bash-stderr></bash-stderr>")]
        turns, count = self.scan([user(app), *cli, user("next"), assistant()])
        self.assertEqual(turns, ["<bash-input>ls</bash-input>", "<bash-input>pwd</bash-input>", "next"])
        self.assertEqual(count, "-- 3 genuine turn(s), 0 mid-turn, 0 cancelled")

    # --- cancellation still works on desktop-app rows -----------------------------------

    def test_cancelled_turn_with_a_message_queued_ahead_of_the_reply(self):
        # A turn cancelled with Esc, its replacement sent, and a follow-up queued before the
        # model's first row: only the first is cancelled.
        rows = [*typed_idle("maybe send it to alpha"), user("[Request interrupted by user]"),
                *typed_idle("actually, send it to beta"),
                queue("enqueue", "staging"), assistant(), tool_result(), *absorbed("staging"), assistant()]
        turns, count = self.scan(rows)
        self.assertEqual(turns, ["maybe send it to alpha  [cancelled]", "actually, send it to beta",
                                 "staging  [mid-turn]"])
        self.assertEqual(count, "-- 3 genuine turn(s), 1 mid-turn, 1 cancelled")

    # --- slicing to the current arc ------------------------------------------------------

    def test_after_slices_by_iso_timestamp_and_by_wall_clock(self):
        def at(row, minute):
            row["timestamp"] = (T0 + dt.timedelta(minutes=minute)).isoformat().replace("+00:00", "Z")
            return row
        rows = [at(user("earlier arc"), 0), at(assistant(), 1),
                at(user("this arc"), 30), at(assistant(), 31)]
        cut = T0 + dt.timedelta(minutes=20)
        turns, count = self.scan(rows, "--after", cut.isoformat().replace("+00:00", "Z"))
        self.assertEqual(turns, ["this arc"])
        self.assertTrue(count.startswith("-- 1 genuine turn(s), 0 mid-turn, 0 cancelled after "))
        turns, _ = self.scan(rows, "--after", cut.strftime("%H:%M"), "--tz", "UTC")
        self.assertEqual(turns, ["this arc"])


if __name__ == "__main__":
    unittest.main()
