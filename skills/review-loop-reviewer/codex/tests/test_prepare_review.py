from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path


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

    def test_archive_path_traversal_is_rejected(self) -> None:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            info = tarfile.TarInfo("root/../../escape")
            payload = b"bad"
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(
                prepare_review.ReviewPreparationError, "unsafe archive"
            ):
                prepare_review.safe_extract_tar(
                    archive.getvalue(), Path(temp) / "tree", strip_first=True
                )

    def test_safe_archive_is_materialized_with_root_stripped(self) -> None:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            info = tarfile.TarInfo("root/src/app.py")
            payload = b"print('ok')\n"
            info.size = len(payload)
            info.mode = 0o644
            bundle.addfile(info, io.BytesIO(payload))
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp) / "tree"
            prepare_review.safe_extract_tar(archive.getvalue(), tree, strip_first=True)
            self.assertEqual((tree / "src" / "app.py").read_bytes(), b"print('ok')\n")


if __name__ == "__main__":
    unittest.main()
