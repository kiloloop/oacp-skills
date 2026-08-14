from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_verdict.py"
SPEC = importlib.util.spec_from_file_location("validate_verdict", SCRIPT)
assert SPEC and SPEC.loader
validate_verdict = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_verdict)


HEAD = "0123456789abcdef0123456789abcdef01234567"


def base_verdict():
    return {
        "packet_id": "20260101_example_codex_r1",
        "source_review_packet": "",
        "reviewer": "codex",
        "round": 1,
        "created_at_utc": "2026-01-01T00:00:00Z",
        "reviewed_head": HEAD,
        "summary": "Review completed.",
        "findings": [],
        "qa_validation": {
            "commands_run": [
                {"command": "make preflight", "result": "pass", "notes": ""}
            ]
        },
        "nits": [],
        "escalation": None,
    }


def finding(finding_id="F-001", severity="P1", blocking=True):
    return {
        "id": finding_id,
        "severity": severity,
        "blocking": blocking,
        "status": "open",
        "area": "code",
        "file": "src/app.py",
        "line": 10,
        "repro": "Run test.",
        "expected": "Test passes.",
        "evidence": "Test fails.",
        "recommendation": "Fix the branch.",
    }


class ValidateVerdictTests(unittest.TestCase):
    def test_clean_verdict_passes(self) -> None:
        result = validate_verdict.normalize_verdict(
            base_verdict(), findings_ref="packets/findings/result.yaml"
        )
        self.assertTrue(result["gate_passed"])
        self.assertEqual(result["message_type"], "review_lgtm")
        self.assertEqual(result["body"]["validated_head"], HEAD)

    def test_nonblocking_finding_requires_structured_nit(self) -> None:
        data = base_verdict()
        data["findings"] = [finding(severity="P3", blocking=False)]
        result = validate_verdict.normalize_verdict(
            data, findings_ref="packets/findings/result.yaml"
        )
        self.assertFalse(result["gate_passed"])
        self.assertEqual(result["missing_nits"], ["F-001"])

        data["nits"] = [
            {
                "nit_id": "NIT-001",
                "tier": "P3",
                "summary": "Follow up.",
                "owner": "author",
                "next_action": "Open an issue.",
                "source": "F-001",
            }
        ]
        result = validate_verdict.normalize_verdict(
            data, findings_ref="packets/findings/result.yaml"
        )
        self.assertTrue(result["gate_passed"])

    def test_p1_cannot_be_marked_nonblocking(self) -> None:
        data = base_verdict()
        data["findings"] = [finding(severity="P1", blocking=False)]
        with self.assertRaisesRegex(validate_verdict.VerdictError, "must be blocking"):
            validate_verdict.normalize_verdict(
                data, findings_ref="packets/findings/result.yaml"
            )

    def test_nit_tier_must_match_deferred_finding(self) -> None:
        data = base_verdict()
        data["findings"] = [finding(severity="P3", blocking=False)]
        data["nits"] = [
            {
                "nit_id": "NIT-001",
                "tier": "P2",
                "summary": "Follow up.",
                "owner": "author",
                "next_action": "Open an issue.",
                "source": "F-001",
            }
        ]
        with self.assertRaisesRegex(validate_verdict.VerdictError, "does not match"):
            validate_verdict.normalize_verdict(
                data, findings_ref="packets/findings/result.yaml"
            )

    def test_findings_ref_must_be_safe_and_relative(self) -> None:
        with self.assertRaisesRegex(validate_verdict.VerdictError, "relative"):
            validate_verdict.normalize_verdict(
                base_verdict(), findings_ref="../outside.yaml"
            )

    def test_failed_validation_forces_feedback(self) -> None:
        data = base_verdict()
        data["qa_validation"]["commands_run"][0]["result"] = "fail"
        result = validate_verdict.normalize_verdict(
            data, findings_ref="packets/findings/result.yaml"
        )
        self.assertFalse(result["gate_passed"])
        self.assertEqual(result["message_type"], "review_feedback")

    def test_budget_escalation_forces_feedback(self) -> None:
        data = base_verdict()
        data["escalation"] = "reviewer_budget_exceeded"
        result = validate_verdict.normalize_verdict(
            data, findings_ref="packets/findings/result.yaml"
        )
        self.assertEqual(result["body"]["escalation"], "reviewer_budget_exceeded")
        self.assertEqual(result["message_type"], "review_feedback")

    def test_renderer_creates_new_yaml_files(self) -> None:
        result = validate_verdict.normalize_verdict(
            base_verdict(), findings_ref="packets/findings/result.yaml"
        )
        with tempfile.TemporaryDirectory() as temp:
            packet = Path(temp) / "packet.yaml"
            body = Path(temp) / "body.yaml"
            validate_verdict.write_new_yaml(packet, result["packet"])
            validate_verdict.write_new_yaml(body, result["body"])
            self.assertEqual(yaml.safe_load(packet.read_text())["reviewed_head"], HEAD)
            self.assertEqual(yaml.safe_load(body.read_text())["merge_ready"], True)
            with self.assertRaises(FileExistsError):
                validate_verdict.write_new_yaml(packet, result["packet"])


if __name__ == "__main__":
    unittest.main()
