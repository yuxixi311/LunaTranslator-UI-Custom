"""Isolated, opt-in Hy-MT2 preset and owned llama.cpp process lifecycle.

This is a launcher around the existing llama.cpp/Sakura implementation, not an
inference engine. It never changes another provider or the advanced launcher.
"""

import atexit
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler
import uuid

PROVIDER_ID = "local_hymt"
DEFAULT_PORT = 18080
DEFAULT_PRESET = "hymt2-1.8b-q4"
# Tencent's 1.8B / 7B card, immutable revision 9a341cd1b679d3efd23b46e847b01745a71ed792.
# llama.cpp names the repetition field repeat_penalty, unlike transformers.
HYMT2_SAMPLING = {
    "temperature": 0.7,
    "top_p": 0.6,
    "top_k": 20,
    "repeat_penalty": 1.05,
}


class LocalTranslationError(Exception):
    pass


def setup_config(config):
    """Only initialize our own namespace; never migrate existing settings."""
    settings = config.setdefault("local_translation", {})
    for key, value in {
        "preset": DEFAULT_PRESET,
        "runtime": "",
        "model": "",
        "device": "cpu",
        "port": DEFAULT_PORT,
    }.items():
        settings.setdefault(key, value)
    return settings


def set_local_enabled(config, enabled):
    config["fanyi"][PROVIDER_ID]["use"] = bool(enabled)


def loopback_url(port):
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise LocalTranslationError("本地端口必须是 1024–65535 之间的整数")
    return "http://127.0.0.1:{}/".format(port)


