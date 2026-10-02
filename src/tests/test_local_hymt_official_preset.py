"""Official-card fidelity for the isolated preset; no quality assertions."""

import ast
import copy
import json
from pathlib import Path
import sys
import types
import unittest

APP = Path(__file__).resolve().parents[1] / "LunaTranslator"
sys.path.insert(0, str(APP))
from language import Languages
from myutils.local_translation import HYMT2_SAMPLING, local_args
from myutils.local_transport import local_request_body


def load_translators():
    tree = ast.parse((APP / "translator/sakura_base.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TS")
    names = {"hymt2_make_messages", "make_gpt_dict_text"}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"Languages": Languages, "GptDict": list}
    exec(compile(ast.Module(body=methods, type_ignores=[]), "sakura_base.py", "exec"), namespace)
    base = type("SakuraTranslator", (), {name: namespace[name] for name in names})
    tree = ast.parse((APP / "translator/local_hymt.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TS")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "hymt2_make_messages"]
    namespace["SakuraTranslator"] = base
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "local_hymt.py", "exec"), namespace)
    return base, namespace["TS"]


class OfficialPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.local = load_translators()

    def translator(self, target, local=True):
        instance = (self.local if local else self.base)()
        instance.tgtlang_1 = target
        instance.srclang = "ja"
        instance.contextReal = []
        instance.checklangzhconv = lambda language, text: text
        return instance

    def test_chinese_instructions_use_chinese_language_names(self):
        for target in (Languages.Chinese, Languages.TradChinese):
            with self.subTest(target=target.engname):
                messages = self.translator(target).hymt2_make_messages(0, "雨が止んだ。")
                self.assertEqual(messages, [{"role": "user", "content": "将以下文本翻译为{}，注意只需要输出翻译后的结果，不要额外解释：\n\n雨が止んだ。".format(target.zhsname)}])
                self.assertNotIn(target.engname, messages[0]["content"])

    def test_existing_provider_chinese_prompt_is_unchanged(self):
        # This change is confined to the new preset, not the shared translator.
        messages = self.translator(Languages.Chinese, local=False).hymt2_make_messages(0, "合成例")
        self.assertIn("Simplified Chinese", messages[0]["content"])

    def test_english_prompt_and_both_glossary_paths_are_inherited(self):
        glossary = [types.SimpleNamespace(src="アキ", dst="阿纪", info=None)]
        for target, terms in ((Languages.English, []), (Languages.Chinese, glossary), (Languages.TradChinese, glossary), (Languages.English, glossary)):
            with self.subTest(target=target.engname, glossary=bool(terms)):
                actual = self.translator(target).hymt2_make_messages(0, "合成例", terms)
                expected = self.translator(target, local=False).hymt2_make_messages(0, "合成例", terms)
                self.assertEqual(actual, expected)
                self.assertTrue(all(message["role"] != "system" for message in actual))

    def test_history_is_preserved_without_mutating_prior_messages(self):
        translator = self.translator(Languages.Chinese)
        history = [{"role": "user", "content": "先ほどの文"}, {"role": "assistant", "content": "之前的句子"}]
        translator.contextReal = copy.deepcopy(history)
        messages = translator.hymt2_make_messages(1, "今の文")
        self.assertEqual(messages[:-1], history)
        self.assertEqual(translator.contextReal, history)
        self.assertIn("翻译为简体中文", messages[-1]["content"])


class OfficialSamplingTests(unittest.TestCase):
    def test_new_provider_is_explicitly_experimental_and_disabled(self):
        config = json.loads((APP / "defaultconfig/config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["fanyi"]["local_hymt"]["use"])
        self.assertIn("实验性", config["fanyi"]["local_hymt"]["name"])
        quick = (APP / "gui/setting/quick.py").read_text(encoding="utf-8")
        dialog = (APP / "gui/setting/local_translation.py").read_text(encoding="utf-8")
        self.assertIn("Hy-MT2（实验性）", quick)
        self.assertIn("语义或占位符错误", dialog)
        self.assertIn("质量未验证", dialog)

    def test_sampling_matches_pinned_1_8b_and_7b_card(self):
        self.assertEqual(HYMT2_SAMPLING, {"temperature": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05})

    def test_stale_new_preset_values_cannot_silently_override_protocol(self):
        stale = {"Temperature": 0.6, "Temperature.use": False, "top_p": 0.8, "top_p_use": False, "repetition_penalty": 1, "repetition_penalty_use": False, "frequency_penalty_use": True, "max_tokens": 512}
        before = copy.deepcopy(stale)
        args = local_args(stale, 18080, "model")
        self.assertEqual(stale, before)
        for key, expected in (("Temperature", 0.7), ("top_p", 0.6), ("top_k", 20), ("repetition_penalty", 1.05), ("Temperature.use", True), ("top_p_use", True), ("repetition_penalty_use", True), ("frequency_penalty_use", False)):
            self.assertEqual(args[key], expected)
        self.assertEqual(args["max_tokens"], 512)

    def test_native_body_uses_repeat_penalty_and_explicit_top_k(self):
        raw = {"temperature": 0.6, "top_p": 0.8, "top_k": 40, "repetition_penalty": 1, "repeat_penalty": 1, "frequency_penalty": 1, "max_tokens": 512, "stream": True, "messages": [{"role": "user", "content": "合成例"}]}
        before = copy.deepcopy(raw)
        body = local_request_body(raw, "owned-alias")
        self.assertEqual(raw, before)
        self.assertNotIn("repetition_penalty", body)
        self.assertNotIn("frequency_penalty", body)
        for key, value in HYMT2_SAMPLING.items():
            self.assertEqual(body[key], value)
        self.assertEqual(body["model"], "owned-alias")
        self.assertEqual(body["max_tokens"], 512)
        self.assertTrue(body["stream"])

    def test_new_defaults_and_controls_match_fixed_sampling(self):
        config = json.loads((APP / "defaultconfig/translatorsetting.json").read_text(encoding="utf-8"))
        new = config["local_hymt"]
        self.assertEqual(new["args"]["Temperature"], 0.7)
        self.assertEqual(new["args"]["top_p"], 0.6)
        self.assertEqual(new["args"]["top_k"], 20)
        self.assertEqual(new["args"]["repetition_penalty"], 1.05)
        for key in ("Temperature", "top_p", "top_k", "repetition_penalty", "frequency_penalty"):
            self.assertTrue(new["argstype"][key]["hide"])
        self.assertEqual(config["sakura"]["args"]["Temperature"], 0.6)
        self.assertEqual(config["sakura"]["args"]["top_p"], 0.8)
        self.assertEqual(config["sakura"]["args"]["repetition_penalty"], 1)


if __name__ == "__main__":
    unittest.main()
