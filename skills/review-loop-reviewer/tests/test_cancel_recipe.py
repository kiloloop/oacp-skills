"""The sender-pause cancellation recipe in SKILL.md, run against the real finalizer.

Pulls the `oacp autonomy finalize` commands out of the "Sender replaces or pauses
the round" bullet, fills the placeholders, and runs each documented branch on a
synthetic round record. The record keeps the OACP audit schema (version 2); its
ids and names are made up. Skipped unless oacp-cli 0.5.3+ is on PATH.
"""

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "SKILL.md"
RECORD_NAME = "20260801T010000Z_msg-20260801010000-author-0001.yaml"
PACKET = "packets/findings/20260801_pr1_reviewer_r1.yaml"


def _finalizer_available():
    if not shutil.which("oacp"):
        return False
    res = subprocess.run(["oacp", "autonomy", "finalize", "--help"], capture_output=True, text=True)
    return res.returncode == 0 and "--deliverable-landed" in res.stdout


pytestmark = pytest.mark.skipif(not _finalizer_available(), reason="needs oacp-cli 0.5.3+ on PATH")


def utc(minutes_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def recipe():
    """The bullet's inline code spans that start with `oacp autonomy finalize`, plus the deliverable flag."""
    text = SKILL.read_text()
    start = text.index("- **Sender replaces or pauses the round**")
    end = text.index("\n- ", start + 1)
    spans = re.findall(r"`([^`]+)`", " ".join(line.strip() for line in text[start:end].splitlines()))
    checkpoint = next(s for s in spans if s.startswith("oacp autonomy finalize <audit> --checkpoint"))
    cancel = next(s for s in spans if s.startswith("oacp autonomy finalize <audit> --final-state cancelled"))
    deliverable = next(s for s in spans if s.startswith("--deliverable-landed"))
    return checkpoint, cancel, deliverable


def fill(command, audit, clock):
    values = {"audit": str(audit), "N": "1", "action": "writes_findings_packet", "ref": PACKET, **clock}
    filled = re.sub(r"<([^>]+)>", lambda m: values[m.group(1)], command)   # KeyError = a new placeholder
    return filled.split()


def drop(args, *flags):
    out = list(args)
    for flag in flags:
        i = out.index(flag)
        del out[i:i + 2]
    return out


def round_record():
    scope = {
        "max_actual_minutes": 30, "max_actual_files_touched": 3,
        "allowed_types": ["review_request"], "max_round": 3,
        "expires_at_utc": "2099-01-01T00:00:00Z",
        "creates_or_updates_pr": False, "comments_on_github": False, "commits_changes": False,
        "merges_pr": False, "files_issues": False, "writes_findings_packet": True,
        "sends_oacp_reply": True, "submits_github_review": False,
    }
    envelope = dict(scope, estimated_minutes=30, expected_files_touched=3, risk_tier="P1",
                    target_repo="", destructive_ops=False, external_side_effects=False,
                    touches_auth_config_or_secrets=False, touches_dependencies=False,
                    public_visibility=False, sends_oacp_reply_only=True, continuation_grants={})
    return {
        "schema_version": 2, "spec_version": "0.4.3", "created_at_utc": "2026-08-01T01:00:00Z",
        "receiver": "reviewer", "sender": "author", "message_id": "msg-20260801010000-author-0001",
        "message_sha256": "c0ffee", "message_type": "review_request",
        "decision": "auto_accepted", "mode": "auto_review",
        "reason_codes": ["continuation_grant_accepted"],
        "scope_envelope": envelope, "scope_envelope_source": "continuation_grant",
        "continuation_grant": {"decision": "accepted", "scope": scope},
        "result": {
            "final_state": "pending", "completion_kind": "auto_accepted",
            "actual_minutes": None, "actual_files_touched": None,
            "predicted_risk_materialized": False, "completed_at_utc": None,
            "envelope_enforcement": "none",
        },
    }


@pytest.fixture
def audit(tmp_path):
    path = tmp_path / RECORD_NAME
    path.write_text(json.dumps(round_record()))   # JSON is valid YAML
    return path


@pytest.fixture
def clock():
    """One synthetic round: its start and the notice are captured once and shared by every command."""
    return {"UTC the round started": utc(3), "UTC the notice or replacement arrived": utc(1)}


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def assert_cancelled_and_valid(audit, res):
    assert res.returncode == 0, res.stdout + res.stderr
    assert "— cancelled" in res.stdout
    check = run(["oacp", "autonomy", "finalize", str(audit), "--validate"])
    assert check.returncode == 0 and "0 error finding(s)" in check.stdout, check.stdout + check.stderr


def test_round_that_never_started(audit, clock):
    _, cancel, _ = recipe()
    args = drop(fill(cancel, audit, clock), "--started-at", "--actual-files-touched")
    assert_cancelled_and_valid(audit, run(args))


def test_round_in_flight_with_no_effect(audit, clock):
    _, cancel, _ = recipe()
    assert_cancelled_and_valid(audit, run(fill(cancel, audit, clock)))


def test_round_in_flight_after_writing_the_findings_packet(audit, clock):
    checkpoint, cancel, deliverable = recipe()
    res = run(fill(checkpoint, audit, clock))
    assert res.returncode == 0, res.stdout + res.stderr
    assert_cancelled_and_valid(audit, run(fill(cancel, audit, clock) + fill(deliverable, audit, clock)))
    text = audit.read_text()
    assert PACKET in text and "writes_findings_packet: true" in text


def test_realized_on_the_cancel_is_refused(audit, clock):
    _, cancel, _ = recipe()
    assert "--realized" not in cancel
    before = audit.read_text()
    res = run(fill(cancel, audit, clock) + ["--realized", "writes_findings_packet"])
    assert res.returncode == 2 and "clock/count actuals only" in res.stdout + res.stderr
    assert audit.read_text() == before
