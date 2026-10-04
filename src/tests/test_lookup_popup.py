"""Run real popup/viewer methods with fake Qt/engines; not native Windows QA."""

import ast
from pathlib import Path
import sys
import types
import unittest
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "LunaTranslator"


def load_class(path, name, methods, namespace, bases=None):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    if bases is not None:
        cls.bases = [ast.Name(id=base, ctx=ast.Load()) for base in bases]
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, str(ROOT / path), "exec"), namespace)
    return namespace[name]


class Signal:
    def __init__(self):
        self.callbacks = []
        self.calls = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        self.calls.append(args)
        for callback in self.callbacks:
            callback(*args)


class Widget:
    def __init__(self, *args, **kwargs):
        self.visible = False

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True

    def isVisible(self):
        return self.visible

    def isAncestorOf(self, other):
        return getattr(other, "owner", None) is self

    def closeEvent(self, event):
        self.hide()

    def focusOutEvent(self, event):
        pass

    def move(self, pos):
        self.position = pos

    def resize(self, *size):
        pass

    def setFocus(self):
        pass


class Draggable(Widget):
    pass


class Resizable(Widget):
    pass


class Timer:
    def __init__(self, *args):
        self.timeout = Signal()
        self.active = False

    def setInterval(self, interval):
        pass

    def stop(self):
        self.active = False

    def start(self):
        self.active = True


class Text:
    def setText(self, text):
        self.text = text

    def clear(self):
        self.text = ""


class Tabs:
    def __init__(self):
        self.tabs = []
        self.tabBarClicked = Signal()

    def count(self):
        return len(self.tabs)

    def removeTab(self, index):
        self.tabs.pop(index)

    def insertTab(self, index, label):
        self.tabs.insert(index, label)

    def setCurrentIndex(self, index):
        pass

    def setVisible(self, visible):
        pass


class Engine:
    def __init__(self):
        self.calls = []

    def safesearch(self, callback, word, sentence):
        self.calls.append((callback, word, sentence))


class PopupTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "cishuvisrank": ["first", "second"],
            "ignoredict_S_click": ["second"],
            "ignoredict_S_hover": [],
            "WordViewTooltipHideFocus": True,
            "is_search_word_auto_tts_2": True,
            "usesearchword_S_hover": True,
        }
        self.tts = []
        self.buttons = set()
        self.focus = None
        self.cursor_in_source = True
        source = types.SimpleNamespace(
            rect=lambda: types.SimpleNamespace(contains=lambda p: self.cursor_in_source),
            mapFromGlobal=lambda p: p,
        )
        self.base = types.SimpleNamespace(
            cishus={"first": Engine(), "second": Engine()},
            read_text=self.tts.append,
            checkkeypresssatisfy=lambda key, *args: True,
            translation_ui=types.SimpleNamespace(translate_text=source),
        )
        for name in ("hover_search_word", "click_search_word", "lookup_source_pressed", "lookup_source_released"):
            setattr(self.base, name, Signal())
        namespace = {
            "QWidget": Widget, "uuid": uuid, "functools": __import__("functools"),
            "gobject": types.SimpleNamespace(base=self.base), "globalconfig": self.config,
            "tryprint": lambda f: f, "dynamiccishuname": lambda key: key,
        }
        viewer = load_class("gui/showword.py", "WordViewer", {
            "currWord", "readyData", "searchword", "cancel_search", "reset", "__show_dict_result_function",
        }, namespace)
        self.view = viewer()
        self.view.tab = Tabs()
        self.view.tabonehide = True
        self.view.textOutput = Text()
        self.view.thisps = {}
        self.view.tabks = []
        self.view.cache_results = {}
        self.view.bad_result = set()
        self.view.cache_results_highlighted = {}
        self.view.savemdictfoldstate = {}
        self.view._WordViewer__firstresult = None
        self.view._WordViewer__curr_word = ""
        self.view.current = None
        self.view.first_result_shown = Signal()
        self.view._WordViewer__show_dict_result = Signal()
        self.view._WordViewer__show_dict_result.connect(self.view._WordViewer__show_dict_result_function)
        namespace.update({
            "resizableframeless": Resizable, "DraggableQWidget": Draggable,
            "Qt": types.SimpleNamespace(WindowType=types.SimpleNamespace(FramelessWindowHint=1, WindowStaysOnTopHint=2)),
            "QTimer": Timer, "QCursor": types.SimpleNamespace(pos=lambda: (10, 10)),
            "QApplication": types.SimpleNamespace(focusWidget=lambda: self.focus),
            "windows": types.SimpleNamespace(VK_LBUTTON=1, VK_RBUTTON=2, GetAsyncKeyState=lambda key: -1 if key in self.buttons else 0),
            "QPoint": lambda *p: p, "limitpos": lambda pos, *args: pos,
            "_TR": lambda value: value,
        })
        popup = load_class("gui/flowsearchword.py", "WordViewTooltip", {
            "__init__", "__load", "close", "closeEvent", "_dismiss_lookup", "Leave",
            "focusOutEvent", "source_press", "source_release", "observe_source_word",
            "_click_searchword", "searchword", "_search_from_popup", "_set_word_status",
            "showresult", "moveresult_1", "__detectkey",
        }, namespace)
        self.popup = popup(None)
        self.popup._WordViewTooltip__state = 2
        self.popup.lastword = None
        self.popup.view = self.view
        self.popup.wordlabel = Text()
        self.view.first_result_shown.connect(self.popup.showresult)
        self.module_patch = patch.dict(sys.modules, {
            "gui.rendertext.tooltipswidget": types.SimpleNamespace(
                tooltipswidget=types.SimpleNamespace(hidetooltipwindow=self.popup.Leave)
            ),
        })
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.serial = 0

    def press(self, token=None):
        self.serial += 1
        token = token or str(self.serial)
        self.popup.source_press(token)
        return token

    def click(self, word="猫", sentence="猫がいる。", append=False, token=None):
        token = token or self.press()
        self.popup.source_release(token)
        self.popup._click_searchword(word, sentence, append, token)
        return token

    def result(self, index=-1, engine="first", value="definition"):
        self.base.cishus[engine].calls[index][0](value)

    def calls(self, engine="first"):
        return self.base.cishus[engine].calls

    def test_left_then_left_closes_and_third_reopens(self):
        self.click()
        self.result()
        self.assertEqual(self.popup.wordlabel.text, "猫 · 已查词")
        self.assertTrue(self.popup.visible)
        self.click()
        self.assertFalse(self.popup.visible)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.tts, ["猫"])
        self.click()
        self.assertEqual(len(self.calls()), 2)

    def test_right_repeat_closes_before_append(self):
        self.click()
        self.result()
        self.click(append=True)
        self.assertFalse(self.popup.visible)
        self.assertEqual(self.view.currWord, "猫")
        self.assertEqual(len(self.calls()), 1)

    def test_different_word_left_and_right_preserve_search_and_append(self):
        self.click()
        self.click("犬")
        self.assertEqual(self.view.currWord, "犬")
        self.click("小屋", append=True)
        self.assertEqual(self.view.currWord, "犬小屋")
        self.click("小屋", append=True)
        self.assertEqual(len(self.calls()), 3)

    def test_word_normalization_and_changed_sentence(self):
        self.click(" 猫 ")
        self.click("猫")
        self.assertEqual(len(self.calls()), 1)
        self.click("猫", "別の猫。")
        self.assertEqual(len(self.calls()), 2)

    def test_pending_repeat_and_late_callback_never_reopen(self):
        self.click()
        self.click(append=True)
        self.result()
        self.popup.showresult()  # A queued first-result signal is harmless too.
        self.assertFalse(self.popup.visible)
        self.assertEqual(self.view.cache_results, {})
        self.assertEqual(len(self.calls()), 1)

    def test_close_button_and_close_event_cancel_late_result(self):
        for closer in (self.popup.close, lambda: self.popup.closeEvent(None)):
            self.click()
            closer()
            self.result()
            self.assertFalse(self.popup.visible)
            self.assertIsNone(self.view.current)

    def test_old_results_cannot_replace_new_query(self):
        self.click()
        self.click("犬")
        self.result(0, value="old")
        self.assertFalse(self.popup.visible)
        self.result(1, value="new")
        self.assertEqual(self.view.cache_results, {"first": "new"})
        self.assertEqual(self.popup.wordlabel.text, "犬 · 已查词")

    def test_focus_dismiss_before_or_after_press_left_and_right(self):
        for before_press in (True, False):
            for button in (1, 2):
                with self.subTest(before_press=before_press, button=button):
                    self.click()
                    self.result()
                    count = len(self.calls())
                    self.buttons = {button}
                    if before_press:
                        self.popup.focusOutEvent(None)
                        token = self.press()
                    else:
                        token = self.press()
                        self.popup.focusOutEvent(None)
                    self.buttons.clear()
                    self.click(append=button == 2, token=token)
                    self.assertFalse(self.popup.visible)
                    self.assertEqual(len(self.calls()), count)
                    self.click()
                    self.assertEqual(len(self.calls()), count + 1)
                    self.popup.close()

    def test_canceled_selection_or_modifier_click_does_not_swallow_next(self):
        self.click()
        self.result()
        self.buttons = {1}
        self.popup.focusOutEvent(None)
        token = self.press()
        self.popup.source_release(token)  # No small-window action for this gesture.
        self.buttons.clear()
        self.click()
        self.assertEqual(len(self.calls()), 2)

    def test_source_leave_and_outside_focus_loss_allow_fresh_lookup(self):
        self.click()
        self.result()
        self.buttons = {1}
        self.cursor_in_source = False
        self.popup.focusOutEvent(None)
        self.popup.Leave()
        self.cursor_in_source = True
        self.buttons.clear()
        self.click()
        self.assertEqual(len(self.calls()), 2)

    def test_keyboard_focus_loss_has_no_mouse_tombstone(self):
        self.click()
        self.result()
        self.popup.focusOutEvent(None)
        self.click()
        self.assertEqual(len(self.calls()), 2)

    def test_popup_child_focus_is_not_outside(self):
        self.click()
        self.result()
        self.focus = types.SimpleNamespace(owner=self.popup)
        self.popup.focusOutEvent(None)
        self.assertTrue(self.popup.visible)
        self.assertIsNotNone(self.view.current)

    def test_popup_navigation_back_and_repeated_internal_lookup(self):
        self.click()
        self.result()
        self.popup._search_from_popup("犬")
        self.result()
        self.popup._search_from_popup("猫")  # Explicit navigation remains a lookup.
        self.result()
        self.popup._search_from_popup("猫")
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(len(self.calls("second")), 3)
        self.popup.close()
        self.popup._search_from_popup("stale hidden link")
        self.assertEqual(len(self.calls()), 4)

    def test_open_full_window_data_survives_cancel(self):
        self.click()
        self.result()
        data = self.view.readyData
        self.popup.close()
        self.assertEqual(self.view.readyData, data)
        self.assertEqual(self.view.currWord, "猫")

    def test_duplicate_or_late_older_click_does_not_reopen(self):
        old = self.click()
        token = self.click()
        self.popup._click_searchword("猫", "猫がいる。", False, token)
        self.popup._click_searchword("猫", "猫がいる。", False, old)
        self.assertEqual(len(self.calls()), 1)
        self.assertFalse(self.popup.visible)

    def test_hover_timer_cancel_and_no_automatic_reopen(self):
        self.popup.searchword("待つ", "文", fromhover=True, show=False)
        timer = self.popup._WordViewTooltip__f
        self.assertTrue(timer.active)
        self.popup.close()
        self.popup._WordViewTooltip__detectkey()
        self.assertFalse(timer.active)
        self.assertEqual(len(self.calls()), 0)
        self.click()
        self.click()
        self.popup.searchword("猫", "猫がいる。", fromhover=True, show=True)
        self.assertEqual(len(self.calls()), 1)
        self.popup.Leave()
        self.popup.searchword("猫", "猫がいる。", fromhover=True, show=True)
        self.assertEqual(len(self.calls()), 2)

    def test_hover_same_word_new_sentence_is_new_lookup(self):
        self.popup.searchword("猫", "one", fromhover=True, show=True)
        self.popup.searchword("猫", "two", fromhover=True, show=True)
        self.assertEqual(len(self.calls()), 2)

    def test_filtered_engines_and_user_config_are_preserved(self):
        config = __import__("copy").deepcopy(self.config)
        self.click()
        self.click(append=True)
        self.assertEqual(self.calls("second"), [])
        self.assertEqual(self.config, config)

    def test_propagated_press_does_not_erase_focus_snapshot(self):
        self.click()
        self.result()
        self.buttons = {1}
        token = self.press()
        self.popup.focusOutEvent(None)
        self.popup.source_press(token)
        self.buttons.clear()
        self.click(token=token)
        self.assertEqual(len(self.calls()), 1)

    def dispatcher(self, **config):
        class Word:
            specialinfo = None
            word = "猫"
            prototype = "原形"

            @staticmethod
            def from_dict(value):
                return Word()

        clipboard = types.SimpleNamespace(text="before:", setText=lambda text: setattr(clipboard, "text", text))
        settings = {"usewordoriginfor": {}, "useopenlinklink1": []}
        settings.update(config)
        namespace = {
            "QObject": object, "threader": lambda f: f,
            "WordSegResult": Word, "globalconfig": settings,
            "NativeUtils": types.SimpleNamespace(ClipBoard=clipboard),
            "os": types.SimpleNamespace(startfile=lambda url: None),
        }
        dispatcher = load_class("LunaTranslator.py", "BASEOBJECT", {"clickwordcallback"}, namespace)()
        dispatcher.currenttext = "猫がいる。"
        dispatcher.checkkeypresssatisfy = lambda key: -1
        dispatcher.searchwordW = types.SimpleNamespace(search_word=Signal())
        dispatcher.click_search_word = self.base.click_search_word
        return dispatcher, clipboard

    def test_small_popup_routing_retains_origin_option_and_click_token(self):
        dispatcher, _ = self.dispatcher(
            usesearchword=False, usesearchword_S=True,
            usewordoriginfor={"searchword_S": True},
        )
        token = self.press()
        dispatcher.clickwordcallback({}, False, token)
        self.assertEqual(self.view.currWord, "原形")
        self.assertEqual(self.base.click_search_word.calls[-1][-1], token)
        token = self.press()
        dispatcher.clickwordcallback({}, True, token)
        self.assertEqual(len(self.calls()), 1)

    def test_full_window_and_copy_right_click_are_unchanged(self):
        dispatcher, clipboard = self.dispatcher(usecopyword=True)
        dispatcher.clickwordcallback({}, True, "unrelated-token")
        self.assertEqual(clipboard.text, "before:猫")
        self.assertEqual(dispatcher.searchwordW.search_word.calls, [("猫", "猫がいる。", True)])
        self.assertEqual(self.base.click_search_word.calls, [])

    def test_modifier_selected_other_action_does_not_toggle_popup(self):
        dispatcher, clipboard = self.dispatcher(usecopyword=True, usesearchword_S=True)
        self.click()
        dispatcher.checkkeypresssatisfy = lambda key: key == "copyword"
        dispatcher.clickwordcallback({}, False, self.press())
        self.assertEqual(clipboard.text, "猫")
        self.assertEqual(len(self.calls()), 1)
        self.assertIsNotNone(self.popup._lookup_key)


if __name__ == "__main__":
    unittest.main()
