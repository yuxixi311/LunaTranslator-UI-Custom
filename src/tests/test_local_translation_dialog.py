"""Headless method-level UI regression checks, not a Qt/Windows UI pass."""

import ast
import copy
from pathlib import Path
import threading
import types
import unittest

PATH = Path(__file__).resolve().parents[1] / "LunaTranslator/gui/setting/local_translation.py"


def dialog_class(namespace):
    tree = ast.parse(PATH.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    wanted = {"reject", "closeEvent", "cancel_job", "start_selected"}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    class FakeDialog:
        def reject(self):
            self.dismissed = True
        def closeEvent(self, event):
            self.dismissed = True
    namespace.update(QDialog=FakeDialog, copy=copy, _TR=lambda text: text)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), str(PATH), "exec"), namespace)
    return namespace["LocalTranslationDialog"]


class DialogMethodTests(unittest.TestCase):
    def setUp(self):
        self.server = types.SimpleNamespace(cancel=threading.Event(), snapshot=lambda: ("starting", ""))
        self.cls = dialog_class({"local_server": self.server})
        self.dialog = self.cls()
        self.dialog.busy = True
        self.dialog.cancel = threading.Event()
        self.dialog.status = types.SimpleNamespace(setText=lambda text: None)

    def test_escape_and_close_cancel_busy_work(self):
        for action in (lambda: self.dialog.reject(), lambda: self.dialog.closeEvent(None)):
            self.dialog.cancel.clear()
            self.server.cancel.clear()
            action()
            self.assertTrue(self.dialog.cancel.is_set())
            self.assertTrue(self.server.cancel.is_set())
            self.assertTrue(self.dialog.dismissed)

    def test_dismissal_keeps_ready_model_running(self):
        self.dialog.busy = False
        self.dialog.reject()
        self.assertFalse(self.dialog.cancel.is_set())
        self.assertFalse(self.server.cancel.is_set())

    def test_start_snapshots_widgets_before_worker_dispatch(self):
        callbacks = []
        launches = []
        server = types.SimpleNamespace(start=lambda *args, **kwargs: launches.append((args, kwargs)))
        cls = dialog_class({
            "local_server": server,
            "gobject": types.SimpleNamespace(getcachedir=lambda _: "synthetic-log"),
            "NativeUtils": types.SimpleNamespace(AutoKillProcess="synthetic-guard"),
        })
        dialog = cls()
        dialog.settings = {"port": 18080}
        dialog.preset = lambda: {"filename": "before.gguf"}
        dialog.progress = types.SimpleNamespace(emit=lambda *args: None)
        dialog.cancel = threading.Event()
        dialog.run_job = lambda kind, job: callbacks.append(job)
        dialog.start_selected()
        dialog.settings["port"] = 18081
        def forbidden_widget_read():
            raise AssertionError("worker read a Qt widget")
        dialog.preset = forbidden_widget_read
        callbacks[0]()
        self.assertEqual(launches[0][0][0]["port"], 18080)
        self.assertEqual(launches[0][0][1]["filename"], "before.gguf")


if __name__ == "__main__":
    unittest.main()
