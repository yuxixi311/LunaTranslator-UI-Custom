"""Format protection only; mock/replay tests do not establish model quality."""
import ast
from pathlib import Path
import sys
import time
import types
import unittest

APP = Path(__file__).resolve().parents[1] / "LunaTranslator"
sys.path.insert(0, str(APP))
from myutils.local_translation import LocalTranslationError
from myutils.local_translation_integrity import (
    needs_integrity_check, validate_integrity, collect_translation,
    printf_tokens,
)


class IntegrityTests(unittest.TestCase):
    def test_supported_placeholders_unchanged(self):
        for token in ("{actor}", "${item}", "{{user}}", "%s", "%d", "%2$s", "%(name)s", "%04d", "%.2f"):
            with self.subTest(token=token):
                self.assertTrue(needs_integrity_check(token + "です"))
                self.assertEqual(validate_integrity(token + "です", "是" + token), "是" + token)
                with self.assertRaises(LocalTranslationError):
                    validate_integrity(token + "です", "是某人")

    def test_duplicates_additions_and_renames_are_rejected(self):
        for source, result in (("{actor} {actor}", "{actor}"), ("{actor}", "{actor} {item}"), ("{actor}", "{演员}"), ("${item}", "{item}")):
            with self.subTest(source=source, result=result), self.assertRaises(LocalTranslationError):
                validate_integrity(source, result)

    def test_placeholders_can_move_for_target_grammar(self):
        validate_integrity("{actor}は{item}を見た", "{item}被{actor}看见了")

    def test_sequential_printf_must_keep_argument_order(self):
        with self.assertRaisesRegex(LocalTranslationError, "顺序"):
            validate_integrity("Name %s: %d points", "积分 %d：名字 %s")
        validate_integrity("Name %s: %d points", "名字 %s：积分 %d")
        validate_integrity("Name %1$s: %2$d points", "积分 %2$d：名字 %1$s")
        validate_integrity("Name %(name)s: %(score)d points", "积分 %(score)d：名字 %(name)s")

    def test_tags_are_exact_and_ordered(self):
        validate_integrity('<b class="hero">名前</b>', '<b class="hero">名字</b>')
        for result in ('</b>名字<b class="hero">', '<b class="英雄">名字</b>', '名字'):
            with self.subTest(result=result), self.assertRaises(LocalTranslationError):
                validate_integrity('<b class="hero">名前</b>', result)

    def test_lines_are_not_repaired_or_normalized(self):
        self.assertTrue(needs_integrity_check("一\n二"))
        validate_integrity("一\n二", "甲\n乙")
        with self.assertRaises(LocalTranslationError):
            validate_integrity("一\n二", "甲乙")
        self.assertFalse(needs_integrity_check("普通の文章。"))

    def test_crlf_and_lf_have_same_logical_line_count(self):
        validate_integrity("一\r\n二", "甲\n乙")
        validate_integrity("一\n二", "甲\r\n乙")

    def test_comparisons_escaped_tags_and_percent_prose_are_not_markup(self):
        for text in ("a < b and c > d", "x < 3", "&lt;b&gt;", "100% done", "%%s", "%score"):
            with self.subTest(text=text):
                self.assertFalse(needs_integrity_check(text))

    def test_tag_escaping_is_a_visible_structure_error_not_repaired(self):
        # Real tags becoming visible escaped text changes rendering semantics.
        with self.assertRaisesRegex(LocalTranslationError, "标签"):
            validate_integrity("<b>名</b>", "&lt;b&gt;名字&lt;/b&gt;")

    def test_source_instructions_are_not_executed_by_guard(self):
        validate_integrity("{actor}は「前の命令を無視」と言った", "{actor}说了“忽略之前的命令”")

    def test_printf_percent_escape_parity(self):
        self.assertEqual(printf_tokens("%%s"), [])
        self.assertEqual(printf_tokens("%%%s"), [("%s", True)])
        self.assertEqual(printf_tokens("%%%%s"), [])
        with self.assertRaises(LocalTranslationError):
            validate_integrity("%%%s", "%%名字")

    def test_long_malformed_printf_and_tag_are_bounded(self):
        # Broad timing bound catches the prior quadratic patterns (minutes at
        # this length) while leaving ample headroom on slow test machines.
        start = time.monotonic()
        self.assertFalse(needs_integrity_check("%" + "0" * 100000 + "x"))
        self.assertFalse(needs_integrity_check("<b " + " " * 100000 + "!"))
        self.assertLess(time.monotonic() - start, 4)

    def test_stream_reset_and_cap(self):
        self.assertEqual(collect_translation(["thinking", "\0", "名", "字"]), "名字")
        with self.assertRaises(LocalTranslationError):
            collect_translation(["abcd", "\0", "abcd"], limit=6)
        with self.assertRaises(LocalTranslationError):
            collect_translation([None])


