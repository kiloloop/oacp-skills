#!/usr/bin/env python3
"""Capture immutable PR metadata, patch, and exact-head tree for review."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence


FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GH_FIELDS = (
    "number,title,body,isDraft,baseRefName,headRefName,headRefOid,"
    "headRepositoryOwner,headRepository"
)


class ReviewPreparationError(RuntimeError):
    pass


def _repo(value: str, label: str) -> str:
    if not REPO.fullmatch(value or ""):
        raise ReviewPreparationError(f"{label} must be owner/name")
    return value


def normalize_pr_metadata(
    payload: dict[str, Any],
    *,
    base_repo: str,
    expected_head: str | None = None,
) -> dict[str, Any]:
    base_repo = _repo(base_repo, "base repo")
    head = str(payload.get("headRefOid") or "")
    if not FULL_SHA.fullmatch(head):
        raise ReviewPreparationError("PR headRefOid must be a full 40-character SHA")
    if expected_head and head.lower() != expected_head.lower():
        raise ReviewPreparationError(
            f"PR head {head} does not match expected head {expected_head}"
        )

    head_repository = payload.get("headRepository") or {}
    head_owner = payload.get("headRepositoryOwner") or {}
    if not isinstance(head_repository, dict) or not isinstance(head_owner, dict):
        raise ReviewPreparationError("unexpected GitHub head repository metadata")
    head_repo = head_repository.get("nameWithOwner")
    if not head_repo:
        owner = head_owner.get("login") or head_owner.get("name")
        name = head_repository.get("name")
        if owner and name:
            head_repo = f"{owner}/{name}"
    if not head_repo:
        raise ReviewPreparationError(
            "head repository is unavailable; exact tree cannot be bound"
        )

    base_ref = str(payload.get("baseRefName") or "")
    head_ref = str(payload.get("headRefName") or "")
    if not base_ref or not head_ref:
        raise ReviewPreparationError("PR base/head branch metadata is incomplete")
    try:
        number = int(payload.get("number"))
    except (TypeError, ValueError) as exc:
        raise ReviewPreparationError("PR number is invalid") from exc

    return {
        "pr": number,
        "title": str(payload.get("title") or ""),
        "body": str(payload.get("body") or ""),
        "is_draft": bool(payload.get("isDraft")),
        "base_repo": base_repo,
        "head_repo": _repo(str(head_repo), "head repo"),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "reviewed_head": head.lower(),
    }


def run_text(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), check=False, capture_output=True, text=True)


def gh_metadata(
    base_repo: str,
    pr: int,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_text,
) -> dict[str, Any]:
    command = ["gh", "pr", "view", str(pr), "--repo", base_repo, "--json", GH_FIELDS]
    completed = runner(command)
    if completed.returncode != 0:
        raise ReviewPreparationError(completed.stderr.strip() or "gh pr view failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewPreparationError(f"invalid gh pr view JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewPreparationError("gh pr view JSON must be an object")
    return payload


def gh_diff(
    base_repo: str,
    pr: int,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_text,
) -> str:
    command = ["gh", "pr", "diff", str(pr), "--repo", base_repo, "--patch"]
    completed = runner(command)
    if completed.returncode != 0:
        raise ReviewPreparationError(completed.stderr.strip() or "gh pr diff failed")
    return completed.stdout


def _safe_parts(name: str, *, strip_first: bool) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ReviewPreparationError(f"unsafe archive path: {name}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if strip_first and parts:
        parts = parts[1:]
    return parts


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath(
            [str(root.resolve()), str(candidate.resolve())]
        ) == str(root.resolve())
    except ValueError:
        return False


def _git_error(completed: subprocess.CompletedProcess[bytes], fallback: str) -> str:
    return os.fsdecode(completed.stderr).strip() or fallback


def _index_entries(payload: bytes) -> list[tuple[str, str, Path]]:
    entries: list[tuple[str, str, Path]] = []
    seen: set[Path] = set()
    for record in payload.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_name = record.split(b"\t", 1)
            raw_mode, raw_oid, raw_stage = metadata.split(b" ", 2)
            mode = raw_mode.decode("ascii")
            oid = raw_oid.decode("ascii")
            stage = raw_stage.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReviewPreparationError("invalid local Git index entry") from exc
        if stage != "0":
            raise ReviewPreparationError("local Git index contains unmerged entries")
        if mode == "160000":
            raise ReviewPreparationError(
                "gitlink requires a separately verified recursive checkout; "
                "this helper cannot claim a complete submodule tree"
            )
        if mode not in {"100644", "100755", "120000"}:
            raise ReviewPreparationError(
                f"unsupported tracked mode {mode} for exact-tree materialization"
            )
        name = os.fsdecode(raw_name)
        parts = _safe_parts(name, strip_first=False)
        if not parts:
            raise ReviewPreparationError("local Git index contains an empty path")
        path = Path(*parts)
        if path in seen:
            raise ReviewPreparationError(f"duplicate local Git path: {name}")
        seen.add(path)
        entries.append((mode, oid, path))
    return entries


def _write_batch_tree(batch, entries: list[tuple[str, str, Path]], staging: Path) -> None:
    """Materialize raw cat-file records without checkout/export transformations."""
    for mode, oid, path in entries:
        header = batch.readline(1024)
        fields = header.rstrip(b"\n").split(b" ")
        if not header.endswith(b"\n") or len(fields) != 3:
            raise ReviewPreparationError("malformed or missing cat-file batch header")
        if fields[:2] != [oid.encode("ascii"), b"blob"]:
            raise ReviewPreparationError("cat-file batch object identity or type mismatch")
        try:
            size = int(fields[2])
        except ValueError as exc:
            raise ReviewPreparationError("invalid cat-file batch size") from exc
        if size < 0:
            raise ReviewPreparationError("invalid cat-file batch size")
        target = staging / path
        if not _inside(staging, target.parent):
            raise ReviewPreparationError(f"local Git path escapes destination: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "120000":
            payload = batch.read(size)
            if len(payload) != size:
                raise ReviewPreparationError("truncated cat-file batch blob")
            link_target = os.fsdecode(payload)
            link = PurePosixPath(link_target)
            if not link_target or link.is_absolute() or ".." in link.parts:
                raise ReviewPreparationError(f"unsafe symlink: {path}")
            target.symlink_to(link_target)
        else:
            remaining = size
            with target.open("xb") as output:
                while remaining:
                    chunk = batch.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ReviewPreparationError("truncated cat-file batch blob")
                    output.write(chunk)
                    remaining -= len(chunk)
            target.chmod(0o755 if mode == "100755" else 0o644)
        if batch.read(1) != b"\n":
            raise ReviewPreparationError("missing cat-file batch blob separator")
    if batch.read(1):
        raise ReviewPreparationError("unexpected extra cat-file batch records")


def _materialize_local_git_tree(
    *, head: str, repo_root: Path, destination: Path
) -> None:
    repo_root = repo_root.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ReviewPreparationError(f"review tree already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.", dir=destination.parent
    ) as temporary:
        scratch = Path(temporary)
        staging = scratch / "tree"
        staging.mkdir()
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(scratch / "index")
        git = ["git", "-C", str(repo_root)]

        read_tree = subprocess.run(
            [*git, "read-tree", head],
            check=False,
            capture_output=True,
            env=environment,
        )
        if read_tree.returncode != 0:
            raise ReviewPreparationError(_git_error(read_tree, "git read-tree failed"))
        listed = subprocess.run(
            [*git, "ls-files", "--stage", "-z"],
            check=False,
            capture_output=True,
            env=environment,
        )
        if listed.returncode != 0:
            raise ReviewPreparationError(_git_error(listed, "git ls-files failed"))
        entries = _index_entries(listed.stdout)

        # One batch process avoids per-file startup costs. Spool its output to
        # disk so a large tree does not require buffering every blob in memory.
        with (scratch / "blobs.batch").open("w+b") as batch:
            blobs = subprocess.run(
                [*git, "cat-file", "--batch"],
                input=b"".join(oid.encode("ascii") + b"\n" for _, oid, _ in entries),
                stdout=batch,
                stderr=subprocess.PIPE,
                check=False,
                env=environment,
            )
            if blobs.returncode != 0:
                raise ReviewPreparationError(_git_error(blobs, "git cat-file batch failed"))
            batch.seek(0)
            _write_batch_tree(batch, entries, staging)

        if destination.exists() or destination.is_symlink():
            raise ReviewPreparationError(f"review tree already exists: {destination}")
        staging.replace(destination)


def materialize_exact_tree(
    *,
    head: str,
    head_repo: str,
    base_repo: str,
    destination: Path,
    repo_root: Path | None = None,
    text_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_text,
) -> str:
    if repo_root is None:
        discovered = text_runner(["git", "rev-parse", "--show-toplevel"])
        repo_root = (
            Path(discovered.stdout.strip()) if discovered.returncode == 0 else None
        )
    if repo_root is not None:
        exists = text_runner(
            ["git", "-C", str(repo_root), "cat-file", "-e", f"{head}^{{commit}}"]
        )
        if exists.returncode == 0:
            _materialize_local_git_tree(
                head=head, repo_root=repo_root, destination=destination
            )
            return "local_git"

    raise ReviewPreparationError(
        "exact head is unavailable in local Git; fetch the full base/fork head "
        "using the consuming repository's authorized Git identity and retry. "
        "Archive fallback is disabled because export attributes can change it"
    )


def prepare_review(
    *,
    base_repo: str,
    pr: int,
    expected_head: str | None,
    output_dir: Path | None,
    dry_run: bool,
    repo_root: Path | None = None,
    metadata_reader: Callable[[str, int], dict[str, Any]] = gh_metadata,
    diff_reader: Callable[[str, int], str] = gh_diff,
    materializer: Callable[..., str] = materialize_exact_tree,
) -> dict[str, Any]:
    first = normalize_pr_metadata(
        metadata_reader(base_repo, pr),
        base_repo=base_repo,
        expected_head=expected_head,
    )
    if first["pr"] != pr:
        raise ReviewPreparationError(
            f"GitHub returned PR #{first['pr']} for requested #{pr}"
        )
    if dry_run:
        return {**first, "dry_run": True}
    if first["is_draft"]:
        raise ReviewPreparationError("formal OACP review requires a GitHub-ready PR")
    if output_dir is None:
        raise ReviewPreparationError(
            "--output-dir is required unless --dry-run is used"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    short = first["reviewed_head"][:12]
    patch_path = output_dir / f"pr-{pr}-{short}.patch"
    tree_dir = output_dir / f"tree-{short}"
    context_path = output_dir / f"context-{short}.json"
    for path in (patch_path, tree_dir, context_path):
        if path.exists() or path.is_symlink():
            raise ReviewPreparationError(
                f"refusing to overwrite review evidence: {path}"
            )

    patch = diff_reader(base_repo, pr)
    source = materializer(
        head=first["reviewed_head"],
        head_repo=first["head_repo"],
        base_repo=first["base_repo"],
        destination=tree_dir,
        repo_root=repo_root,
    )
    patch_path.write_text(patch, encoding="utf-8")
    second = normalize_pr_metadata(
        metadata_reader(base_repo, pr),
        base_repo=base_repo,
        expected_head=first["reviewed_head"],
    )
    context = {
        **second,
        "dry_run": False,
        "tree_source": source,
        "tree_dir": str(tree_dir),
        "patch_file": str(patch_path),
        "diff_line_count": len(patch.splitlines()),
    }
    context_path.write_text(
        json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    context["context_file"] = str(context_path)
    return context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-head")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repo-root", type=Path,
                        help="local checkout containing the exact head (default: current checkout)")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = prepare_review(
            base_repo=args.repo,
            pr=args.pr,
            expected_head=args.expected_head,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            repo_root=args.repo_root,
        )
    except ReviewPreparationError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": "ready", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
