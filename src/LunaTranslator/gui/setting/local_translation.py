"""Explicit first-use setup for the isolated Hy-MT2 local translator."""

import copy
import os
from pathlib import Path
import threading

from qtsymbols import *
import gobject
import NativeUtils
from myutils.config import globalconfig, _TR
from myutils.local_model_download import (
    MODEL_PRESETS, download_model, verify_model, CancelledDownload,
)
from myutils.local_translation import (
    PROVIDER_ID, setup_config, set_local_enabled, local_server,
)


class LocalTranslationDialog(QDialog):
    progress = pyqtSignal(object, object)
    finished_job = pyqtSignal(str, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(_TR("本地翻译 · Hy-MT2（实验性）"))
        self.resize(680, 620)
        self.settings = setup_config(globalconfig)
        self.busy = False
        self.cancel = threading.Event()
        layout = QVBoxLayout(self)
        intro = QLabel(_TR(
            "实验性功能，翻译可能出现语义或占位符错误，尚未证明优于在线翻译。免 API Key，本地推理。首次使用需自行选择官方 llama.cpp 运行库，并下载模型或导入同版本 GGUF。\n"
            "仅本预设连接 127.0.0.1，不会自动回退到付费云端。原有接口开关保持不变；"
            "如需所有翻译均离线，请在翻译设置中手动关闭其他在线接口。"
        ))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self.presets = QComboBox()
        for key, preset in MODEL_PRESETS.items():
            self.presets.addItem(preset["title"] + _TR("（实验性）"), key)
        index = self.presets.findData(self.settings["preset"])
        self.presets.setCurrentIndex(max(0, index))
        form.addRow(_TR("模型"), self.presets)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setOpenExternalLinks(True)
        form.addRow(self.details)
        self.model_path = QLineEdit(self.settings["model"])
        self.model_path.setReadOnly(True)
        form.addRow(_TR("已选模型"), self.model_path)
        buttons = QHBoxLayout()
        self.download = QPushButton(_TR("下载并校验模型"))
        self.import_model = QPushButton(_TR("导入同版本 GGUF…"))
        buttons.addWidget(self.download)
        buttons.addWidget(self.import_model)
        form.addRow(buttons)
        self.runtime_path = QLineEdit(self.settings["runtime"])
        self.runtime_path.setReadOnly(True)
        self.pick_runtime = QPushButton(_TR("选择 llama-server.exe…"))
        form.addRow(_TR("运行库"), self.runtime_path)
        form.addRow(self.pick_runtime)
        runtime_help = QLabel(
            '<a href="https://github.com/ggml-org/llama.cpp/releases">'
            + _TR("官方 llama.cpp Windows x64 运行库") + '</a><br>'
            + _TR("解压后保留 exe 和同目录 DLL；CPU 选择 CPU 包，NVIDIA 可选 CUDA 包。"
                  "也可继续使用原来的 llama.cpp Launcher 下载功能，再在此选择 exe。")
        )
        runtime_help.setWordWrap(True)
        runtime_help.setOpenExternalLinks(True)
        form.addRow(runtime_help)
        self.device = QComboBox()
        self.device.addItem(_TR("CPU（默认，兼容性优先）"), "cpu")
        self.device.addItem(_TR("GPU / 自动（需对应 CUDA / Vulkan 运行库）"), "auto")
        self.device.setCurrentIndex(max(0, self.device.findData(self.settings["device"])))
        form.addRow(_TR("运行方式"), self.device)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(self.settings["port"])
        form.addRow(_TR("本机端口"), self.port)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        form.addRow(self.bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow(self.status)
        controls = QHBoxLayout()
        self.start = QPushButton(_TR("启动并启用实验性本地翻译"))
        self.stop = QPushButton(_TR("停止本地翻译"))
        self.cancel_button = QPushButton(_TR("取消当前操作"))
        controls.addWidget(self.start)
        controls.addWidget(self.stop)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        footer = QHBoxLayout()
        log_button = QPushButton(_TR("打开本地服务日志"))
        close_button = QPushButton(_TR("关闭"))
        footer.addWidget(log_button)
        footer.addStretch()
        footer.addWidget(close_button)
        layout.addLayout(footer)
        note = QLabel(_TR("关闭窗口会取消未完成的下载 / 启动；已就绪的模型会继续运行。"
                          "上下文固定为 2048，单请求；固定采用官方四项采样参数。轻量模型可能出现语义错误，尚未证明优于在线翻译。"))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.presets.currentIndexChanged.connect(self.change_preset)
        self.device.currentIndexChanged.connect(lambda _: self.settings.__setitem__("device", self.device.currentData()))
        self.port.valueChanged.connect(lambda value: self.settings.__setitem__("port", value))
        self.pick_runtime.clicked.connect(self.choose_runtime)
        self.download.clicked.connect(self.download_selected)
        self.import_model.clicked.connect(self.import_selected)
        self.start.clicked.connect(self.start_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.cancel_button.clicked.connect(self.cancel_job)
        close_button.clicked.connect(self.close)
        log_button.clicked.connect(self.open_log)
        self.progress.connect(self.show_progress)
        self.finished_job.connect(self.job_done)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_state)
        self.timer.start(500)
        self.update_details()
        self.refresh_state()

    def preset(self):
        return MODEL_PRESETS[self.presets.currentData()]

    def model_directory(self):
        return gobject.getcachedir("local-translation-models")

    def change_preset(self, _):
        self.settings["preset"] = self.presets.currentData()
        candidate = Path(self.model_directory()) / self.preset()["filename"]
        self.settings["model"] = str(candidate) if candidate.is_file() else ""
        self.model_path.setText(self.settings["model"])
        self.update_details()

    def update_details(self):
        preset = self.preset()
        lightweight = self.presets.currentData() == "hymt2-1.8b-q4"
        hint = (
            "轻量实验预设：模型约 1.13 GB；建议预留约 3–4 GB 可用内存，CPU 可运行但速度因设备而异。"
            if lightweight else
            "较大实验预设（质量未验证）：模型约 4.62 GB；建议预留约 6–7 GB 显存并留足系统内存。与游戏同时运行时可能不足。"
        )
        self.details.setText(
            _TR(hint) + "<br>" + _TR("资源数值为短上下文规划估计，尚非本程序实测。")
            + '<br><a href="' + preset["license_url"] + '">Tencent Hy-MT2 · Apache-2.0</a>'
            + " · " + _TR("应用仍为 GPL-3.0-only")
            + "<br>" + _TR("下载字节数：") + str(preset["size"])
        )

    def choose_runtime(self):
        path, _ = QFileDialog.getOpenFileName(self, _TR("选择官方 llama.cpp 运行库"), self.settings["runtime"], "llama-server.exe (llama-server.exe)")
        if path:
            self.settings["runtime"] = path
            self.runtime_path.setText(path)

    def run_job(self, kind, job):
        if self.busy:
            return
        self.busy = True
        self.cancel = threading.Event()
        self.bar.setValue(0)
        self.status.setText(_TR({"download": "下载并校验中…", "import": "校验导入模型…", "start": "校验模型并启动中…", "stop": "停止中…"}[kind]))
        self.refresh_state()

        def worker():
            try:
                result = job()
            except Exception as exc:
                result = exc
            self.finished_job.emit(kind, result)

        threading.Thread(target=worker, daemon=True).start()

    def download_selected(self):
        preset = self.preset()
        answer = QMessageBox.question(
            self, _TR("首次模型下载"),
            _TR("从腾讯官方 Hugging Face 仓库下载 {}（{} 字节）？\n"
                "许可证 Apache-2.0，链接已显示。需联网和足够磁盘空间；完成后可离线推理。\n"
                "仅校验成功后安装。取消会清理临时文件，下次重新下载。").format(preset["title"], preset["size"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_job("download", lambda: download_model(preset, self.model_directory(), cancelled=self.cancel.is_set, progress=self.progress.emit))

    def import_selected(self):
        path, _ = QFileDialog.getOpenFileName(self, _TR("导入所选版本的 GGUF（将校验 SHA-256）"), self.settings["model"], "GGUF (*.gguf)")
        if path:
            preset = self.preset()
            self.run_job("import", lambda: verify_model(path, preset, cancelled=self.cancel.is_set, progress=self.progress.emit))

    def start_selected(self):
        # Read Qt widgets on the UI thread before dispatching the worker.
        settings = copy.deepcopy(self.settings)
        preset = self.preset()
        log_path = gobject.getcachedir("local-translation-server.log")
        self.run_job("start", lambda: local_server.start(
            settings, preset, log_path,
            progress=self.progress.emit, guard_factory=NativeUtils.AutoKillProcess,
            cancelled=self.cancel.is_set,
        ))

    def stop_selected(self):
        self.enable_local(False)
        self.run_job("stop", local_server.stop)

    def enable_local(self, enabled):
        set_local_enabled(globalconfig, enabled)
        gobject.base.prepare(PROVIDER_ID)

    def cancel_job(self):
        self.cancel.set()
        if local_server.snapshot()[0] in ("verifying", "starting"):
            local_server.cancel.set()
        self.status.setText(_TR("正在取消，请等待当前读写结束…"))

    def job_done(self, kind, result):
        self.busy = False
        if isinstance(result, CancelledDownload) or self.cancel.is_set():
            if kind == "start":
                self.run_job("stop", local_server.stop)
                return
            self.status.setText(_TR("已取消；未启用新模型"))
        elif isinstance(result, Exception):
            self.status.setText(_TR("操作失败：") + str(result))
        elif kind in ("download", "import"):
            self.settings["model"] = str(result)
            self.model_path.setText(str(result))
            self.status.setText(_TR("模型大小和 SHA-256 校验成功，可以启动"))
            self.bar.setValue(1000)
        elif kind == "start":
            self.enable_local(True)
            self.status.setText(_TR("本地模型已就绪，已启用本地翻译；其他接口开关保持不变"))
        else:
            self.status.setText(_TR("本地翻译已停止"))
        self.refresh_state()

    def show_progress(self, done, total):
        self.bar.setValue(int(done * 1000 / total) if total else 0)
        self.bar.setFormat("{:.1f}%".format(done * 100 / total) if total else "0%")

    def refresh_state(self):
        state, error = local_server.snapshot()
        running = state in ("verifying", "starting", "ready", "stopping")
        for control in (self.presets, self.download, self.import_model, self.pick_runtime, self.device, self.port):
            control.setEnabled(not self.busy and not running)
        self.start.setEnabled(not self.busy and not running)
        self.stop.setEnabled(not self.busy and running)
        self.cancel_button.setEnabled(self.busy)
        if not self.busy and state == "error":
            self.status.setText(error)
            if globalconfig["fanyi"][PROVIDER_ID]["use"]:
                self.enable_local(False)
        elif not self.busy and not self.status.text():
            self.status.setText(_TR("本地模型已就绪" if state == "ready" else "尚未启动；请选择模型和运行库"))

    def open_log(self):
        path = gobject.getcachedir("local-translation-server.log")
        if os.path.isfile(path):
            os.startfile(path)
        else:
            QMessageBox.information(self, _TR("本地翻译"), _TR("尚无服务日志"))

    def reject(self):
        # Escape uses QDialog.reject(), not QWidget.closeEvent().
        if self.busy:
            self.cancel_job()
        super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.cancel_job()
        super().closeEvent(event)


def show_local_translation(parent):
    # Reuse the dialog so closing/reopening during a cancellation cannot start
    # a competing download or create a second launcher.
    dialog = getattr(gobject.base, "local_translation_dialog", None)
    if dialog is None:
        dialog = LocalTranslationDialog(parent)
        gobject.base.local_translation_dialog = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
