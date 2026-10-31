"""Realistic audit formats; all repository, agent, branch, and path names are synthetic."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "wrap_up_audit.py"
SPEC = importlib.util.spec_from_file_location("wrap_up_audit", SCRIPT)
assert SPEC and SPEC.loader
wrap_up_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrap_up_audit)
HEAD = "a" * 40
LATER = "b" * 40
REPO = "example-org/example"


def merged_pr(**changes):
    return {
        "state": "MERGED", "headRefOid": HEAD, "headRefName": "topic",
        "headRepository": {"nameWithOwner": REPO}, "isCrossRepository": False,
        **changes,
    }


class WrapUpAuditTests(unittest.TestCase):
    def branch_report(self, *, tip=HEAD, rows=None, owned=True, owned_path=True,
                      status=(), ancestry=False, prefix=False, current=False):
        root = Path("/repo")
        worktree = root / ".worktrees" / "topic"
        response = subprocess.CompletedProcess([], 0, json.dumps(
            [merged_pr()] if rows is None else rows), "")
        with (
            patch.object(wrap_up_audit, "github_repo", return_value=REPO),
            patch.object(wrap_up_audit, "local_branch_worktree_paths",
                         return_value={"topic": str(worktree)}),
            patch.object(wrap_up_audit, "git_stdout", return_value=tip),
            patch.object(wrap_up_audit, "merged_branches",
                         return_value=["topic"] if ancestry else []),
            patch.object(wrap_up_audit, "status_lines",
                         return_value=None if status is None else list(status)),
            patch.object(wrap_up_audit, "run", return_value=response) as gh,
        ):
            result = wrap_up_audit.branch_pr_states(
                root, "main", current_worktree=worktree if current else root,
                owned_branches={"topic"} if owned else set(),
                owned_worktrees={worktree} if owned_path else set(),
                keep_branch_prefixes={"top"} if prefix else set(),
                github_auth="explicit_token_env",
            )
        return result["candidates"][0], gh

    def test_branch_cleanup_closure_matrix(self):
        cases = [
            ({}, "remove_worktree_before_force_delete_with_user_approval"),
            ({"tip": LATER}, "keep_local_tip_diverged"),
            ({"rows": [merged_pr(headRepository={"nameWithOwner": "other/fork"})]},
             "keep_pr_identity_mismatch"),
            ({"rows": [merged_pr(isCrossRepository=True)]}, "keep_pr_identity_mismatch"),
            ({"rows": [merged_pr(headRepository=None)]}, "keep_pr_identity_mismatch"),
            ({"rows": [merged_pr(state="OPEN")]}, "keep_pr_identity_mismatch"),
            ({"rows": []}, "keep_not_confirmed_merged"),
            ({"tip": ""}, "keep_local_tip_unknown"),
            ({"owned": False}, "keep_ownership_unverified"),
            ({"owned_path": False}, "keep_ownership_unverified"),
            ({"status": None}, "keep_status_unknown"),
            ({"status": [" M source.py"]}, "keep_dirty_worktree_branch"),
            ({"ancestry": True}, "remove_worktree_before_safe_delete"),
            ({"prefix": True}, "keep_persistent_policy_branch"),
            ({"current": True}, "keep_current_worktree_branch"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                row, gh = self.branch_report(**args)
                self.assertEqual(row["recommendation"], expected)
                self.assertEqual(row["worktree_path"], "/repo/.worktrees/topic")
                self.assertEqual(row["local_tip"], args.get("tip", HEAD))
                if args.get("ancestry") or expected in {
                    "keep_ownership_unverified", "keep_status_unknown",
                    "keep_dirty_worktree_branch", "keep_persistent_policy_branch",
                    "keep_current_worktree_branch", "keep_local_tip_unknown",
                }:
                    gh.assert_not_called()

    def test_merged_pr_query_records_exact_identity_fields(self):
        row, gh = self.branch_report()
        self.assertEqual(row["pr_head_oid"], HEAD)
        self.assertTrue(row["pr_repo_matches"])
        argv = gh.call_args.args[0]
        self.assertEqual(argv, [
            "gh", "pr", "list", "--repo", REPO, "--head", "topic",
            "--state", "merged", "--limit", "100", "--json",
            "state,headRefOid,headRefName,headRepository,isCrossRepository",
        ])

    def test_reused_branch_finds_matching_merged_head(self):
        row, _ = self.branch_report(rows=[merged_pr(headRefOid=LATER), merged_pr()])
        self.assertEqual(row["pr_head_oid"], HEAD)
        self.assertTrue(row["recommendation"].startswith("remove_"))

    def test_pr_lookup_errors_never_become_merge_proof(self):
        for response in (
            subprocess.CompletedProcess([], 1, "", "permission denied"),
            subprocess.CompletedProcess([], 0, "not JSON", ""),
            subprocess.CompletedProcess([], 0, '{}', ""),
            subprocess.CompletedProcess([], 0, '[null]', ""),
        ):
            with self.subTest(response=response), patch.object(
                wrap_up_audit, "run", return_value=response
            ):
                evidence = wrap_up_audit.pr_state_for_branch(Path("/repo"), REPO, "topic", HEAD)
            self.assertFalse(wrap_up_audit.squash_head_matches(evidence, HEAD))

    def test_worktree_cleanup_closure_matrix(self):
        root = Path("/repo")
        worktree = root / ".worktrees" / "topic"
        cases = [
            ({}, "remove_worktree_then_force_delete_branch_with_user_approval"),
            ({"ancestry": True}, "remove_worktree_then_safe_delete_branch"),
            ({"owned": False}, "keep_ownership_unverified"),
            ({"status": None}, "keep_status_unknown"),
            ({"status": ["?? note.txt"]}, "keep_dirty_worktree"),
            ({"tip": LATER}, "keep_unmerged_worktree"),
            ({"repo_match": False}, "keep_unmerged_worktree"),
            ({"prefix": True}, "keep_persistent_policy_worktree"),
            ({"current": True}, "keep_current_worktree"),
            ({"persistent": True}, "keep_persistent_policy_worktree"),
        ]
        for config, expected in cases:
            with (
                self.subTest(config=config),
                patch.object(wrap_up_audit, "parse_worktrees", return_value=[{
                    "worktree": str(worktree), "branch": "refs/heads/topic",
                }]),
                patch.object(wrap_up_audit, "merged_branches",
                             return_value=["topic"] if config.get("ancestry") else []),
                patch.object(wrap_up_audit, "status_lines",
                             return_value=config.get("status", [])),
                patch.object(wrap_up_audit, "git_stdout", return_value=config.get("tip", HEAD)),
            ):
                rows = wrap_up_audit.classify_worktrees(
                    root, "main", worktree if config.get("current") else root,
                    owned_worktrees={worktree} if config.get("owned", True) else set(),
                    owned_branches={"topic"} if config.get("owned", True) else set(),
                    keep_worktrees={worktree} if config.get("persistent") else set(),
                    keep_branch_prefixes={"top"} if config.get("prefix") else set(),
                    branch_evidence={"topic": {
                        "pr_state": "MERGED", "pr_head_oid": HEAD,
                        "pr_repo_matches": config.get("repo_match", True),
                    }},
                )
            self.assertEqual(rows[0]["recommendation"], expected)
            self.assertEqual(rows[0]["status_known"], config.get("status", []) is not None)
            self.assertEqual(rows[0]["path"], str(worktree))

    def test_status_failure_is_unknown_through_every_consumer(self):
        with patch.object(wrap_up_audit, "git", return_value=subprocess.CompletedProcess(
            [], 1, "", "corrupt index")):
            self.assertIsNone(wrap_up_audit.status_lines(Path("/repo")))
        with patch.object(wrap_up_audit, "status_lines", return_value=None):
            self.assertEqual(wrap_up_audit.classify_repo_changes(Path("/repo"))["effective_state"],
                             "status_unknown")

    def test_missing_worktree_remains_unknown_in_worktree_and_branch_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "repo"
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            root.mkdir()
            git("init", "-b", "main")
            git("-c", "user.name=Example", "-c", "user.email=example@example.com",
                "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "fixture")
            worktree = root / ".worktrees" / "topic"
            git("worktree", "add", "-b", "topic", str(worktree))
            worktree.rename(Path(directory) / "moved-worktree")
            self.assertIsNone(wrap_up_audit.status_lines(worktree))
            rows = wrap_up_audit.classify_worktrees(
                root, "main", root, owned_branches={"topic"}, owned_worktrees={worktree},
            )
            row = next(row for row in rows if row["branch"] == "topic")
            self.assertEqual(row["recommendation"], "keep_status_unknown")
            self.assertFalse(row["status_known"])
            self.assertIsNone(row["dirty"])
            self.assertTrue(row["prunable"])
            with (
                patch.object(wrap_up_audit, "github_repo", return_value=REPO),
                patch.object(wrap_up_audit, "pr_state_for_branch") as pr_lookup,
            ):
                report = wrap_up_audit.branch_pr_states(
                    root, "main", current_worktree=root,
                    owned_branches={"topic"}, owned_worktrees={worktree},
                    github_auth="explicit_token_env",
                )
            self.assertEqual(report["candidates"][0]["recommendation"], "keep_status_unknown")
            pr_lookup.assert_not_called()

            # The published workflow passes debrief's bound home explicitly,
            # even when both ambient home variables point elsewhere.
            bound = Path(directory).resolve() / "bound"
            (root / ".agent-memory.json").write_text(json.dumps({
                "schema_version": 1, "home": "../bound", "project": "example",
            }))
            environment = dict(os.environ, GH_TOKEN="", GITHUB_TOKEN="",
                               OACP_HOME=str(root / "other-oacp"),
                               AGENT_MEMORY_HOME=str(root / "other-memory"))
            completed = subprocess.run([
                sys.executable, str(SCRIPT), "--repo", str(root), "--json",
                "--memory-home", str(bound), "--owned-branch", "topic",
                "--owned-worktree", str(worktree),
            ], cwd=root, env=environment, capture_output=True, text=True, check=True)
            snapshot = json.loads(completed.stdout)
            self.assertEqual(snapshot["memory"]["root"], str(bound))
            missing = next(row for row in snapshot["worktrees"] if row["branch"] == "topic")
            self.assertEqual(missing["recommendation"], "keep_status_unknown")
            healthy = next(row for row in snapshot["worktrees"] if row["branch"] == "main")
            self.assertEqual(healthy["recommendation"], "keep_current_worktree")

    def test_os_status_errors_are_unknown(self):
        with patch.object(wrap_up_audit, "git", side_effect=PermissionError("unreadable")):
            self.assertIsNone(wrap_up_audit.status_lines(Path("/repo")))

    def test_pr_state_pass_skips_without_explicit_github_auth(self):
        with patch.object(wrap_up_audit, "github_repo") as gh:
            result = wrap_up_audit.branch_pr_states(Path("/repo"), "main")
        self.assertEqual(result["reason"], "github_auth_not_explicit")
        gh.assert_not_called()

    def test_memory_resolution_precedence_and_relative_binding(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory) / "repo"
            child = root / "subdir"
            child.mkdir(parents=True)
            (root / ".agent-memory.json").write_text(json.dumps({
                "schema_version": 1, "home": "../bound", "project": "example",
            }))
            expected = root.parent / "bound"
            self.assertEqual(wrap_up_audit.resolve_memory_home(child), expected.resolve())
            with patch.dict(os.environ, {"OACP_HOME": str(root / "compat")}):
                self.assertEqual(wrap_up_audit.resolve_memory_home(root), (root / "compat").resolve())
                with patch.dict(os.environ, {"AGENT_MEMORY_HOME": str(root / "preferred")}):
                    self.assertEqual(wrap_up_audit.resolve_memory_home(root), (root / "preferred").resolve())
                    self.assertEqual(wrap_up_audit.resolve_memory_home(root, str(root / "explicit")),
                                     (root / "explicit").resolve())

    def test_invalid_nearest_binding_never_falls_back(self):
        for data in ("not JSON", '[]', '{"schema_version":true,"home":"store"}',
                     '{"schema_version":2,"home":"store"}',
                     '{"schema_version":1,"home":""}',
                     '{"schema_version":1,"home":"store","project":2}'):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory, (
                patch.dict(os.environ, {}, clear=True)
            ):
                root = Path(directory)
                (root / ".agent-memory.json").write_text(data)
                with self.assertRaises(ValueError):
                    wrap_up_audit.resolve_memory_home(root)

    def test_broken_binding_slots_never_fall_back(self):
        for kind in ("directory", "dangling"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory, (
                patch.dict(os.environ, {}, clear=True)
            ):
                root = Path(directory)
                binding = root / ".agent-memory.json"
                if kind == "directory":
                    binding.mkdir()
                else:
                    binding.symlink_to(root / "absent")
                with self.assertRaises(ValueError):
                    wrap_up_audit.resolve_memory_home(root)

    def test_workspace_marker_selects_home(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory) / "repo"
            root.mkdir()
            home = Path(directory) / "store"
            marker = home / "projects" / "example" / "workspace.json"
            marker.parent.mkdir(parents=True)
            marker.write_text('{}')
            (root / "workspace.json").symlink_to(marker)
            self.assertEqual(wrap_up_audit.resolve_memory_home(root), home.resolve())

    def test_project_memory_opt_out_precedes_memory_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-b", "main", str(root)],
                           check=True, capture_output=True, text=True)
            (root / ".no-org-memory").touch()
            args = argparse.Namespace(repo=str(root), workspace_root=directory)
            with patch.object(wrap_up_audit, "memory_status") as memory, (
                patch.dict(os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": ""})
            ):
                report = wrap_up_audit.audit(args)
            memory.assert_not_called()
            self.assertEqual(report["memory"]["reason"], "project_opt_out")

    def test_workspace_location_never_selects_memory_home(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(wrap_up_audit.default_workspace_root(Path("/workspace/repo")),
                             Path("/workspace"))
            self.assertEqual(wrap_up_audit.resolve_oacp_root(Path("/unused")),
                             (Path.home() / "oacp").resolve())
