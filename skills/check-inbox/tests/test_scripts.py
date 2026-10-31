"""Guard-path tests for the check-inbox Claude scripts.

Covers the fail-closed archival guards and the finalize wrappers' refusals. The
wrappers are exercised against a stub `oacp` on PATH, so no OACP install is needed;
CanonicalReplyCoverage additionally drives the real finalizer through the wrapper and
skips when `oacp` (0.5.3+) is not installed. Audit records there are synthetic.
Run: python3 -m unittest discover -s skills/check-inbox/tests (or pytest).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ARCHIVE = SCRIPTS / "oacp_archive.sh"
FINALIZE = SCRIPTS / "finalize_done.sh"
SEND_DONE = SCRIPTS / "send_done_and_finalize.sh"

MESSAGE = b"id: msg-20260101000000-peer-0001\nfrom: peer\nto: claude\ntype: notification\n"

# Stub CLI: `oacp autonomy finalize … --dry-run` succeeds with a JSON summary; anything
# else exits 9 so a test notices if a refusal path reached the CLI.
STUB_OACP = """#!/usr/bin/env bash
case " $* " in
  *" autonomy finalize "*"--dry-run"*) echo '{"dry_run": true, "final_state": "done"}'; exit 0 ;;
esac
echo "stub oacp: unexpected call: $*" >&2
exit 9
"""


def run(cmd, env=None, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)


class ArchiveGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name) / "inbox"
        (self.inbox / "archive").mkdir(parents=True)
        self.name = "20260101000000_peer_notification_abcd.yaml"
        (self.inbox / self.name).write_bytes(MESSAGE)
        self.sha = hashlib.sha256(MESSAGE).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, sha=None):
        return run(["bash", str(ARCHIVE), str(self.inbox), self.name, sha or self.sha])

    def test_archives_on_matching_digest(self):
        res = self.archive()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("ARCHIVED:", res.stdout)
        self.assertFalse((self.inbox / self.name).exists())
        self.assertEqual((self.inbox / "archive" / self.name).read_bytes(), MESSAGE)

    def test_digest_drift_retains(self):
        res = self.archive(sha="0" * 64)
        self.assertEqual(res.returncode, 1)
        self.assertIn("RETAINED: digest drift", res.stdout)
        self.assertTrue((self.inbox / self.name).exists())

    def test_existing_destination_is_never_overwritten(self):
        (self.inbox / "archive" / self.name).write_bytes(b"history\n")
        res = self.archive()
        self.assertEqual(res.returncode, 1)
        self.assertIn("RETAINED: destination exists", res.stdout)
        self.assertEqual((self.inbox / "archive" / self.name).read_bytes(), b"history\n")
        self.assertTrue((self.inbox / self.name).exists())

    def test_missing_archive_dir_is_not_created(self):
        (self.inbox / "archive").rmdir()
        res = self.archive()
        self.assertEqual(res.returncode, 1)
        self.assertIn("RETAINED: archive/ missing", res.stdout)
        self.assertFalse((self.inbox / "archive").exists())

    def test_symlinked_archive_dir_retains(self):
        (self.inbox / "archive").rmdir()
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        (self.inbox / "archive").symlink_to(elsewhere)
        res = self.archive()
        self.assertEqual(res.returncode, 1)
        self.assertIn("symlinked", res.stdout)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_non_bare_filename_retains(self):
        res = run(["bash", str(ARCHIVE), str(self.inbox), "../x.yaml", self.sha])
        self.assertEqual(res.returncode, 1)
        self.assertIn("RETAINED: filename must be a bare inbox entry name", res.stdout)
        self.assertTrue((self.inbox / self.name).exists())
        self.assertEqual(list((self.inbox / "archive").iterdir()), [])

    def test_usage_error(self):
        res = run(["bash", str(ARCHIVE), str(self.inbox)])
        self.assertEqual(res.returncode, 2)


class WrapperFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        bindir = root / "bin"
        bindir.mkdir()
        stub = bindir / "oacp"
        stub.write_text(STUB_OACP)
        stub.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
        self.env.pop("OACP_HOME", None)
        self.env.update(OACP_RUNTIME_MODEL="test-model", OACP_RUNTIME_EFFORT="high")
        self.record = root / "20260101T000001Z_msg-20260101000000-peer-0001.yaml"
        self.record.write_text("result:\n  final_state: pending\n  actual_minutes: null\n")
        self.body = root / "done.txt"
        self.body.write_text("Done. Clock -> {{END}} ({{MINUTES}} min)\n")

    def tearDown(self):
        self.tmp.cleanup()

    def finalize(self, *args):
        return run(["bash", str(FINALIZE), str(self.record), *args], env=self.env)

    def send_done(self, *finalize_args, extra=()):
        cmd = ["bash", str(SEND_DONE), str(self.record), "demo", "peer",
               "msg-20260101000000-peer-0001", "conv-20260101-peer-1", "Re: task",
               str(self.body), *extra, "--", *finalize_args]
        return run(cmd, env=self.env)


class FinalizeWrappers(WrapperFixture):

    def test_passes_realized_sends_oacp_reply_to_the_finalizer(self):
        # Coverage is the canonical finalizer's call (see CanonicalReplyCoverage), not the wrapper's.
        res = self.finalize("--", "--started-at", "2026-01-01T00:00:05Z",
                            "--realized", "sends_oacp_reply")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("REFUSED", res.stderr)
        self.assertIn("dry-run passed", res.stdout)

    def test_refuses_completed_at_and_owned_flags(self):
        for flag in ("--completed-at", "--final-state", "--checkpoint", "--dry-run"):
            res = self.finalize("--", flag, "x")
            self.assertEqual(res.returncode, 2, flag)
            self.assertIn("REFUSED", res.stderr)

    def test_dry_run_only_without_commit(self):
        res = self.finalize("--", "--started-at", "2026-01-01T00:00:05Z")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("dry-run passed", res.stdout)
        self.assertNotIn("real finalize", res.stdout)

    def test_send_done_requires_started_at(self):
        res = self.send_done("--actual-files-touched", "1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("--started-at", res.stderr)

    def test_send_done_refuses_reply_message_id(self):
        res = self.send_done("--started-at", "2026-01-01T00:00:05Z", "--reply-message-id", "x")
        self.assertEqual(res.returncode, 1)
        self.assertIn("supplied by this script", res.stderr)

    def test_send_done_refuses_minutes_on_paused_record(self):
        self.record.write_text(
            "result:\n  threshold_checkpoint:\n    paused_at_utc: '2026-01-01T00:10:00Z'\n")
        res = self.send_done("--started-at", "2026-01-01T00:00:05Z", extra=("--print-only",))
        self.assertEqual(res.returncode, 1)
        self.assertIn("paused_at_utc", res.stderr)

    def test_send_done_pins_end_on_terminal_time_checkpoint(self):
        self.record.write_text(
            "result:\n  completed_at_utc: '2026-01-01T00:20:00Z'\n"
            "  threshold_checkpoint:\n    terminal_time: true\n")
        self.body.write_text("Done. Clock -> {{END}}\n")
        res = self.send_done("--started-at", "2026-01-01T00:00:05Z", extra=("--print-only",))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Clock -> 2026-01-01T00:20:00Z", res.stdout)


# Synthetic admission records in the OACP audit schema (schema_version 2); only the
# envelope and grant differ between cases.
ENVELOPE = {
    "estimated_minutes": 45, "expected_files_touched": 5, "risk_tier": "P1",
    "target_repo": "example-org/example-repo", "destructive_ops": False,
    "external_side_effects": True, "touches_auth_config_or_secrets": False,
    "touches_dependencies": False, "public_visibility": False,
    "creates_or_updates_pr": True, "comments_on_github": False, "commits_changes": True,
    "merges_pr": False, "files_issues": False, "sends_oacp_reply_only": False,
    "continuation_grants": {},
}
APPROVED = {
    "recorded": True, "actor": "example-human", "decision": "approved",
    "decided_at_utc": "2026-08-01T01:10:00Z", "decision_latency_seconds": 600,
    "pause_reason_codes": ["expected_files_touched_exceeds_threshold"],
    "grant": {"decision": "not_requested"},
}
GRANT_SCOPE = {
    "max_actual_minutes": 30, "max_actual_files_touched": 3,
    "allowed_types": ["review_request"], "max_round": 3,
    "expires_at_utc": "2099-01-01T00:00:00Z",
    "creates_or_updates_pr": False, "comments_on_github": False, "commits_changes": False,
    "merges_pr": False, "files_issues": False, "writes_findings_packet": True,
    "sends_oacp_reply": True, "submits_github_review": False,
}


def admission_record(envelope, granted=False):
    record = {
        "schema_version": 2, "spec_version": "0.4.3", "created_at_utc": "2026-08-01T01:00:00Z",
        "receiver": "claude", "sender": "peer", "message_id": "msg-20260801010000-peer-0001",
        "message_sha256": "c0ffee", "decision": "paused", "mode": "auto_review",
        "reason_codes": ["expected_files_touched_exceeds_threshold"],
        "scope_envelope": envelope,
        "continuation_grant": {"decision": "not_present", "scope": None},
        "result": {
            "final_state": "paused", "completion_kind": "admission_paused",
            "actual_minutes": None, "actual_files_touched": None,
            "predicted_risk_materialized": False, "completed_at_utc": None,
            "envelope_enforcement": "none", "human_outcome": APPROVED,
        },
    }
    if granted:
        record.update(decision="auto_accepted", message_type="review_request",
                      scope_envelope_source="continuation_grant",
                      continuation_grant={"decision": "accepted", "scope": GRANT_SCOPE})
        record["result"].update(final_state="pending", completion_kind="auto_accepted")
        del record["result"]["human_outcome"]
    return record


def _oacp_finalizer_available():
    if not shutil.which("oacp"):
        return False
    res = run(["oacp", "autonomy", "finalize", "--help"])
    return res.returncode == 0 and "sends_oacp_reply" in res.stdout


@unittest.skipUnless(_oacp_finalizer_available(), "needs oacp-cli 0.5.3+ on PATH")
class CanonicalReplyCoverage(unittest.TestCase):
    """The wrapper hands `--realized sends_oacp_reply` to the real finalizer, which admits a
    covered reply and refuses an uncovered one (exit 2, oacp-cli 0.5.4+); an undeclared boundary
    action still pauses at the dry-run (exit 4)."""

    def dry_run(self, record, *realized):
        start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260801T010000Z_msg-20260801010000-peer-0001.yaml"
            path.write_text(json.dumps(record))   # JSON is valid YAML
            args = ["bash", str(FINALIZE), str(path), "--", "--started-at", start,
                    "--actual-files-touched", "2"]
            for effect in realized:
                args += ["--realized", effect]
            res = run(args, env=dict(os.environ, OACP_RUNTIME_MODEL="test-model",
                                     OACP_RUNTIME_EFFORT="high"))
            self.assertEqual(path.read_text(), json.dumps(record), "a dry-run must write nothing")
        return res

    def test_profile_declaring_the_reply_covers_it(self):
        res = self.dry_run(admission_record(dict(ENVELOPE, sends_oacp_reply=True)),
                           "creates_or_updates_pr", "commits_changes", "sends_oacp_reply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("within_declared_envelope", res.stdout)

    def test_reply_only_profile_covers_it(self):
        reply_only = dict(ENVELOPE, external_side_effects=False, creates_or_updates_pr=False,
                          commits_changes=False, sends_oacp_reply_only=True)
        res = self.dry_run(admission_record(reply_only), "sends_oacp_reply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("within_declared_envelope", res.stdout)

    def test_grant_permitting_the_reply_covers_it(self):
        granted = dict(ENVELOPE, estimated_minutes=30, expected_files_touched=3, target_repo="",
                       external_side_effects=False, creates_or_updates_pr=False,
                       commits_changes=False, sends_oacp_reply_only=True,
                       writes_findings_packet=True, sends_oacp_reply=True,
                       submits_github_review=False)
        res = self.dry_run(admission_record(granted, granted=True),
                           "writes_findings_packet", "sends_oacp_reply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_uncovered_reply_is_refused(self):
        res = self.dry_run(admission_record(dict(ENVELOPE)),
                           "creates_or_updates_pr", "commits_changes", "sends_oacp_reply")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("grant-only effect", res.stdout + res.stderr)

    def test_undeclared_boundary_action_pauses_at_the_dry_run(self):
        res = self.dry_run(admission_record(dict(ENVELOPE)),
                           "creates_or_updates_pr", "commits_changes", "merges_pr")
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertIn("paused_for_reauthorization", res.stdout)


class RuntimeFromTranscript(WrapperFixture):
    """finalize_done.sh reads model and effort from the session transcript when the caller
    supplies neither, and refuses when it cannot."""

    def setUp(self):
        super().setUp()
        for key in ("OACP_RUNTIME_MODEL", "OACP_RUNTIME_EFFORT", "CLAUDE_CODE_SESSION_ID"):
            self.env.pop(key, None)
        self.cfg = Path(self.tmp.name) / "config"
        self.env["CLAUDE_CONFIG_DIR"] = str(self.cfg)

    def write_transcript(self, sid, rows):
        path = self.cfg / "projects" / "-demo-repo" / f"{sid}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_reads_runtime_from_the_session_transcript(self):
        self.write_transcript("sess-1", [
            {"type": "user", "message": {"content": "go"}},
            {"type": "assistant", "message": {"model": "model-a"}, "perTurnEffort": "high"},
            {"type": "assistant", "message": {"model": "<synthetic>"}},
        ])
        self.env["CLAUDE_CODE_SESSION_ID"] = "sess-1"
        res = self.finalize("--", "--started-at", "2026-01-01T00:00:05Z")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("runtime from session transcript: model=model-a effort=high", res.stderr)

    def test_refuses_without_runtime_or_transcript(self):
        res = self.finalize("--", "--started-at", "2026-01-01T00:00:05Z")
        self.assertEqual(res.returncode, 2)
        self.assertIn("REFUSED: no runtime model", res.stderr)
        self.assertNotIn("dry-run", res.stdout)

    def test_explicit_flags_skip_the_transcript(self):
        res = self.finalize("--", "--started-at", "2026-01-01T00:00:05Z",
                            "--model", "model-b", "--effort", "low")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("session transcript", res.stderr)


def load_pin_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pin_trusted_scripts", SCRIPTS / "pin_trusted_scripts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    import yaml  # noqa: F401  (pin_trusted_scripts.py imports it at module load)
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


@unittest.skipUnless(HAVE_YAML, "PyYAML not installed")
class PinTrustedScripts(unittest.TestCase):
    """The config splice and pin merge behind pin_trusted_scripts.py."""

    def setUp(self):
        self.mod = load_pin_module()

    def test_merge_refreshes_by_real_path_appends_missing_and_keeps_hand_pins(self):
        existing = [
            {"path": "/opt/skills/a.sh", "sha256": "old"},
            {"path": "/opt/hand/extra.sh", "sha256": "keep"},
        ]
        desired = [
            {"path": "/opt/skills/a.sh", "sha256": "new"},
            {"path": "/opt/skills/b.sh", "sha256": "bbb"},
        ]
        merged, changes = self.mod.merge(existing, desired)
        self.assertEqual([pin["sha256"] for pin in merged], ["new", "keep", "bbb"])
        self.assertEqual(changes, ["refreshed: /opt/skills/a.sh", "added: /opt/skills/b.sh"])

    def test_merge_reports_nothing_when_pins_match(self):
        pins = [{"path": "/opt/skills/a.sh", "sha256": "same"}]
        self.assertEqual(self.mod.merge(pins, pins)[1], [])

    def test_splice_inserts_the_block_above_the_auth_trailer(self):
        block = self.mod.render_block({"trusted_scripts": [{"path": "/opt/skills/a.sh", "sha256": "abc"}]})
        out = self.mod.splice_block("autonomy:\n  default_mode: always_pause\nauth: x\n", block)
        self.assertTrue(out.endswith(block + "auth: x\n"), out)

    def test_splice_replaces_an_existing_block_and_keeps_later_keys(self):
        text = ("envelope:\n  trusted_scripts:\n    - path: /old.sh\n      sha256: o\n"
                "signing:\n  sign_messages: true\n")
        block = self.mod.render_block({"trusted_scripts": [{"path": "/new.sh", "sha256": "n"}]})
        out = self.mod.splice_block(text, block)
        self.assertNotIn("/old.sh", out)
        self.assertTrue(out.startswith(block), out)
        self.assertTrue(out.endswith("signing:\n  sign_messages: true\n"), out)


FAKE_COMPILER = """
def trusted_scripts(config):
    section = config.get("envelope") or {}
    pins = section.get("trusted_scripts") or []
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) - {"path", "sha256", "env"}:
            raise ValueError("malformed pin")
    return list(pins)
