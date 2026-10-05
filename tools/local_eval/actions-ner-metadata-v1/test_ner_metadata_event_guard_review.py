"""Offline G/H event fixtures. No GitHub calls, checkout, or real git commands."""

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch


PATH = pathlib.Path(__file__).with_name("ner_metadata_event_guard_review.py")
SPEC = importlib.util.spec_from_file_location("metadata_guard_review", PATH)
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


def fixtures():
    before, after = "1" * 40, "2" * 40
    env = {"LUNA_SOURCE_COMMIT": before, "GITHUB_SHA": after,
           "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
           "GITHUB_REPOSITORY": G.REPOSITORY, "GITHUB_REF": "refs/heads/" + G.BRANCH,
           "GITHUB_RUN_ATTEMPT": "1", "RUNNER_ENVIRONMENT": "github-hosted",
           "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "GITHUB_RUN_ID": "123",
           "GITHUB_WORKFLOW_REF": G.REPOSITORY + "/" + G.WORKFLOW + "@refs/heads/" + G.BRANCH,
           "GITHUB_WORKFLOW_SHA": after, "LUNA_MANIFEST_SHA": "3" * 64,
           "ImageOS": "ubuntu24", "ImageVersion": "20261005.1.0",
           "GITHUB_EVENT_PATH": "/offline-fixture/event.json"}
    event = {"repository": {"full_name": G.REPOSITORY, "private": False},
             "ref": env["GITHUB_REF"], "before": before, "after": after,
             "created": False, "deleted": False, "forced": False,
             "head_commit": {"id": after}}
    return event, env


class EventGuardReviewTests(unittest.TestCase):
    def setUp(self):
        self.socket_patch = patch("socket.socket", side_effect=AssertionError("offline event fixtures only"))
        self.process_patch = patch("subprocess.check_output", side_effect=AssertionError("real git is forbidden"))
        self.socket_patch.start()
        self.process_patch.start()

    def tearDown(self):
        self.process_patch.stop()
        self.socket_patch.stop()

    def test_disabled_main_cannot_read_event_or_run_git(self):
        with patch.object(G, "SOURCE_ONLY", True), patch.object(G, "guard") as guard, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(G.main(), 2)
            guard.assert_not_called()

    def test_exact_public_push_fixture_is_accepted(self):
        event, env = fixtures()
        result = G.validate_event(event, env)
        self.assertEqual(result["source_commit"], env["LUNA_SOURCE_COMMIT"])
        self.assertEqual(result["trigger_commit"], env["GITHUB_SHA"])

    def test_wrong_environment_or_attempt_is_rejected(self):
        changes = {"GITHUB_REPOSITORY": "other/repo", "GITHUB_REF": "refs/heads/main",
                   "GITHUB_RUN_ATTEMPT": "2", "GITHUB_EVENT_NAME": "workflow_dispatch",
                   "GITHUB_WORKFLOW_SHA": "4" * 40, "RUNNER_ENVIRONMENT": "self-hosted",
                   "RUNNER_OS": "Windows", "RUNNER_ARCH": "ARM64", "GITHUB_ACTIONS": "false"}
        for key, value in changes.items():
            with self.subTest(key=key):
                event, env = fixtures()
                env[key] = value
                with self.assertRaises(RuntimeError):
                    G.validate_event(event, env)

    def test_private_forced_created_deleted_and_wrong_before_rejected(self):
        for field in ("private", "created", "deleted", "forced", "before", "after", "head_commit"):
            with self.subTest(field=field):
                event, env = fixtures()
                if field == "private":
                    event["repository"]["private"] = True
                elif field in ("created", "deleted", "forced"):
                    event[field] = True
                elif field == "head_commit":
                    event[field]["id"] = "4" * 40
                else:
                    event[field] = "4" * 40
                with self.assertRaises(RuntimeError):
                    G.validate_event(event, env)

    def test_workflow_only_single_parent_clean_tree(self):
        event, env = fixtures()
        files = {G.SOURCE_DIR + "/collector.py": {"sha256": "4" * 64, "bytes": 1}}
        expected = {("rev-parse", "HEAD"): env["GITHUB_SHA"],
                    ("show", "-s", "--format=%P", "HEAD"): env["LUNA_SOURCE_COMMIT"],
                    ("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"): G.WORKFLOW,
                    ("status", "--porcelain", "--untracked-files=all"): "",
                    ("ls-tree", "-r", "--name-only", "HEAD", "--", G.SOURCE_DIR):
                        "\n".join(list(files) + [G.SOURCE_DIR + "/SOURCE_MANIFEST.json"])}
        def fake_git(*args):
            return expected[args]
        with patch.object(G, "read_json", return_value=event), patch.object(G, "git", side_effect=fake_git), patch.object(G, "verify_sources", return_value={"files": files}):
            self.assertEqual(G.guard(env)["source_commit"], env["LUNA_SOURCE_COMMIT"])
            expected[("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")] += "\nextra-file"
            with self.assertRaises(RuntimeError):
                G.guard(env)
            expected[("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")] = G.WORKFLOW
            expected[("show", "-s", "--format=%P", "HEAD")] += " " + "5" * 40
            with self.assertRaises(RuntimeError):
                G.guard(env)

    def test_source_manifest_hash_and_file_hash_are_required(self):
        with tempfile.TemporaryDirectory(prefix="metadata-guard-fake-") as temporary:
            repo = pathlib.Path(temporary).resolve()
            source = repo / G.SOURCE_DIR
            source.mkdir(parents=True)
            data = b"# inert public fixture\n"
            (source / "collector.py").write_bytes(data)
            manifest = {"protocol": G.PROTOCOL, "public_base": G.PUBLIC_BASE,
                        "files": {G.SOURCE_DIR + "/collector.py": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}}}
            path = source / "SOURCE_MANIFEST.json"
            path.write_text(json.dumps(manifest))
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(G.verify_sources(expected, repo=repo), manifest)
            with self.assertRaises(RuntimeError):
                G.verify_sources("0" * 64, repo=repo)
            (source / "collector.py").write_bytes(b"changed")
            with self.assertRaises(RuntimeError):
                G.verify_sources(expected, repo=repo)


if __name__ == "__main__":
    unittest.main()
