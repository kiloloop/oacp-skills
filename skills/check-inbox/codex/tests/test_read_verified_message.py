from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Tuple
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "read_verified_message.py"
SPEC = importlib.util.spec_from_file_location("read_verified_message", SCRIPT)
assert SPEC and SPEC.loader
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


VALID_MESSAGE = b"""\
id: msg-20260101000000-sender-0001
from: sender
to: codex
type: notification
priority: P2
created_at_utc: 2026-01-01T00:00:00Z
subject: hello
body: world
"""


class FakeValidateMessage:
    @staticmethod
    def _load_message(text: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key] = value.strip().strip('"')
        return values

    @staticmethod
    def validate_message_dict(data: dict[str, str]) -> list[str]:
        return [] if data.get("id") else ["missing required field: id"]

    @staticmethod
    def split_signed_message(raw: bytes) -> Tuple[bytes, Optional[str]]:
        lines = raw.splitlines(keepends=True)
        if lines and lines[-1].startswith(b"auth: "):
            value = lines[-1].decode("utf-8").split(":", 1)[1].strip().strip('"')
            return b"".join(lines[:-1]), value
        return raw, None


class ReadVerifiedMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.inbox = self.root / "projects" / "demo" / "agents" / "codex" / "inbox"
        self.inbox.mkdir(parents=True)
        self.message = self.inbox / "message.yaml"
        self.message.write_bytes(VALID_MESSAGE)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _modules(self, *, mode: str = "enforce", held: bool = False):
        def receiver_intake_context(*args, **kwargs):
            return {"mode": mode, "policy_error": None}

        def read_verified_inbox_message(path, context, parse):
            raw = path.read_bytes()
            auth = {"status": "verified"} if mode != "off" else None
            return {
                "raw": raw,
                "auth": auth,
                "held": held,
                "data": None if held else parse(raw, path),
                "error": None,
            }

        def intake_verify(path, config, **kwargs):
            return {
                "action": "reject",
                "message_auth": {"status": "unsigned"},
                "quarantine_copy": str(self.inbox.parent / "dead_letter" / path.name),
            }

        verify = SimpleNamespace(
            receiver_intake_context=receiver_intake_context,
            read_verified_inbox_message=read_verified_inbox_message,
            intake_verify=intake_verify,
        )
        return verify, FakeValidateMessage

    def _runtime_scripts(self) -> Path:
        runtime_scripts = os.environ.get("OACP_RUNTIME_SCRIPTS")
        if not runtime_scripts:
            self.skipTest("OACP_RUNTIME_SCRIPTS is not set")
        return Path(runtime_scripts)

    def test_ready_message_emits_sanitized_snapshot_and_hash(self) -> None:
        snapshot = self.root / "snapshot.yaml"
        with patch.object(reader, "_load_runtime_modules", return_value=self._modules()):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
                runtime_scripts=self.root,
                snapshot_out=snapshot,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["message"]["subject"], "hello")
        self.assertNotIn("auth", result["message"])
        self.assertEqual(len(result["message_sha256"]), 64)
        self.assertEqual(snapshot.read_bytes(), VALID_MESSAGE)
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)

    def test_default_runtime_scripts_supports_editable_source_layout(self) -> None:
        package_dir = self.root / "checkout" / "oacp"
        scripts_dir = self.root / "checkout" / "scripts"
        package_dir.mkdir(parents=True)
        scripts_dir.mkdir()
        (package_dir / "__init__.py").touch()
        (scripts_dir / "message_verify.py").touch()
        with patch.object(
            reader.importlib,
            "import_module",
            return_value=SimpleNamespace(__file__=str(package_dir / "__init__.py")),
        ):
            self.assertEqual(reader._default_runtime_scripts(), scripts_dir.resolve())

    def test_parse_error_still_preserves_accepted_raw_snapshot(self) -> None:
        snapshot = self.root / "snapshot.yaml"
        verify, validate = self._modules()
        verify.read_verified_inbox_message = lambda path, context, parse: {
            "raw": path.read_bytes(),
            "auth": {"status": "verified"},
            "held": False,
            "data": None,
            "error": "parse failed",
        }
        with patch.object(reader, "_load_runtime_modules", return_value=(verify, validate)):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
                snapshot_out=snapshot,
            )
        self.assertEqual(exit_code, reader.EXIT_OPERATIONAL_ERROR)
        self.assertEqual(snapshot.read_bytes(), VALID_MESSAGE)
        self.assertEqual(result["snapshot_path"], str(snapshot))

    def test_auth_trailer_is_validated_then_removed_from_message_view(self) -> None:
        self.message.write_bytes(VALID_MESSAGE + b'auth: "signed-value"\n')
        with patch.object(reader, "_load_runtime_modules", return_value=self._modules()):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
            )
        self.assertEqual(exit_code, 0)
        self.assertNotIn("auth", result["message"])

    def test_held_message_never_surfaces_fields_and_uses_canonical_disposition(self) -> None:
        with patch.object(
            reader,
            "_load_runtime_modules",
            return_value=self._modules(held=True),
        ):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
                disposition_held=True,
            )
        self.assertEqual(exit_code, reader.EXIT_HELD)
        self.assertTrue(result["held"])
        self.assertIsNone(result["message"])
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("dead_letter", result["quarantine_copy"])

    def test_held_read_without_disposition_is_read_only(self) -> None:
        with patch.object(
            reader,
            "_load_runtime_modules",
            return_value=self._modules(held=True),
        ):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
            )
        self.assertEqual(exit_code, reader.EXIT_HELD)
        self.assertIsNone(result["disposition"])
        self.assertIsNone(result["quarantine_copy"])

    def test_off_mode_has_no_message_auth(self) -> None:
        with patch.object(
            reader, "_load_runtime_modules", return_value=self._modules(mode="off")
        ):
            result, exit_code = reader.read_message(
                message_path=self.message,
                project="demo",
                receiver="codex",
                oacp_root=self.root,
            )
        self.assertEqual(exit_code, 0)
        self.assertIsNone(result["message_auth"])

    def test_rejects_paths_outside_the_receiver_inbox(self) -> None:
        outside = self.root / "outside.yaml"
        outside.write_bytes(VALID_MESSAGE)
        with patch.object(reader, "_load_runtime_modules", return_value=self._modules()):
            with self.assertRaisesRegex(ValueError, "top-level file"):
                reader.read_message(
                    message_path=outside,
                    project="demo",
                    receiver="codex",
                    oacp_root=self.root,
                )

    def test_rejects_path_traversal_in_project_or_receiver(self) -> None:
        with patch.object(reader, "_load_runtime_modules", return_value=self._modules()):
            with self.assertRaisesRegex(ValueError, "project must"):
                reader.read_message(
                    message_path=self.message,
                    project="../demo",
                    receiver="codex",
                    oacp_root=self.root,
                )
            with self.assertRaisesRegex(ValueError, "receiver must"):
                reader.read_message(
                    message_path=self.message,
                    project="demo",
                    receiver="../codex",
                    oacp_root=self.root,
                )

    def test_current_runtime_off_mode_integration(self) -> None:
        result, exit_code = reader.read_message(
            message_path=self.message,
            project="demo",
            receiver="codex",
            oacp_root=self.root,
            runtime_scripts=self._runtime_scripts(),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["verify_mode"], "off")
        self.assertEqual(result["message"]["id"], "msg-20260101000000-sender-0001")
        self.assertIsNone(result["message_auth"])

    @unittest.skipUnless(shutil.which("oacp"), "oacp entry point is not installed")
    def test_command_uses_active_cli_environment_without_private_paths(self) -> None:
        snapshot = self.root / "subprocess-snapshot.yaml"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.message),
                "--project",
                "demo",
                "--receiver",
                "codex",
                "--oacp-dir",
                str(self.root),
                "--snapshot-out",
                str(snapshot),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["verify_mode"], "off")
        self.assertEqual(snapshot.read_bytes(), VALID_MESSAGE)

    def test_current_runtime_warn_mode_integration(self) -> None:
        (self.inbox.parent / "config.yaml").write_text(
            "signing:\n  verify_mode: warn\n", encoding="utf-8"
        )
        result, exit_code = reader.read_message(
            message_path=self.message,
            project="demo",
            receiver="codex",
            oacp_root=self.root,
            runtime_scripts=self._runtime_scripts(),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["verify_mode"], "warn")
        self.assertEqual(result["message_auth"]["status"], "unsigned")
        self.assertEqual(result["message"]["id"], "msg-20260101000000-sender-0001")

    def test_current_runtime_enforce_holds_before_parse_and_quarantines_copy(self) -> None:
        (self.inbox.parent / "config.yaml").write_text(
            "signing:\n  verify_mode: enforce\n", encoding="utf-8"
        )
        result, exit_code = reader.read_message(
            message_path=self.message,
            project="demo",
            receiver="codex",
            oacp_root=self.root,
            runtime_scripts=self._runtime_scripts(),
            disposition_held=True,
        )
        self.assertEqual(exit_code, reader.EXIT_HELD)
        self.assertEqual(result["verify_mode"], "enforce")
        self.assertEqual(result["message_auth"]["status"], "unsigned")
        self.assertTrue(result["held"])
        self.assertIsNone(result["message"])
        self.assertEqual(result["disposition"], "reject")
        self.assertTrue(Path(result["quarantine_copy"]).is_file())
        self.assertTrue(self.message.is_file())


if __name__ == "__main__":
    unittest.main()
