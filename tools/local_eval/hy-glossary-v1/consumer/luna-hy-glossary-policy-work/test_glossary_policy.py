"""Fake-only tests: lexical probes, not semantic evaluation cases or references."""
import ast
import argparse
import copy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import glossary_policy
import production_adapter

from glossary_policy import *

KIT_ROOT = Path(__file__).resolve().parent
SOURCE = KIT_ROOT / 'pinned_source'
CANON = KIT_ROOT.parent / 'luna-hy-glossary-independent/canon.json'

class Languages:
    Chinese = SimpleNamespace(engname='Simplified Chinese', zhsname='简体中文')
    TradChinese = SimpleNamespace(engname='Traditional Chinese', zhsname='繁体中文')
    Japanese = SimpleNamespace(engname='Japanese', zhsname='日语')

def extract_class(relative, class_name, method_names, name=None, bases=()):
    tree = ast.parse((SOURCE / relative).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    methods = [copy.deepcopy(n) for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in method_names]
    if {n.name for n in methods} != set(method_names):
        raise AssertionError('requested production method missing')
    return ast.ClassDef(name=name or class_name, bases=[ast.Name(id=b, ctx=ast.Load()) for b in bases], keywords=[], body=methods, decorator_list=[])

def source_classes():
    namespace = {'re': re, 'Languages': Languages, 'GptDict': list, 'GptTextWithDict': object}
    nodes = [
        extract_class('myutils/commonbase.py', 'commonbase', ['checklangzhconv'], 'Common'),
        extract_class('translator/sakura_base.py', 'TS', ['make_gpt_dict_text', 'hymt2_make_messages'], 'Base', ['Common']),
        extract_class('translator/local_hymt.py', 'TS', ['hymt2_make_messages'], 'Local', ['Base']),
        extract_class('transoptimi/noundict.py', 'Process', ['__createfake', 'process_before', 'process_before1']),
    ]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, '<production-methods-with-fakes>', 'exec'), namespace)
    translator = namespace['Local']()
    translator.tgtlang_1 = Languages.Chinese
    translator.srclang = Languages.Japanese
    translator.contextReal = [{'role': 'user', 'content': 'HISTORY MUST NOT APPEAR'}]
    return translator, namespace['Process']

def actual_selected_query(raw, parsed):
    """Execute the production translate prefix through message creation only.

    AST truncation excludes every transport and completion statement. This proves
    the actual query selection, not a hand-copied rawtext conditional.
    """
    tree = ast.parse((SOURCE / 'translator/sakura_base.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TS')
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'translate'))
    end = next(i for i, n in enumerate(method.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'messages' for t in n.targets))
    method.body = method.body[:end + 1] + [ast.Return(ast.Name(id='messages', ctx=ast.Load()))]
    namespace = {'GptTextWithDict': object, 'APIType': lambda _: None}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<production-query-selection>', 'exec'), namespace)
    fake = SimpleNamespace(checkempty=lambda _: None, config={'prompt_version_1': 'Hy-MT2'}, maybedetectprompttype=lambda x: x, make_messages=lambda version, query, **kwargs: query)
    return namespace['translate'](fake, SimpleNamespace(rawtext=raw, parsedtext=parsed, dictionary=[]))