"""

HAND_PINS = [
    {"path": "/opt/manual #1/check.sh", "sha256": "a" * 64},
    {"path": "/opt/a: b/check.sh", "sha256": "b" * 64, "env": ["DATA_ONLY"]},
    {"path": "/opt/plain/check.sh", "sha256": "c" * 64},
]


@unittest.skipUnless(HAVE_YAML, "PyYAML not installed")
class PinTrustedScriptsApply(unittest.TestCase):
    """The real helper against a synthetic OACP home, skills dir and compiler loader."""

    def setUp(self):
        import yaml
        self.yaml = yaml
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.cfg = self.home / "projects" / "demo" / "agents" / "claude" / "config.yaml"
        self.cfg.parent.mkdir(parents=True)
        self.compiler = root / "compiler"
        self.compiler.mkdir()
        (self.compiler / "envelope_compiler.py").write_text(FAKE_COMPILER)
        self.skills = root / "skills"
        wrapper = self.skills / "check-inbox" / "scripts" / "finalize_done.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes(b"#!/usr/bin/env bash\necho synthetic\n")
        self.wrapper = str(wrapper)
        self.wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        self.config = {
            "autonomy": {"default_mode": "always_pause"},
            "envelope": {"trusted_scripts": HAND_PINS, "note_for_humans": "kept: a, b"},
            "signing": {"sign_messages": True},
        }
        self.cfg.write_text(yaml.safe_dump(self.config, sort_keys=False) + 'auth: "x"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def helper(self, *extra):
        return run(["python3", str(SCRIPTS / "pin_trusted_scripts.py"), str(self.home),
                    str(self.compiler), "--skills-dir", str(self.skills), *extra])

    def test_apply_keeps_hand_pins_and_unrelated_keys_exactly(self):
        res = self.helper("--apply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        after = self.yaml.safe_load(self.cfg.read_text())
        expected = HAND_PINS + [{"path": self.wrapper, "sha256": self.wrapper_sha}]
        self.assertEqual(after["envelope"]["trusted_scripts"], expected)
        self.assertEqual(after["envelope"]["note_for_humans"], "kept: a, b")
        for key in ("autonomy", "signing"):
            self.assertEqual(after[key], self.config[key])
        self.assertEqual(after["auth"], "x")

    def test_dry_run_writes_nothing(self):
        before = self.cfg.read_bytes()
        res = self.helper()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("would pin 4 scripts (dry run)", res.stdout)
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_second_apply_is_skipped_as_up_to_date(self):
        self.assertEqual(self.helper("--apply").returncode, 0)
        before = self.cfg.read_bytes()
        res = self.helper("--apply")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("pins up to date", res.stdout)
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_malformed_existing_block_is_refused_unwritten(self):
        self.cfg.write_text("envelope:\n  trusted_scripts:\n    - path: /x.sh\n      bogus: 1\nauth: x\n")
        before = self.cfg.read_bytes()
        res = self.helper("--apply")
        self.assertEqual(res.returncode, 1)
        self.assertIn("REFUSED", res.stderr)
        self.assertEqual(self.cfg.read_bytes(), before)


# Stub CLI for a full Done run: send answers with a message id, finalize succeeds, and any
# `oacp envelope …` call is logged so a test can prove the wrapper never clears.
STUB_FULL = """#!/usr/bin/env bash
case " $* " in
  *" envelope "*) echo "$*" >> "$OACP_STUB_LOG"; exit 0 ;;
  *" autonomy finalize "*"--dry-run"*) echo '{"dry_run": true, "final_state": "done"}'; exit 0 ;;
  *" autonomy finalize "*) echo '{"final_state": "done"}'; exit 0 ;;
  *" send "*) echo '{"message_id": "msg-20260101000100-claude-0002", "inbox_path": "/dev/null"}'; exit 0 ;;
