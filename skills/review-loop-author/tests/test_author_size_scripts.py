"""Tests for the review-request sizing scripts: diff_sizes.sh and lockfile_compare.py.

Each case builds a throwaway git repository, so no network or OACP install is needed.
Run: python3 -m unittest discover -s skills/review-loop-author/tests (or pytest).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DIFF_SIZES = SCRIPTS / "diff_sizes.sh"
LOCK_COMPARE = SCRIPTS / "lockfile_compare.py"

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.invalid",
    GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.invalid",
    GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=GIT_ENV, check=True).stdout.strip()


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, files, message):
        for name, text in files.items():
            (self.repo / name).write_text(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")


class DiffSizes(Repo):
    def run_sizes(self, *args):
        return subprocess.run(["bash", str(DIFF_SIZES), *args], capture_output=True, text=True,
                              env=GIT_ENV)

    def test_prints_numstat_rows_and_shortstat_totals_against_the_merge_base(self):
        base = self.commit({"a.txt": "one\n"}, "base")
        git(self.repo, "checkout", "-q", "-b", "feature")
        head = self.commit({"a.txt": "one\ntwo\nthree\n", "b.txt": "new\n"}, "feature")
        git(self.repo, "checkout", "-q", "main")
        self.commit({"c.txt": "main moved on\n"}, "main moves")
        res = self.run_sizes(str(self.repo), "main", head)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f"numstat main...{head}", res.stdout)
        self.assertIn("2\t0\ta.txt", res.stdout)
        self.assertIn("1\t0\tb.txt", res.stdout)
        self.assertNotIn("c.txt", res.stdout, "three-dot range measures from the branch point")
        self.assertIn("2 files changed, 3 insertions(+)", res.stdout)
        self.assertNotEqual(base, head)

    def test_usage_error(self):
        res = self.run_sizes(str(self.repo), "main")
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_bad_ref_returns_gits_exit(self):
        self.commit({"a.txt": "one\n"}, "base")
        res = self.run_sizes(str(self.repo), "main", "no-such-ref")
        self.assertNotEqual(res.returncode, 0)


class LockfileCompare(Repo):
    def lock(self, packages):
        body = {"name": "demo", "lockfileVersion": 3, "packages": {"": {"name": "demo"}}}
        for name, version in packages.items():
            body["packages"][f"node_modules/{name}"] = {"version": version}
        return json.dumps(body, indent=2) + "\n"

    def test_counts_removed_added_and_version_changed_names(self):
        base = self.commit({"package-lock.json": self.lock({"left-pad": "1.0.0", "kept": "2.0.0"})}, "base")
        head = self.commit({"package-lock.json": self.lock({"kept": "2.1.0", "fresh": "0.1.0"})}, "head")
        res = subprocess.run(["python3", str(LOCK_COMPARE), "--repo", str(self.repo), "--base", base,
                              "--head", head, "--path", "package-lock.json"],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("2 -> 2 entries", res.stdout)
        self.assertIn("names removed 1: left-pad", res.stdout)
        self.assertIn("names added 1: fresh", res.stdout)
        self.assertIn("names version-changed 1", res.stdout)
        self.assertIn("  kept: 2.0.0 -> 2.1.0", res.stdout)

    def test_unknown_lockfile_format_exits_1(self):
        ref = self.commit({"Gemfile.lock": "GEM\n"}, "base")
        res = subprocess.run(["python3", str(LOCK_COMPARE), "--repo", str(self.repo), "--base", ref,
                              "--head", ref, "--path", "Gemfile.lock"],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("unknown lockfile format", res.stderr)


SKILL_MD = Path(__file__).resolve().parents[1] / "SKILL.md"


def documented_recount():
    """The dispatched-task recount command exactly as SKILL.md documents it, comment stripped."""
    lines = [line for line in SKILL_MD.read_text().splitlines()
             if line.startswith('git -C "$REPO_PATH" diff --name-only <base>...HEAD')]
    assert len(lines) == 1, lines
    return lines[0].split("#", 1)[0].strip()


class RecountTiming(Repo):
    """The documented recount runs after the commit: a newly added fix file is counted."""

    def recount(self, base):
        cmd = documented_recount().replace("<base>", base)
        res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                             env=dict(GIT_ENV, REPO_PATH=str(self.repo)))
        self.assertEqual(res.returncode, 0, res.stderr)
        return int(res.stdout.strip())

    def test_counts_a_new_fix_file_once_committed(self):
        base = self.commit({"a.txt": "one\n"}, "base")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit({"a.txt": "one\ntwo\n"}, "round 1")
        (self.repo / "fix.txt").write_text("fix\n")
        git(self.repo, "add", "fix.txt")
        self.assertEqual(self.recount(base), 1, "before the commit the range cannot see fix.txt")
        git(self.repo, "commit", "-q", "-m", "round 2 fix")
        self.assertEqual(self.recount(base), 2)


if __name__ == "__main__":
    unittest.main()
