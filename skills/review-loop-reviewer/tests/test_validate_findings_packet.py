"""Focused tests for validate_findings_packet.py.

Fixtures keep the real packet/body shape; file names, SHAs, and finding text
are synthetic.
"""

import importlib.util
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_findings_packet.py"
spec = importlib.util.spec_from_file_location("validate_findings_packet", SCRIPT)
vfp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vfp)

HEAD = "0123456789abcdef0123456789abcdef01234567"


def finding(fid="F-001", severity="P1", blocking=True, status="open"):
    return {
        "id": fid, "severity": severity, "blocking": blocking, "status": status,
        "area": "code", "file": "example.py", "line": 3, "repro": "run it",
        "expected": "no crash", "evidence": "trace", "recommendation": "guard the call",
    }


def base_packet():
    return {
        "packet_id": "20260101_demo_claude_r1",
        "source_review_packet": "",
        "reviewer": "claude",
        "round": 1,
        "created_at_utc": "2026-01-01T06:00:00Z",
        "reviewed_head": HEAD,
        "summary": {"verdict": "fail", "blocking_count": 1, "non_blocking_count": 1},
        "findings": [finding(), finding("F-002", "P3", False)],
        "qa_validation": {"commands_run": [{"command": "make test", "result": "pass", "notes": ""}]},
    }


def passing_packet():
    p = base_packet()
    p["summary"] = {"verdict": "pass", "blocking_count": 0, "non_blocking_count": 1}
    p["findings"] = [finding("F-001", "P1", True, "fixed"), finding("F-002", "P3", False, "open")]
    return p


def lgtm_body(**extra):
    body = {
        "quality_gate_result": "pass", "merge_ready": True, "validated_head": HEAD,
        "nits": [{"nit_id": "NIT-001", "tier": "P3", "summary": "reword", "owner": "author",
                  "next_action": "follow-up doc PR", "source": "F-002"}],
        "withheld_side_effects": [], "round": 1,
    }
    body.update(extra)
    return body


def feedback_body(**extra):
    body = {
        "quality_gate_result": "fail", "merge_ready": False, "validated_head": HEAD, "nits": [],
        "findings_packet": "packets/findings/20260101_demo_claude_r1.yaml",
        "round": 1, "blocking_count": 1, "withheld_side_effects": [],
    }
    body.update(extra)
    return body


def has(problems, text):
    return any(text in m for m in problems)


def test_valid_fail_packet_and_body():
    assert vfp.validate(base_packet()) == []
    assert vfp.validate(base_packet(), feedback_body()) == []


def test_valid_pass_packet_with_nit_body():
    assert vfp.validate(passing_packet(), lgtm_body()) == []


@pytest.mark.parametrize("status", [
    "fixed", "wont_fix", "open", "addressed", "resolved", "deferred", "withdrawn", "not_fixed",
])
@pytest.mark.parametrize("severity,blocking", [
    ("P0", True), ("P1", True), ("P2", True), ("P2", False), ("P3", False),
])
def test_only_fixed_and_wont_fix_resolve(status, severity, blocking):
    p = passing_packet()
    p["findings"] = [finding("F-001", severity, blocking, status)]
    resolved = status in {"fixed", "wont_fix"}
    p["summary"]["blocking_count"] = 0 if resolved or not blocking else 1
    p["summary"]["non_blocking_count"] = 0 if resolved or blocking else 1
    body = lgtm_body(nits=[])
    problems = vfp.validate(p, body)
    assert has(problems, "unresolved P0/blocking") == (not resolved and blocking)
    assert has(problems, "without a nit") == (not resolved and not blocking)
    assert (problems == []) == resolved


def test_pass_with_deferred_needs_body():
    assert has(vfp.validate(passing_packet()), "pass --body")


def test_count_mismatch_rejected():
    p = base_packet()
    p["summary"]["blocking_count"] = 5
    assert has(vfp.validate(p), "blocking_count=5")


def test_missing_qa_validation_rejected():
    p = base_packet()
    del p["qa_validation"]
    assert has(vfp.validate(p), "qa_validation.commands_run")


def test_pass_with_warn_validation_rejected():
    p = passing_packet()
    p["qa_validation"]["commands_run"][0]["result"] = "warn"
    assert has(vfp.validate(p, lgtm_body()), "not passing")


def test_fail_verdict_tolerates_failing_validation():
    p = base_packet()
    p["qa_validation"]["commands_run"][0]["result"] = "fail"
    assert vfp.validate(p) == []


def test_tiering_enforced():
    p = base_packet()
    p["findings"][0]["severity"] = "P0"
    p["findings"][0]["blocking"] = False
    p["findings"][1]["blocking"] = True
    problems = vfp.validate(p)
    assert has(problems, "P0 findings must be blocking")
    assert has(problems, "P3 findings must be non-blocking")


def test_duplicate_ids_and_missing_recommendation_rejected():
    p = base_packet()
    p["findings"][1]["id"] = "F-001"
    p["findings"][0]["recommendation"] = ""
    problems = vfp.validate(p)
    assert has(problems, "duplicate id")
    assert has(problems, "recommendation is required")


def test_bad_timestamp_and_short_head_rejected():
    p = base_packet()
    p["created_at_utc"] = "yesterday"
    p["reviewed_head"] = HEAD[:12]
    problems = vfp.validate(p)
    assert has(problems, "created_at_utc")
    assert has(problems, "reviewed_head")


def test_body_head_mismatch_rejected():
    body = lgtm_body(validated_head="f" * 40)
    assert has(vfp.validate(passing_packet(), body), "validated_head")


def test_body_wrong_gate_fields_rejected():
    body = lgtm_body(quality_gate_result="fail", merge_ready="true")
    problems = vfp.validate(passing_packet(), body)
    assert has(problems, "quality_gate_result")
    assert has(problems, "merge_ready")


def test_nit_tier_must_match_finding():
    body = lgtm_body()
    body["nits"][0]["tier"] = "P2"
    assert has(vfp.validate(passing_packet(), body), "does not match")


def test_feedback_body_checks():
    body = feedback_body(blocking_count=0, findings_packet="/abs/packet.yaml", escalation="bogus")
    problems = vfp.validate(base_packet(), body)
    assert has(problems, "body.blocking_count")
    assert has(problems, "findings_packet")
    assert has(problems, "escalation")


def test_escalation_not_allowed_on_pass():
    body = lgtm_body(escalation="max_rounds_exceeded")
    assert has(vfp.validate(passing_packet(), body), "not allowed on a passing")


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump(base_packet()), encoding="utf-8")
    assert vfp.main([str(good)]) == 0

    bad_packet = base_packet()
    bad_packet["summary"]["verdict"] = "pass"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(bad_packet), encoding="utf-8")
    assert vfp.main([str(bad)]) == 2

    assert vfp.main([str(tmp_path / "missing.yaml")]) == 3

    # A hand-typed plain scalar containing ": " is the classic broken body.
    broken = tmp_path / "body.yaml"
    broken.write_text("quality_gate_result: pass\nnits:\n  - summary: a: b\n", encoding="utf-8")
    assert vfp.main([str(good), "--body", str(broken)]) == 3

    body = tmp_path / "feedback.yaml"
    body.write_text(yaml.safe_dump(feedback_body()), encoding="utf-8")
    assert vfp.main([str(good), "--body", str(body)]) == 0
