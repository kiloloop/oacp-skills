#!/usr/bin/env python3
"""Read one OACP inbox message through the canonical receive boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shlex
import shutil
import stat
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


EXIT_OPERATIONAL_ERROR = 2
EXIT_HELD = 3
EXIT_SCHEMA_INVALID = 4


def _safe_path_component(value: str, label: str) -> str:
    if not value or value.startswith(".") or "/" in value or "\\" in value:
        raise ValueError(
            f"{label} must not be empty, start with '.', or contain path separators"
        )
    return value


def _default_runtime_scripts() -> Path:
    """Resolve the scripts bundled with the active installed OACP package."""
    package = importlib.import_module("oacp")
    package_file = getattr(package, "__file__", None)
    if not package_file:
        raise RuntimeError("cannot resolve the installed oacp package location")
    package_dir = Path(package_file).resolve().parent
    source_scripts = package_dir.parent / "scripts"
    if (source_scripts / "message_verify.py").is_file():
        return source_scripts
    return package_dir / "_scripts"


def _reexec_with_active_cli_python() -> None:
    """Use the interpreter that owns the active oacp entry point when needed."""
    if os.environ.get("OACP_READER_REEXEC") == "1":
        return
    executable = shutil.which("oacp")
    if not executable:
        return
    try:
        first_line = Path(executable).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()[0]
    except (OSError, IndexError):
        return
    if not first_line.startswith("#!"):
        return
    parts = shlex.split(first_line[2:].strip())
    if not parts:
        return
    interpreter_args: list[str] = []
    if Path(parts[0]).name == "env":
        if len(parts) != 2:
            return
        interpreter = shutil.which(parts[1])
        if not interpreter:
            return
    else:
        interpreter = parts[0]
        interpreter_args = parts[1:]
    if not Path(interpreter).is_file():
        return
    if Path(interpreter).resolve() == Path(sys.executable).resolve():
        return
    environment = dict(os.environ)
    environment["OACP_READER_REEXEC"] = "1"
    os.execve(
        interpreter,
        [
            interpreter,
            *interpreter_args,
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        environment,
    )


def _load_runtime_modules(runtime_scripts: Optional[Path]) -> Tuple[Any, Any]:
    runtime_scripts = (runtime_scripts or _default_runtime_scripts()).resolve()
    if not (runtime_scripts / "message_verify.py").is_file():
        raise RuntimeError(
            f"runtime scripts directory lacks message_verify.py: {runtime_scripts}"
        )
    if not (runtime_scripts / "validate_message.py").is_file():
        raise RuntimeError(
            f"runtime scripts directory lacks validate_message.py: {runtime_scripts}"
        )

    sys.path.insert(0, str(runtime_scripts))
    try:
        message_verify = importlib.import_module("message_verify")
        validate_message = importlib.import_module("validate_message")
    finally:
        sys.path.pop(0)
    return message_verify, validate_message


def _parse_snapshot(raw: bytes, path: Path, validate_message: Any) -> Dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"message is not valid UTF-8: {path}: {exc}") from exc
    data = validate_message._load_message(text)
    if not isinstance(data, dict):
        raise ValueError(f"top-level YAML must be a mapping: {path}")
    return data


def _validation_errors(
    raw: bytes, data: Dict[str, Any], validate_message: Any
) -> list[str]:
    errors = list(validate_message.validate_message_dict(data))
    if "auth" in data:
        _, trailer_value = validate_message.split_signed_message(raw)
        if trailer_value is None:
            errors.append(
                "field 'auth' must be the final physical line of the file: "
                'auth: "<base64url>" followed by exactly one LF (no CRLF)'
            )
        elif str(data.get("auth")) != trailer_value:
            errors.append(
                "field 'auth' parsed value does not match the raw trailer line"
            )
    return errors


def _regular_inbox_path(
    message_path: Path,
    *,
    oacp_root: Path,
    project: str,
    receiver: str,
) -> Tuple[Path, Path]:
    project = _safe_path_component(project, "project")
    receiver = _safe_path_component(receiver, "receiver")
    inbox_dir = (
        oacp_root / "projects" / project / "agents" / receiver / "inbox"
    ).resolve()
    candidate = message_path.expanduser()
    if candidate.parent.resolve() != inbox_dir:
        raise ValueError(
            f"message path must be a top-level file in {inbox_dir}: {candidate}"
        )
    if candidate.suffix != ".yaml":
        raise ValueError(f"message path must end in .yaml: {candidate}")
    mode = candidate.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(
            f"message path must be a regular file, not a symlink: {candidate}"
        )
    return candidate, inbox_dir


def _write_snapshot(raw: bytes, snapshot_out: Path) -> None:
    snapshot_out = snapshot_out.expanduser()
    snapshot_out.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        snapshot_out,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)


def read_message(
    *,
    message_path: Path,
    project: str,
    receiver: str,
    oacp_root: Path,
    runtime_scripts: Optional[Path] = None,
    snapshot_out: Optional[Path] = None,
    disposition_held: bool = False,
) -> Tuple[Dict[str, Any], int]:
    message_verify, validate_message = _load_runtime_modules(runtime_scripts)
    message_path, inbox_dir = _regular_inbox_path(
        message_path,
        oacp_root=oacp_root,
        project=project,
        receiver=receiver,
    )
    context = message_verify.receiver_intake_context(
        inbox_dir.parent,
        receiver=receiver,
        project=project,
        oacp_dir=str(oacp_root),
    )
    read = message_verify.read_verified_inbox_message(
        message_path,
        context,
        lambda raw, path: _parse_snapshot(raw, path, validate_message),
    )

    raw = read.get("raw")
    digest = hashlib.sha256(raw).hexdigest() if isinstance(raw, bytes) else None
    result: Dict[str, Any] = {
        "path": str(message_path),
        "verify_mode": context.get("mode", "off"),
        "policy_error": context.get("policy_error"),
        "held": bool(read.get("held")),
        "message_auth": read.get("auth"),
        "message_sha256": digest,
        "snapshot_path": None,
        "validation_errors": [],
        "message": None,
        "disposition": None,
        "quarantine_copy": None,
        "error": read.get("error"),
    }

    if raw is None:
        return result, EXIT_OPERATIONAL_ERROR
    if read.get("held"):
        if disposition_held:
            disposition = message_verify.intake_verify(
                message_path,
                inbox_dir.parent / "config.yaml",
                receiver=receiver,
                oacp_dir=str(oacp_root),
                message_raw=raw,
                verify_mode=str(context.get("mode", "enforce")),
            )
            result["disposition"] = disposition.get("action")
            result["message_auth"] = disposition.get("message_auth")
            result["quarantine_copy"] = disposition.get("quarantine_copy")
            if disposition.get("action") != "reject":
                result["error"] = (
                    "held snapshot was not rejected by canonical intake; "
                    "retain the source and rerun intake"
                )
                return result, EXIT_OPERATIONAL_ERROR
        return result, EXIT_HELD

    if snapshot_out is not None:
        _write_snapshot(raw, snapshot_out)
        result["snapshot_path"] = str(snapshot_out.expanduser())

    if read.get("error"):
        return result, EXIT_OPERATIONAL_ERROR
    data = read.get("data")
    if not isinstance(data, dict):
        result["error"] = "verified snapshot did not parse as a mapping"
        return result, EXIT_OPERATIONAL_ERROR

    errors = _validation_errors(raw, data, validate_message)
    result["validation_errors"] = errors
    sanitized = dict(data)
    sanitized.pop("auth", None)
    result["message"] = sanitized
    if errors:
        return result, EXIT_SCHEMA_INVALID
    return result, 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--oacp-dir", required=True, type=Path)
    parser.add_argument(
        "--runtime-scripts",
        type=Path,
        help="override the scripts bundled with the installed OACP package",
    )
    parser.add_argument(
        "--snapshot-out",
        type=Path,
        help=(
            "write the exact raw intake-snapshot bytes (YAML, including any "
            "auth trailer) to a new mode-0600 file; stdout remains the "
            "structured JSON result"
        ),
    )
    parser.add_argument(
        "--disposition-held",
        action="store_true",
        help=(
            "write aside accepted raw bytes for a held enforce result through "
            "the canonical receiver dead-letter mechanism"
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        _reexec_with_active_cli_python()
        result, exit_code = read_message(
            message_path=args.message,
            project=args.project,
            receiver=args.receiver,
            oacp_root=args.oacp_dir.expanduser().resolve(),
            runtime_scripts=args.runtime_scripts,
            snapshot_out=args.snapshot_out,
            disposition_held=args.disposition_held,
        )
    except Exception as exc:
        result = {
            "path": str(args.message),
            "held": False,
            "message": None,
            "error": str(exc),
        }
        exit_code = EXIT_OPERATIONAL_ERROR
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
