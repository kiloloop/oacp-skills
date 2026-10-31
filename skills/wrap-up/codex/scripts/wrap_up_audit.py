#!/usr/bin/env python3
"""Read-only audit helpers for the wrap-up skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd)


def git_stdout(cwd: Path, *args: str) -> str:
    proc = git(cwd, *args)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def repo_root(path: Path) -> Path:
    proc = git(path, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"not a git repo: {path}")
    return Path(proc.stdout.strip()).resolve()


def git_common_dir(path: Path) -> Path | None:
    proc = git(path, "rev-parse", "--git-common-dir")
    if proc.returncode != 0:
        return None
    common_dir = Path(proc.stdout.strip()).expanduser()
    if not common_dir.is_absolute():
        common_dir = path / common_dir
    return common_dir.resolve()


def current_worktree_for_target(root: Path, cwd: Path) -> Path:
    """Return the current target worktree, conservatively defaulting to root."""
    try:
        candidate = repo_root(cwd)
    except RuntimeError:
        return root
    if git_common_dir(candidate) != git_common_dir(root):
        return root
    return candidate


def default_workspace_root(root: Path) -> Path:
    configured = os.environ.get("WORKSPACE_ROOT")
    return Path(configured).expanduser() if configured else root.parent


def detect_base_branch(root: Path) -> str:
    ref = git_stdout(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if ref.startswith("origin/"):
        return ref.split("/", 1)[1]
    return "main"


def merged_branches(root: Path, base_branch: str) -> list[str]:
    proc = git(root, "branch", "--format=%(refname:short)", "--merged", base_branch)
    if proc.returncode != 0:
        return []
    branches: list[str] = []
    for line in proc.stdout.splitlines():
        branch = line.strip()
        if not branch:
            continue
        branch = branch.lstrip("*+").strip()
        if branch and branch != base_branch:
            branches.append(branch)
    return branches


def github_repo(root: Path) -> str | None:
    try:
        proc = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=root)
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    repo = proc.stdout.strip()
    return repo or None


def local_branch_worktree_paths(root: Path) -> dict[str, str]:
    proc = git(root, "for-each-ref", "--format=%(refname:short) %(worktreepath)", "refs/heads/")
    if proc.returncode != 0:
        return {}
    branches: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        branch, _, worktree_path = line.partition(" ")
        branches[branch] = worktree_path.strip()
    return branches


def pr_state_for_branch(
    root: Path, repo: str, branch: str, local_tip: str,
) -> dict[str, Any]:
    """Read merged same-repository PR evidence, never a branch-name-only verdict."""
    result: dict[str, Any] = {
        "pr_state": None, "pr_head_oid": None, "pr_repo_matches": False,
        "reason": "pr_lookup_failed",
    }
    try:
        proc = run([
            "gh", "pr", "list", "--repo", repo, "--head", branch,
            "--state", "merged", "--limit", "100", "--json",
            "state,headRefOid,headRefName,headRepository,isCrossRepository",
        ], cwd=root)
    except FileNotFoundError:
        return result
    if proc.returncode != 0:
        return result
    try:
        rows = json.loads(proc.stdout)
    except (TypeError, ValueError):
        return result
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return result
    matches = [
        row for row in rows
        if row.get("state") == "MERGED"
        and row.get("headRefName") == branch
        and row.get("isCrossRepository") is False
        and isinstance(row.get("headRepository"), dict)
        and str(row["headRepository"].get("nameWithOwner", "")).lower() == repo.lower()
        and isinstance(row.get("headRefOid"), str)
        and row["headRefOid"]
    ]
    if not matches:
        result["reason"] = "pr_identity_mismatch" if rows else "not_confirmed_merged"
        return result
    match = next((row for row in matches if row["headRefOid"] == local_tip), matches[0])
    return {
        "pr_state": "MERGED", "pr_head_oid": match["headRefOid"],
        "pr_repo_matches": True,
        "reason": None if match["headRefOid"] == local_tip else "local_tip_diverged",
    }


def squash_head_matches(evidence: dict[str, Any], local_tip: str) -> bool:
    return bool(
        local_tip and evidence.get("pr_state") == "MERGED"
        and evidence.get("pr_repo_matches") is True
        and local_tip == evidence.get("pr_head_oid")
    )


def kept_by_prefix(branch: str, prefixes: set[str]) -> bool:
    return any(branch.startswith(prefix) for prefix in prefixes)


def github_auth_mode(args: argparse.Namespace) -> str | None:
    """Return the explicitly authorized gh mode, if any.

    Token environment variables are treated as caller-supplied credentials.
    Ambient gh auth is disabled unless the caller opts in after applying the
    repository's identity policy.
    """
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return "explicit_token_env"
    if getattr(args, "allow_ambient_gh", False):
        return "ambient_opt_in"
    return None


def branch_pr_states(
    root: Path,
    base_branch: str,
    *,
    keep_branches: set[str] | None = None,
    keep_worktrees: set[Path] | None = None,
    keep_branch_prefixes: set[str] | None = None,
    owned_branches: set[str] | None = None,
    owned_worktrees: set[Path] | None = None,
    current_worktree: Path | None = None,
    github_auth: str | None = None,
) -> dict[str, Any]:
    keep_branches = keep_branches or set()
    keep_worktrees = keep_worktrees or set()
    keep_branch_prefixes = keep_branch_prefixes or set()
    owned_branches = owned_branches or set()
    owned_worktrees = owned_worktrees or set()
    current_worktree = current_worktree.resolve() if current_worktree else None
    if github_auth is None:
        return {"status": "skipped", "reason": "github_auth_not_explicit", "candidates": []}
    repo = github_repo(root)
    if not repo:
        return {"status": "skipped", "reason": "gh_repo_unavailable", "candidates": []}
    merged = set(merged_branches(root, base_branch))
    candidates: list[dict[str, Any]] = []
    for branch, worktree_path in sorted(local_branch_worktree_paths(root).items()):
        if branch == base_branch:
            continue
        path = Path(worktree_path).resolve() if worktree_path else None
        row: dict[str, Any] = {
            "branch": branch, "worktree_path": str(path) if path else None,
            "pr_state": None, "pr_head_oid": None, "pr_repo_matches": False,
            "local_tip": git_stdout(root, "rev-parse", "--verify", f"refs/heads/{branch}"),
        }
        worktree_status = status_lines(path) if path else []
        if branch in keep_branches or kept_by_prefix(branch, keep_branch_prefixes):
            recommendation = "keep_persistent_policy_branch"
        elif path and path == current_worktree:
            recommendation = "keep_current_worktree_branch"
        elif path and path in keep_worktrees:
            recommendation = "keep_persistent_policy_worktree_branch"
        elif branch not in owned_branches or (path and path not in owned_worktrees):
            recommendation = "keep_ownership_unverified"
        elif path and worktree_status is None:
            recommendation = "keep_status_unknown"
        elif path and worktree_status:
            recommendation = "keep_dirty_worktree_branch"
        elif not row["local_tip"]:
            recommendation = "keep_local_tip_unknown"
        elif branch in merged:
            recommendation = (
                "remove_worktree_before_safe_delete" if path else "safe_delete_branch"
            )
        else:
            row.update(pr_state_for_branch(root, repo, branch, row["local_tip"]))
            if squash_head_matches(row, row["local_tip"]):
                recommendation = (
                    "remove_worktree_before_force_delete_with_user_approval"
                    if path else "force_delete_with_user_approval"
                )
            else:
                recommendation = "keep_" + (row.get("reason") or "not_confirmed_merged")
        row["recommendation"] = recommendation
        candidates.append(row)
    return {"status": "ok", "auth_mode": github_auth, "repo": repo, "candidates": candidates}


def parse_worktrees(root: Path) -> list[dict[str, str]]:
    proc = git(root, "worktree", "list", "--porcelain")
    if proc.returncode != 0:
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        if " " in line:
            key, value = line.split(" ", 1)
        else:
            key, value = line, ""
        current[key] = value
    if current:
        entries.append(current)
    return entries


def status_lines(path: Path) -> list[str] | None:
    try:
        proc = git(path, "status", "--porcelain")
    except OSError:
        # A registered worktree can disappear or become unreadable before audit.
        return None
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line]


def branch_from_entry(entry: dict[str, str]) -> str:
    branch = entry.get("branch", "")
    prefix = "refs/heads/"
    if branch.startswith(prefix):
        return branch[len(prefix) :]
    return branch


def has_remote_tracking_ref(root: Path, branch: str) -> bool:
    if not branch:
        return False
    proc = git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
    return proc.returncode == 0


def classify_worktrees(
    root: Path,
    base_branch: str,
    current_root: Path,
    *,
    keep_branches: set[str] | None = None,
    keep_worktrees: set[Path] | None = None,
    keep_branch_prefixes: set[str] | None = None,
    owned_branches: set[str] | None = None,
    owned_worktrees: set[Path] | None = None,
    branch_evidence: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    keep_branches = keep_branches or set()
    keep_worktrees = keep_worktrees or set()
    keep_branch_prefixes = keep_branch_prefixes or set()
    owned_branches = owned_branches or set()
    owned_worktrees = owned_worktrees or set()
    branch_evidence = branch_evidence or {}
    merged = set(merged_branches(root, base_branch))
    repo_worktrees = (root / ".worktrees").resolve()
    codex_runtime_root = (Path.home() / ".codex" / "worktrees").resolve()
    out: list[dict[str, Any]] = []
    for entry in parse_worktrees(root):
        path = Path(entry.get("worktree", "")).expanduser().resolve()
        branch = branch_from_entry(entry)
        worktree_status = status_lines(path)
        under_repo_worktrees = path == repo_worktrees or repo_worktrees in path.parents
        under_codex_runtime = path == codex_runtime_root or codex_runtime_root in path.parents
        is_current = path == current_root
        protected = (
            branch == base_branch or branch in keep_branches or path in keep_worktrees
            or kept_by_prefix(branch, keep_branch_prefixes)
        )
        owned = path in owned_worktrees and branch in owned_branches
        evidence = branch_evidence.get(branch, {})
        local_tip = git_stdout(root, "rev-parse", "--verify", f"refs/heads/{branch}") if branch else ""
        if is_current:
            recommendation = "keep_current_worktree"
        elif protected:
            recommendation = "keep_persistent_policy_worktree"
        elif under_codex_runtime:
            recommendation = "report_detached_runtime_worktree"
        elif not branch or not owned:
            recommendation = "keep_ownership_unverified"
        elif worktree_status is None:
            recommendation = "keep_status_unknown"
        elif worktree_status:
            recommendation = "keep_dirty_worktree"
        elif not local_tip:
            recommendation = "keep_local_tip_unknown"
        elif branch in merged:
            recommendation = "remove_worktree_then_safe_delete_branch"
        elif squash_head_matches(evidence, local_tip):
            recommendation = "remove_worktree_then_force_delete_branch_with_user_approval"
        elif evidence.get("reason"):
            recommendation = "keep_" + evidence["reason"]
        else:
            recommendation = "keep_unmerged_worktree"
        out.append({
            "path": str(path), "branch": branch or None, "detached": not bool(branch),
            "current": is_current, "repo_local_worktree": under_repo_worktrees,
            "codex_runtime_worktree": under_codex_runtime,
            "protected_by_policy": protected, "session_owned": owned,
            "status_known": worktree_status is not None,
            "prunable": "prunable" in entry,
            "dirty": bool(worktree_status) if worktree_status is not None else None,
            "status": worktree_status, "local_tip": local_tip or None,
            "merged_into_base": branch in merged if branch else False,
            "pr_state": evidence.get("pr_state"), "pr_head_oid": evidence.get("pr_head_oid"),
            "pr_repo_matches": evidence.get("pr_repo_matches", False),
            "recommendation": recommendation,
        })
    return out


def project_from_marker(root: Path, marker: str) -> dict[str, str] | None:
    marker_path = root / marker
    if not (marker_path.is_file() or marker_path.is_symlink()):
        return None
    try:
        resolved = marker_path.resolve() if marker_path.is_symlink() else marker_path
        with resolved.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001 - report malformed local markers without failing wrap-up
        return {"marker": marker, "path": str(marker_path), "error": str(exc)}
    project = data.get("project_name") or data.get("project")
    if not project:
        return {"marker": marker, "path": str(marker_path), "error": "missing project_name"}
    return {"marker": marker, "path": str(marker_path), "project": str(project)}


def resolve_project(root: Path) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    for marker in (".oacp", "workspace.json"):
        result = project_from_marker(root, marker)
        if not result:
            continue
        if "project" in result:
            return result
        errors.append(result)
    return {"project": None, "errors": errors}


def resolve_oacp_root(workspace_root: Path) -> Path:
    # The inbox home is separate from agent-memory bindings. No workspace-name guess.
    return Path(os.environ.get("OACP_HOME") or "~/oacp").expanduser().resolve()


def resolve_memory_home(root: Path, explicit: str | None = None) -> Path:
    """Match agent-memory's explicit/env/binding/marker/default precedence."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    for name in ("AGENT_MEMORY_HOME", "OACP_HOME"):
        if os.environ.get(name):
            return Path(os.environ[name]).expanduser().resolve()
    directories = [root, *root.parents]
    for directory in directories:
        binding = directory / ".agent-memory.json"
        try:
            binding.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError(f"cannot inspect memory binding: {binding}: {exc}") from exc
        try:
            data = json.loads(binding.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"unreadable memory binding: {binding}: {exc}") from exc
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError(f"invalid memory binding schema: {binding}")
        home = data.get("home")
        project = data.get("project")
        if not isinstance(home, str) or not home or (
            project is not None and (not isinstance(project, str) or not project)
        ):
            raise ValueError(f"invalid memory binding home/project: {binding}")
        path = Path(home).expanduser()
        return (path if path.is_absolute() else binding.parent / path).resolve()
    for directory in directories:
        try:
            candidates = [directory / "workspace.json"] + [
                item for item in directory.iterdir()
                if item.name != "workspace.json" and item.is_symlink()
            ]
        except OSError:
            continue
        for marker in candidates:
            try:
                target = marker.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if (target.name == "workspace.json" and target.is_file()
                    and target.parent.parent.name == "projects"):
                return target.parent.parent.parent
    return (Path.home() / "agent-memory").resolve()


