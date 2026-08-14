from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "review_wait.py"
SPEC = importlib.util.spec_from_file_location("review_wait", SCRIPT)
assert SPEC and SPEC.loader
review_wait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_wait)


class ReviewWaitTests(unittest.TestCase):
    def test_capability_fallback_omits_unsupported_flags(self) -> None:
        command = review_wait.build_watch_command(
            executable="oacp",
            project="demo",
            agent="codex",
            oacp_dir=Path("/tmp/oacp"),
            state_id="review-1",
            since="epoch",
            capabilities={"state_id": False, "since": False},
        )
        self.assertNotIn("--state-id", command)
        self.assertNotIn("--since", command)
        self.assertEqual(command[:4], ["oacp", "watch", "--project", "demo"])

    def test_scoped_command_includes_state_and_since(self) -> None:
        command = review_wait.build_watch_command(
            executable="oacp",
            project="demo",
            agent="codex",
            oacp_dir=Path("/tmp/oacp"),
            state_id="review-1",
            since="now",
            capabilities={"state_id": True, "since": True},
        )
        self.assertEqual(command[-4:], ["--state-id", "review-1", "--since", "now"])

    def test_scan_parses_json_lines_without_message_bodies(self) -> None:
        event = {"event": "new_message", "file": "one.yaml", "type": "review_lgtm"}

        def runner(command):
            return subprocess.CompletedProcess(command, 0, json.dumps(event) + "\n", "")

        result = review_wait.scan_once(["oacp", "watch"], runner=runner)
        self.assertEqual(result["status"], "new_message")
        self.assertEqual(result["events"], [event])

    def test_direct_fallback_surfaces_inbox_candidates(self) -> None:
        rows = [{"file": "held.yaml", "held": True}]

        def runner(command):
            return subprocess.CompletedProcess(command, 0, json.dumps(rows), "")

        result = review_wait.direct_scan(
            executable="oacp",
            project="demo",
            agent="codex",
            oacp_dir=Path("/tmp/oacp"),
            runner=runner,
        )
        self.assertEqual(result["status"], "new_message")
        self.assertEqual(result["candidates"], rows)

    def test_wait_returns_on_second_scan(self) -> None:
        results = iter(
            [
                {"status": "no_change", "events": [], "error": None},
                {
                    "status": "new_message",
                    "events": [{"file": "two.yaml"}],
                    "error": None,
                },
            ]
        )
        clock = [0.0]

        def sleep(seconds: float) -> None:
            clock[0] += seconds

        result, exit_code = review_wait.wait_for_change(
            lambda: next(results),
            lambda: {"ok": True, "rows": []},
            timeout_seconds=10,
            interval_seconds=1,
            now=lambda: clock[0],
            sleep=sleep,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "new_message")
        self.assertEqual(result["scans"], 2)

    def test_timeout_always_runs_final_inbox_snapshot(self) -> None:
        calls = []
        result, exit_code = review_wait.wait_for_change(
            lambda: {"status": "no_change", "events": [], "error": None},
            lambda: (
                calls.append("final") or {"ok": True, "rows": [{"file": "late.yaml"}]}
            ),
            timeout_seconds=0,
            interval_seconds=1,
            now=lambda: 1.0,
            sleep=lambda seconds: None,
        )
        self.assertEqual(exit_code, review_wait.EXIT_TIMEOUT)
        self.assertEqual(calls, ["final"])
        self.assertEqual(result["final_inbox"]["rows"][0]["file"], "late.yaml")

    def test_watch_failure_stops_without_waiting(self) -> None:
        result, exit_code = review_wait.wait_for_change(
            lambda: {"status": "error", "events": [], "error": "boom"},
            lambda: {"ok": True, "rows": []},
            timeout_seconds=10,
            interval_seconds=1,
        )
        self.assertEqual(exit_code, review_wait.EXIT_ERROR)
        self.assertEqual(result["error"], "boom")


if __name__ == "__main__":
    unittest.main()
