"""Offline fake-response tests, prepared only; no real HTTP, packages, or NER.

These tests are intentionally not run by the workflow template. They exercise
the source module with injected responses and a socket prohibition. Running
them is a separate local review step, never a GitHub metadata request.
"""

import importlib.util
import io
import json
import pathlib
import unittest
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).with_name("ner_metadata_fetcher_review.py")
SPEC = importlib.util.spec_from_file_location("metadata_review", SOURCE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def wheel(name, version, tag="py3-none-any", size=100):
    filename = name.replace("-", "_") + "-" + version + "-" + tag + ".whl"
    return {"filename": filename,
            "url": "https://files.pythonhosted.org/packages/aa/bb/" + "c" * 60 + "/" + filename,
            "packagetype": "bdist_wheel", "size": size,
            "digests": {"sha256": "d" * 64}, "requires_python": ">=3.8",
            "core-metadata": {"sha256": "e" * 64}, "yanked": False}


def release(name, version):
    return {"info": {"name": name, "version": version, "requires_python": ">=3.8",
                     "requires_dist": [], "license_expression": "MIT", "license": None,
                     "classifiers": []}, "urls": [wheel(name, version)]}


class FakeFetch:
    def __init__(self, mutate=None, fail_at=None, padded_size=None):
        self.calls = []
        self.mutate = mutate
        self.fail_at = fail_at
        self.padded_size = padded_size

    def __call__(self, url, deadline, body_limit):
        self.calls.append(url)
        if self.fail_at == len(self.calls):
            raise M.Stop("transport_failure")
        name, version = url.split("/")[-3:-1]
        data = release(name, version)
        if self.mutate:
            self.mutate(data, len(self.calls))
        body = json.dumps(data).encode("utf-8")
        if self.padded_size:
            body += b" " * max(0, self.padded_size - len(body))
        return body


class Headers(dict):
    def get_content_type(self):
        return self.get("Content-Type", "application/json")


class FakeResponse:
    def __init__(self, body=b"{}", url=None, status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = Headers(headers or {})
        self.url = url or "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        self.bytes_read = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.closed = True

    def geturl(self):
        return self.url

    def read(self, count):
        result = self.body.read(count)
        self.bytes_read += len(result)
        return result


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return self.response


def fake_transport(response):
    transport = object.__new__(M.MetadataTransport)
    transport.clock = lambda: 0.0
    transport.received_bytes = 0
    transport.urls = {"https://pypi.org/pypi/" + n + "/" + v + "/json" for n, v in M.PINS.items()}
    transport.opener = FakeOpener(response)
    return transport


class MetadataReviewTests(unittest.TestCase):
    def setUp(self):
        self.no_socket = patch("socket.socket", side_effect=AssertionError("Real network is forbidden in offline tests"))
        self.no_socket.start()

    def tearDown(self):
        self.no_socket.stop()

    def test_source_only_main_never_constructs_transport(self):
        with patch.object(M, "SOURCE_ONLY", True), patch.object(M, "emit") as emit, patch.object(M, "MetadataTransport") as transport:
            self.assertEqual(M.main(), 2)
            transport.assert_not_called()
            self.assertEqual(emit.call_args.args[0]["code"], "source_only_disabled")

    def test_exact_49_allowlisted_gets_no_binary_requests(self):
        fetch = FakeFetch()
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["status"], "metadata_reads_complete")
        self.assertEqual(result["attempted_gets"], 49)
        self.assertEqual(len(result["records"]), 49)
        self.assertEqual(result["aggregate_selected_wheel_bytes"], 4900)
        self.assertEqual(fetch.calls, ["https://pypi.org/pypi/" + n + "/" + v + "/json" for n, v in M.PINS.items()])
        self.assertLessEqual(len(M.json_bytes(result)) + 1, M.MAX_OUTPUT_BYTES)
        self.assertEqual(result["dependency_closure"], "unresolved_pending_source_review")

    def test_first_transport_failure_preserves_prefix_no_retry(self):
        fetch = FakeFetch(fail_at=3)
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["code"], "transport_failure")
        self.assertEqual(len(fetch.calls), 3)
        self.assertEqual(len(result["records"]), 2)
        self.assertIsNone(result["aggregate_selected_wheel_bytes"])

    def test_wrong_version_stops(self):
        def wrong(data, index):
            data["info"]["version"] = "999"
        fetch = FakeFetch(mutate=wrong)
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["code"], "version_mismatch")
        self.assertEqual(len(fetch.calls), 1)

    def test_wrong_name_stops(self):
        fetch = FakeFetch(mutate=lambda data, index: data["info"].update(name="unexpected"))
        self.assertEqual(M.collect(fetch, clock=lambda: 0.0)["code"], "version_mismatch")

    def test_raw_requirements_do_not_expand_allowlist_or_claim_resolution(self):
        raw = ["unreviewed-package>=9; extra == 'cuda'", "another-package @ https://example.invalid/package"]
        fetch = FakeFetch(mutate=lambda data, index: data["info"].update(requires_dist=raw))
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(len(fetch.calls), 49)
        self.assertEqual(result["records"][0]["requires_dist"], raw)
        self.assertEqual(result["dependency_closure"], "unresolved_pending_source_review")

    def test_ambiguous_wheels_are_reported_without_selection(self):
        def ambiguous(data, index):
            if index == 1:
                info = data["info"]
                data["urls"].append(wheel(info["name"], info["version"], "cp312-cp312-manylinux_2_28_x86_64"))
        result = M.collect(FakeFetch(mutate=ambiguous), clock=lambda: 0.0)
        self.assertEqual(result["status"], "metadata_reads_complete")
        self.assertEqual(result["records"][0]["selection_status"], "ambiguous_source_review_required")
        self.assertEqual(len(result["records"][0]["candidate_files_for_review"]), 2)
        self.assertIsNone(result["aggregate_selected_wheel_bytes"])

    def test_abi3_is_unresolved_not_incompatible(self):
        def abi3(data, index):
            if index == 1:
                info = data["info"]
                data["urls"] = [wheel(info["name"], info["version"], "cp39-abi3-manylinux_2_28_x86_64")]
        result = M.collect(FakeFetch(mutate=abi3), clock=lambda: 0.0)
        row = result["records"][0]
        self.assertIsNone(row["selected"])
        self.assertEqual(row["selection_status"], "not_selected_by_limited_policy_not_incompatible")
        self.assertEqual(len(row["candidate_files_for_review"]), 1)

    def test_composite_tag_is_accepted_under_limited_policy(self):
        self.assertTrue(M.strict_wheel_match("spacy-3.8.15-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", "spacy", "3.8.15"))
        self.assertFalse(M.strict_wheel_match("spacy-3.8.15-cp312-cp312-manylinux_2_24_x86_64.whl", "spacy", "3.8.15"))
        self.assertFalse(M.strict_wheel_match("spacy-3.8.15-cp313-cp313-manylinux_2_28_x86_64.whl", "spacy", "3.8.15"))
        self.assertFalse(M.strict_wheel_match("spacy-3.8.15-cp312-cp312-win_amd64.whl", "spacy", "3.8.15"))

    def test_yanked_candidate_is_not_selected(self):
        fetch = FakeFetch(mutate=lambda data, index: data["urls"][0].update(yanked=True))
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["records"][0]["selection_status"], "yanked_source_review_required")
        self.assertIsNone(result["aggregate_selected_wheel_bytes"])

    def test_duplicate_json_keys_stop(self):
        result = M.collect(lambda *unused: b'{"info":{},"info":{}}', clock=lambda: 0.0)
        self.assertEqual(result["code"], "invalid_json")

    def test_non_json_payload_stops(self):
        result = M.collect(lambda *unused: b'<html>untrusted</html>', clock=lambda: 0.0)
        self.assertEqual(result["code"], "invalid_json")

    def test_response_cap(self):
        result = M.collect(lambda *unused: b'x' * (M.MAX_RESPONSE_BYTES + 1), clock=lambda: 0.0)
        self.assertEqual(result["code"], "response_too_large")
        self.assertEqual(result["attempted_gets"], 1)

    def test_aggregate_cap_without_ninth_get(self):
        fetch = FakeFetch(padded_size=M.MAX_RESPONSE_BYTES)
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["code"], "aggregate_too_large")
        self.assertEqual(result["attempted_gets"], 8)
        self.assertEqual(result["metadata_bytes"], M.MAX_TOTAL_BYTES)

    def test_output_cap_retains_bounded_prefix(self):
        fetch = FakeFetch(mutate=lambda data, index: data["info"].update(requires_python="x" * M.MAX_OUTPUT_BYTES))
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["code"], "output_limit")
        self.assertLessEqual(len(M.json_bytes(result)) + 1, M.MAX_OUTPUT_BYTES)

    def test_long_licence_is_bounded_and_explicitly_truncated(self):
        licence = "BSD licence with bundled third-party notices. " * 2000
        fetch = FakeFetch(mutate=lambda data, index: data["info"].update(license=licence))
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["status"], "metadata_reads_complete_with_truncated_fields")
        self.assertEqual(result["attempted_gets"], 49)
        legacy = result["records"][0]["licence_declared_by_registry"]["legacy"]
        self.assertTrue(legacy["truncated"])
        self.assertEqual(legacy["characters_total"], len(licence))
        self.assertEqual(legacy["sha256"], M.hashlib.sha256(licence.encode()).hexdigest())
        self.assertEqual(legacy["preview"], licence[:256])

    def test_long_requirements_are_bounded_and_never_called_complete(self):
        requirements = ["dependency" + str(index) + ">=1.0; extra == 'test'" for index in range(500)]
        fetch = FakeFetch(mutate=lambda data, index: data["info"].update(requires_dist=requirements if index == 1 else []))
        result = M.collect(fetch, clock=lambda: 0.0)
        self.assertEqual(result["status"], "metadata_reads_complete_with_truncated_fields")
        self.assertFalse(result["records"][0]["requires_dist_complete"])
        self.assertTrue(result["records"][0]["requires_dist"]["truncated"])
        self.assertEqual(result["dependency_closure"], "unresolved_pending_source_review")

    def test_deadline_stops_after_current_fetch(self):
        now = [0.0]
        fetch = FakeFetch()
        def timed(*args):
            data = fetch(*args)
            now[0] = 51.0
            return data
        result = M.collect(timed, clock=lambda: now[0])
        self.assertEqual(result["code"], "deadline")
        self.assertEqual(len(fetch.calls), 1)

    def test_raw_exception_is_never_in_receipt(self):
        def fail(*unused):
            raise RuntimeError("secret-canary-token-local-path")
        result = M.collect(fail, clock=lambda: 0.0)
        self.assertEqual(result["code"], "internal_failure")
        self.assertNotIn(b"secret-canary", M.json_bytes(result))

    def test_transport_rejects_binary_url_before_open(self):
        transport = fake_transport(FakeResponse())
        with self.assertRaises(M.Stop) as caught:
            transport("https://files.pythonhosted.org/packages/fake.whl", 50, 100)
        self.assertEqual(caught.exception.code, "invalid_allowlist")
        self.assertEqual(transport.opener.calls, [])

    def test_transport_rejects_redirect_status_and_non_json(self):
        url = "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        examples = [
            (FakeResponse(url="https://example.invalid/", headers={}), "redirect_rejected"),
            (FakeResponse(url=url, status=503), "http_status"),
            (FakeResponse(url=url, headers={"Content-Type": "text/html"}), "non_json"),
        ]
        for response, code in examples:
            with self.subTest(code=code):
                transport = fake_transport(response)
                with self.assertRaises(M.Stop) as caught:
                    transport(url, 50, 100)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(transport.opener.calls), 1)
                self.assertTrue(response.closed)

    def test_transport_never_reads_sentinel_byte_over_cap(self):
        url = "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        response = FakeResponse(body=b'x' * 11, url=url)
        transport = fake_transport(response)
        with self.assertRaises(M.Stop) as caught:
            transport(url, 50, 10)
        self.assertEqual(caught.exception.code, "response_too_large")
        self.assertEqual(response.bytes_read, 10)
        self.assertEqual(transport.received_bytes, 10)

    def test_declared_oversize_stops_without_body_read(self):
        url = "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        response = FakeResponse(body=b'x' * 11, url=url, headers={"Content-Length": "11"})
        transport = fake_transport(response)
        with self.assertRaises(M.Stop):
            transport(url, 50, 10)
        self.assertEqual(response.bytes_read, 0)

    def test_exact_declared_cap_is_allowed_without_extra_read(self):
        url = "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        response = FakeResponse(body=b'{}', url=url, headers={"Content-Length": "2"})
        transport = fake_transport(response)
        self.assertEqual(transport(url, 50, 2), b'{}')
        self.assertEqual(response.bytes_read, 2)

    def test_redirect_handler_raises_without_replacement_request(self):
        with self.assertRaises(M.Stop) as caught:
            M.NoRedirect().redirect_request(None, None, 302, None, None, "https://example.invalid/")
        self.assertEqual(caught.exception.code, "redirect_rejected")

    def test_redirect_response_is_closed(self):
        response_body = io.BytesIO(b"redirect")
        with self.assertRaises(M.Stop):
            M.NoRedirect().redirect_request(None, response_body, 302, None, None, "https://example.invalid/")
        self.assertTrue(response_body.closed)

    def test_http_error_response_is_closed(self):
        url = "https://pypi.org/pypi/annotated-doc/0.0.5/json"
        body = io.BytesIO(b"untrusted-error-text")
        error = M.urllib.error.HTTPError(url, 503, "untrusted-error-text", {}, body)
        transport = fake_transport(FakeResponse(url=url))
        with patch.object(transport.opener, "open", side_effect=error):
            with self.assertRaises(M.Stop) as caught:
                transport(url, 50, 100)
        self.assertEqual(caught.exception.code, "http_status")
        self.assertTrue(body.closed)

    def test_cancellation_is_finite(self):
        for exception in (KeyboardInterrupt(), SystemExit("untrusted-exit-text")):
            with self.subTest(exception=type(exception).__name__):
                def cancel(*unused):
                    raise exception
                result = M.collect(cancel, clock=lambda: 0.0)
                self.assertEqual(result["code"], "cancelled")
                self.assertNotIn(b"untrusted-exit-text", M.json_bytes(result))

    def test_nonstandard_json_constants_are_rejected(self):
        for literal in (b"NaN", b"Infinity", b"-Infinity"):
            result = M.collect(lambda *unused: b'{"extra":' + literal + b'}', clock=lambda: 0.0)
            self.assertEqual(result["code"], "invalid_json")

    def test_retained_registry_field_types(self):
        for field, value in (("requires_python", 3.12), ("license", {}),
                             ("license_expression", []), ("classifiers", [None])):
            fetch = FakeFetch(mutate=lambda data, index: data["info"].update({field: value}))
            self.assertEqual(M.collect(fetch, clock=lambda: 0.0)["code"], "invalid_metadata")

    def test_post_parse_deadline_prevents_completion(self):
        now = [0.0]
        original = M.parse_release
        def slow_parse(*args):
            result = original(*args)
            now[0] = 51.0
            return result
        with patch.object(M, "parse_release", side_effect=slow_parse):
            result = M.collect(FakeFetch(), clock=lambda: now[0])
        self.assertEqual(result["code"], "deadline")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["attempted_gets"], 1)
        self.assertEqual(result["elapsed_ms"], 51000)

    def test_elapsed_overrun_is_not_hidden(self):
        now = [0.0]
        def delayed(*unused):
            now[0] = 70.0
            raise M.Stop("deadline")
        result = M.collect(delayed, clock=lambda: now[0])
        self.assertEqual(result["elapsed_ms"], 70000)


if __name__ == "__main__":
    unittest.main()
