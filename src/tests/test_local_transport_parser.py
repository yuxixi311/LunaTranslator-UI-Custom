"""Production Sakura parser with synthetic HTTP framing; no sockets or Qt.

Compile the unchanged parser functions from source to avoid importing Windows
application dependencies. Feed the local adapter a real stdlib HTTPResponse so
chunked framing, Unicode decoding and early stream cleanup are exercised.
"""

import ast
import http.client
import io
import json
from pathlib import Path
import sys
import types
import unittest


APP = Path(__file__).resolve().parents[1] / "LunaTranslator"
sys.path.insert(0, str(APP))
from myutils.local_transport import LocalResponse


def load_production_parser():
    # Sakura imports this shared parser unchanged through gptcommon.
    path = APP / "translator/gptcommon.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {"stream_event_parser", "commonparseresponse_good"}
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in functions} != names:
        raise AssertionError("Missing requested production parser functions")
    namespace = {"requests": types.SimpleNamespace(Response=object), "json": json}
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace["commonparseresponse_good"]


class FakeSocket:
    def __init__(self, wire):
        self.reader = io.BufferedReader(io.BytesIO(wire))

    def makefile(self, *args, **kwargs):
        return self.reader


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def chunked_response(payload):
    # Tiny chunks split both SSE lines and multibyte UTF-8 characters. The
    # HTTPResponse must remove framing before LocalResponse decodes each line.
    chunks = [payload[index : index + 2] for index in range(0, len(payload), 2)]
    body = b"".join(
        format(len(chunk), "x").encode("ascii") + b"\r\n" + chunk + b"\r\n"
        for chunk in chunks
    ) + b"0\r\n\r\n"
    wire = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/event-stream; charset=utf-8\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n" + body
    )
    socket = FakeSocket(wire)
    raw = http.client.HTTPResponse(socket)
    raw.begin()
    connection = FakeConnection()
    return LocalResponse(connection, raw), connection, socket


def event(content=None, finish_reason=None):
    data = {
        "model": "owned-alias",
        "choices": [
            {
                "delta": {"content": content} if content is not None else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode("utf-8")


def collect(generator):
    pieces = []
    while True:
        try:
            pieces.append(next(generator))
        except StopIteration as stopped:
            return pieces, stopped.value


class SakuraLocalParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parse = staticmethod(load_production_parser())

    def assert_closed(self, adapted, connection, socket):
        self.assertTrue(adapted.response.isclosed())
        self.assertTrue(connection.closed)
        self.assertTrue(socket.reader.closed)

    def test_chunked_unicode_and_finish_reason_close_before_trailer(self):
        payload = (
            event("こんにちは")
            + event("世界🌏")
            + event(finish_reason="stop")
            # This must not be parsed after the completion event.
            + b"data: not valid JSON\n\n"
        )
        adapted, connection, socket = chunked_response(payload)
        self.addCleanup(adapted.close)
        model_hook = []
        pieces, result = collect(self.parse(adapted, True, False, model_hook))
        self.assertEqual(pieces, ["こんにちは", "世界🌏"])
        self.assertEqual(result, "こんにちは世界🌏")
        self.assertEqual(model_hook, ["owned-alias"] * 3)
        self.assert_closed(adapted, connection, socket)

    def test_done_sentinel_closes_before_invalid_trailer(self):
        payload = event("訳文") + b"data: [DONE]\n\ndata: invalid\n\n"
        adapted, connection, socket = chunked_response(payload)
        self.addCleanup(adapted.close)
        pieces, result = collect(self.parse(adapted, True, False))
        self.assertEqual((pieces, result), (["訳文"], "訳文"))
        self.assert_closed(adapted, connection, socket)

    def test_parser_failure_closes_stream(self):
        adapted, connection, socket = chunked_response(b"data: invalid\n\n")
        self.addCleanup(adapted.close)
        with self.assertRaisesRegex(Exception, "invalid"):
            collect(self.parse(adapted, True, False))
        self.assert_closed(adapted, connection, socket)


if __name__ == "__main__":
    unittest.main()
