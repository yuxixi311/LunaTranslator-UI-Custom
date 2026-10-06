"""In-memory fakes only: never create sockets, subprocesses, or asset files."""
import json
from pathlib import Path
import unittest

import header_logic as h


class FakeDeadline:
    def __init__(self, fail_after=None, value=10.0):
        self.calls = 0
        self.fail_after = fail_after
        self.value = value

    def remaining(self):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise h.ProbeFailure("DEADLINE_EXPIRED")
        return self.value


class FakeReader:
    def __init__(self, header, body=b""):
        self.data = header + body
        self.header_length = len(header)
        self.position = 0
        self.requests = []
        self.body_reads = 0

    def read(self, n, remaining):
        self.requests.append((n, remaining))
        if self.position >= self.header_length:
            self.body_reads += 1
        chunk = self.data[self.position:self.position + n]
        self.position += len(chunk)
        return chunk


class PureHeaderTests(unittest.TestCase):
    def parse(self, payload, body=b"", deadline=None):
        reader = FakeReader(payload, body)
        status, headers = h.read_headers(reader, deadline or FakeDeadline())
        self.assertEqual(reader.position, len(payload))
        self.assertEqual(reader.body_reads, 0)
        self.assertTrue(all(n == 1 and remaining > 0 for n, remaining in reader.requests))
        return status, headers

    def failure(self, payload, code):
        with self.assertRaises(h.ProbeFailure) as caught:
            h.read_headers(FakeReader(payload), FakeDeadline())
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertEqual(caught.exception.args, (code,))

    def test_200_stops_before_body_and_returns_lowercase_headers(self):
        self.assertEqual(self.parse(b"HTTP/1.1 200 OK\r\nX-A: a \r\nContent-Length: 987654\r\n\r\n",
                                    b"SENSITIVE_BODY_MUST_NOT_BE_READ"),
                         (200, {b"x-a": b"a", b"content-length": b"987654"}))

    def test_other_statuses_stop_at_first_header_block(self):
        for status in (100, 200, 301, 302, 303, 307, 308, 404, 999):
            with self.subTest(status=status):
                self.parse(f"HTTP/1.0 {status}\r\n\r\n".encode(), b"HTTP/1.1 200 OK\r\n\r\nBODY")

    def test_status_syntax(self):
        for status in (b"HTTP/2 200 OK", b"HTTP/1.2 200 OK", b"HTTP/1.1 20 OK",
                       b"HTTP/1.1 2000 OK", b"HTTP/1.1 200\tOK", b"HTTP/1.1 200 \x80"):
            with self.subTest(status=status):
                self.failure(status + b"\r\n\r\n", "ASSET_STATUS_LINE_REJECTED")

    def test_line_cap_includes_crlf(self):
        line = b"X:" + b"a" * 2044 + b"\r\n"
        self.assertEqual(len(line), 2048)
        self.parse(b"HTTP/1.1 200\r\n" + line + b"\r\n")
        self.failure(b"HTTP/1.1 200\r\n" + b"X:" + b"a" * 2045 + b"\r\n\r\n", "HTTP_LINE_LIMIT")
        self.parse(b"HTTP/1.1 200 " + b"a" * 2033 + b"\r\n\r\n")
        self.failure(b"HTTP/1.1 200 " + b"a" * 2034 + b"\r\n\r\n", "HTTP_LINE_LIMIT")

    def test_header_block_cap_exact_and_over(self):
        first = b"HTTP/1.1 200\r\n"
        fields = [f"X-{i}:".encode() + b"a" * (2048 - len(f"X-{i}:".encode()) - 2) + b"\r\n"
                  for i in range(7)]
        remaining = 16384 - len(first) - sum(map(len, fields)) - 2
        last = b"Z:" + b"a" * (remaining - 4) + b"\r\n"
        payload = first + b"".join(fields) + last + b"\r\n"
        self.assertEqual(len(payload), 16384)
        self.parse(payload)
        self.failure(payload[:-2] + b"Y:a\r\n\r\n", "HTTP_HEADER_BLOCK_LIMIT")

    def test_header_field_count(self):
        payload = b"HTTP/1.1 200\r\n" + b"".join(f"X-{i}: v\r\n".encode() for i in range(64))
        self.assertEqual(len(self.parse(payload + b"\r\n")[1]), 64)
        self.failure(payload + b"X-64: v\r\n\r\n", "ASSET_HEADER_FIELDS_REJECTED")

    def test_bad_fields_duplicate_and_controls(self):
        for field in (b"missing colon", b" folded:value", b"\tfolded:value"):
            self.failure(b"HTTP/1.1 200\r\n" + field + b"\r\n\r\n", "ASSET_HEADER_FIELDS_REJECTED")
        for field in (b":value", b"X :value", b"X(:value", b"X:v\x00", b"X:v\x7f"):
            self.failure(b"HTTP/1.1 200\r\n" + field + b"\r\n\r\n", "ASSET_HEADER_SYNTAX_REJECTED")
        self.failure(b"HTTP/1.1 200\r\nX:a\r\nx:b\r\n\r\n", "ASSET_HEADER_SYNTAX_REJECTED")

    def test_historical_header_tab_handling_is_preserved(self):
        self.assertEqual(self.parse(b"HTTP/1.1 200\r\nX: \ta\tb\t \r\n\r\n"), (200, {b"x": b"a\tb"}))

    def test_crlf_and_eof(self):
        for payload in (b"HTTP/1.1 200\n\n", b"HTTP/1.1 200\rX", b"HTTP/1.1 200\r\nX:a\n"):
            self.failure(payload, "HTTP_CRLF_REJECTED")
        for payload in (b"", b"HTTP/1.1 200", b"HTTP/1.1 200\r", b"HTTP/1.1 200\r\n"):
            self.failure(payload, "HTTP_EOF_OR_INVALID_READ")

    def test_invalid_reader_results_and_exceptions_are_fixed(self):
        for value in (None, "x", bytearray(b"x"), b"", b"xx", 1):
            class InvalidReader:
                def read(self, n, remaining):
                    return value
            with self.assertRaises(h.ProbeFailure) as caught:
                h.read_headers(InvalidReader(), FakeDeadline())
            self.assertEqual(caught.exception.code, "HTTP_EOF_OR_INVALID_READ")
        class RaisingReader:
            def read(self, n, remaining):
                raise ValueError("SENSITIVE_READER_TEXT")
        with self.assertRaises(h.ProbeFailure) as caught:
            h.read_headers(RaisingReader(), FakeDeadline())
        self.assertEqual(caught.exception.args, ("UNKNOWN_FAILURE",))
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("SENSITIVE", repr(caught.exception))

    def test_deadline_before_and_after_read(self):
        for limit in (0, 1, 10):
            reader = FakeReader(b"HTTP/1.1 200\r\n\r\n", b"body")
            with self.assertRaises(h.ProbeFailure) as caught:
                h.read_headers(reader, FakeDeadline(fail_after=limit))
            self.assertEqual(caught.exception.code, "DEADLINE_EXPIRED")
            self.assertEqual(reader.body_reads, 0)
        for value, code in ((0, "DEADLINE_EXPIRED"), (-1, "DEADLINE_EXPIRED"),
                            (float("nan"), "UNKNOWN_FAILURE"), (float("inf"), "UNKNOWN_FAILURE"),
                            (True, "UNKNOWN_FAILURE")):
            with self.assertRaises(h.ProbeFailure) as caught:
                h.read_headers(FakeReader(b""), FakeDeadline(value=value))
            self.assertEqual(caught.exception.code, code)


