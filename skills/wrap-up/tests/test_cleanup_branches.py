from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_branches.sh"


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_dry_run_without_keep_handles_empty_array_on_macos_bash(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run("git", "init", "-q", cwd=repo)
    run("git", "checkout", "-q", "-b", "main", cwd=repo)
    run("git", "config", "user.name", "Test User", cwd=repo)
    run("git", "config", "user.email", "test@example.invalid", cwd=repo)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "tracked.txt", cwd=repo)
    run("git", "commit", "-q", "-m", "base", cwd=repo)
    run("git", "branch", "merged-topic", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_gh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(repo), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "WOULD prune (ancestry): merged-topic" in result.stdout
    assert "cleanup_branches: complete" in result.stdout
