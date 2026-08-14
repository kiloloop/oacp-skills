#!/usr/bin/env python3
"""Validate a reviewer verdict and render an OACP findings packet/body."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
SEVERITIES = {"P0", "P1", "P2", "P3"}
RESOLVED = {"fixed", "wont_fix"}
ESCALATIONS = {"reviewer_budget_exceeded", "max_rounds_exceeded"}


class VerdictError(ValueError):
    pass


def _required_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise VerdictError(f"{key} must be a non-empty string")
    return value.strip()


def normalize_verdict(data: dict[str, Any], *, findings_ref: str) -> dict[str, Any]:
    findings_path = PurePosixPath(findings_ref)
    if (
        findings_path.is_absolute()
        or ".." in findings_path.parts
        or findings_path.suffix != ".yaml"
    ):
        raise VerdictError(
            "findings_ref must be a relative .yaml path without traversal"
        )
    packet_id = _required_string(data, "packet_id")
    reviewer = _required_string(data, "reviewer")
    created_at = _required_string(data, "created_at_utc")
    summary_text = _required_string(data, "summary")
    reviewed_head = _required_string(data, "reviewed_head").lower()
    if not FULL_SHA.fullmatch(reviewed_head):
        raise VerdictError("reviewed_head must be a full 40-character SHA")
    try:
        round_number = int(data.get("round"))
    except (TypeError, ValueError) as exc:
        raise VerdictError("round must be a positive integer") from exc
    if round_number < 1:
        raise VerdictError("round must be a positive integer")

    raw_findings = data.get("findings", [])
    if not isinstance(raw_findings, list):
        raise VerdictError("findings must be a list")
    findings: list[dict[str, Any]] = []
    finding_ids: set[str] = set()
    unresolved_blocking: list[str] = []
    unresolved_nonblocking: list[str] = []
    unresolved_nonblocking_tiers: dict[str, str] = {}
    for raw in raw_findings:
        if not isinstance(raw, dict):
            raise VerdictError("each finding must be an object")
        finding = dict(raw)
        finding_id = _required_string(finding, "id")
        if finding_id in finding_ids:
            raise VerdictError(f"duplicate finding id: {finding_id}")
        finding_ids.add(finding_id)
        severity = _required_string(finding, "severity").upper()
        if severity not in SEVERITIES:
            raise VerdictError(f"invalid severity for {finding_id}: {severity}")
        if not isinstance(finding.get("blocking"), bool):
            raise VerdictError(f"blocking must be boolean for {finding_id}")
        blocking = finding["blocking"]
        if severity in {"P0", "P1"} and not blocking:
            raise VerdictError(f"{severity} finding {finding_id} must be blocking")
        if severity == "P3" and blocking:
            raise VerdictError(f"P3 finding {finding_id} cannot be blocking")
        status = _required_string(finding, "status").lower()
        finding.update({"severity": severity, "status": status})
        for key in ("area", "file", "repro", "expected", "evidence", "recommendation"):
            if not isinstance(finding.get(key, ""), str):
                raise VerdictError(f"{key} must be a string for {finding_id}")
        if status not in RESOLVED:
            if severity == "P0" or blocking:
                unresolved_blocking.append(finding_id)
            elif severity in {"P2", "P3"}:
                unresolved_nonblocking.append(finding_id)
                unresolved_nonblocking_tiers[finding_id] = severity
        findings.append(finding)

    qa_validation = data.get("qa_validation") or {}
    if not isinstance(qa_validation, dict):
        raise VerdictError("qa_validation must be an object")
    commands = qa_validation.get("commands_run", [])
    if not isinstance(commands, list):
        raise VerdictError("qa_validation.commands_run must be a list")
    normalized_commands: list[dict[str, Any]] = []
    for row in commands:
        if not isinstance(row, dict):
            raise VerdictError("each validation row must be an object")
        command = _required_string(row, "command")
        result = _required_string(row, "result").lower()
        if result not in {"pass", "fail", "warn"}:
            raise VerdictError(f"invalid validation result for {command}: {result}")
        normalized_commands.append({**row, "command": command, "result": result})
    all_validation_pass = bool(normalized_commands) and all(
        row["result"] == "pass" for row in normalized_commands
    )

    raw_nits = data.get("nits", [])
    if not isinstance(raw_nits, list):
        raise VerdictError("nits must be a list")
    nits: list[dict[str, Any]] = []
    nit_ids: set[str] = set()
    nit_sources: set[str] = set()
    for raw in raw_nits:
        if not isinstance(raw, dict):
            raise VerdictError("each nit must be an object")
        nit = dict(raw)
        nit_id = _required_string(nit, "nit_id")
        if nit_id in nit_ids:
            raise VerdictError(f"duplicate nit id: {nit_id}")
        nit_ids.add(nit_id)
        tier = _required_string(nit, "tier").upper()
        if tier not in {"P2", "P3"}:
            raise VerdictError(f"nit {nit_id} tier must be P2 or P3")
        for key in ("summary", "owner", "next_action"):
            _required_string(nit, key)
        source = nit.get("source")
        if source is not None:
            if not isinstance(source, str) or not source.strip():
                raise VerdictError(f"nit {nit_id} source must be a non-empty string")
            source = source.strip()
            expected_tier = unresolved_nonblocking_tiers.get(source)
            if expected_tier and tier != expected_tier:
                raise VerdictError(
                    f"nit {nit_id} tier {tier} does not match {source} severity {expected_tier}"
                )
            nit_sources.add(source)
        nit["tier"] = tier
        nits.append(nit)

    missing_nits = sorted(set(unresolved_nonblocking) - nit_sources)
    escalation = data.get("escalation")
    if escalation in (None, ""):
        escalation = None
    elif escalation not in ESCALATIONS:
        raise VerdictError(f"unsupported escalation: {escalation}")

    gate_passed = (
        not unresolved_blocking
        and all_validation_pass
        and not missing_nits
        and escalation is None
    )
    verdict = "pass" if gate_passed else "fail"
    packet = {
        "packet_id": packet_id,
        "source_review_packet": str(data.get("source_review_packet") or ""),
        "reviewer": reviewer,
        "round": round_number,
        "created_at_utc": created_at,
        "reviewed_head": reviewed_head,
        "summary": {
            "verdict": verdict,
            "blocking_count": len(unresolved_blocking),
            "non_blocking_count": len(unresolved_nonblocking),
            "text": summary_text,
        },
        "findings": findings,
        "qa_validation": {
            "commands_run": normalized_commands,
            "deployment_check": qa_validation.get(
                "deployment_check",
                {"ready": gate_passed, "rollback_verified": False, "notes": ""},
            ),
        },
    }
    message_type = "review_lgtm" if gate_passed else "review_feedback"
    if gate_passed:
        body: dict[str, Any] = {
            "quality_gate_result": "pass",
            "merge_ready": True,
            "review_round": round_number,
            "validated_head": reviewed_head,
            "nits": nits,
        }
    else:
        body = {
            "findings_packet": findings_ref,
            "round": round_number,
            "blocking_count": len(unresolved_blocking),
            "validated_head": reviewed_head,
        }
        if escalation:
            body["escalation"] = escalation
    telemetry = data.get("telemetry")
    if telemetry:
        if not isinstance(telemetry, dict):
            raise VerdictError("telemetry must be an object")
        body["telemetry"] = telemetry

    return {
        "message_type": message_type,
        "gate_passed": gate_passed,
        "unresolved_blocking": unresolved_blocking,
        "unresolved_nonblocking": unresolved_nonblocking,
        "missing_nits": missing_nits,
        "all_validation_pass": all_validation_pass,
        "packet": packet,
        "body": body,
    }


def write_new_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        yaml.safe_dump(value, handle, sort_keys=False, allow_unicode=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verdict", type=Path)
    parser.add_argument("--findings-ref", required=True)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        raw = json.loads(args.verdict.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise VerdictError("verdict JSON root must be an object")
        result = normalize_verdict(raw, findings_ref=args.findings_ref)
        if not args.dry_run:
            if args.packet.exists() or args.body.exists():
                raise VerdictError("refusing to overwrite packet or message body")
            write_new_yaml(args.packet, result["packet"])
            write_new_yaml(args.body, result["body"])
    except (OSError, json.JSONDecodeError, VerdictError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 2

    output = {
        key: value for key, value in result.items() if key not in {"packet", "body"}
    }
    output.update(
        {
            "status": "ready",
            "packet_path": None if args.dry_run else str(args.packet),
            "body_path": None if args.dry_run else str(args.body),
        }
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