def validate_local_url(url, port):
    expected = urlsplit(loopback_url(port))
    parsed = urlsplit(url)
    if (
        parsed.scheme != expected.scheme
        or parsed.netloc != expected.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise LocalTranslationError("本地翻译仅允许连接此预设的 127.0.0.1 端口")
    return url


def local_args(args, port, alias):
    result = copy.deepcopy(dict(args))
    result.update({
        "API接口地址": loopback_url(port),
        "model": alias,
        "prompt_version_1": "Hy-MT2",
        "customparams": [],
        "Temperature": HYMT2_SAMPLING["temperature"],
        "Temperature.use": True,
        "top_p": HYMT2_SAMPLING["top_p"],
        "top_p_use": True,
        "top_k": HYMT2_SAMPLING["top_k"],
        "repetition_penalty": HYMT2_SAMPLING["repeat_penalty"],
        "repetition_penalty_use": True,
        "frequency_penalty_use": False,
    })
    # A short-context preset must not request a million output tokens.
    result["max_tokens"] = min(1024, max(1, int(result.get("max_tokens", 512))))
    result["append_context_num"] = min(3, max(1, int(result.get("append_context_num", 3))))
    return result


def build_command(runtime, model, port, device, alias):
    loopback_url(port)
    if device not in ("cpu", "auto"):
        raise LocalTranslationError("请选择 CPU 或 GPU / 自动")
    command = [
        str(Path(runtime).resolve()), "-m", str(Path(model).resolve()),
        "--host", "127.0.0.1", "--port", str(port), "--ctx-size", "2048",
        "--parallel", "1", "--alias", alias,
        "--gpu-layers", "0" if device == "cpu" else "99",
    ]
    if device == "cpu":
        command.extend(["--device", "none"])
    return command


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise LocalTranslationError("拒绝本地服务重定向")


def local_json(url, port):
    validate_local_url(url, port)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(url, timeout=2) as response:
        if response.status != 200:
            raise LocalTranslationError("本地服务尚未就绪")
        data = response.read(64 * 1024 + 1)
        if len(data) > 64 * 1024:
            raise LocalTranslationError("本地状态响应过大")
        return json.loads(data.decode("utf-8"))


def check_port_available(port):
    loopback_url(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise LocalTranslationError("端口 {} 已被占用或不可用；请更换端口，不会停止其他程序".format(port)) from exc


class LocalServer:
    """Keep a handle only to the process created by this preset.

    No PID discovery, process-name kill, or connection to someone else's server.
    A fresh alias ties readiness to this launch, rather than any HTTP listener.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.process = None
        self.guard = None
        self.log = None
        self.state = "stopped"
        self.error = ""
        self.port = None
        self.alias = None

    def snapshot(self):
        # UI timers must not wait behind process termination/reaping. State/error
        # are immutable values; a busy lifecycle operation exposes its last state.
        if not self.lock.acquire(blocking=False):
            return self.state, self.error
        try:
            if self.process is not None and self.process.poll() is not None:
                self.state = "error"
                self.error = "本地模型进程已退出（代码 {}）；请查看日志，检查内存、显存和运行库".format(self.process.returncode)
            return self.state, self.error
        finally:
            self.lock.release()

    def require_ready(self):
        with self.lock:
            state, error = self.snapshot()
            if state != "ready":
                raise LocalTranslationError(error or "请先在常用设置中启动本地翻译并等待就绪")
            return self.port, self.alias

    def start(self, settings, preset, log_path, progress=None, guard_factory=None, timeout=180, cancelled=None):
        from myutils.local_model_download import verify_model, CancelledDownload

        settings = copy.deepcopy(settings)
        is_cancelled = lambda: self.cancel.is_set() or bool(cancelled and cancelled())
        with self.lock:
            if self.state in ("verifying", "starting", "ready", "stopping"):
                raise LocalTranslationError("本地模型已启动或正在处理，请先停止")
            self._cleanup()
            self.cancel.clear()
            self.error = ""
            self.state = "verifying"
        try:
            runtime = Path(settings.get("runtime", ""))
            model = Path(settings.get("model", ""))
            if not runtime.is_file() or runtime.name.lower() != "llama-server.exe":
                raise LocalTranslationError("请先选择官方 llama.cpp 的 llama-server.exe（需保留同目录 DLL）")
            verify_model(model, preset, cancelled=is_cancelled, progress=progress or (lambda *_: None))
            port = settings.get("port", DEFAULT_PORT)
            check_port_available(port)
            alias = "luna-local-" + uuid.uuid4().hex
            command = build_command(runtime, model, port, settings.get("device", "cpu"), alias)
            with self.lock:
                if is_cancelled():
                    raise CancelledDownload()
                self.log = open(log_path, "ab", buffering=0)
                # Never pass a shell or reuse advanced-launcher environment overrides.
                self.process = subprocess.Popen(
                    command, cwd=str(runtime.resolve().parent), stdin=subprocess.DEVNULL,
                    stdout=self.log, stderr=subprocess.STDOUT, shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if guard_factory:
                    self.guard = guard_factory(self.process.pid)
                    if not getattr(self.guard, "_refkep", None):
                        raise LocalTranslationError("无法保护本地模型进程的退出生命周期，已停止本次启动")
                elif os.name == "nt":
                    raise LocalTranslationError("Windows 本地启动需要进程退出保护")
                self.port, self.alias = port, alias
                self.state = "starting"
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if is_cancelled():
                    raise CancelledDownload()
                with self.lock:
                    if self.process is None or self.process.poll() is not None:
                        raise LocalTranslationError("llama-server 启动失败；请检查日志、DLL、模型兼容性和可用内存")
                try:
                    health = local_json(loopback_url(port) + "health", port)
                    models = local_json(loopback_url(port) + "v1/models", port)
                    if health.get("status") == "ok" and any(
                        item.get("id") == alias for item in models.get("data", [])
                    ):
                        with self.lock:
                            if is_cancelled() or self.process is None or self.process.poll() is not None:
                                raise CancelledDownload()
                            self.state = "ready"
                        return
                except CancelledDownload:
                    raise
                except (OSError, ValueError, LocalTranslationError, AttributeError):
                    pass
                self.cancel.wait(0.25)
            raise LocalTranslationError("模型在 180 秒内未就绪；请查看日志或改用较小模型 / CPU")
        except Exception as exc:
            with self.lock:
                self._cleanup()
                self.state = "stopped" if isinstance(exc, CancelledDownload) else "error"
                self.error = "" if isinstance(exc, CancelledDownload) else str(exc)
            raise

    def _cleanup(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
        self.guard = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def stop(self):
        self.cancel.set()
        with self.lock:
            self.state = "stopping"
            self._cleanup()
            self.state = "stopped"
            self.error = ""


local_server = LocalServer()
atexit.register(local_server.stop)
