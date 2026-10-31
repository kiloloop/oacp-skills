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


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run("git", "init", "-q", cwd=repo)
    run("git", "checkout", "-q", "-b", "main", cwd=repo)
    run("git", "config", "user.name", "Test User", cwd=repo)
    run("git", "config", "user.email", "test@example.invalid", cwd=repo)
    # Hermetic: a contributor's global commit signing must not leak in.
    run("git", "config", "commit.gpgsign", "false", cwd=repo)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "tracked.txt", cwd=repo)
    run("git", "commit", "-q", "-m", "base", cwd=repo)
    return repo


def fake_gh_env(tmp_path: Path, body: str = "exit 1\n") -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    return env


def run_script(
    repo: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def branches(repo: Path) -> set[str]:
    out = run("git", "branch", "--format=%(refname:short)", cwd=repo).stdout
    return set(out.split())


def test_dry_run_without_keep_handles_empty_array_on_macos_bash(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    run("git", "branch", "merged-topic", cwd=repo)

    result = run_script(repo, fake_gh_env(tmp_path), "--dry-run")

    assert "WOULD prune (ancestry): merged-topic" in result.stdout
    assert "cleanup_branches: complete" in result.stdout


def test_ancestry_pass_prunes_from_a_worktree_on_another_branch(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    run("git", "branch", "feature", cwd=repo)
    run("git", "checkout", "-q", "-b", "merged-topic", cwd=repo)
    (repo / "tracked.txt").write_text("topic\n", encoding="utf-8")
    run("git", "commit", "-q", "-am", "topic", cwd=repo)
    run("git", "checkout", "-q", "main", cwd=repo)
    run("git", "merge", "-q", "--ff-only", "merged-topic", cwd=repo)
    run("git", "branch", "probe", "merged-topic", cwd=repo)
    worktree = tmp_path / "wt"
    run("git", "worktree", "add", "-q", str(worktree), "feature", cwd=repo)

    # Precondition: `git branch -d` refuses here, because the tip is merged
    # into the base but not into this worktree's HEAD.
    probe = subprocess.run(
        ["git", "branch", "-d", "probe"],
        cwd=worktree,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode != 0, probe.stdout + probe.stderr

    result = run_script(worktree, fake_gh_env(tmp_path))

    assert "pruned (ancestry): merged-topic" in result.stdout
    assert "KEEP feature — checked out at" in result.stdout
    assert "KEEP main — base branch" in result.stdout
    assert branches(repo) == {"main", "feature"}


def test_keep_prefix_reserves_a_peer_namespace(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    run("git", "branch", "merged-topic", cwd=repo)
    run("git", "branch", "peer/merged-topic", cwd=repo)

    result = run_script(
        repo, fake_gh_env(tmp_path), "--keep-prefix", "peer/"
    )

    assert "KEEP peer/merged-topic — reserved prefix peer/" in result.stdout
    assert "pruned (ancestry): merged-topic" in result.stdout
    assert branches(repo) == {"main", "peer/merged-topic"}


def test_skipped_pass_2_surfaces_the_gh_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = fake_gh_env(
        tmp_path,
        'echo "x509: OSStatus -26276" >&2\nexit 1\n',
    )

    result = run_script(repo, env, "--dry-run")

    assert "SKIP pass 2" in result.stdout
    assert "x509: OSStatus -26276" in result.stdout
    assert "re-run unsandboxed" in result.stdout
    assert "cleanup_branches: complete" in result.stdout
