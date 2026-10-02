"""Headless checks for llama.cpp flags and Hy-MT2 prompt construction.

Only the functions under test are compiled from the production source. This
avoids importing the Windows/PyQt application or launching a model server.
"""

import ast
import shlex
import unittest
from pathlib import Path
from types import SimpleNamespace


APP = Path(__file__).resolve().parents[1] / "LunaTranslator"


def load_functions(path, names, namespace, class_name=None):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = tree.body
    if class_name:
        body = next(
            node.body
            for node in body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    functions = [
        node
        for node in body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in functions} != set(names):
        raise AssertionError("Missing requested production function")
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


class LlamaServerCommandTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "device": "cpu",
            "gpu-layers-which": "number",
            "gpu-layers": 7,
        }
        self.get_command = load_functions(
            APP / "gui" / "setting" / "translate.py",
            ["getllamaservercmd"],
            {
                "globalconfig": {"llama.cpp": self.config},
                "__getllamacppdevices": lambda path: ["cpu"],
            },
        )["getllamaservercmd"]

    def command_tokens(self, version):
        return shlex.split(
            self.get_command(
                "/local tools/llama-server.exe", "/models/test model.gguf", version
            )
        )

    def test_modern_flash_attention_on_and_off(self):
        for version in (6325, 6326, 10105):
            for value in ("on", "off"):
                with self.subTest(version=version, value=value):
                    self.config["flash-attn"] = value
                    tokens = self.command_tokens(version)
                    self.assertEqual(tokens.count("--flash-attn"), 1)
                    self.assertEqual(tokens[tokens.index("--flash-attn") + 1], value)
                    self.assertNotIn("-fa", tokens)

    def test_modern_auto_and_missing_setting_emit_no_bare_auto(self):
        for value in ("auto", None):
            with self.subTest(value=value):
                if value is None:
                    self.config.pop("flash-attn", None)
                else:
                    self.config["flash-attn"] = value
                tokens = self.command_tokens(6325)
                self.assertNotIn("--flash-attn", tokens)
                self.assertNotIn("-fa", tokens)
                self.assertNotIn("auto", tokens)

    def test_old_build_only_emits_boolean_flag_for_on(self):
        for value in ("on", "off", "auto", None):
            with self.subTest(value=value):
                if value is None:
                    self.config.pop("flash-attn", None)
                else:
                    self.config["flash-attn"] = value
                tokens = self.command_tokens(6324)
                self.assertEqual(tokens.count("-fa"), int(value == "on"))
                self.assertNotIn("--flash-attn", tokens)
                for standalone_value in ("on", "off", "auto"):
                    self.assertNotIn(standalone_value, tokens)

    def test_flash_attention_preserves_other_server_arguments(self):
        self.config.update(
            {
                "flash-attn": "off",
                "host": "127.0.0.1",
                "port": 8081,
                "ctx-size-use": True,
                "ctx-size": 4096,
                "parallel-use": True,
                "parallel": 1,
            }
        )
        tokens = self.command_tokens(6325)
        self.assertEqual(tokens[0], "/local tools/llama-server.exe")
        for flag, value in (
            ("-m", "/models/test model.gguf"),
            ("--host", "127.0.0.1"),
            ("--port", "8081"),
            ("--ctx-size", "4096"),
            ("--parallel", "1"),
            ("--gpu-layers", "7"),
            ("--device", "none"),
            ("--flash-attn", "off"),
        ):
            self.assertEqual(tokens[tokens.index(flag) + 1], value)
        self.assertIn("--metrics", tokens)


