"""Synthetic lifecycle/config tests; no Qt, Windows runtime, weights or network."""

import ast
import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "LunaTranslator"
sys.path.insert(0, str(APP))
from myutils import local_translation as local
from myutils.local_model_download import CancelledDownload


class FakeProcess:
    pid = 12345
    returncode = None

    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class LocalTranslationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = self.root / "llama-server.exe"
        self.exe.write_bytes(b"synthetic, never executed")
        self.model = self.root / "model.gguf"
        self.model.write_bytes(b"synthetic, never loaded")
        self.server = local.LocalServer()
        self.addCleanup(self.server.stop)
        self.settings = dict(runtime=str(self.exe), model=str(self.model), port=18080, device="cpu")

    def start(self, **kwargs):
        # Fake children need a fake valid Windows job guard, never an OS handle.
        kwargs.setdefault("guard_factory", lambda pid: types.SimpleNamespace(_refkep=object()))
        self.server.start(self.settings, {}, self.root / "server.log", **kwargs)

    def test_setup_and_toggle_preserve_all_other_settings(self):
        config = {
            "fanyi": {"google": {"use": True}, "deepseek": {"use": False, "key": "synthetic-key"}, local.PROVIDER_ID: {"use": False}},
            "llama.cpp": {"host": "192.168.1.8", "model": "old.gguf", "autolaunch": True},
            "custom": [1, 2],
        }
        before = copy.deepcopy(config)
        local.setup_config(config)
        local.set_local_enabled(config, True)
        local.set_local_enabled(config, False)
        del config["local_translation"]
        self.assertEqual(config, before)

    def test_new_defaults_are_additive_and_disabled(self):
        config = json.loads((APP / "defaultconfig/config.json").read_text())
        self.assertFalse(config["fanyi"][local.PROVIDER_ID]["use"])
        args = json.loads((APP / "defaultconfig/translatorsetting.json").read_text())[local.PROVIDER_ID]["args"]
        self.assertEqual(args["prompt_version_1"], "Hy-MT2")
        self.assertEqual(args["API接口地址"], "http://127.0.0.1:18080/")
        self.assertEqual(args["customparams"], [])

    def test_existing_local_selection_survives_opening(self):
        config = {"local_translation": dict(self.settings, preset="hymt2-7b-q4")}
        before = copy.deepcopy(config)
        local.setup_config(config)
        self.assertEqual(config, before)

    def test_commands_are_loopback_only_and_no_shell_string(self):
        command = local.build_command(self.exe, self.model, 18080, "cpu", "test-model")
        self.assertIsInstance(command, list)
        self.assertEqual(command[command.index("--host") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("--gpu-layers") + 1], "0")
        self.assertIn("none", command)
        gpu = local.build_command(self.exe, self.model, 18080, "auto", "test-model")
        self.assertNotIn("--device", gpu)
        self.assertEqual(gpu[gpu.index("--gpu-layers") + 1], "99")

    def test_rejects_external_or_ambiguous_urls_and_invalid_ports(self):
        for url in ("http://localhost:18080/", "http://127.0.0.1:18081/", "http://127.0.0.1:18080@evil.example/", "https://127.0.0.1:18080/", "http://127.0.0.1:18080/?x=1", "http://127.0.0.1:18080/#x"):
            with self.subTest(url=url), self.assertRaises(local.LocalTranslationError):
                local.validate_local_url(url, 18080)
        for port in (0, 80, 65536, True, "18080"):
            with self.subTest(port=port), self.assertRaises(local.LocalTranslationError):
                local.loopback_url(port)

    def test_sanitized_args_pin_prompt_and_do_not_mutate_saved_args(self):
        original = {"API接口地址": "https://cloud.example/", "prompt_version_1": "auto", "customparams": [{"key": "api_key"}], "max_tokens": 1000000, "append_context_num": 99999}
        before = copy.deepcopy(original)
        result = local.local_args(original, 18080, "local-model")
        self.assertEqual(original, before)
        self.assertEqual(result["prompt_version_1"], "Hy-MT2")
        self.assertEqual(result["customparams"], [])
        self.assertEqual(result["model"], "local-model")
        self.assertEqual(result["max_tokens"], 1024)
        self.assertEqual(result["append_context_num"], 3)

    def test_occupied_port_does_not_spawn_or_kill_anything(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.settings["port"] = listener.getsockname()[1]
            with patch("myutils.local_model_download.verify_model"), patch.object(local.subprocess, "Popen") as popen:
                with self.assertRaises(local.LocalTranslationError):
                    self.start()
                popen.assert_not_called()
            self.assertEqual(self.server.state, "error")

    def test_requires_health_and_matching_model_then_stops_only_owned_process(self):
        process = FakeProcess()
        def status(url, port):
            return {"status": "ok"} if url.endswith("health") else {"data": [{"id": self.server.alias}]}
        with patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process) as popen, patch.object(local, "local_json", side_effect=status):
            with patch.object(local, "os", types.SimpleNamespace(name="nt")):
                self.start()
            self.assertEqual(self.server.require_ready(), (18080, self.server.alias))
            self.assertFalse(popen.call_args.kwargs["shell"])
            with self.assertRaises(local.LocalTranslationError):
                self.start()
            self.server.stop()
        self.assertTrue(process.terminated)
        self.assertEqual(self.server.state, "stopped")

    def test_wrong_model_never_ready_and_is_cleaned_up(self):
        process = FakeProcess()
        with patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process), patch.object(local, "local_json", return_value={"status": "ok", "data": [{"id": "someone-else"}]}):
            with self.assertRaises(local.LocalTranslationError):
                self.start(timeout=0.01)
        self.assertTrue(process.terminated)
        self.assertIsNone(self.server.process)

    def test_early_exit_is_not_ready(self):
        process = FakeProcess()
        process.returncode = 2
        with patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process):
            with self.assertRaises(local.LocalTranslationError):
                self.start()
        self.assertEqual(self.server.state, "error")

    def test_close_before_worker_start_cancels_without_launch(self):
        def verify(*args, **kwargs):
            if kwargs["cancelled"]():
                raise CancelledDownload()
        with patch("myutils.local_model_download.verify_model", side_effect=verify), patch.object(local.subprocess, "Popen") as popen:
            with self.assertRaises(CancelledDownload):
                self.start(cancelled=lambda: True)
            popen.assert_not_called()
        self.assertEqual(self.server.state, "stopped")

    def test_missing_windows_job_guard_fails_and_stops_own_process(self):
        for guard in (None, types.SimpleNamespace(_refkep=None)):
            process = FakeProcess()
            with self.subTest(guard=guard), patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process):
                with self.assertRaises(local.LocalTranslationError):
                    self.start(guard_factory=lambda pid: guard)
            self.assertTrue(process.terminated)
            self.assertNotEqual(self.server.state, "ready")

    def test_windows_missing_guard_factory_fails_before_readiness(self):
        process = FakeProcess()
        with patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process), patch.object(local, "local_json") as health, patch.object(local, "os", types.SimpleNamespace(name="nt")):
            with self.assertRaisesRegex(local.LocalTranslationError, "Windows 本地启动需要进程退出保护"):
                self.start(guard_factory=None)
            health.assert_not_called()
        self.assertTrue(process.terminated)
        self.assertIsNone(self.server.process)
        self.assertIsNone(self.server.guard)
        self.assertIsNone(self.server.log)
        self.assertEqual(self.server.state, "error")

    def test_guard_factory_failure_stops_owned_process_before_readiness(self):
        process = FakeProcess()
        def fail_guard(pid):
            self.assertEqual(pid, process.pid)
            raise OSError("synthetic job failure")
        with patch("myutils.local_model_download.verify_model"), patch.object(local, "check_port_available"), patch.object(local.subprocess, "Popen", return_value=process), patch.object(local, "local_json") as health:
            with self.assertRaisesRegex(OSError, "synthetic job failure"):
                self.start(guard_factory=fail_guard)
            health.assert_not_called()
        self.assertTrue(process.terminated)
        self.assertIsNone(self.server.process)
        self.assertIsNone(self.server.guard)
        self.assertIsNone(self.server.log)
        self.assertEqual(self.server.state, "error")

    def test_status_poll_does_not_block_behind_slow_stop(self):
        waiting = threading.Event()
        release = threading.Event()
        process = FakeProcess()
        def wait(timeout=None):
            waiting.set()
            release.wait(2)
            return 0
        process.wait = wait
        self.server.process = process
        self.server.state = "ready"
        worker = threading.Thread(target=self.server.stop)
        worker.start()
        self.assertTrue(waiting.wait(1))
        try:
            result = []
            poller = threading.Thread(target=lambda: result.append(self.server.snapshot()))
            poller.start()
            poller.join(timeout=0.2)
            self.assertFalse(poller.is_alive(), "UI status poll blocked during stop")
            self.assertEqual(result[0][0], "stopping")
        finally:
            release.set()
            worker.join(timeout=2)

    def test_process_death_removes_ready_state(self):
        process = FakeProcess()
        self.server.process = process
        self.server.state = "ready"
        process.returncode = 1
        with self.assertRaises(local.LocalTranslationError):
            self.server.require_ready()
        self.assertEqual(self.server.state, "error")

    def test_http_redirects_are_refused(self):
        with self.assertRaises(local.LocalTranslationError):
            local._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://remote.example")


