"""Nine fake-only tests, verified 2026-10-07. No test uses a real network transport."""
import io
import json
import unittest
from unittest.mock import patch
import collect_metadata as m


class Response:
    def __init__(self, body=b"{}", status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read(self, size):
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Tests(unittest.TestCase):
    def fake_client(self, response, clock=lambda: 0):
        return m.Client(transport=lambda url, timeout: response, clock=clock)

    def test_only_literal_metadata_urls(self):
        for url in m.ALLOWED_REQUESTS:
            m.validate_request(url)
        for url in ["http://pypi.org/pypi/peft/0.21.2/json", m.INDEX + "?x=1",
                    "https://download-r2.pytorch.org/whl/cu128/torch.whl",
                    "https://files.pythonhosted.org/a.whl.metadata",
                    "https://pypi.org.evil.example/pypi/peft/0.21.2/json",
                    "https://user:password@pypi.org/pypi/peft/0.21.2/json"]:
            with self.assertRaises(m.Stop):
                m.validate_request(url)

    def test_redirect_and_first_failure_stop(self):
        c = self.fake_client(Response(status=302))
        report = m.collect(c)
        self.assertEqual(report["status"], "stopped_on_first_failure")
        self.assertEqual(c.requests, 1)
        self.assertEqual(report["packages"], [])
        self.assertFalse(report["install_ready"])

    def test_exception_details_are_never_exported(self):
        class SecretTransportFailure(Exception):
            def __str__(self):
                raise AssertionError("Exception string must not be inspected")

            def __repr__(self):
                raise AssertionError("Exception repr must not be inspected")

        def failing_transport(url, timeout):
            raise SecretTransportFailure("FAKE_SECRET_VALUE", "https://private.invalid/FAKE_SECRET_VALUE")

        report = m.collect(m.Client(transport=failing_transport))
        encoded = json.dumps(report)
        self.assertEqual(report["error_code"], "UNEXPECTED_ERROR")
        for text in ("FAKE_SECRET_VALUE", "private.invalid", "SecretTransportFailure"):
            self.assertNotIn(text, encoded)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(m.Stop("FAKE_SECRET_VALUE").code, "UNEXPECTED_ERROR")

    def test_torch_link_is_recorded_never_requested(self):
        html = ('<a href="https://download-r2.pytorch.org/whl/cu128/' +
                m.TORCH_FILENAME.replace("+", "%2B") + '#sha256=' + 'a' * 64 + '">wheel</a>')
        record = m.parse_torch(html.encode())
        self.assertIsNone(record["size_bytes"])
        self.assertFalse(record["wheel_contacted"])
        with self.assertRaises(m.Stop):
            m.validate_request(record["wheel_url_record_only"])
        with self.assertRaises(m.Stop):
            m.parse_torch(html.replace("download-r2.pytorch.org", "evil.example").encode())
        with self.assertRaises(m.Stop):
            m.parse_torch((html + html).encode())
        with self.assertRaises(m.Stop):
            m.parse_torch(html.replace("a" * 64, "bad").encode())

    def test_payload_caps(self):
        c = self.fake_client(Response(b"x" * 17))
        with patch.object(m, "MAX_RESPONSE", 16):
            with self.assertRaises(m.Stop):
                c.get(next(u for u in m.ALLOWED_REQUESTS if u.endswith("/json")), "application/json")
        self.assertEqual(c.total, 16)
        c = self.fake_client(Response(headers={"Content-Type": "application/json", "Content-Length": "1048577"}))
        with self.assertRaises(m.Stop):
            c.get("https://pypi.org/pypi/peft/0.21.2/json", "application/json")
        self.assertEqual(c.total, 0)

    def test_deadline_stops_before_transport(self):
        now = [0]
        c = self.fake_client(Response(), clock=lambda: now[0])
        now[0] = 111
        with self.assertRaises(m.Stop):
            c.get("https://pypi.org/pypi/peft/0.21.2/json", "application/json")
        self.assertEqual(c.requests, 0)

    def test_transport_header_body_deadline_advances_stop(self):
        for phase in ("transport", "headers", "body"):
            with self.subTest(phase=phase):
                now = [0]

                class AdvancingResponse(Response):
                    def getheader(self, key, default=None):
                        if phase == "headers":
                            now[0] = 111
                        return super().getheader(key, default)

                    def read(self, size):
                        if phase == "body":
                            now[0] = 111
                        return super().read(size)

                def transport(url, timeout):
                    if phase == "transport":
                        now[0] = 111
                    return AdvancingResponse(b"")

                c = m.Client(transport=transport, clock=lambda: now[0])
                with self.assertRaises(m.Stop) as raised:
                    c.get("https://pypi.org/pypi/peft/0.21.2/json", "application/json")
                self.assertEqual(raised.exception.code, "DEADLINE_REACHED")
                self.assertEqual(c.sources, [])

    def test_reject_duplicate_nonfinite_and_nullable_text_schema(self):
        for body in (b'{"info": {}, "info": {}}', b'{"unused": NaN}', b'{"unused": Infinity}', b'{"unused": -Infinity}', b'{"unused": 1e999}'):
            with self.subTest(body=body):
                with self.assertRaises(m.Stop) as raised:
                    m.parse_pypi("peft", body)
                self.assertEqual(raised.exception.code, "JSON_SCHEMA_INVALID")
        for field in ("requires_python", "license", "license_expression"):
            for invalid in ([], {}, 123, True):
                with self.subTest(field=field, invalid=invalid):
                    body = json.dumps({"info": {field: invalid}}).encode()
                    with self.assertRaises(m.Stop) as raised:
                        m.parse_pypi("peft", body)
                    self.assertEqual(raised.exception.code, "JSON_SCHEMA_INVALID")

    def test_fixed_release_schema_size_sha(self):
        obj = {"info": {"name": "peft", "version": "0.21.2", "requires_dist": ["torch>=1.13"]},
               "urls": [{"filename": m.FILENAMES["peft"], "url": "https://files.pythonhosted.org/a/" + m.FILENAMES["peft"],
                         "packagetype": "bdist_wheel", "yanked": False, "size": 123, "digests": {"sha256": "b" * 64}}]}
        record = m.parse_pypi("peft", json.dumps(obj).encode())
        self.assertEqual(record["size_bytes"], 123)
        self.assertEqual(record["requires_dist"], ["torch>=1.13"])
        obj["urls"][0]["size"] = True
        with self.assertRaises(m.Stop):
            m.parse_pypi("peft", json.dumps(obj).encode())
        obj["urls"][0]["size"] = 123
        obj["info"]["version"] = "0.21.3"
        with self.assertRaises(m.Stop):
            m.parse_pypi("peft", json.dumps(obj).encode())


if __name__ == "__main__":
    unittest.main()
