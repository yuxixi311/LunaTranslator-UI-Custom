import importlib.util
import os
import sys
import threading
import types
import unittest
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIOPLAYER = os.path.join(ROOT, "LunaTranslator", "myutils", "audioplayer.py")


def load_audioplayer():
    native = types.ModuleType("NativeUtils")
    native.calls = []
    native.bass_handle_pause = lambda handle: native.calls.append(
        ("pause", handle)
    ) or True
    native.bass_handle_resume = lambda handle, restart: native.calls.append(
        ("resume", handle, restart)
    ) or True
    native.bass_handle_isplaying = lambda handle: False
    native.bass_handle_free = lambda handle: None

    config = types.ModuleType("myutils.config")
    config.globalconfig = {}
    wrapper = types.ModuleType("myutils.wrapper")
    wrapper.threader = lambda function: function

    spec = importlib.util.spec_from_file_location("audioplayer_under_test", AUDIOPLAYER)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "NativeUtils": native,
            "myutils.config": config,
            "myutils.wrapper": wrapper,
        },
    ):
        spec.loader.exec_module(module)
    return module, native


class AudioPauseTests(unittest.TestCase):
    def test_playonce_toggles_pause_and_resume_without_restart(self):
        module, native = load_audioplayer()
        player = object.__new__(module.playonce)
        player.handle = 42
        player.idle = False
        player.paused = False

        self.assertTrue(player.toggle_pause())
        self.assertTrue(player.paused)
        self.assertTrue(player.toggle_pause())
        self.assertFalse(player.paused)
        self.assertEqual(native.calls, [("pause", 42), ("resume", 42, False)])

    def test_series_player_delegates_to_current_audio(self):
        module, _ = load_audioplayer()
        current = object.__new__(module.playonce)
        current.handle = 7
        current.idle = False
        current.paused = False
        series = object.__new__(module.series_audioplayer)
        series.current = current
        series.current_lock = threading.Lock()

        self.assertTrue(series.toggle_pause())
        self.assertTrue(current.paused)

    def test_playback_loop_keeps_paused_handle_alive(self):
        with open(AUDIOPLAYER, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("while _playonce.isplaying or _playonce.paused:", source)


if __name__ == "__main__":
    unittest.main()
