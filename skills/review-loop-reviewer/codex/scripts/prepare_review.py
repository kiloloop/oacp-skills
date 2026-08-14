#!/usr/bin/env python3
"""Capture immutable PR metadata, patch, and exact-head tree for review."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
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


def run_bytes(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(command), check=False, capture_output=True)


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


def safe_extract_tar(archive: bytes, destination: Path, *, strip_first: bool) -> None:
    if destination.exists():
        raise ReviewPreparationError(f"review tree already exists: {destination}")
    destination.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as bundle:
            members = bundle.getmembers()
            roots = {
                _safe_parts(member.name, strip_first=False)[0]
                for member in members
                if _safe_parts(member.name, strip_first=False)
            }
            if strip_first and len(roots) != 1:
                raise ReviewPreparationError(
                    "GitHub archive must have one top-level directory"
                )

            ordered = sorted(
                members, key=lambda item: (not item.isdir(), len(item.name))
            )
            for member in ordered:
                parts = _safe_parts(member.name, strip_first=strip_first)
                if not parts:
                    continue
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not _inside(destination, target.parent):
                    raise ReviewPreparationError(
                        f"archive escapes destination: {member.name}"
                    )
                if member.isdir():
                    target.mkdir(exist_ok=True)
                    continue
                if target.exists() or target.is_symlink():
                    raise ReviewPreparationError(
                        f"duplicate archive path: {member.name}"
                    )
                if member.issym():
                    link = PurePosixPath(member.linkname)
                    if link.is_absolute() or ".." in link.parts:
                        raise ReviewPreparationError(f"unsafe symlink: {member.name}")
                    link_target = target.parent.joinpath(*link.parts)
                    if not _inside(destination, link_target):
                        raise ReviewPreparationError(
                            f"symlink escapes destination: {member.name}"
                        )
                    target.symlink_to(member.linkname)
                    continue
                if not (member.isfile() or member.islnk()):
                    raise ReviewPreparationError(
                        f"unsupported archive member: {member.name}"
                    )
                source = bundle.extractfile(member)
                if source is None:
                    raise ReviewPreparationError(
                        f"archive member has no content: {member.name}"
                    )
                descriptor = os.open(
                    target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(descriptor, "wb") as handle:
                    shutil.copyfileobj(source, handle)
                os.chmod(target, member.mode & 0o777)
    except Exception:
        # Leave the bounded temp evidence in place for diagnosis; callers choose cleanup.
        raise


def materialize_exact_tree(
    *,
    head: str,
    head_repo: str,
    base_repo: str,
    destination: Path,
    text_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = run_text,
    bytes_runner: Callable[
        [Sequence[str]], subprocess.CompletedProcess[bytes]
    ] = run_bytes,
) -> str:
    exists = text_runner(["git", "cat-file", "-e", f"{head}^{{commit}}"])
    if exists.returncode == 0:
        archived = bytes_runner(["git", "archive", "--format=tar", head])
        if archived.returncode == 0:
            safe_extract_tar(archived.stdout, destination, strip_first=False)
            return "local_git"

    for repo in dict.fromkeys([head_repo, base_repo]):
        archived = bytes_runner(["gh", "api", f"repos/{repo}/tarball/{head}"])
        if archived.returncode == 0:
            safe_extract_tar(archived.stdout, destination, strip_first=True)
            return f"github:{repo}"
    raise ReviewPreparationError(
        "unable to materialize exact head from local Git or GitHub"
    )


def prepare_review(
    *,
    base_repo: str,
    pr: int,
    expected_head: str | None,
    output_dir: Path | None,
    dry_run: bool,
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
    patch_path.write_text(patch, encoding="utf-8")
    source = materializer(
        head=first["reviewed_head"],
        head_repo=first["head_repo"],
        base_repo=first["base_repo"],
        destination=tree_dir,
    )
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
        )
    except ReviewPreparationError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": "ready", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
