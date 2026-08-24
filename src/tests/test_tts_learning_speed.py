import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "LunaTranslator")
sys.path.insert(0, APP)
os.chdir(ROOT)

from myutils.tts_speed import next_tts_speed_rate, tts_speed_label
from tts.basettsclass import SpeechParam, TTSbase, normalize_tts_text


class TtsLearningSpeedTests(unittest.TestCase):
    def test_speed_cycles_from_default_through_three_steps(self):
        rate = 0
        labels = []
        for _ in range(4):
            labels.append(tts_speed_label(rate))
            rate = next_tts_speed_rate(rate)

        self.assertEqual(labels, ["1.0X", "0.6X", "0.8X", "1.0X"])

    def test_learning_rates_generate_expected_edge_prosody(self):
        base = object.__new__(TTSbase)

        self.assertIn("rate='-40%'", base.createSSML("テスト", "voice", SpeechParam(-8, 0)))
        self.assertIn("rate='-20%'", base.createSSML("テスト", "voice", SpeechParam(-4, 0)))
        self.assertIn("rate='0%'", base.createSSML("テスト", "voice", SpeechParam(0, 0)))

    def test_ellipsis_becomes_pause_without_changing_decimals(self):
        original = "待って……本当に...価格は0.6です。。。。次へ・・・まだ⋯⋯"
        normalized = normalize_tts_text(original)

        self.assertEqual(normalized, "待って、本当に、価格は0.6です、次へ、まだ、")
        self.assertNotIn("……", normalized)
        self.assertNotIn("...", normalized)
        self.assertIn("0.6", normalized)


if __name__ == "__main__":
    unittest.main()