class LocalTransportTests(unittest.TestCase):
    def test_real_transport_is_direct_and_ignores_environment_proxy(self):
        import http.server
        import os
        from myutils.local_transport import LocalSession
        seen = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.path, body, dict(self.headers)))
                payload = json.dumps({"choices": [{"message": {"content": "synthetic translation"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            with patch.object(local.local_server, "require_ready", return_value=(port, "owned-model")), patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}):
                session = LocalSession()
                response = session.post("http://127.0.0.1:{}/v1/chat/completions".format(port), json={"model": "wrong", "messages": []}, proxies={"http": "bad"}, headers={"Authorization": "secret"})
                self.assertEqual(response.json()["choices"][0]["message"]["content"], "synthetic translation")
                session.close_response()
                with self.assertRaises(local.LocalTranslationError):
                    session.post("https://remote.example/chat", json={})
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0][1]["model"], "owned-model")
            for key, value in local.HYMT2_SAMPLING.items():
                self.assertEqual(seen[0][1][key], value)
            self.assertNotIn("repetition_penalty", seen[0][1])
            self.assertNotIn("Authorization", seen[0][2])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_stream_and_redirect_response_cleanup(self):
        import io
        from email.message import Message
        from myutils import local_transport as transport
        connection = types.SimpleNamespace(close=lambda: None)
        response = io.BytesIO(b'data: {"choices": []}\n\ndata: [DONE]\n')
        response.status = 200
        response.headers = Message()
        adapted = transport.LocalResponse(connection, response)
        self.assertEqual(list(adapted.iter_lines(decode_unicode=True)), ['data: {"choices": []}', '', 'data: [DONE]'])
        self.assertTrue(response.closed)
        raw = io.BytesIO(b'')
        raw.status = 302
        raw.headers = Message()
        raw.headers["Location"] = "https://remote.example"
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.getresponse.return_value = raw
        with patch.object(local.local_server, "require_ready", return_value=(18080, "model")), patch.object(transport.http.client, "HTTPConnection", return_value=connection) as factory:
            with self.assertRaises(local.LocalTranslationError):
                transport.LocalSession().post("http://127.0.0.1:18080/v1/chat/completions", json={})
            factory.assert_called_once_with("127.0.0.1", 18080, timeout=3)
            self.assertTrue(raw.closed)
            self.assertTrue(connection.close.called)


if __name__ == "__main__":
    unittest.main()