def inbox_status(project: str | None, oacp_root: Path) -> dict[str, Any]:
    if not project:
        return {"status": "skipped", "reason": "project_not_resolved"}
    try:
        proc = run(["oacp", "inbox", project, "--agent", "codex", "--oacp-dir", str(oacp_root), "--json"])
    except FileNotFoundError:
        return {"status": "skipped", "reason": "oacp_not_found"}
    if proc.returncode != 0:
        return {"status": "skipped", "reason": "oacp_inbox_failed", "stderr": proc.stderr.strip()}
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "failed", "reason": "invalid_json", "error": str(exc)}
    pending: list[str] = []
    inbox_path = ""
    for agent in report.get("agents", []):
        inbox_path = inbox_path or str(agent.get("inbox_path", ""))
        for message in agent.get("messages", []):
            path = str(message.get("path", "")).strip()
            if path.endswith(".yaml"):
                pending.append(path)
    return {
        "status": "pending" if pending else "clean",
        "inbox_path": inbox_path,
        "pending_yaml": pending,
    }


def memory_status(oacp_root: Path) -> dict[str, Any]:
    enabled = (oacp_root / ".oacp-memory-repo").is_file()
    head = git_stdout(oacp_root, "rev-parse", "--short", "HEAD") if enabled else ""
    dirty = status_lines(oacp_root) if enabled else []
    return {
        "root": str(oacp_root),
        "enabled": enabled,
        "head": head or None,
        "dirty": dirty,
    }