class PureProjectionTests(unittest.TestCase):
    def project(self, location=None, status=302):
        headers = {} if location is None else {b"location": location}
        result = h.classify_response(status, headers, dict(h.EXACT_HOST_CLASSES))
        self.assertEqual(set(result), {"status", "location_form", "host_class", "authority", "current_policy_outcome"})
        self.assertIn(result["status"], h.STATUS_VALUES)
        self.assertIn(result["location_form"], h.LOCATION_FORM_VALUES)
        self.assertIn(result["host_class"], h.HOST_CLASS_VALUES)
        self.assertIn(result["authority"], h.AUTHORITY_VALUES)
        self.assertIn(result["current_policy_outcome"], h.POLICY_VALUES)
        self.assertLessEqual(len(json.dumps(result)), 2048)
        return result

    def test_all_official_hosts_and_expected_bridge(self):
        self.assertEqual(len(h.EXACT_HOST_CLASSES), 22)
        for host, expected in h.EXACT_HOST_CLASSES.items():
            result = self.project(("https://" + host + "/file").encode())
            self.assertEqual(result["host_class"], expected)
            self.assertEqual(result["authority"], "CANONICAL_HTTPS_443")
            self.assertEqual(result["current_policy_outcome"],
                             "ACCEPTS_EXISTING_HOST_AND_AUTHORITY" if host == h.EXPECTED_BRIDGE else "REJECTS_HOST")

    def test_frozen_proposal_and_official_vocabulary(self):
        source = Path(__file__).resolve().parent
        proposal = json.loads((source / "PROTOCOL.json").read_text())
        official = json.loads((source / "OFFICIAL_HOST_FIELDS.json").read_text())
        self.assertEqual(h.INITIAL_URL, proposal["initial_request"]["url"])
        self.assertEqual(h.EXACT_HOST_CLASSES, proposal["exact_host_observation_classes"])
        self.assertEqual(set(h.EXACT_HOST_CLASSES) - {h.EXPECTED_BRIDGE},
                         {host for values in official["fields"].values() for host in values})
        for values, key in ((h.STATUS_VALUES, "status_enum"), (h.LOCATION_FORM_VALUES, "location_form_enum"),
                            (h.AUTHORITY_VALUES, "authority_enum"), (h.POLICY_VALUES, "current_policy_outcome_enum"),
                            (h.FAILURE_CODES, "failure_enum")):
            self.assertEqual(values, set(proposal["public_projection"][key]))

    def test_absent_and_empty_location(self):
        self.assertEqual(self.project(), {"status": "HTTP_302", "location_form": "ABSENT", "host_class": "NO_LOCATION",
                                         "authority": "UNOBSERVED", "current_policy_outcome": "REJECTS_OTHER_EXISTING_URL_RULE"})
        self.assertEqual(self.project(b"")["host_class"], "UNPARSEABLE")

    def test_relative_and_network_path(self):
        for value in (b"file", b"/file", b"?signature=OPAQUE_SECRET", b"https:/file", b"https:file"):
            result = self.project(value)
            self.assertEqual(result["host_class"], "HF_META_HUGGINGFACE_CO")
            self.assertEqual(result["authority"], "IMPLICIT_SAME_ORIGIN")
            self.assertEqual(result["current_policy_outcome"], "REJECTS_HOST")
        result = self.project(b"//cas-bridge.xethub.hf.co/file")
        self.assertEqual(result["location_form"], "NETWORK_PATH")
        self.assertEqual(result["current_policy_outcome"], "ACCEPTS_EXISTING_HOST_AND_AUTHORITY")

    def test_unknown_hosts_never_use_suffix_matching(self):
        for host in ("unknown.invalid", "evil.cas-bridge.xethub.hf.co", "cas-bridge.xethub.hf.co.evil.invalid",
                     "cas-bridge.xethub.hf.co.", "huggingface.co.evil.invalid", "127.0.0.1", "[2001:db8::1]"):
            result = self.project(("https://" + host + "/file").encode())
            self.assertEqual(result["host_class"], "OTHER_UNREVIEWED_HOST")
            self.assertEqual(result["current_policy_outcome"], "REJECTS_HOST")
            self.assertNotIn(host, json.dumps(result))

    def test_hostname_and_authority_shape_are_separate(self):
        for authority in ("CAS-BRIDGE.XETHUB.HF.CO", "cas-bridge.xethub.hf.co:0443", "cas-bridge.xethub.hf.co:"):
            result = self.project(("https://" + authority + "/file").encode())
            self.assertEqual(result["host_class"], "EXISTING_EXPECTED_BRIDGE")
            self.assertEqual(result["authority"], "NONCANONICAL_HTTPS_443")
            self.assertEqual(result["current_policy_outcome"], "REJECTS_AUTHORITY_SHAPE")
        for authority in ("cas-bridge.xethub.hf.co", "cas-bridge.xethub.hf.co:443"):
            result = self.project(("https://" + authority + "/file").encode())
            self.assertEqual(result["authority"], "CANONICAL_HTTPS_443")
            self.assertEqual(result["current_policy_outcome"], "ACCEPTS_EXISTING_HOST_AND_AUTHORITY")

    def test_malformed_and_rejected_url_rules(self):
        base = b"https://cas-bridge.xethub.hf.co/file"
        values = [b"\x00" + base, b" " + base, base + b"\n", base + b"\x7f", base + b"\x80", base + b"\\",
                  base + b"#", base + b"#fragment", b"http://cas-bridge.xethub.hf.co/file", b"ftp://host/file",
                  b"https://user@cas-bridge.xethub.hf.co/file", b"https://user:secret@cas-bridge.xethub.hf.co/file",
                  b"https://cas-bridge.xethub.hf.co:444/file", b"https://cas-bridge.xethub.hf.co:bad/file",
                  b"https://cas-bridge.xethub.hf.co:999999/file", b"https://[broken/file", b"a" * 2049]
        for location in values:
            result = self.project(location)
            self.assertEqual((result["location_form"], result["host_class"], result["authority"], result["current_policy_outcome"]),
                             ("INVALID", "UNPARSEABLE", "REJECTED_AUTHORITY", "REJECTS_OTHER_EXISTING_URL_RULE"))

    def test_historical_path_semantics(self):
        base = b"https://cas-bridge.xethub.hf.co"
        for path in (b"", b"/", b"/a/../file", b"/a/./file", b"/a/%2e%2e/file", b"/a/%252e%252e/file",
                     b"/a%2ffile", b"/a%5cfile", b"/a%252ffile", b"/%ff", b"/%2525252541"):
            result = self.project(base + path)
            self.assertEqual(result["current_policy_outcome"], "REJECTS_OTHER_EXISTING_URL_RULE")
        for path in (b"/file", b"/a%20file", b"/a%2520file", b"/a%ZZfile", b"/a%41file", b"/a%252541file"):
            self.assertEqual(self.project(base + path)["current_policy_outcome"], "ACCEPTS_EXISTING_HOST_AND_AUTHORITY")
        for path in (b"../file", b"/a/../file", b"/a/%2e%2e/file"):
            self.assertEqual(self.project(path)["current_policy_outcome"], "REJECTS_OTHER_EXISTING_URL_RULE")

    def test_signed_query_is_opaque_and_never_emitted(self):
        secret = "SECRET_SIGNATURE_VALUE_123"
        location = ("https://cas-bridge.xethub.hf.co/private-path?X-Amz-Signature=" + secret + "&x=%2f%5c%ff").encode()
        result = self.project(location)
        self.assertEqual(result["current_policy_outcome"], "ACCEPTS_EXISTING_HOST_AND_AUTHORITY")
        encoded = json.dumps(result)
        for private in (secret, "X-Amz", "private-path", "https://", "cas-bridge"):
            self.assertNotIn(private, encoded)

    def test_location_length_limit_and_join_expansion(self):
        base = b"https://cas-bridge.xethub.hf.co/"
        exact = base + b"a" * (2048 - len(base))
        self.assertEqual(self.project(exact)["current_policy_outcome"], "ACCEPTS_EXISTING_HOST_AND_AUTHORITY")
        self.assertEqual(self.project(exact + b"a")["host_class"], "UNPARSEABLE")
        self.assertEqual(self.project(b"a" * 2048)["host_class"], "UNPARSEABLE")

    def test_nonredirect_outcome_with_and_without_location(self):
        for status in (0, 100, 200, 201, 304, 400, 500, 999):
            for location in (None, b"", b"https://cas-bridge.xethub.hf.co/file", b"https://unknown.invalid/file"):
                result = self.project(location, status)
                self.assertEqual(result["current_policy_outcome"], "NOT_A_REDIRECT")
                self.assertEqual(result["status"], "HTTP_200" if status == 200 else "OTHER_HTTP_STATUS")

    def test_all_redirect_status_labels(self):
        for status in (301, 302, 303, 307, 308):
            self.assertEqual(self.project(status=status)["status"], "HTTP_" + str(status))

    def test_bad_input_and_map_cannot_inject_output(self):
        maps = [{}, {"SENSITIVE_HOST": "SENSITIVE_ENUM"}, {**h.EXACT_HOST_CLASSES, "unknown.invalid": "EXISTING_EXPECTED_BRIDGE"}]
        for mapping in maps:
            with self.assertRaises(h.ProbeFailure) as caught:
                h.classify_response(302, {}, mapping)
            self.assertEqual(caught.exception.args, ("UNKNOWN_FAILURE",))
        for code in ("https://SENSITIVE_HOST/?signature=SECRET", None, [], {"secret": "value"}):
            failure = h.ProbeFailure(code)
            self.assertEqual(failure.code, "UNKNOWN_FAILURE")
            self.assertEqual(failure.args, ("UNKNOWN_FAILURE",))


if __name__ == "__main__":
    unittest.main()
