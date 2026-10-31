#!/usr/bin/env python3
"""Validate review-request effects before an author sends the body."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

BASELINE_EFFECTS = frozenset({"writes_findings_packet", "sends_oacp_reply"})
GITHUB_REVIEW_EFFECT = "submits_github_review"
KNOWN_EFFECTS = BASELINE_EFFECTS | {"comments_on_github", GITHUB_REVIEW_EFFECT}


class ReviewRequestError(ValueError):
    """The request body conflicts with the selected approval-gate facts."""


def load_body(path: Path) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReviewRequestError(f"cannot read body file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ReviewRequestError(f"body is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ReviewRequestError("body must be a YAML mapping")
    return parsed


def validate_effects(
    body: dict[str, Any],
    *,
    approval_required: bool,
    reviewer_eligible: bool,
    approval_withheld_reason: str | None,
) -> dict[str, Any]:
    effects_value = body.get("side_effects")
    if not isinstance(effects_value, list) or not all(
        isinstance(effect, str) and effect for effect in effects_value
    ):
        raise ReviewRequestError("side_effects must be an explicit list of names")
    if len(effects_value) != len(set(effects_value)):
        raise ReviewRequestError("side_effects must not contain duplicates")

    effects = set(effects_value)
    unknown = sorted(effects - KNOWN_EFFECTS)
    if unknown:
        raise ReviewRequestError("unknown review effect names: " + ", ".join(unknown))
    missing_baseline = sorted(BASELINE_EFFECTS - effects)
    if missing_baseline:
        raise ReviewRequestError(
            "side_effects must explicitly include baseline effects: "
            + ", ".join(missing_baseline)
        )

    withheld_reason = (approval_withheld_reason or "").strip()
    if reviewer_eligible and not approval_required:
        raise ReviewRequestError(
            "--reviewer-eligible is meaningful only with --approval-required"
        )
    if withheld_reason and not approval_required:
        raise ReviewRequestError(
            "--approval-withheld-reason is meaningful only with --approval-required"
        )
    if reviewer_eligible and withheld_reason:
        raise ReviewRequestError(
            "an eligible reviewer cannot also have an approval-withheld reason"
        )

    submits_review = GITHUB_REVIEW_EFFECT in effects
    if approval_required and reviewer_eligible and not submits_review:
        raise ReviewRequestError(
            "approval-gated request with an eligible reviewer must include "
            "submits_github_review"
        )
    if approval_required and not reviewer_eligible:
        if submits_review:
            raise ReviewRequestError(
                "request declares submits_github_review but the reviewer is not eligible"
            )
        if not withheld_reason:
            raise ReviewRequestError(
                "approval-gated request without an eligible reviewer requires "
                "--approval-withheld-reason"
            )

    return {
        "approval_required": approval_required,
        "approval_withheld_reason": withheld_reason or None,
        "reviewer_eligible": reviewer_eligible,
        "side_effects": effects_value,
        "status": "ok",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--approval-required", action="store_true")
    parser.add_argument("--reviewer-eligible", action="store_true")
    parser.add_argument("--approval-withheld-reason")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = validate_effects(
            load_body(args.body_file),
            approval_required=args.approval_required,
            reviewer_eligible=args.reviewer_eligible,
            approval_withheld_reason=args.approval_withheld_reason,
        )
    except ReviewRequestError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
