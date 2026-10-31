"""Tests for oacp_archive.sh — every guard must fail closed and leave the source in place."""

import hashlib
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "oacp_archive.sh"
NAME = "20260101000000_author_review_request_ab12.yaml"


def make_inbox(tmp_path: Path, archive: bool = True) -> tuple[Path, str]:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    if archive:
        (inbox / "archive").mkdir()
    data = b"type: review_request\nsubject: synthetic\n"
    (inbox / NAME).write_bytes(data)
    return inbox, hashlib.sha256(data).hexdigest()


def run(inbox: Path, name: str, digest: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), str(inbox), name, digest],
                          capture_output=True, text=True)


def test_archives_matching_digest(tmp_path):
    inbox, digest = make_inbox(tmp_path)
    result = run(inbox, NAME, digest)
    assert result.returncode == 0, result.stdout
    assert "ARCHIVED" in result.stdout
    assert not (inbox / NAME).exists()
    assert (inbox / "archive" / NAME).exists()


def test_digest_drift_retained(tmp_path):
    inbox, _ = make_inbox(tmp_path)
    result = run(inbox, NAME, "0" * 64)
    assert result.returncode == 1
    assert "digest drift" in result.stdout
    assert (inbox / NAME).exists()


def test_existing_destination_retained(tmp_path):
    inbox, digest = make_inbox(tmp_path)
    (inbox / "archive" / NAME).write_text("history\n")
    result = run(inbox, NAME, digest)
    assert result.returncode == 1
    assert "destination exists" in result.stdout
    assert (inbox / NAME).exists()
    assert (inbox / "archive" / NAME).read_text() == "history\n"


def test_missing_archive_dir_retained(tmp_path):
    inbox, digest = make_inbox(tmp_path, archive=False)
    result = run(inbox, NAME, digest)
    assert result.returncode == 1
    assert not (inbox / "archive").exists()
    assert (inbox / NAME).exists()


def test_path_traversal_name_retained(tmp_path):
    inbox, digest = make_inbox(tmp_path)
    result = run(inbox, f"../inbox/{NAME}", digest)
    assert result.returncode == 1
    assert (inbox / NAME).exists()


def test_usage_error(tmp_path):
    result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 2