PID_PATTERN = re.compile(r"\bpid\b[^0-9]*(\d+)|^(\d+)$", re.IGNORECASE)


def read_lock_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        match = PID_PATTERN.search(line.strip())
        if match:
            raw = match.group(1) or match.group(2)
            try:
                return int(raw)
            except ValueError:
                return None
    return None


def pid_active(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def classify_repo_changes(root: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    lines = status_lines(root)
    if lines is None:
        return {"candidates": [], "excluded_ephemeral": [], "effective_state": "status_unknown"}
    for line in lines:
        path_text = line[3:] if len(line) > 3 else line.strip()
        path = root / path_text
        reason = ""
        detail: dict[str, Any] = {}

        if path_text == ".claude/settings.local.json":
            reason = "local permissions/settings"
        elif path_text.endswith("settings.local.json"):
            reason = "local settings file"
        elif path_text == ".claude/scheduled_tasks.lock":
            pid = read_lock_pid(path)
            detail["pid"] = pid
            detail["pid_active"] = pid_active(pid) if pid else False
            if pid and detail["pid_active"]:
                reason = "live scheduled task lockfile"
            else:
                reason = "stale scheduled task lockfile"

        item = {"status": line[:2], "path": path_text, **detail}
        if reason:
            excluded.append({**item, "reason": reason})
        else:
            candidates.append(item)
    return {
        "candidates": candidates,
        "excluded_ephemeral": excluded,
        "effective_state": "no_changes" if not candidates else "has_candidate_changes",
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(Path(args.repo).expanduser().resolve())
    current_root = current_worktree_for_target(root, Path.cwd())
    workspace_root = Path(args.workspace_root).expanduser().resolve() if args.workspace_root else default_workspace_root(root)
    base_branch = detect_base_branch(root)
    project = resolve_project(root)
    oacp_root = resolve_oacp_root(workspace_root)
    keep_branches = {branch.strip() for branch in getattr(args, "keep_branch", []) if branch.strip()}
    keep_worktrees: set[Path] = set()
    for raw_path in getattr(args, "keep_worktree", []):
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = root / path
        keep_worktrees.add(path.resolve())
    keep_prefixes = set(getattr(args, "keep_branch_prefix", []))
    owned_branches = set(getattr(args, "owned_branch", []))
    owned_worktrees = {
        (Path(value) if Path(value).is_absolute() else root / value).resolve()
        for value in getattr(args, "owned_worktree", [])
    }
    merged = merged_branches(root, base_branch)
    branch_states = branch_pr_states(
        root,
        base_branch,
        keep_branches=keep_branches,
        keep_worktrees=keep_worktrees,
        keep_branch_prefixes=keep_prefixes, owned_branches=owned_branches,
        owned_worktrees=owned_worktrees, current_worktree=current_root,
        github_auth=github_auth_mode(args),
    )
    branch_evidence = {item["branch"]: item for item in branch_states.get("candidates", [])}
    memory_opt_out = root / ".no-org-memory"
    if memory_opt_out.exists() or memory_opt_out.is_symlink():
        memory = {
            "status": "skipped",
            "reason": "project_opt_out",
            "marker": str(memory_opt_out),
            "root": None,
            "enabled": False,
            "head": None,
            "dirty": [],
        }
    else:
        try:
            memory = memory_status(resolve_memory_home(root, getattr(args, "memory_home", None)))
        except ValueError as exc:
            memory = {"status": "failed", "reason": "memory_home_unresolved",
                      "error": str(exc), "root": None, "enabled": False,
                      "head": None, "dirty": None}

    return {
        "repo": str(root),
        "current_worktree": str(current_root),
        "base_branch": base_branch,
        "merged_branches": [branch for branch in merged if branch not in keep_branches],
        "protected_cleanup": {
            "branches": sorted(keep_branches),
            "worktrees": sorted(str(path) for path in keep_worktrees),
            "branch_prefixes": sorted(keep_prefixes),
        },
        "session_owned": {
            "branches": sorted(owned_branches),
            "worktrees": sorted(str(path) for path in owned_worktrees),
        },
        "branch_pr_states": branch_states,
        "worktrees": classify_worktrees(
            root,
            base_branch,
            current_root,
            keep_branches=keep_branches,
            keep_worktrees=keep_worktrees,
            keep_branch_prefixes=keep_prefixes, owned_branches=owned_branches,
            owned_worktrees=owned_worktrees, branch_evidence=branch_evidence,
        ),
        "project": project,
        "inbox": inbox_status(project.get("project"), oacp_root),
        "memory": memory,
        "repo_changes": classify_repo_changes(root),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit helper for the wrap-up skill.")
    parser.add_argument("--repo", default=".", help="Repository path to audit.")
    parser.add_argument("--workspace-root", help="Workspace location for audit context; never selects memory home.")
    parser.add_argument("--memory-home", help="Explicit agent-memory home; overrides environment and bindings.")
    parser.add_argument(
        "--keep-branch",
        action="append",
        default=[],
        help="Persistent branch to exclude from cleanup recommendations; repeat as needed.",
    )
    parser.add_argument(
        "--keep-worktree",
        action="append",
        default=[],
        help="Persistent worktree to exclude from cleanup recommendations; repeat as needed.",
    )
    parser.add_argument(
        "--allow-ambient-gh",
        action="store_true",
        help=(
            "Allow PR-state queries through the current ambient gh identity. "
            "Use only after the repository policy explicitly permits it."
        ),
    )
    parser.add_argument("--keep-branch-prefix", action="append", default=[],
                        help="Reserved peer namespace; repeat as needed.")
    parser.add_argument("--owned-branch", action="append", default=[],
                        help="Exact branch this session created, established from creation evidence.")
    parser.add_argument("--owned-worktree", action="append", default=[],
                        help="Exact worktree this session created, established from creation evidence.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    try:
        result = audit(args)
    except Exception as exc:  # noqa: BLE001 - CLI should report local audit blockers cleanly
        print(f"wrap_up_audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Repo: {result['repo']}")
        print(f"Base branch: {result['base_branch']}")
        print(f"Merged branches: {len(result['merged_branches'])}")
        branch_pr_states = result.get("branch_pr_states") or {}
        squash_candidates = [
            item
            for item in branch_pr_states.get("candidates", [])
            if item.get("recommendation")
            in {
                "force_delete_with_user_approval",
                "remove_worktree_before_force_delete_with_user_approval",
            }
        ]
        print(f"Squash-merged branch candidates: {len(squash_candidates)}")
        print(f"Worktrees: {len(result['worktrees'])}")
        print(f"Inbox: {result['inbox']['status']}")
        print(f"Memory enabled: {result['memory']['enabled']}")
        if result["memory"].get("reason"):
            print(f"Memory skip reason: {result['memory']['reason']}")
        print(f"Repo changes: {result['repo_changes']['effective_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
