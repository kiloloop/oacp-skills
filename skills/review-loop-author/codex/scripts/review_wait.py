#!/usr/bin/env python3
"""Capability-aware, model-free wait helper for an OACP author loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Sequence


EXIT_ERROR = 2
EXIT_TIMEOUT = 4


def parse_json_lines(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("watch JSONL rows must be objects")
        events.append(value)
    return events


def watch_capabilities(help_text: str) -> dict[str, bool]:
    return {
        "state_id": "--state-id" in help_text,
        "since": "--since" in help_text,
    }


def build_watch_command(
    *,
    executable: str,
    project: str,
    agent: str,
    oacp_dir: Path,
    state_id: str,
    since: str,
    capabilities: dict[str, bool],
) -> list[str]:
    command = [
        executable,
        "watch",
        "--project",
        project,
        "--agent",
        agent,
        "--oacp-dir",
        str(oacp_dir),
        "--json",
    ]
    if capabilities.get("state_id"):
        command.extend(["--state-id", state_id])
    if capabilities.get("since"):
        command.extend(["--since", since])
    return command


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def scan_once(
    command: Sequence[str],
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    completed = runner(command)
    try:
        events = parse_json_lines(completed.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "status": "error",
            "events": [],
            "error": f"invalid watch JSON: {exc}",
            "returncode": completed.returncode,
        }
    if completed.returncode != 0:
        return {
            "status": "error",
            "events": events,
            "error": completed.stderr.strip() or "oacp watch failed",
            "returncode": completed.returncode,
        }
    return {
        "status": "new_message" if events else "no_change",
        "events": events,
        "error": None,
        "returncode": 0,
    }


def final_inbox_snapshot(
    *,
    executable: str,
    project: str,
    agent: str,
    oacp_dir: Path,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    command = [
        executable,
        "inbox",
        project,
        "--agent",
        agent,
        "--oacp-dir",
        str(oacp_dir),
        "--json",
    ]
    completed = runner(command)
    if completed.returncode != 0:
        return {
            "ok": False,
            "rows": None,
            "error": completed.stderr.strip() or "oacp inbox failed",
        }
    try:
        rows = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"ok": False, "rows": None, "error": f"invalid inbox JSON: {exc}"}
    return {"ok": True, "rows": rows, "error": None}


def _snapshot_has_rows(snapshot: dict[str, Any]) -> bool:
    rows = snapshot.get("rows")
    if isinstance(rows, list):
        return bool(rows)
    if isinstance(rows, dict):
        messages = rows.get("messages")
        return bool(messages) if isinstance(messages, (list, dict)) else bool(rows)
    return False


def direct_scan(
    *,
    executable: str,
    project: str,
    agent: str,
    oacp_dir: Path,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    snapshot = final_inbox_snapshot(
        executable=executable,
        project=project,
        agent=agent,
        oacp_dir=oacp_dir,
        runner=runner,
    )
    if not snapshot["ok"]:
        return {
            "status": "error",
            "events": [],
            "candidates": None,
            "error": snapshot["error"],
        }
    return {
        "status": "new_message" if _snapshot_has_rows(snapshot) else "no_change",
        "events": [],
        "candidates": snapshot["rows"],
        "error": None,
    }


def wait_for_change(
    scan: Callable[[], dict[str, Any]],
    final_scan: Callable[[], dict[str, Any]],
    *,
    timeout_seconds: float,
    interval_seconds: float,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    deadline = now() + timeout_seconds
    scans = 0
    while True:
        result = scan()
        scans += 1
        result["scans"] = scans
        if result["status"] == "new_message":
            return result, 0
        if result["status"] == "error":
            return result, EXIT_ERROR
        remaining = deadline - now()
        if remaining <= 0:
            snapshot = final_scan()
            return {
                "status": "timeout",
                "events": [],
                "scans": scans,
                "final_inbox": snapshot,
            }, EXIT_TIMEOUT
        sleep(min(interval_seconds, remaining))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prime", action="store_true")
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--wait", action="store_true")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--oacp-dir", required=True, type=Path)
    parser.add_argument("--state-id", required=True)
    parser.add_argument("--oacp", default="oacp")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--since", default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.timeout_seconds < 0 or args.interval_seconds <= 0:
        raise SystemExit("timeouts must be non-negative and interval must be positive")

    help_result = run_command([args.oacp, "watch", "--help"])
    if help_result.returncode != 0:
        print(json.dumps({"status": "error", "error": "oacp watch --help failed"}))
        return EXIT_ERROR
    capabilities = watch_capabilities(help_result.stdout + help_result.stderr)
    since = args.since or ("now" if args.prime else "epoch")
    oacp_dir = args.oacp_dir.expanduser()
    if capabilities["state_id"]:
        command = build_watch_command(
            executable=args.oacp,
            project=args.project,
            agent=args.agent,
            oacp_dir=oacp_dir,
            state_id=args.state_id,
            since=since,
            capabilities=capabilities,
        )

        def scan() -> dict[str, Any]:
            return scan_once(command)

        cursor_mode = "scoped"
    else:

        def scan() -> dict[str, Any]:
            return direct_scan(
                executable=args.oacp,
                project=args.project,
                agent=args.agent,
                oacp_dir=oacp_dir,
            )

        cursor_mode = "direct_inbox"

    if args.prime or args.once:
        result = scan()
        result.update({"cursor_mode": cursor_mode, "capabilities": capabilities})
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] != "error" else EXIT_ERROR

    result, exit_code = wait_for_change(
        scan,
        lambda: final_inbox_snapshot(
            executable=args.oacp,
            project=args.project,
            agent=args.agent,
            oacp_dir=oacp_dir,
        ),
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    result.update({"cursor_mode": cursor_mode, "capabilities": capabilities})
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