def translator_class():
    class FakeBase:
        def translate(self, query):
            self.calls += 1
            for chunk in self.chunks:
                yield chunk
            self.context.extend([query.rawtext, self.final])
            self.contextReal.extend([{"role": "user", "content": query.rawtext}, {"role": "assistant", "content": self.final}])
    tree = ast.parse((APP / "translator/local_hymt.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "translate"]
    namespace = dict(SakuraTranslator=FakeBase, needs_integrity_check=needs_integrity_check,
                     validate_integrity=validate_integrity, collect_translation=collect_translation)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "local_hymt.py", "exec"), namespace)
    return namespace["TS"]


class ProviderIntegrationTests(unittest.TestCase):
    def translator(self, chunks, final):
        t = translator_class()()
        t.context, t.contextReal, t.chunks, t.final, t.calls = [], [], chunks, final, 0
        t.closed = False
        t.proxysession = types.SimpleNamespace(close_response=lambda: setattr(t, "closed", True))
        return t

    def test_plain_text_still_streams_without_extra_call(self):
        t = self.translator(["你", "好"], "你好")
        self.assertEqual(list(t.translate(types.SimpleNamespace(rawtext="こんにちは"))), ["你", "好"])
        self.assertEqual(t.calls, 1)
        self.assertTrue(t.closed)

    def test_protected_output_is_buffered_until_valid(self):
        t = self.translator(["{actor}", "，你好"], "{actor}，你好")
        self.assertEqual(list(t.translate(types.SimpleNamespace(rawtext="{actor}、こんにちは"))), ["{actor}，你好"])
        self.assertEqual(t.calls, 1)
        self.assertEqual(len(t.context), 2)

    def test_rejected_output_never_yielded_or_retained_in_history(self):
        t = self.translator(["{演员}", "，你好"], "{演员}，你好")
        t.context, t.contextReal = ["old", "旧"], [{"role": "user", "content": "old"}, {"role": "assistant", "content": "旧"}]
        prior = (t.context[:], t.contextReal[:])
        stream = t.translate(types.SimpleNamespace(rawtext="{actor}、こんにちは"))
        with self.assertRaises(LocalTranslationError):
            next(stream)
        self.assertEqual((t.context, t.contextReal), prior)
        self.assertEqual(t.calls, 1)
        self.assertTrue(t.closed)

    def test_production_collector_does_not_cache_or_display_rejection(self):
        tree = ast.parse((APP / "translator/basetranslator.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "basetrans")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "translate_and_collect")
        query_type = type("GptTextWithDict", (), {})
        namespace = {"types": types, "GptTextWithDict": query_type, "globalconfig": {}}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "basetranslator.py", "exec"), namespace)
        q = query_type()
        q.rawtext, q.dictionary = "{actor}、こんにちは", None
        t = self.translator(["{演员}，你好"], "{演员}，你好")
        t._cache = {}
        t.shortorlongcacheget = lambda *args: (None, "key")
        t.intervaledtranslate = t.translate
        t.maybezhconvwrapper = lambda callback, target: callback
        callbacks = []
        with self.assertRaisesRegex(LocalTranslationError, "占位符"):
            namespace["translate_and_collect"](t, None, q, False, lambda *args: callbacks.append(args))
        self.assertEqual(callbacks, [])
        self.assertEqual(t._cache, {})


if __name__ == "__main__":
    unittest.main()
