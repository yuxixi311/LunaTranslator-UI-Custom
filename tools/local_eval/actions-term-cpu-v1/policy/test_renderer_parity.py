"""Source-only AST parity against the actual local_hymt subclass.

Reference files are exact public source bytes from application commit
49d3435e95f847a42e0e10053e9155a1695b5432. No app modules or native tools run.
The short strings below are illustrative implementation checks, not fresh19.
"""
import ast
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import term_lock_policy as p


ROOT = Path(__file__).resolve().parent
PINS = {
    "commonbase.py": "c562d635565477af7d399273aa3048879652a6e1420f861154b7c958d11c8172",
    "sakura_base.py": "3d9883f7965693cbe17a80db9a8d95ab95213737a782fc69acbee34cfa0ae28f",
    "local_hymt.py": "5ea7215c0330ba43adacbb386517ed56bb5e5ab236088644196b36f8efdd98dc",
}
RAW = (ROOT / "global_declarations.json").read_bytes()
GLOSSARY = [{"src": r["src"], "dst": r["dst"]} for r in json.loads(RAW)["entries"]]


def reference_renderer():
    trees = {}
    for filename, expected in PINS.items():
        raw = (ROOT / "pinned_renderer" / filename).read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise AssertionError("public reference source hash mismatch")
        trees[filename] = ast.parse(raw)
    def selected(filename, old_name, new_name, methods, base=None):
        original = next(n for n in trees[filename].body if isinstance(n, ast.ClassDef) and n.name == old_name)
        body = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in methods]
        if {n.name for n in body} != set(methods):
            raise AssertionError("reference method missing")
        return ast.ClassDef(name=new_name, bases=[ast.Name(id=base, ctx=ast.Load())] if base else [],
                            keywords=[], body=body, decorator_list=[])
    nodes = [
        selected("commonbase.py", "commonbase", "ReferenceCommon", ["checklangzhconv"]),
        selected("sakura_base.py", "TS", "ReferenceBase", ["make_gpt_dict_text", "hymt2_make_messages"], "ReferenceCommon"),
        selected("local_hymt.py", "TS", "ReferenceLocal", ["hymt2_make_messages"], "ReferenceBase"),
    ]
    langs = SimpleNamespace(
        Chinese=SimpleNamespace(engname="Simplified Chinese", zhsname="简体中文"),
        TradChinese=SimpleNamespace(engname="Traditional Chinese", zhsname="繁体中文"),
    )
    namespace = {"Languages": langs, "GptDict": list}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), "<pinned-local-hymt-renderer>", "exec"), namespace)
    reference = namespace["ReferenceLocal"]()
    reference.tgtlang_1 = langs.Chinese
    reference.srclang = "ja"
    reference.contextReal = []
    return reference


class RendererParityTests(unittest.TestCase):
    def test_actual_local_subclass_no_glossary_override(self):
        reference = reference_renderer()
        for source in ("", "_", GLOSSARY[0]["src"]):
            messages = reference.hymt2_make_messages(0, source, None)
            self.assertEqual(messages, [{"role": "user", "content": p.ORDINARY + source}])

    def test_inherited_glossary_and_masked_queries_are_exact(self):
        reference = reference_renderer()
        for source in ["_"] + [r["src"] for r in GLOSSARY] + [GLOSSARY[0]["src"] * 2]:
            plan = p.prepare(source, p.SCOPE_ID, GLOSSARY, RAW)
            original_matched = [SimpleNamespace(**r, info="") for r in GLOSSARY if r["src"] in source]
            a = reference.hymt2_make_messages(0, source, original_matched)
            b = reference.hymt2_make_messages(0, plan.masked_source, original_matched)
            self.assertEqual(a, [{"role": "user", "content": plan.baseline_prompt}])
            self.assertEqual(b, [{"role": "user", "content": plan.provisional_prompt}])


if __name__ == "__main__":
    unittest.main()