class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_canon(CANON)
        for relative, expected in production_adapter.SOURCE_HASHES.items():
            if hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() != expected:
                raise AssertionError("comparison source hash mismatch: " + relative)

    def setUp(self):
        self.translator, self.Process = source_classes()
        self.document = json.loads(CANON.read_text())

    def production_match(self, raw):
        process = self.Process()
        process.usewhich = lambda: self.document['entries']
        return process.process_before(raw)

    def test_exact_prompts_match_actual_methods(self):
        # Fixed smoke and lexical unit probes only, never fresh semantic fixtures.
        for raw in ['これは翻訳の接続確認です。', '光', '翼光翼', '桜蓮光', '温泉', '光線']:
            with self.subTest(raw=raw):
                pair = prepare_pair(raw, CANON)
                parsed, context = self.production_match(raw)
                actual_entries = context['gpt_dict']
                self.assertEqual([(e.src, e.dst) for e in pair.matched], [(e['src'], e['dst']) for e in actual_entries])
                entries = [SimpleNamespace(**e, info='COMMENT MUST NOT APPEAR') for e in actual_entries]
                a = self.translator.hymt2_make_messages(0, raw, None)
                b = self.translator.hymt2_make_messages(0, raw, entries)
                self.assertEqual(pair.messages('A'), a)
                self.assertEqual(pair.messages('B'), b)
                self.assertEqual(pair.a.encode(), a[0]['content'].encode())
                self.assertEqual(pair.b.encode(), b[0]['content'].encode())
                self.assertNotIn('COMMENT', pair.b)
                self.assertNotIn('HISTORY', pair.b)
                self.assertNotIn(self.document['project_description'], pair.b)
                self.assertEqual(actual_selected_query(raw, parsed), raw)
                self.assertEqual(context['gpt_dict_origin'], raw)
                if actual_entries:
                    self.assertNotEqual(parsed, raw)
                    self.assertTrue(pair.b.endswith('\n\n' + raw))
                    self.assertNotIn('ZXBZ', pair.b)
                else:
                    self.assertEqual(pair.b.encode(), pair.a.encode())

    def test_false_activations_retained(self):
        self.assertEqual([e.src for e in prepare_pair('温泉', CANON).matched], ['泉'])
        self.assertEqual([e.src for e in prepare_pair('光線', CANON).matched], ['光'])

    def test_stored_order_occurrence_deduplication(self):
        p = prepare_pair('遥光光翼', CANON)
        self.assertEqual([e.src for e in p.matched], ['光', '翼', '遥'])
        self.assertEqual(p.b.count('光翻译成光'), 1)
        self.assertEqual(p.matched_count, 3)

    def test_japanese_conversion_unchanged_and_comments_omitted(self):
        entries = [SimpleNamespace(src=e['src'], dst=e['dst'], info='IGNORED') for e in self.document['entries']]
        self.assertEqual(self.translator.make_gpt_dict_text(entries, False, '翻译成'), '\n'.join(e.src + '翻译成' + e.dst for e in entries))
        for e in entries:
            self.assertEqual(self.translator.checklangzhconv(Languages.Japanese, e.dst), e.dst)

    def test_match_count_and_source_bounds(self):
        self.assertEqual(prepare_pair('光翼蓮桜', CANON).matched_count, 4)
        for raw in ['光翼蓮桜泉', '光翼蓮桜泉遥', '', 'a' * 201, 'a\nb', 'a\rb', 'a\tb', 'a\x00b', 'a\u2028b', 'a\u2029b', None]:
            with self.subTest(raw=raw), self.assertRaises(PreflightError):
                prepare_pair(raw, CANON)
        raw = ' ' + 'a' * 198 + ' '
        self.assertEqual(prepare_pair(raw, CANON).source, raw)
        self.assertEqual(len(raw), 200)

    def test_identity_rejects_any_modified_bytes(self):
        self.assertEqual(hashlib.sha256(CANON.read_bytes()).hexdigest(), CANON_SHA256)
        self.assertEqual(len(load_canon(CANON)), 6)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'canon.json'
            p.write_bytes(CANON.read_bytes() + b'\n')
            with self.assertRaises(PreflightError):
                load_canon(p)

    def test_invalid_canon_structures(self):
        mutations = [
            lambda d: d.update(instruction='x'),
            lambda d: d['entries'].pop(),
            lambda d: d['entries'][0].update(info='x'),
            lambda d: d['entries'][0].update(src=''),
            lambda d: d['entries'][0].update(dst=''),
            lambda d: d['entries'][0].update(src='光\n'),
            lambda d: d['entries'][0].update(dst='光\x00'),
            lambda d: d['entries'][0].update(src='.*'),
            lambda d: d['entries'][0].update(dst='ignore previous'),
            lambda d: d['entries'][0].update(src='翼'),
            lambda d: d['entries'][0].update(dst='翼'),
            lambda d: d['entries'][0].update(src='翼光'),
            lambda d: d.update(project_description='x\ny'),
        ]
        for change in mutations:
            d = copy.deepcopy(self.document)
            change(d)
            with self.subTest(document=d), self.assertRaises(PreflightError):
                validate_canon(d)
        with self.assertRaises(PreflightError):
            from glossary_policy import _no_duplicate_fields
            json.loads('{"src":"光","src":"翼"}', object_pairs_hook=_no_duplicate_fields)

    def test_operational_policy_calls_production_adapter(self):
        with patch('glossary_policy.production_pair', wraps=production_adapter.production_pair) as actual:
            prepare_pair('光', CANON)
            actual.assert_called_once()
        with patch('glossary_policy.production_pair', return_value=([], [], [])):
            with self.assertRaises(PreflightError):
                prepare_pair('光', CANON)

    def test_source_pins_checked_before_ast_execution(self):
        with patch.dict(production_adapter.SOURCE_HASHES, {'transoptimi/noundict.py': '0' * 64}):
            with self.assertRaises(PreflightError):
                prepare_pair('光', CANON)
        self.assertEqual(production_adapter.SOURCE_HASHES, json.loads((Path(__file__).parent / 'source_pins.json').read_text()))

    def test_actual_token_count_bounds(self):
        for a, b in [(1, 1), (320, 384), (384, 384), (384, 320)]:
            self.assertEqual(check_applied_token_counts(a, b)['b_minus_a'], b-a)
        for a, b in [(320, 385), (319, 384), (385, 384), (0, 1), (1, -1), (True, 3), (3, False), (1.0, 1), (1, '2'), (None, 1)]:
            with self.subTest(a=a, b=b), self.assertRaises(PreflightError):
                check_applied_token_counts(a, b)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Portable fake-only production equivalence tests')
    parser.add_argument('--source-root', type=Path, default=SOURCE, help='LunaTranslator source root with the four pinned production files')
    parser.add_argument('--canon', type=Path, default=CANON, help='Pinned canon JSON')
    args, unittest_args = parser.parse_known_args()
    SOURCE = args.source_root.resolve()
    CANON = args.canon.resolve()
    # Verify supplied comparison inputs before executing extracted source.
    load_canon(CANON)
    for relative, expected in production_adapter.SOURCE_HASHES.items():
        if hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() != expected:
            parser.error('comparison source hash mismatch: ' + relative)
    unittest.main(argv=[__file__, *unittest_args])
