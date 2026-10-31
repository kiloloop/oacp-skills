#!/usr/bin/env python3
"""Validate a review findings packet (and its terminal body) before sending.

Checks the packet against the OACP findings contract
(templates/findings_packet.template.yaml + review_loop.md quality gate):
schema shape, severity tiering, summary counts, verdict consistency, and
recorded validation evidence. Only the closure statuses ``fixed`` and
``wont_fix`` resolve a finding; every other status counts as unresolved.

With ``--body``, also checks the terminal review_lgtm / review_feedback body
the author will parse with ``yaml.safe_load``: required review-loop fields,
``validated_head`` equal to the packet's ``reviewed_head``, structured nits,
and a nit naming every deferred (unresolved non-blocking) finding on a pass.

Exit codes: 0 = valid, 2 = contract violations (listed), 3 = file/parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

SEVERITIES = {"P0", "P1", "P2", "P3"}
RESOLVED = {"fixed", "wont_fix"}
VERDICTS = {"pass", "fail"}
QA_RESULTS = {"pass", "fail", "warn"}
ESCALATIONS = {"max_rounds_exceeded", "reviewer_budget_exceeded"}
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("PyYAML is required") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a YAML mapping")
    return data


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(packet: dict, body: dict | None = None) -> list[str]:
    problems: list[str] = []
    err = problems.append

    for key in ("packet_id", "reviewer", "round", "created_at_utc",
                "reviewed_head", "summary", "findings"):
        if key not in packet:
            err(f"missing required top-level key: {key}")
    if problems:
        return problems

    if not isinstance(packet["round"], int) or isinstance(packet["round"], bool) \
            or packet["round"] < 1:
        err("round must be an integer >= 1")
    if not ISO_Z.match(str(packet["created_at_utc"])):
        err("created_at_utc must be ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ)")
    head = packet["reviewed_head"]
    if not isinstance(head, str) or not FULL_SHA.match(head):
        err("reviewed_head must be the full 40-character lowercase SHA from git/gh output")

    summary = packet["summary"]
    if not isinstance(summary, dict):
        err("summary must be a mapping")
        return problems
    verdict = summary.get("verdict")
    if verdict not in VERDICTS:
        err(f"summary.verdict must be one of {sorted(VERDICTS)}")

    findings = packet["findings"]
    if not isinstance(findings, list):
        err("findings must be a list")
        return problems

    seen_ids: set = set()
    unresolved_blocking: list[str] = []
    deferred: dict[str, str] = {}  # unresolved non-blocking finding id -> severity
    for i, f in enumerate(findings):
        label = f"findings[{i}]"
        if not isinstance(f, dict):
            err(f"{label}: not a mapping")
            continue
        fid = f.get("id", "")
        if not re.match(r"^F-\d+$", str(fid)):
            err(f"{label}: id must match F-<digits>, got {fid!r}")
        if fid in seen_ids:
            err(f"{label}: duplicate id {fid}")
        seen_ids.add(fid)

        sev = f.get("severity")
        if sev not in SEVERITIES:
            err(f"{label}: severity must be one of {sorted(SEVERITIES)}")
        blocking = f.get("blocking")
        if not isinstance(blocking, bool):
            err(f"{label}: blocking must be a boolean")
        status = f.get("status")
        if not _text(status):
            err(f"{label}: status must be a non-empty string (template seeds 'open')")
        if not _text(f.get("recommendation")):
            err(f"{label}: recommendation is required (every finding needs a concrete fix)")

        # Protocol tiering: P0/P1 always blocking; P3 never blocking.
        if sev in {"P0", "P1"} and blocking is False:
            err(f"{label}: {sev} findings must be blocking")
        if sev == "P3" and blocking is True:
            err(f"{label}: P3 findings must be non-blocking (defer via LGTM nits)")

        if _text(status) and status.strip().lower() not in RESOLVED:
            if sev == "P0" or blocking is True:
                unresolved_blocking.append(str(fid))
            elif blocking is False and sev in {"P2", "P3"}:
                deferred[str(fid)] = sev

    if summary.get("blocking_count") != len(unresolved_blocking):
        err(f"summary.blocking_count={summary.get('blocking_count')} but "
            f"{len(unresolved_blocking)} unresolved blocking finding(s) present")
    if summary.get("non_blocking_count") != len(deferred):
        err(f"summary.non_blocking_count={summary.get('non_blocking_count')} but "
            f"{len(deferred)} unresolved non-blocking finding(s) present")

    qa = packet.get("qa_validation")
    commands = qa.get("commands_run") if isinstance(qa, dict) else None
    if not isinstance(commands, list) or not commands:
        err("qa_validation.commands_run must be a non-empty list (gate requires recorded validation)")
        commands = []
    failing = []
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict) or not _text(cmd.get("command")):
            err(f"qa_validation.commands_run[{i}]: command is required")
            continue
        result = cmd.get("result")
        if result not in QA_RESULTS:
            err(f"qa_validation.commands_run[{i}]: result must be one of {sorted(QA_RESULTS)}")
        elif result != "pass":
            failing.append(cmd["command"])

    if verdict == "pass":
        if unresolved_blocking:
            err("verdict=pass but unresolved P0/blocking finding(s) present: "
                + ", ".join(unresolved_blocking)
                + " (only fixed/wont_fix resolve a finding)")
        if failing:
            err("verdict=pass but validation commands not passing: "
                + ", ".join(str(c) for c in failing)
                + " (warn/fail/skipped evidence does not satisfy the gate)")
        if deferred and body is None:
            err("verdict=pass with deferred non-blocking finding(s) "
                + ", ".join(sorted(deferred))
                + ": pass --body so their structured nits can be checked")

    if body is not None:
        validate_body(body, packet, verdict, len(unresolved_blocking), deferred, err)
    return problems


def validate_body(body, packet, verdict, blocking_count, deferred, err) -> None:
    passing = verdict == "pass"
    if body.get("quality_gate_result") != ("pass" if passing else "fail"):
        err(f"body.quality_gate_result must be {'pass' if passing else 'fail'} "
            f"for verdict={verdict}")
    if body.get("merge_ready") is not passing:
        err(f"body.merge_ready must be boolean {str(passing).lower()} for verdict={verdict}")
    if body.get("validated_head") != packet.get("reviewed_head"):
        err("body.validated_head must equal the packet's reviewed_head (full SHA, verbatim)")
    for key in ("round", "review_round"):
        if key in body and body[key] != packet.get("round"):
            err(f"body.{key}={body[key]!r} but packet round is {packet.get('round')!r}")

    nits = body.get("nits")
    if not isinstance(nits, list):
        err("body.nits must be a list ([] when nothing is deferred)")
        nits = []
    nit_ids: set = set()
    sources: set = set()
    for i, nit in enumerate(nits):
        label = f"body.nits[{i}]"
        if not isinstance(nit, dict):
            err(f"{label}: not a mapping")
            continue
        for key in ("nit_id", "summary", "owner", "next_action"):
            if not _text(nit.get(key)):
                err(f"{label}: {key} is required")
        if nit.get("nit_id") in nit_ids:
            err(f"{label}: duplicate nit_id {nit.get('nit_id')}")
        nit_ids.add(nit.get("nit_id"))
        tier = nit.get("tier")
        if tier not in {"P2", "P3"}:
            err(f"{label}: tier must be P2 or P3")
        source = nit.get("source")
        if source is not None:
            if not _text(source):
                err(f"{label}: source must be a non-empty string when present")
                continue
            source = source.strip()
            if source in deferred and tier != deferred[source]:
                err(f"{label}: tier {tier} does not match {source} severity {deferred[source]}")
            sources.add(source)
    if passing:
        missing = sorted(set(deferred) - sources)
        if missing:
            err("deferred finding(s) without a nit naming them as source: " + ", ".join(missing))

    escalation = body.get("escalation")
    if escalation is not None:
        if passing:
            err("body.escalation is not allowed on a passing verdict")
        elif escalation not in ESCALATIONS:
            err(f"body.escalation must be one of {sorted(ESCALATIONS)}")
    withheld = body.get("withheld_side_effects")
    if withheld is not None and not (
            isinstance(withheld, list) and all(_text(w) for w in withheld)):
        err("body.withheld_side_effects must be a list of effect names")

    if not passing:
        ref = body.get("findings_packet")
        path = PurePosixPath(ref) if _text(ref) else None
        if path is None or path.is_absolute() or ".." in path.parts or path.suffix != ".yaml":
            err("body.findings_packet must be a workspace-relative .yaml path without traversal")
        if "round" not in body:
            err("body.round is required on review_feedback")
        if body.get("blocking_count") != blocking_count:
            err(f"body.blocking_count={body.get('blocking_count')!r} but packet has "
                f"{blocking_count} unresolved blocking finding(s)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("packet", type=Path)
    parser.add_argument("--body", type=Path, help="terminal message body file to check")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args(argv)

    try:
        packet = load_yaml(args.packet)
        body = load_yaml(args.body) if args.body else None
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # yaml parse errors
        print(f"error: unparseable YAML: {exc}", file=sys.stderr)
        return 3

    problems = validate(packet, body)
    if args.json:
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
    elif problems:
        print(f"INVALID: {len(problems)} contract violation(s)")
        for p in problems:
            print(f"  - {p}")
    else:
        print("OK: packet" + (" and body satisfy" if body is not None else " satisfies")
              + " the findings contract")
    return 2 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