esac
echo "stub oacp: unexpected call: $*" >&2
exit 9
"""


class SendDoneEnvelopeReport(WrapperFixture):
    """After the terminal finalize the Done wrapper reports the active envelope and never clears it."""

    def setUp(self):
        super().setUp()
        root = Path(self.tmp.name)
        (root / "bin" / "oacp").write_text(STUB_FULL)
        self.log = root / "oacp-calls.log"
        self.home = root / "home"
        self.env.update(OACP_HOME=str(self.home), OACP_STUB_LOG=str(self.log))
        self.envelope = self.home / "projects" / "demo" / "agents" / "claude" / "state" / "active_envelope.json"
        self.record.write_text("message_id: msg-20260101000000-peer-0001\n"
                               "result:\n  final_state: pending\n  actual_minutes: null\n")
        self.body.write_text("Done.\n")

    def done(self):
        return self.send_done("--started-at", "2026-01-01T00:00:05Z")

    def write_envelope(self, text):
        self.envelope.parent.mkdir(parents=True, exist_ok=True)
        self.envelope.write_text(text)
        return self.envelope.read_bytes()

    def assert_never_cleared(self):
        self.assertFalse(self.log.exists() and "envelope" in self.log.read_text(),
                         "the wrapper must not call oacp envelope")

    def test_own_envelope_is_reported_with_the_standalone_clear(self):
        before = self.write_envelope(json.dumps({"message_id": "msg-20260101000000-peer-0001"}))
        res = self.done()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("still active for this task", res.stdout)
        self.assertIn(f"oacp envelope clear --project demo --receiver claude --oacp-dir {self.home}", res.stdout)
        self.assertEqual(self.envelope.read_bytes(), before)
        self.assert_never_cleared()

    def test_another_tasks_envelope_is_named_and_kept(self):
        before = self.write_envelope(json.dumps({"message_id": "msg-20260101000500-peer-0009"}))
        res = self.done()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("belongs to msg-20260101000500-peer-0009", res.stderr)
        self.assertEqual(self.envelope.read_bytes(), before)
        self.assert_never_cleared()

    def test_unreadable_envelope_state_is_kept(self):
        before = self.write_envelope("{not json")
        res = self.done()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("unreadable state", res.stderr)
        self.assertEqual(self.envelope.read_bytes(), before)
        self.assert_never_cleared()

    def test_no_envelope(self):
        res = self.done()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("envelope: none active", res.stdout)
        self.assert_never_cleared()


if __name__ == "__main__":
    unittest.main()
