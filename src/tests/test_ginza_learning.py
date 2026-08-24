import json
import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "LunaTranslator")
sys.path.insert(0, APP)
os.chdir(ROOT)

from myutils.ginzanlp import build_learning_units, dependency_role, enrich_word_segments
from sometypes import WordSegResult


class GinzaLearningTests(unittest.TestCase):
    def test_dependency_roles_are_conservative(self):
        self.assertEqual(dependency_role("nsubj"), "subject")
        self.assertEqual(dependency_role("obj"), "object")
        self.assertEqual(dependency_role("ROOT"), "predicate")
        self.assertEqual(dependency_role("advmod"), "modifier")
        self.assertIsNone(dependency_role("case"))

    def test_ginza_enriches_without_replacing_mecab_boundaries(self):
        text = "私はリンゴを食べる。"
        words = [WordSegResult(value) for value in ["私", "は", "リンゴ", "を", "食べる", "。"]]
        analysis = {
            "tokens": [],
            "bunsetu": [
                {"id": 0, "text": "私は", "start": 0, "end": 2, "dep": "nsubj", "head": "食べる", "role": "subject"},
                {"id": 1, "text": "リンゴを", "start": 2, "end": 6, "dep": "obj", "head": "食べる", "role": "object"},
                {"id": 2, "text": "食べる。", "start": 6, "end": 10, "dep": "ROOT", "head": "食べる", "role": "predicate"},
            ],
            "learning_units": [
                {"id": 0, "text": "私は", "start": 0, "end": 2},
                {"id": 1, "text": "リンゴを食べる。", "start": 2, "end": 10},
            ],
        }

        enriched = enrich_word_segments(text, words, analysis)

        self.assertEqual([word.word for word in enriched], [word.word for word in words])
        self.assertEqual([word.grammar_role for word in enriched], ["subject", "subject", "object", "object", "predicate", "predicate"])
        self.assertTrue(enriched[0].bunsetu_start)
        self.assertTrue(enriched[1].bunsetu_end)
        self.assertEqual(enriched[2].bunsetu_text, "リンゴを")
        self.assertEqual(enriched[2].learning_unit_text, "リンゴを食べる。")
        self.assertTrue(enriched[2].learning_unit_start)
        self.assertTrue(enriched[-1].learning_unit_end)

    def test_learning_units_merge_adjacent_case_phrase_with_its_head(self):
        bunsetu = [
            {"id": 0, "text": "役に", "start": 0, "end": 2, "dep": "obl", "head": "立っ", "head_start": 2, "role": None},
            {"id": 1, "text": "立ってたなら", "start": 2, "end": 8, "dep": "advcl", "head": "ある", "head_start": 12, "role": "modifier"},
            {"id": 2, "text": "一つ", "start": 8, "end": 10, "dep": "obl", "head": "ある", "head_start": 12, "role": None},
        ]

        units = build_learning_units(bunsetu)

        self.assertEqual(units[0]["text"], "役に立ってたなら")
        self.assertEqual(units[0]["bunsetu_ids"], [0, 1])
        self.assertEqual(units[0]["role"], "modifier")
        self.assertEqual(units[1]["text"], "一つ")

    def test_word_result_round_trip_preserves_syntax_fields(self):
        original = WordSegResult(
            "私",
            grammar_role="subject",
            grammar_dep="nsubj",
            grammar_head="食べる",
            bunsetu_id=0,
            bunsetu_text="私は",
            bunsetu_start=True,
            learning_unit_id=0,
            learning_unit_text="私は食べる",
            learning_unit_start=True,
        )
        restored = WordSegResult.from_dict(original.as_dict())

        self.assertEqual(restored.grammar_role, "subject")
        self.assertEqual(restored.grammar_dep, "nsubj")
        self.assertEqual(restored.bunsetu_text, "私は")
        self.assertTrue(restored.bunsetu_start)
        self.assertEqual(restored.learning_unit_text, "私は食べる")
        self.assertTrue(restored.learning_unit_start)

    def test_default_config_and_settings_expose_offline_model(self):
        with open(os.path.join(APP, "defaultconfig", "config.json"), encoding="utf-8") as handle:
            config = json.load(handle)
        with open(os.path.join(APP, "gui", "setting", "cishu.py"), encoding="utf-8") as handle:
            settings_source = handle.read()

        self.assertTrue(config["ginza"]["use"])
        self.assertEqual(config["ginza"]["display_mode"], 0)
        self.assertIn("GiNZA 离线句法", settings_source)
        self.assertIn("学习分组（推荐）", settings_source)
        self.assertIn("文节边界", settings_source)
        self.assertIn("词元详情", settings_source)
        self.assertNotIn("文节 + 角色", settings_source)

    def test_learning_palette_is_semantic_and_distinct(self):
        with open(os.path.join(APP, "defaultconfig", "config.json"), encoding="utf-8") as handle:
            config = json.load(handle)

        content_roles = ["名詞", "動詞", "形容詞", "副詞", "助詞", "助動詞", "代名詞"]
        content_colors = [config["cixingcolor"][name] for name in content_roles]
        grammar_colors = list(config["grammar_role_color"].values())

        self.assertEqual(config["learning_ui_feature_revision"], 7)
        self.assertEqual(config["showcixing_touming"], 24)
        self.assertEqual(len(content_colors), len(set(content_colors)))
        self.assertEqual(len(grammar_colors), len(set(grammar_colors)))
        self.assertEqual(config["cixingcolor"]["名詞"], "#4C8DFF")
        self.assertEqual(config["cixingcolor"]["動詞"], "#F06A6A")

    def test_renderers_use_same_family_border_and_hover(self):
        with open(os.path.join(APP, "htmlcode", "uiwebview", "mainui.html"), encoding="utf-8") as handle:
            html = handle.read()
        with open(os.path.join(APP, "gui", "rendertext", "textbrowser.py"), encoding="utf-8") as handle:
            qt_renderer = handle.read()

        self.assertIn("--lt-word-border", html)
        self.assertIn("--lt-word-hover", html)
        self.assertIn("margin-left: 0.13em", html)
        self.assertIn(".lt-syntax-group", html)
        self.assertIn("word.learning_unit_id", html)
        self.assertIn("color.hoverget()", qt_renderer)
        self.assertIn("color.borderget()", qt_renderer)


if __name__ == "__main__":
    unittest.main()
