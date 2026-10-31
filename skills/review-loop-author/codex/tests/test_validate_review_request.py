"""Realistic validation formats; repository, agent, and path names are synthetic."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_review_request.py"
SPEC = importlib.util.spec_from_file_location("validate_review_request", SCRIPT)
assert SPEC and SPEC.loader
validate_review_request = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_review_request)


BASE_BODY = {
    "side_effects": ["writes_findings_packet", "sends_oacp_reply"],
}


class ValidateReviewRequestTests(unittest.TestCase):
    def test_non_gated_request_accepts_explicit_baseline(self) -> None:
        result = validate_review_request.validate_effects(
            BASE_BODY,
            approval_required=False,
            reviewer_eligible=False,
            approval_withheld_reason=None,
        )
        self.assertEqual(result["status"], "ok")

    def test_approval_gate_defaults_to_formal_review_for_eligible_reviewer(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            validate_review_request.ReviewRequestError,
            "must include submits_github_review",
        ):
            validate_review_request.validate_effects(
                BASE_BODY,
                approval_required=True,
                reviewer_eligible=True,
                approval_withheld_reason=None,
            )

    def test_eligible_reviewer_accepts_formal_review_effect(self) -> None:
        body = {
            "side_effects": [
                "writes_findings_packet",
                "sends_oacp_reply",
                "submits_github_review",
            ]
        }
        result = validate_review_request.validate_effects(
            body,
            approval_required=True,
            reviewer_eligible=True,
            approval_withheld_reason=None,
        )
        self.assertEqual(result["status"], "ok")

    def test_ineligible_reviewer_requires_withheld_reason(self) -> None:
        with self.assertRaisesRegex(
            validate_review_request.ReviewRequestError,
            "requires --approval-withheld-reason",
        ):
            validate_review_request.validate_effects(
                BASE_BODY,
                approval_required=True,
                reviewer_eligible=False,
                approval_withheld_reason=None,
            )

    def test_ineligible_reviewer_accepts_recorded_withholding(self) -> None:
        result = validate_review_request.validate_effects(
            BASE_BODY,
            approval_required=True,
            reviewer_eligible=False,
            approval_withheld_reason="reviewer authored the pull request",
        )
        self.assertEqual(
            result["approval_withheld_reason"],
            "reviewer authored the pull request",
        )

    def test_unknown_and_duplicate_effects_are_rejected(self) -> None:
        for extra, expected in (("submit_github_review", "unknown review effect"),
                                ("sends_oacp_reply", "duplicates")):
            with self.subTest(extra=extra), self.assertRaisesRegex(
                validate_review_request.ReviewRequestError, expected
            ):
                validate_review_request.validate_effects(
                    {"side_effects": [*BASE_BODY["side_effects"], extra]},
                    approval_required=False, reviewer_eligible=False,
                    approval_withheld_reason=None,
                )

    def test_inconsistent_approval_facts_are_rejected(self) -> None:
        for required, eligible, reason, expected in (
            (False, True, None, "meaningful only"),
            (False, False, "unavailable", "meaningful only"),
            (True, True, "unavailable", "cannot also"),
        ):
            with self.subTest(required=required, eligible=eligible, reason=reason), (
                self.assertRaisesRegex(validate_review_request.ReviewRequestError, expected)
            ):
                validate_review_request.validate_effects(
                    BASE_BODY, approval_required=required, reviewer_eligible=eligible,
                    approval_withheld_reason=reason,
                )

    def test_cli_reads_yaml_and_rejects_invalid_input(self) -> None:
        cases = (
            ("side_effects: [writes_findings_packet, sends_oacp_reply]", 0),
            ("side_effects: [writes_findings_packet, sends_oacp_reply, typo]", 2),
            ("[not-a-mapping]", 2),
            ("side_effects: [unterminated", 2),
        )
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.yaml"
            for text, expected in cases:
                with self.subTest(text=text):
                    body.write_text(text)
                    result = subprocess.run([sys.executable, str(SCRIPT), "--body-file", str(body)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)["status"],
                                     "ok" if expected == 0 else "error")
            body.unlink()
            result = subprocess.run([sys.executable, str(SCRIPT), "--body-file", str(body)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot read body file", json.loads(result.stdout)["error"])

    def test_baseline_effects_must_be_explicit(self) -> None:
        with self.assertRaisesRegex(
            validate_review_request.ReviewRequestError,
            "explicitly include baseline effects",
        ):
            validate_review_request.validate_effects(
                {"side_effects": ["submits_github_review"]},
                approval_required=True,
                reviewer_eligible=True,
                approval_withheld_reason=None,
            )


if __name__ == "__main__":
    unittest.main()
