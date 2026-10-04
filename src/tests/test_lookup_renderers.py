"""Exercise actual renderer event handlers with small Qt/native test doubles.

These tests cover dispatch and cancellation, not native Windows focus ordering.
"""

import ast
import functools
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1] / "LunaTranslator"
LEFT, RIGHT, MIDDLE = 1, 2, 4


class Event:
    def __init__(self, button=LEFT, timestamp=100, pos=(5, 5)):
        self._button, self._timestamp, self._pos = button, timestamp, pos
        self.ignored = False

    def button(self):
        return self._button

    def timestamp(self):
        return self._timestamp

    def pos(self):
        return self._pos

    def ignore(self):
        self.ignored = True


class Signal:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def emit(self, *args):
        self.log.append((self.name, args))


class Widget:
    def focusOutEvent(self, event):
        pass

    def mousePressEvent(self, event):
        self.base_presses += 1

    def mouseReleaseEvent(self, event):
        self.base_releases += 1

    def mouseDoubleClickEvent(self, event):
        # QTextEdit handles double-click selection without calling the subclass
        # mousePressEvent again. The subclass must announce its new gesture.
        self.base_double_clicks += 1
        self.pr = "selected word"


def load_renderer(name, namespace):
    path = ROOT / "gui/rendertext/textbrowser.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    cls.bases = [ast.Name(id="Widget", ctx=ast.Load())]
    # Retain press helper methods as implementations evolve, while avoiding the
    # real renderer constructor and all painting/layout machinery.
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and
                (node.name.startswith("mouse") or "press" in node.name.lower()
                 or node.name == "focusOutEvent")]
    for node in ast.walk(cls):
        if isinstance(node, ast.arg):
            node.annotation = None
        elif isinstance(node, ast.FunctionDef):
            node.returns = None
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class RendererDispatchTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        base = SimpleNamespace(
            lookup_source_pressed=Signal(self.log, "press"),
            lookup_source_released=Signal(self.log, "release"),
            clickwordcallback=lambda *args: self.log.append(("lookup", args)),
        )
        namespace = {
            "Widget": Widget,
            "Qt": SimpleNamespace(MouseButton=SimpleNamespace(LeftButton=LEFT, RightButton=RIGHT, MiddleButton=MIDDLE)),
            "gobject": SimpleNamespace(base=base),
            "tooltipswidget": SimpleNamespace(hidetooltipwindow=lambda source_left=True:
                self.log.append(("hide_tooltip", (source_left,)))),
            "print_exc": lambda: None,
        }
        self.label_class = load_renderer("Qlabel_c", dict(namespace))
        self.text_class = load_renderer("QTextBrowser_1", dict(namespace))

    def make_widget(self, selectable=False):
        widget = (self.text_class if selectable else self.label_class)()
        widget.base_presses = widget.base_releases = widget.base_double_clicks = 0
        widget.word = {"word": "猫"}
        widget.inside = True
        widget.rect = lambda: SimpleNamespace(contains=lambda pos: widget.inside)
        widget.pr = None
        widget.prpos = None
        widget.ignorecount = 0
        widget.ismousehastext = lambda event: True
        widget.textCursor = lambda: SimpleNamespace(clearSelection=lambda: None)
        widget.setTextCursor = lambda cursor: None
        widget.getcurrlabel = lambda pos: SimpleNamespace(refmask=SimpleNamespace(word=widget.word))
        return widget

    def test_label_left_and_right_share_press_token_with_lookup_and_release(self):
        for button in (LEFT, RIGHT):
            with self.subTest(button=button):
                self.log.clear()
                widget = self.make_widget()
                event = Event(button)
                widget.mousePressEvent(event)
                widget.mouseReleaseEvent(event)
                self.assertEqual([name for name, _ in self.log], ["press", "lookup", "release"])
                token = self.log[0][1][0]
                self.assertEqual(self.log[1][1], (widget.word, button == RIGHT, token))
                self.assertEqual(self.log[2][1], (token,))

    def test_label_release_outside_cancels_without_lookup(self):
        widget = self.make_widget()
        event = Event()
        widget.mousePressEvent(event)
        widget.inside = False
        widget.mouseReleaseEvent(event)
        self.assertEqual([name for name, _ in self.log], ["press", "release"])

    def test_selectable_right_early_return_still_releases_gesture(self):
        widget = self.make_widget(selectable=True)
        event = Event(RIGHT)
        widget.mousePressEvent(event)
        widget.mouseReleaseEvent(event)
        self.assertTrue(event.ignored)
        self.assertEqual([name for name, _ in self.log], ["press", "lookup", "release"])
        self.assertEqual(self.log[0][1], self.log[-1][1])

    def test_selectable_drag_selection_releases_without_lookup(self):
        widget = self.make_widget(selectable=True)
        widget.mousePressEvent(Event())
        widget.pr = "selection"
        widget.mouseReleaseEvent(Event(pos=(8, 5)))
        self.assertEqual([name for name, _ in self.log], ["press", "release"])

    def test_selectable_right_existing_selection_releases_without_lookup(self):
        widget = self.make_widget(selectable=True)
        widget.pr = "selection"
        event = Event(RIGHT)
        widget.mousePressEvent(event)
        widget.mouseReleaseEvent(event)
        self.assertEqual([name for name, _ in self.log], ["press", "release"])

    def test_selectable_blank_press_has_lifecycle(self):
        widget = self.make_widget(selectable=True)
        widget.ismousehastext = lambda event: False
        widget.getcurrlabel = lambda pos: None
        event = Event()
        widget.mousePressEvent(event)
        widget.mouseReleaseEvent(event)
        self.assertEqual([name for name, _ in self.log], ["press", "release"])
        self.assertTrue(event.ignored)
        self.assertEqual(widget.ignorecount, 0)

    def test_selectable_double_click_has_fresh_token_and_preserves_selection(self):
        widget = self.make_widget(selectable=True)
        first = Event(timestamp=100)
        widget.mousePressEvent(first)
        widget.mouseReleaseEvent(first)
        second = Event(timestamp=180)
        widget.mouseDoubleClickEvent(second)
        widget.mouseReleaseEvent(second)
        presses = [args[0] for name, args in self.log if name == "press"]
        self.assertEqual(len(presses), 2)
        self.assertNotEqual(presses[0], presses[1])
        self.assertEqual(widget.base_double_clicks, 1)
        self.assertEqual(widget.pr, "selected word")
        self.assertEqual(self.log[-1], ("release", (presses[-1],)))

    def test_selectable_exception_still_releases_gesture(self):
        widget = self.make_widget(selectable=True)
        event = Event()
        widget.mousePressEvent(event)

        def broken_label(pos):
            raise ValueError("renderer changed during release")

        widget.getcurrlabel = broken_label
        widget.mouseReleaseEvent(event)
        self.assertEqual([name for name, _ in self.log], ["press", "release"])

    def test_selectable_focus_loss_does_not_claim_pointer_left_word(self):
        widget = self.make_widget(selectable=True)
        widget.focusOutEvent(None)
        self.assertEqual(self.log, [("hide_tooltip", (False,))])


