"""Small response adapter for Sakura, using direct loopback HTTP only.

The application's custom requests backends can use native/system proxies even
when passed None. HTTPConnection talks directly to a literal loopback address;
no proxy discovery, redirects, cookies, credentials or remote fallback exist.
"""

import http.client
import json
import threading
from urllib.parse import urlsplit

from myutils.local_translation import (
    LocalTranslationError, local_server, validate_local_url,
)

_MAX_RESPONSE = 4 * 1024 * 1024


class LocalResponse:
    def __init__(self, connection, response):
        self.connection = connection
        self.response = response
        self.status_code = response.status
        self.headers = response.headers
        self._content = None

    def close(self):
        try:
            self.response.close()
        finally:
            self.connection.close()

    @property
    def content(self):
        if self._content is None:
            try:
                self._content = self.response.read(_MAX_RESPONSE + 1)
                if len(self._content) > _MAX_RESPONSE:
                    raise LocalTranslationError("本地翻译响应过大")
            finally:
                self.close()
        return self._content

    @property
    def text(self):
        return self.content.decode("utf-8")

    def json(self):
        return json.loads(self.text)

    def iter_lines(self, decode_unicode=False, **kwargs):
        received = 0
        try:
            while True:
                line = self.response.readline(_MAX_RESPONSE + 1)
                if not line:
                    break
                received += len(line)
                if received > _MAX_RESPONSE:
                    raise LocalTranslationError("本地翻译流响应过大")
                line = line.rstrip(b"\r\n")
                yield line.decode("utf-8") if decode_unicode else line
        finally:
            self.close()

    def __del__(self):
        self.close()


class LocalSession:
    def __init__(self):
        self._responses = threading.local()

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def request(self, method, url, **kwargs):
        port, alias = local_server.require_ready()
        validate_local_url(url, port)
        path = urlsplit(url).path
        if method != "POST" or path not in ("/v1/chat/completions", "/chat/completions"):
            raise LocalTranslationError("本地预设仅支持翻译请求")
        body = dict(kwargs.get("json") or {})
        body["model"] = alias
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.connect()
            connection.sock.settimeout(180)
            connection.request(
                "POST", path, body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "*/*", "Connection": "close"},
            )
            response = LocalResponse(connection, connection.getresponse())
            if response.status_code != 200:
                response.close()
                raise LocalTranslationError("本地翻译服务返回错误 {}；不会切换到云端接口".format(response.status_code))
            self._responses.current = response
            return response
        except (OSError, http.client.HTTPException) as exc:
            connection.close()
            raise LocalTranslationError("本地翻译连接失败或超时；请检查模型状态") from exc
        except Exception:
            connection.close()
            raise

    def close_response(self):
        response = getattr(self._responses, "current", None)
        if response is not None:
            response.close()
            self._responses.current = None
