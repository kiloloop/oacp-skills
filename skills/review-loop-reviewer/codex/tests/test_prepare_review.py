"""Exact-review fixtures use realistic formats and synthetic names and content."""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "prepare_review.py"
SPEC = importlib.util.spec_from_file_location("prepare_review", SCRIPT)
assert SPEC and SPEC.loader
prepare_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_review)


HEAD = "0123456789abcdef0123456789abcdef01234567"
MOVED = "1123456789abcdef0123456789abcdef01234567"


def metadata(head: str = HEAD, *, fork: bool = True, draft: bool = False):
    return {
        "number": 7,
        "title": "Example",
        "body": "Body",
        "isDraft": draft,
        "baseRefName": "main",
        "headRefName": "feature",
        "headRefOid": head,
        "headRepositoryOwner": {"login": "contributor" if fork else "owner"},
        "headRepository": {
            "name": "fork" if fork else "base",
            "nameWithOwner": "contributor/fork" if fork else "owner/base",
        },
    }


class PrepareReviewTests(unittest.TestCase):
    def test_normalizes_base_and_fork_head_repositories_separately(self) -> None:
        result = prepare_review.normalize_pr_metadata(
            metadata(), base_repo="owner/base"
        )
        self.assertEqual(result["base_repo"], "owner/base")
        self.assertEqual(result["head_repo"], "contributor/fork")
        self.assertEqual(result["reviewed_head"], HEAD)

    def test_expected_head_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            prepare_review.ReviewPreparationError, "expected head"
        ):
            prepare_review.normalize_pr_metadata(
                metadata(), base_repo="owner/base", expected_head=MOVED
            )

    def test_dry_run_creates_no_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "must-not-exist"
            result = prepare_review.prepare_review(
                base_repo="owner/base",
                pr=7,
                expected_head=HEAD,
                output_dir=output,
                dry_run=True,
                metadata_reader=lambda repo, pr: metadata(),
            )
            self.assertTrue(result["dry_run"])
            self.assertFalse(output.exists())

    def test_missing_head_can_be_fetched_and_retried_in_same_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            clone = root / "clone"
            source.mkdir()
            def git(repo, *args):
                return subprocess.run(["git", "-C", str(repo), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git(source, "init", "-q")
            (source / "example.txt").write_text("committed bytes\n")
            git(source, "add", "example.txt")
            git(source, "-c", "user.name=Example", "-c", "user.email=example@example.com",
                "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
            head = git(source, "rev-parse", "HEAD")
            clone.mkdir()
            git(clone, "init", "-q")
            output = root / "review"
            options = dict(
                base_repo="owner/base", pr=7, expected_head=head,
                output_dir=output, dry_run=False,
                metadata_reader=lambda repo, pr: metadata(head),
                diff_reader=lambda repo, pr: "diff --git a/example.txt b/example.txt\n",
            )
            # Discover the empty local checkout on the first attempt, then fetch.
            previous = Path.cwd()
            try:
                os.chdir(clone)
                with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "unavailable"):
                    prepare_review.prepare_review(**options)
                self.assertEqual(list(output.iterdir()), [])
                git(clone, "fetch", str(source), head)
                # The retry runs outside every checkout with an explicit source.
                os.chdir(root)
                result = prepare_review.prepare_review(**options, repo_root=clone)
            finally:
                os.chdir(previous)
            self.assertEqual(result["reviewed_head"], head)
            self.assertEqual((Path(result["tree_dir"]) / "example.txt").read_bytes(),
                             b"committed bytes\n")
            self.assertTrue(Path(result["patch_file"]).is_file())
            with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "overwrite"):
                prepare_review.prepare_review(**options, repo_root=clone)

    def test_cli_accepts_explicit_checkout(self) -> None:
        args = prepare_review._parser().parse_args([
            "--repo", "owner/base", "--pr", "7", "--repo-root", "/example/checkout",
            "--output-dir", "/example/review",
        ])
        self.assertEqual(args.repo_root, Path("/example/checkout"))

    def test_head_move_during_preparation_is_rejected(self) -> None:
        rows = iter([metadata(), metadata(MOVED)])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(
                prepare_review.ReviewPreparationError, "expected head"
            ):
                prepare_review.prepare_review(
                    base_repo="owner/base",
                    pr=7,
                    expected_head=HEAD,
                    output_dir=Path(temp) / "review",
                    dry_run=False,
                    metadata_reader=lambda repo, pr: next(rows),
                    diff_reader=lambda repo, pr: "diff --git a/a b/a\n",
                    materializer=lambda **kwargs: (
                        kwargs["destination"].mkdir() or "test"
                    ),
                )

    def test_local_exact_tree_ignores_export_filters_and_preserves_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / ".gitattributes").write_text(
                ".gitattributes export-ignore\nhidden.txt export-ignore text eol=crlf\n",
                encoding="utf-8",
            )
            (repo / "hidden.txt").write_bytes(b"must remain in the exact tree\n")
            executable = repo / "run.sh"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            (repo / "hidden-link").symlink_to("hidden.txt")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=repo,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            tree = root / "tree"
            with mock.patch.object(prepare_review.subprocess, "run", wraps=subprocess.run) as calls:
                source = prepare_review.materialize_exact_tree(
                    head=head,
                    head_repo="owner/base",
                    base_repo="owner/base",
                    destination=tree,
                    repo_root=repo,
                )
            batches = [c for c in calls.call_args_list if c.args[0][-2:] == ["cat-file", "--batch"]]
            self.assertEqual(len(batches), 1)

            self.assertEqual(source, "local_git")
            self.assertTrue((tree / ".gitattributes").is_file())
            self.assertEqual(
                (tree / "hidden.txt").read_bytes(),
                b"must remain in the exact tree\n",
            )
            self.assertTrue((tree / "run.sh").stat().st_mode & 0o111)
            self.assertTrue((tree / "hidden-link").is_symlink())
            self.assertEqual(os.readlink(tree / "hidden-link"), "hidden.txt")

            # A corrupt final batch separator must not expose a partial tree.
            real_run = subprocess.run
            def truncate_batch(command, **kwargs):
                result = real_run(command, **kwargs)
                if command[-2:] == ["cat-file", "--batch"]:
                    kwargs["stdout"].seek(-1, os.SEEK_END)
                    kwargs["stdout"].truncate()
                return result
            index_before = (repo / ".git/index").read_bytes()
            with mock.patch.object(prepare_review.subprocess, "run", side_effect=truncate_batch):
                with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "separator"):
                    prepare_review.materialize_exact_tree(
                        head=head, head_repo="owner/base", base_repo="owner/base",
                        destination=root / "bad-tree", repo_root=repo,
                    )
            self.assertFalse((root / "bad-tree").exists())
            self.assertEqual(list(root.glob(".bad-tree.*")), [])
            self.assertEqual((repo / ".git/index").read_bytes(), index_before)

    def test_missing_local_head_never_uses_archive_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "authorized Git identity"):
                prepare_review.materialize_exact_tree(
                    head=HEAD, head_repo="contributor/fork", base_repo="owner/base",
                    destination=root / "tree", repo_root=repo,
                )
            self.assertFalse((root / "tree").exists())

    def test_gitlink_is_explicitly_unsupported_without_partial_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            repo.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            commit = ["-c", "user.name=Example", "-c", "user.email=example@example.com",
                      "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "fixture"]
            git(*commit)
            base = git("rev-parse", "HEAD")
            git("update-index", "--add", "--cacheinfo", f"160000,{base},module")
            git(*commit)
            head = git("rev-parse", "HEAD")
            index_before = (repo / ".git/index").read_bytes()
            with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "gitlink.*recursive checkout"):
                prepare_review.materialize_exact_tree(
                    head=head, head_repo="owner/base", base_repo="owner/base",
                    destination=root / "tree", repo_root=repo,
                )
            self.assertFalse((root / "tree").exists())
            self.assertEqual((repo / ".git/index").read_bytes(), index_before)

    def test_batch_binary_and_empty_blobs(self) -> None:
        data = b"binary\x00\nbytes"
        batch = io.BytesIO(HEAD.encode() + b" blob " + str(len(data)).encode() + b"\n" + data
                           + b"\n" + MOVED.encode() + b" blob 0\n\n")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prepare_review._write_batch_tree(batch, [("100644", HEAD, Path("data")),
                                                       ("100755", MOVED, Path("empty"))], root)
            self.assertEqual((root / "data").read_bytes(), data)
            self.assertEqual((root / "empty").read_bytes(), b"")
            self.assertTrue((root / "empty").stat().st_mode & 0o111)

    def test_malformed_batch_records_fail_closed(self) -> None:
        oid = HEAD.encode()
        records = [b"", oid + b" missing\n", MOVED.encode() + b" blob 0\n\n",
                   oid + b" tree 0\n\n", oid + b" blob -1\n", oid + b" blob nope\n",
                   oid + b" blob 3\na", oid + b" blob 1\nax", oid + b" blob 0\n\nextra"]
        for payload in records:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(prepare_review.ReviewPreparationError):
                    prepare_review._write_batch_tree(io.BytesIO(payload),
                                                    [("100644", HEAD, Path("data"))], Path(temp))

    def test_unsafe_batch_symlinks_are_refused(self) -> None:
        for link in (b"/absolute-target", b"../outside", b""):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as temp:
                payload = HEAD.encode() + b" blob " + str(len(link)).encode() + b"\n" + link + b"\n"
                with self.assertRaisesRegex(prepare_review.ReviewPreparationError, "unsafe symlink"):
                    prepare_review._write_batch_tree(io.BytesIO(payload),
                                                    [("120000", HEAD, Path("link"))], Path(temp))

    def test_ambiguous_or_unmerged_index_entries_are_refused(self) -> None:
        row = f"100644 {HEAD} 0\tfile\0".encode()
        for payload in (row + row, f"100644 {HEAD} 1\tfile\0".encode(),
                        f"100644 {HEAD} 0\t../escape\0".encode()):
            with self.subTest(payload=payload):
                with self.assertRaises(prepare_review.ReviewPreparationError):
                    prepare_review._index_entries(payload)


if __name__ == "__main__":
    unittest.main()