class HyMt2MessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.languages = SimpleNamespace(
            Chinese=SimpleNamespace(engname="Simplified Chinese", zhsname="简体中文"),
            TradChinese=SimpleNamespace(
                engname="Traditional Chinese", zhsname="繁体中文"
            ),
            English=SimpleNamespace(engname="English", zhsname="英语"),
        )
        methods = load_functions(
            APP / "translator" / "sakura_base.py",
            ["make_gpt_dict_text", "hymt2_make_messages", "make_messages"],
            {"GptDict": list, "Languages": cls.languages},
            class_name="TS",
        )
        methods["checklangzhconv"] = lambda self, language, text: text
        cls.harness = type("HyMt2Harness", (), methods)

    def setUp(self):
        self.translator = self.harness()
        self.translator.srclang = "ja"
        self.translator.tgtlang_1 = self.languages.English
        self.translator.contextReal = []
        self.translator.config = {"use_context": True, "append_context_num": 1}
        self.glossary = [
            SimpleNamespace(src="勇者", dst="Hero", info="not included"),
            SimpleNamespace(src="街", dst="Town", info=""),
        ]
        self.query = "勇者は{街}へ行く。"

    def test_non_chinese_glossary_is_formatted(self):
        messages = self.translator.hymt2_make_messages(0, self.query, self.glossary)
        self.assertEqual(
            messages,
            [
                {
                    "role": "user",
                    "content": "Reference the following translations:\n"
                    "勇者 translates to Hero\n街 translates to Town\n"
                    "Translate the following text into English. Note that you must ONLY "
                    "output the translated result without any additional explanation:\n\n"
                    + self.query,
                }
            ],
        )

    def test_chinese_glossary_keeps_localized_language_and_separator(self):
        for target in (self.languages.Chinese, self.languages.TradChinese):
            with self.subTest(target=target.engname):
                self.translator.tgtlang_1 = target
                messages = self.translator.hymt2_make_messages(
                    0, self.query, self.glossary
                )
                self.assertEqual(
                    messages,
                    [
                        {
                            "role": "user",
                            "content": "参考下面的翻译：\n勇者翻译成Hero\n街翻译成Town\n"
                            "将以下文本翻译为{}，注意只需要输出翻译后的结果，不要额外解释：\n\n{}".format(
                                target.zhsname, self.query
                            ),
                        }
                    ],
                )

    def test_without_glossary_keeps_language_specific_instructions(self):
        for target in (
            self.languages.Chinese,
            self.languages.TradChinese,
            self.languages.English,
        ):
            for glossary in (None, []):
                with self.subTest(target=target.engname, glossary=glossary):
                    self.translator.tgtlang_1 = target
                    messages = self.translator.hymt2_make_messages(
                        0, self.query, glossary
                    )
                    if target == self.languages.English:
                        prompt = (
                            "Translate the following text into {}. Note that you should "
                            "only output the translated result without any additional "
                            "explanation:\n\n{}"
                        )
                    else:
                        prompt = "将以下文本翻译成{},注意只需要输出翻译后的结果,不要额外解释:\n\n{}"
                    self.assertEqual(
                        messages,
                        [
                            {
                                "role": "user",
                                "content": prompt.format(target.engname, self.query),
                            }
                        ],
                    )

    def test_context_selects_recent_pairs_without_mutating_history(self):
        history = [
            {"role": "user", "content": "older query"},
            {"role": "assistant", "content": "older translation"},
            {"role": "user", "content": "latest query"},
            {"role": "assistant", "content": "latest translation"},
        ]
        self.translator.contextReal = list(history)
        for count, expected in (
            (0, []), (1, history[-2:]), (2, history), (10, history)
        ):
            for target in (self.languages.Chinese, self.languages.English):
                with self.subTest(count=count, target=target.engname):
                    self.translator.tgtlang_1 = target
                    messages = self.translator.hymt2_make_messages(
                        count, self.query, self.glossary
                    )
                    self.assertEqual(messages[:-1], expected)
                    self.assertEqual(messages[-1]["role"], "user")
                    self.assertTrue(messages[-1]["content"].endswith(self.query))
                    self.assertEqual(self.translator.contextReal, history)

    def test_requested_context_with_empty_history_only_adds_current_prompt(self):
        messages = self.translator.hymt2_make_messages(3, self.query, self.glossary)
        self.assertEqual(len(messages), 1)
        self.assertEqual(self.translator.contextReal, [])

    def test_make_messages_honors_context_toggle(self):
        self.translator.contextReal = [
            {"role": "user", "content": "previous query"},
            {"role": "assistant", "content": "previous translation"},
        ]
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.translator.config["use_context"] = enabled
                messages = self.translator.make_messages(
                    "Hy-MT2", self.query, self.glossary
                )
                self.assertEqual(
                    messages[:-1], self.translator.contextReal if enabled else []
                )
                self.assertTrue(messages[-1]["content"].endswith(self.query))
                self.assertFalse(self.translator.needzhconv)


if __name__ == "__main__":
    unittest.main()
