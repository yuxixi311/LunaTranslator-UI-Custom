import ast
import copy
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import harness as h

ROOT = Path(__file__).parent


def manifest():
    return {"target": "cp312-win_amd64", "closure_reviewed": True,
            "closure_review_sha256": "a" * 64,
            "wheels": [dict(name=name, version="1.0", license="Apache-2.0",
                            filename=name + "-1.0-py3-none-any.whl",
                            url="https://files.pythonhosted.org/" + name + "-1.0-py3-none-any.whl",
                            sha256="b" * 64, bytes=100,
                            target_compatible_reviewed=True, requires=[])
                       for name in sorted(h.REQUIRED_PACKAGES)]}


def simulate(samples=None, process=None, setup_elapsed=0):
    clock = h.FakeClock()
    resources = h.FakeResources(samples or [h.Sample(5 * h.GIB, h.GIB)])
    process = process or h.FakeProcess()
    return h.simulate_probe(clock, resources, process, setup_elapsed), process


class ManifestTests(unittest.TestCase):
    def test_complete_looking_manifest_is_still_disabled(self):
        value = manifest()
        self.assertEqual(h.validate_manifest(value), [])
        for mode in ("plan", "setup-and-cpu", "cpu-only", "cuda", None):
            result = h.plan(value, mode)
            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["cuda_enabled"])
            self.assertIn("execution_disabled", result["blockers"])

    def test_unknown_metadata_stays_blocked(self):
        for field in ("version", "license", "filename", "url", "sha256", "bytes", "requires", "target_compatible_reviewed"):
            value = manifest()
            value["wheels"][0][field] = None
            self.assertTrue(h.validate_manifest(value), field)

    def test_incomplete_actual_manifest(self):
        value = json.loads((ROOT / "wheel_manifest.incomplete.json").read_text())
        self.assertIn("wheel_closure_missing", h.validate_manifest(value))
        self.assertIn("closure_unreviewed", h.validate_manifest(value))

    def test_numeric_hashes_rejected_without_coercion(self):
        value = manifest()
        value["closure_review_sha256"] = int("1" * 64)
        value["wheels"][0]["sha256"] = int("2" * 64)
        errors = h.validate_manifest(value)
        self.assertIn("closure_review_missing", errors)
        self.assertIn("wheel_hash_missing", errors)

    def test_rejects_untrusted_urls(self):
        for url in ("https://evil.example/file.whl", "http://files.pythonhosted.org/file.whl",
                    "https://secret@files.pythonhosted.org/file.whl", "https://files.pythonhosted.org:bad/file.whl",
                    "https://files.pythonhosted.org/file.whl?token=secret"):
            value = manifest()
            value["wheels"][0]["url"] = url
            self.assertIn("wheel_url_unverified", h.validate_manifest(value))

    def test_download_budget_and_closure(self):
        value = manifest()
        value["wheels"][0]["bytes"] = 4 * h.GIB
        value["wheels"][0]["requires"] = ["missing-dependency"]
        self.assertIn("download_budget_exceeded", h.validate_manifest(value))
        self.assertIn("wheel_dependency_missing", h.validate_manifest(value))

    def test_duplicates_and_missing_direct_package(self):
        value = manifest()
        value["wheels"][1] = copy.deepcopy(value["wheels"][0])
        self.assertIn("duplicate_wheel", h.validate_manifest(value))
        self.assertIn("required_wheels_missing", h.validate_manifest(value))