class TransparentPollingTests(unittest.TestCase):
    def setUp(self):
        self.log, self.jobs, self.eval_callbacks = [], [], []
        self.buttons = set()
        self.inside = True
        base = SimpleNamespace(
            lookup_source_pressed=Signal(self.log, "press"),
            lookup_source_released=Signal(self.log, "release"),
            clickwordcallback=lambda *args: self.log.append(("lookup", args)),
        )
        path = ROOT / "gui/rendertext/webview.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TextBrowser")
        cls.bases = []
        methods = {"_cancel_lookup_mouse", "__starttrans0checker", "__checkmousestate",
                   "__callback", "_handle_lookup_mouse", "getundermouseword"}
        cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in methods]
        namespace = {
            "functools": functools, "uuid": uuid, "json": json,
            "gobject": SimpleNamespace(base=base),
            "QCursor": SimpleNamespace(pos=lambda: (5, 5)),
            "WordSegResult": SimpleNamespace(from_dict=lambda value: value),
            "windows": SimpleNamespace(VK_LBUTTON=LEFT, VK_RBUTTON=RIGHT,
                GetAsyncKeyState=lambda button: -32768 if button in self.buttons else 0),
            "tooltipswidget": SimpleNamespace(
                hidetooltipwindow=lambda: self.log.append(("leave", ())),
                tracetooltipwindow=lambda *args: self.log.append(("hover", args))),
        }
        module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
        exec(compile(module, str(path), "exec"), namespace)
        self.widget = namespace["TextBrowser"]()
        self.widget._lookup_mouse_pending = None
        self.widget._lookup_poll_enabled = True
        self.widget._lookup_poll_generation = 0
        self.widget._lookup_poll_serial = 0
        self.widget._lookup_poll_handled = 0
        self.widget._TextBrowser__tooltipshelper = SimpleNamespace(emit=self.jobs.append)
        self.widget.getundermouseword = lambda result: result
        self.widget.rect = lambda: SimpleNamespace(contains=lambda pos: self.inside)
        self.widget.mapFromGlobal = lambda pos: pos
        self.widget.eval = lambda code, callback: self.eval_callbacks.append(callback)
        self.widget.trans0checker = SimpleNamespace(
            start=lambda interval: self.log.append(("timer_start", (interval,))),
            stop=lambda: self.log.append(("timer_stop", ())),
        )

    def handle(self, serial, word=None, generation=None):
        if word is None:
            word = {"word": "猫"}
        if generation is None:
            generation = self.widget._lookup_poll_generation
        self.widget._handle_lookup_mouse(generation, serial, word)

    def lifecycle(self):
        return [(name, args) for name, args in self.log if name in ("press", "release", "lookup")]

    def test_long_hold_is_one_press_and_one_release_lookup(self):
        self.buttons = {LEFT}
        for serial in range(1, 31):
            self.handle(serial)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press"])
        token = self.lifecycle()[0][1][0]
        self.buttons.clear()
        self.handle(31)
        self.handle(32)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press", "release", "lookup"])
        self.assertEqual(self.lifecycle()[-1][1], ({"word": "猫"}, False, token))

    def test_right_button_preserves_append_intent_after_release(self):
        self.buttons = {RIGHT}
        self.handle(1)
        self.buttons.clear()
        self.handle(2)
        self.assertTrue(self.lifecycle()[-1][1][1])

    def test_leave_bounds_cancels_and_return_without_press_does_not_lookup(self):
        self.buttons = {LEFT}
        self.handle(1)
        old_generation = self.widget._lookup_poll_generation
        self.inside = False
        self.widget._TextBrowser__checkmousestate()
        self.buttons.clear()
        self.inside = True
        self.handle(2)
        self.assertGreater(self.widget._lookup_poll_generation, old_generation)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press", "release"])

    def test_stop_releases_pending_and_invalidates_late_completion(self):
        self.buttons = {LEFT}
        self.handle(1)
        self.widget._TextBrowser__checkmousestate()
        callback = self.eval_callbacks[-1]
        self.widget._TextBrowser__starttrans0checker(1)
        self.buttons.clear()
        callback({"word": "猫"})
        for job in self.jobs:
            job()
        self.assertFalse(self.widget._lookup_poll_enabled)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press", "release"])

    def test_no_word_cancels_and_rejects_older_generation(self):
        self.buttons = {LEFT}
        self.handle(1)
        old_generation = self.widget._lookup_poll_generation
        self.widget._handle_lookup_mouse(old_generation, 2, None)
        self.buttons.clear()
        self.handle(3, generation=old_generation)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press", "release"])

    def test_out_of_order_poll_cannot_create_or_repeat_click(self):
        self.buttons = {LEFT}
        self.handle(3)
        self.buttons.clear()
        self.handle(2)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press"])
        self.handle(4)
        self.handle(3)
        self.assertEqual([name for name, _ in self.lifecycle()], ["press", "release", "lookup"])

    def test_callback_defers_all_state_work_to_ui_helper(self):
        self.buttons = {LEFT}
        self.widget._TextBrowser__callback(0, 1, {"word": "猫"})
        self.assertEqual(self.log, [])
        self.assertIsNone(self.widget._lookup_mouse_pending)
        self.assertEqual(len(self.jobs), 1)
        self.jobs[0]()
        self.assertEqual([name for name, _ in self.lifecycle()], ["press"])

    def test_malformed_payload_cancels_press_and_blocks_late_click(self):
        # Exercise the real JSON/field parser's TypeError, ValueError, KeyError
        # paths, rather than simulating an exception at the handler boundary.
        for index, payload in enumerate((None, "", "[{}]")):
            with self.subTest(payload=payload):
                serial = 10 * index + 1
                self.buttons = {LEFT}
                self.handle(serial)
                generation = self.widget._lookup_poll_generation
                self.widget.get_zoom = lambda: 1
                self.widget.getundermouseword = (
                    type(self.widget).getundermouseword.__get__(self.widget)
                )
                self.widget._TextBrowser__callback(generation, serial + 1, payload)
                self.jobs.pop()()  # This must not raise through the UI slot.
                self.assertIsNone(self.widget._lookup_mouse_pending)
                self.assertGreater(self.widget._lookup_poll_generation, generation)
                self.widget.getundermouseword = lambda result: result
                self.buttons.clear()
                self.handle(serial + 2, generation=generation)
                self.handle(serial + 3)  # Fresh hover with no new press.
                self.assertFalse(any(name == "lookup" for name, _ in self.log))
                self.assertEqual(sum(name == "release" for name, _ in self.log), index + 1)


if __name__ == "__main__":
    unittest.main()
