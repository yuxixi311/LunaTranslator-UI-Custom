"""Offline fixtures only: never requests PyPI, downloads wheels, or imports NER."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("plac147_review", ROOT / "plac147_preflight.py")
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def fixture():
    return {"info": {"name": "plac", "version": "1.4.7", "requires_dist": None,
                     "requires_python": None, "license": "BSD License", "license_expression": None,
                     "classifiers": ["License :: OSI Approved :: BSD License"], "yanked": False},
            "urls": [{"filename": P.FILENAME, "packagetype": "bdist_wheel", "size": 22000,
                      "url": "https://files.pythonhosted.org/packages/aa/bb/" + "c" * 60 + "/" + P.FILENAME,
                      "digests": {"sha256": P.WHEEL_SHA256}, "requires_python": None,
                      "core-metadata": {"sha256": "d" * 64}, "yanked": False}]}


class FakeFetch:
    def __init__(self, data=None, error=None):
        self.data = fixture() if data is None else data
        self.error = error
        self.calls = []

    def __call__(self, url, deadline, limit):
        self.calls.append((url, deadline, limit))
        if self.error is not None:
            raise self.error
        return self.data if isinstance(self.data, bytes) else json.dumps(self.data).encode()


class Plac147Tests(unittest.TestCase):
    def setUp(self):
        self.no_socket = patch("socket.socket", side_effect=AssertionError("Real sockets prohibited"))
        self.no_socket.start()

    def tearDown(self):
        self.no_socket.stop()

    def result(self, data):
        fetch = FakeFetch(data)
        result = P.perform(fetch, clock=lambda: 0)
        self.assertEqual(len(fetch.calls), 1)
        self.assertEqual(fetch.calls[0], (P.URL, 20.0, P.MAX_JSON_BYTES))
        return result

    def test_disabled_main_cannot_construct_transport(self):
        with patch.object(P, "SOURCE_ONLY", True), patch.object(P, "SingleURLTransport") as transport, patch.object(P.F, "emit"):
            self.assertEqual(P.main(), 2)
            transport.assert_not_called()

    def test_success_freezes_actual49_without_any_transition(self):
        result = self.result(fixture())
        self.assertEqual(result["status"], "metadata_verified_manifest_frozen")
        manifest = result["frozen_manifest"]
        self.assertEqual(len(manifest["files"]), 49)
        self.assertEqual(manifest["aggregate_bytes"], P.BASE48_BYTES + 22000)
        self.assertEqual(result["frozen_manifest_sha256"], hashlib.sha256(P.encoded(manifest)).hexdigest())
        self.assertFalse(result["acquisition_allowed"])
        self.assertFalse(result["installation_allowed"])
        self.assertFalse(result["ner_execution_allowed"])
        self.assertLess(len(P.encoded(result)), P.MAX_OUTPUT_BYTES)
        actual48 = [r for r in manifest["files"] if r["name"] != "plac"]
        self.assertEqual(actual48, P.load_baseline()["files"])

    def test_empty_list_dependencies_are_semantically_empty(self):
        data = fixture(); data["info"]["requires_dist"] = []
        self.assertEqual(self.result(data)["status"], "metadata_verified_manifest_frozen")

    def test_explicit_delta_is146_to147(self):
        result = self.result(fixture())
        self.assertEqual(result["version_amendment"], {"from": "plac==1.4.6", "to": "plac==1.4.7"})

    def test_transport_error_stops_with_one_attempt(self):
        fetch = FakeFetch(error=P.F.Stop("transport_failure"))
        result = P.perform(fetch, clock=lambda: 0)
        self.assertEqual(result["code"], "transport_failure")
        self.assertEqual(len(fetch.calls), 1)
        self.assertNotIn("frozen_manifest", result)

    def test_wrong_release_identity(self):
        for field, value in (("name", "other"), ("version", "1.4.5")):
            data = fixture(); data["info"][field] = value
            self.assertEqual(self.result(data)["code"], "release_identity_mismatch")

    def test_any_dependency_declaration_is_terminal(self):
        for requirement in ("argparse", "pytest; extra == 'dev'", "missing; python_version < '3.0'"):
            data = fixture(); data["info"]["requires_dist"] = [requirement]
            self.assertEqual(self.result(data)["code"], "dependency_metadata_mismatch")

    def test_changed_python_declaration_is_terminal(self):
        data = fixture(); data["info"]["requires_python"] = ">=3.8"
        self.assertEqual(self.result(data)["code"], "python_metadata_mismatch")
        data = fixture(); data["urls"][0]["requires_python"] = ">=3.8"
        self.assertEqual(self.result(data)["code"], "python_metadata_mismatch")

    def test_omitted_metadata_declarations_are_not_verified_nulls(self):
        cases = (("info", "requires_dist", "dependency_metadata_mismatch"),
                 ("info", "requires_python", "python_metadata_mismatch"),
                 ("info", "license_expression", "licence_metadata_mismatch"),
                 ("wheel", "requires_python", "python_metadata_mismatch"))
        for location, field, expected in cases:
            with self.subTest(location=location, field=field):
                data = fixture()
                target = data["info"] if location == "info" else data["urls"][0]
                del target[field]
                result = self.result(data)
                self.assertEqual(result["code"], expected)
                self.assertNotIn("frozen_manifest", result)

    def test_licence_change_is_terminal(self):
        for field, value in (("license", "MIT"), ("license_expression", "BSD-2-Clause"), ("classifiers", [])):
            data = fixture(); data["info"][field] = value
            self.assertEqual(self.result(data)["code"], "licence_metadata_mismatch")

    def test_yanked_release_or_wheel_is_terminal(self):
        for location in ("info", "wheel"):
            data = fixture()
            target = data["info"] if location == "info" else data["urls"][0]
            target["yanked"] = True
            self.assertEqual(self.result(data)["code"], "yanked")

    def test_exact_wheel_identity_is_required(self):
        data = fixture(); data["urls"][0]["digests"]["sha256"] = "0" * 64
        self.assertEqual(self.result(data)["code"], "wheel_identity_mismatch")
        data = fixture(); data["urls"][0]["packagetype"] = "sdist"
        self.assertEqual(self.result(data)["code"], "wheel_identity_mismatch")
        data = fixture(); data["urls"][0]["filename"] = "plac-1.4.5-py2.py3-none-any.whl"
        self.assertEqual(self.result(data)["code"], "ambiguous_selected_file")

    def test_duplicate_matching_file_is_terminal(self):
        data = fixture(); data["urls"].append(copy.deepcopy(data["urls"][0]))
        self.assertEqual(self.result(data)["code"], "ambiguous_selected_file")

    def test_selected_url_must_be_official_wheel_url(self):
        data = fixture(); data["urls"][0]["url"] = "https://example.invalid/" + P.FILENAME
        self.assertEqual(self.result(data)["code"], "invalid_metadata")

    def test_size_cap_exact_bound(self):
        for size in (0, -1, True, 32769):
            data = fixture(); data["urls"][0]["size"] = size
            self.assertEqual(self.result(data)["code"], "wheel_size_mismatch")
        data = fixture(); data["urls"][0]["size"] = 32768
        result = self.result(data)
        self.assertEqual(result["frozen_manifest"]["aggregate_bytes"], 207417118)

    def test_json_size_and_syntax_are_bounded(self):
        self.assertEqual(self.result(b'x' * (P.MAX_JSON_BYTES + 1))["code"], "json_size_limit")
        self.assertEqual(self.result(b'not json')["code"], "invalid_json")
        self.assertEqual(self.result(b'{"info":{},"info":{}}')["code"], "invalid_json")
        self.assertEqual(self.result(b'{"info":NaN}')["code"], "invalid_json")

    def test_baseline_hash_failure_precedes_network(self):
        fetch = FakeFetch()
        with patch.object(P, "BASE48_SHA256", "0" * 64):
            result = P.perform(fetch, clock=lambda: 0)
        self.assertEqual(result["code"], "baseline_mismatch")
        self.assertEqual(fetch.calls, [])

    def test_previous_receipt_hash_failure_precedes_network(self):
        fetch = FakeFetch()
        with patch.object(P, "PREVIOUS_METADATA_SHA256", "0" * 64):
            result = P.perform(fetch, clock=lambda: 0)
        self.assertEqual(result["code"], "baseline_mismatch")
        self.assertEqual(fetch.calls, [])

    def test_deadline_no_retry_or_frozen_result(self):
        now = [0]
        fetch = FakeFetch()
        def delayed(*args):
            result = fetch(*args); now[0] = 21; return result
        result = P.perform(delayed, clock=lambda: now[0])
        self.assertEqual(result["code"], "deadline")
        self.assertEqual(len(fetch.calls), 1)
        self.assertNotIn("frozen_manifest", result)

    def test_raw_exception_and_cancellation_never_leak(self):
        for error, code in ((RuntimeError("secret-local-path"), "internal_failure"), (KeyboardInterrupt(), "cancelled"), (SystemExit("secret-local-path"), "cancelled")):
            result = P.perform(FakeFetch(error=error), clock=lambda: 0)
            self.assertEqual(result["code"], code)
            self.assertNotIn(b"secret-local-path", P.encoded(result))

    def test_singleton_transport_blocks_every_old_or_binary_url(self):
        transport = P.SingleURLTransport(clock=lambda: 0)
        self.assertEqual(transport.urls, frozenset({P.URL}))
        for url in ("https://pypi.org/pypi/plac/1.4.6/json", "https://pypi.org/pypi/ginza/5.2.0/json", fixture()["urls"][0]["url"]):
            with self.assertRaises(P.F.Stop) as caught:
                transport(url, 20, P.MAX_JSON_BYTES)
            self.assertEqual(caught.exception.code, "invalid_allowlist")


if __name__ == "__main__":
    unittest.main()