class LifecycleTests(unittest.TestCase):
    def test_nominal_fake_success_and_receipt(self):
        result, process = simulate()
        self.assertEqual(result["status"], "passed")
        self.assertTrue(process.launched and result["cleanup_confirmed"] and result["exit_confirmed"])
        self.assertTrue(result["simulated"])
        self.assertFalse(result["hard_rss_cap_enforced"])
        self.assertFalse(result["execution_enabled"])

    def test_startup_floor_boundary(self):
        result, process = simulate([h.Sample(4 * h.GIB - 1, 0)])
        self.assertFalse(process.launched)
        self.assertEqual(result["reason"], "startup_ram_below_floor")
        result, _ = simulate([h.Sample(4 * h.GIB, 0)])
        self.assertEqual(result["status"], "passed")

    def test_runtime_floor_and_cleanup(self):
        result, process = simulate([h.Sample(4 * h.GIB, 0), h.Sample(2 * h.GIB - 1, 0)])
        self.assertEqual(result["reason"], "runtime_ram_below_floor")
        self.assertEqual(process.terminate_calls, 1)
        self.assertTrue(result["exit_confirmed"])

    def test_runtime_boundary_permitted(self):
        result, _ = simulate([h.Sample(4 * h.GIB, 0), h.Sample(2 * h.GIB, 2 * h.GIB)])
        self.assertEqual(result["status"], "passed")

    def test_rss_exceedance_is_sampled_stop(self):
        result, _ = simulate([h.Sample(5 * h.GIB, 0), h.Sample(5 * h.GIB, 2 * h.GIB + 1)])
        self.assertEqual(result["reason"], "tree_rss_exceeded")
        self.assertEqual(result["peak_sampled_tree_rss_bytes"], 2 * h.GIB + 1)
        self.assertFalse(result["hard_rss_cap_enforced"])

    def test_hung_process_stops_at_work_deadline(self):
        result, process = simulate(process=h.FakeProcess(finish_at=None))
        self.assertEqual(result["reason"], "probe_deadline")
        self.assertEqual(result["elapsed_seconds"], 110)
        self.assertTrue(process.stopped)

    def test_cleanup_failure_blocks_and_preserves_bound(self):
        result, _ = simulate(process=h.FakeProcess(finish_at=None, cleanup_succeeds=False))
        self.assertEqual(result["reason"], "owned_tree_cleanup_unconfirmed")
        self.assertEqual(result["elapsed_seconds"], 120)
        self.assertFalse(result["exit_confirmed"])

    def test_setup_probe_shared_budget(self):
        result, process = simulate(setup_elapsed=1680)
        self.assertTrue(process.launched)
        result, process = simulate(setup_elapsed=1680.001)
        self.assertFalse(process.launched)
        self.assertEqual(result["reason"], "insufficient_active_budget")
        self.assertEqual(h.LIMITS["overall_seconds"] - h.LIMITS["active_seconds"], 300)
        for value in (-1, float("nan"), float("inf"), True):
            result, process = simulate(setup_elapsed=value)
            self.assertFalse(process.launched)

    def test_child_nonzero_is_failure(self):
        result, _ = simulate(process=h.FakeProcess(exit_code=1))
        self.assertEqual(result["status"], "failed")

    def test_unowned_process_never_launched_or_killed(self):
        result, process = simulate(process=h.FakeProcess(owned=False))
        self.assertEqual(result["reason"], "ownership_unverified")
        self.assertFalse(process.launched)
        self.assertEqual(process.terminate_calls, 0)

    def test_sampler_failure_sanitized_with_cleanup(self):
        result, process = simulate([h.Sample(5 * h.GIB, 0), RuntimeError("SECRET PRIVATE PATH")])
        self.assertEqual(result["reason"], "resource_or_process_interface_failed")
        self.assertTrue(process.stopped)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_missing_or_untrusted_sample_prevents_launch(self):
        for value in (None, h.Sample(-1, 0), h.Sample(5 * h.GIB, -1), h.Sample(5 * h.GIB, 0, False)):
            result, process = simulate([value])
            self.assertFalse(process.launched)
            self.assertEqual(result["reason"], "resource_or_process_interface_failed")

    def test_nonfake_backend_rejected(self):
        with self.assertRaisesRegex(TypeError, "fake_backend_required"):
            h.simulate_probe(object(), h.FakeResources([]), h.FakeProcess())


class InertSourceTests(unittest.TestCase):
    def test_template_is_inert_even_when_loaded_and_called(self):
        with patch.dict(sys.modules, {"torch": None, "transformers": None, "peft": None}):
            namespace = runpy.run_path(str(ROOT / "cpu_probe.py.txt"))
            with self.assertRaisesRegex(RuntimeError, "execution_disabled"):
                namespace["prepared_cpu_probe"]("unused")

    def test_source_syntax_and_forbidden_operations(self):
        for filename in ("harness.py", "cpu_probe.py.txt"):
            tree = ast.parse((ROOT / filename).read_text())
            imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            self.assertFalse(set(imports) & {"subprocess", "ctypes", "socket", "requests"})
        tree = ast.parse((ROOT / "cpu_probe.py.txt").read_text())
        pretrained = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute) and node.func.attr == "from_pretrained"]
        self.assertEqual(len(pretrained), 1)
        self.assertEqual(pretrained[0].func.value.id, "PeftModel")
        self.assertTrue(any(k.arg == "local_files_only" and k.value.value is True for k in pretrained[0].keywords))


if __name__ == "__main__":
    unittest.main()
