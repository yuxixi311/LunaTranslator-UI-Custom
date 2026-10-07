"""Fake-only source-policy tests; these are not evaluation fixtures or model data."""
import json
import ast
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import term_lock_policy as p


RAW = Path(__file__).with_name("global_declarations.json").read_bytes()
DOC = json.loads(RAW)
GLOSSARY = [{"src": e["src"], "dst": e["dst"]} for e in DOC["entries"]]
FIRST = DOC["entries"][0]
SECOND = DOC["entries"][1]
UNSAFE = DOC["entries"][-1]


class PolicyTests(unittest.TestCase):
    def prep(self, source, scope=p.SCOPE_ID, glossary=None):
        return p.prepare(source, scope, GLOSSARY if glossary is None else glossary, RAW)

    def active(self):
        return p.apply_token_gate(self.prep(FIRST["src"]), 40, 44)

    def test_scope_global_declaration_identity(self):
        self.assertEqual(sum(r["lock_safe"] for r in p.load_declarations(RAW)["entries"]), 6)
        with self.assertRaises(p.PolicyError):
            p.load_declarations(RAW.replace(b'false', b'true'))
        with self.assertRaises(TypeError):
            p.prepare(FIRST["src"], p.SCOPE_ID, GLOSSARY, RAW, safe=True)

    def test_shared_glossary_is_built_before_masking(self):
        plan = self.prep(FIRST["src"])
        self.assertTrue(plan.eligible)
        before_a, target_a = plan.baseline_prompt.split(p.ORDINARY)
        before_b, target_b = plan.provisional_prompt.split(p.ORDINARY)
        self.assertEqual(before_a, before_b)
        self.assertIn(FIRST["src"] + "翻译成" + FIRST["dst"], before_b)
        self.assertEqual(target_a, FIRST["src"])
        self.assertEqual(target_b, p.MARKER)

    def test_every_safe_term_uses_same_source_only_rule(self):
        for row in DOC["entries"][:-1]:
            with self.subTest(term=row["id"]):
                plan = self.prep(row["src"])
                self.assertTrue(plan.eligible)
                self.assertEqual(plan.entry_id, row["id"])

    def test_homograph_is_globally_unsafe(self):
        self.assertEqual(self.prep(UNSAFE["src"]).reason, "globally_unsafe_entry")
        self.assertEqual(self.prep(UNSAFE["src"] + "。").reason, "globally_unsafe_entry")

    def test_unknown_or_invalid_scope_abstains(self):
        self.assertEqual(self.prep(FIRST["src"], "foreign").reason, "scope_not_declared")
        self.assertEqual(self.prep(FIRST["src"], "").reason, "scope_not_declared")

    def test_subset_or_new_unsafe_entry_cannot_be_case_override(self):
        self.assertEqual(self.prep(FIRST["src"], glossary=GLOSSARY[:-1]).reason, "scope_glossary_mismatch")
        changed = [dict(x) for x in GLOSSARY]
        changed[-1]["dst"] = FIRST["dst"]
        self.assertEqual(self.prep(FIRST["src"], glossary=changed).reason, "scope_glossary_mismatch")
        bad = [dict(x) for x in GLOSSARY]
        bad[0]["safe"] = True
        with self.assertRaises(p.PolicyError):
            self.prep(FIRST["src"], glossary=bad)

    def test_all_entries_count_including_unsafe(self):
        for other in (FIRST["src"], SECOND["src"], UNSAFE["src"]):
            with self.subTest(other=other):
                self.assertEqual(self.prep(FIRST["src"] + "、" + other).reason, "multiple_matches")
        self.assertEqual(p._occurrences("aaa", (p.Entry("aa", "x"), p.Entry("a", "y"))),
                         ((0, 1, 1), (0, 2, 0), (1, 2, 1), (1, 3, 0), (2, 3, 1)))

    def test_no_normalization_or_casefold(self):
        self.assertEqual(self.prep("ｾﾉﾘｱ").reason, "no_match")

    def test_observable_boundaries(self):
        for left, right in (("a", ""), ("", "の"), ("", "1"), ("\u0301", "")):
            self.assertEqual(self.prep(left + FIRST["src"] + right).reason, "unproven_boundary")
        self.assertTrue(self.prep(FIRST["src"] + "、").eligible)

    def test_quote_protected_collision_and_size(self):
        for quote in ('"', "'", "「", "“"):
            self.assertEqual(self.prep(quote + FIRST["src"]).reason, "quoted_source")
        for char in p.PROTECTED_SOURCE_CHARS:
            self.assertEqual(self.prep(FIRST["src"] + char).reason, "protected_source")
        self.assertEqual(self.prep(FIRST["src"] + " {LT1}").reason, "marker_namespace_collision")
        with self.assertRaises(p.PolicyError):
            self.prep("x" * 4097)

    def test_invalid_size_stops_before_scanning_or_rendering(self):
        with patch.object(p, "_occurrences", side_effect=AssertionError("must not scan")) as scan, patch.object(p, "_prompt", side_effect=AssertionError("must not render")) as render:
            for source in ("", "x" * 4097):
                with self.assertRaises(p.PolicyError):
                    self.prep(source)
            with self.assertRaises(p.PolicyError):
                self.prep(FIRST["src"], "x" * 129)
            scan.assert_not_called()
            render.assert_not_called()

    def test_token_gate_fake_counts_boundary_and_no_relaxation(self):
        plan = self.prep(FIRST["src"])
        self.assertTrue(p.apply_token_gate(plan, 20, 28).active)
        over = p.apply_token_gate(plan, 20, 29)
        self.assertFalse(over.active)
        self.assertEqual(over.prompt, plan.baseline_prompt)
        self.assertTrue(p.apply_token_gate(plan, 80, 96).active)
        self.assertFalse(p.apply_token_gate(plan, 80, 97).active)
        self.assertFalse(p.apply_token_gate(plan, 380, 385).active)
        self.assertTrue(p.apply_token_gate(plan, 40, 35).active)
        with self.assertRaises(p.PolicyError):
            p.apply_token_gate(plan, True, 20)

    def test_inactive_requires_identical_request_count(self):
        plan = self.prep(UNSAFE["src"])
        self.assertEqual(plan.baseline_prompt, plan.provisional_prompt)
        with self.assertRaises(p.PolicyError):
            p.apply_token_gate(plan, 20, 21)

    def test_exact_restoration_and_two_guard_stages(self):
        decision = self.active()
        calls = []
        def guard(source, output):
            calls.append((source, output))
            return "this return value must never replace output"
        self.assertEqual(p.restore(decision, p.MARKER, guard), FIRST["dst"])
        self.assertEqual(calls, [(p.MARKER, p.MARKER), (FIRST["src"], FIRST["dst"])])

    def test_invalid_output_markers_never_fallback(self):
        for output in ("", FIRST["dst"], "{lt0}", "{LT00}", "{LT1}", p.MARKER * 2, p.MARKER + "{LT1}"):
            with self.subTest(output=output), self.assertRaises(p.StructuralFailure):
                p.restore(self.active(), output, lambda *_: None)

    def test_guard_failure_propagates_before_success(self):
        calls = []
        def fail(source, output):
            calls.append((source, output))
            raise p.StructuralFailure("fake guard rejection")
        with self.assertRaises(p.StructuralFailure):
            p.restore(self.active(), p.MARKER, fail)
        self.assertEqual(len(calls), 1)

    def test_unchanged_abstention_output_still_guarded(self):
        decision = p.apply_token_gate(self.prep(UNSAFE["src"]), 20, 20)
        seen = []
        self.assertEqual(p.restore(decision, "untouched", lambda *args: seen.append(args)), "untouched")
        self.assertEqual(seen, [(UNSAFE["src"], "untouched")])

    def test_pinned_existing_guard_rejects_structural_damage(self):
        # Reuse only the already available public source helper's pure AST.
        # Do not import its application dependencies or execute any native code.
        path = Path(__file__).resolve().parent.parent / "luna-usage-actions-activation-preparation-20261006/audited/myutils/local_translation_integrity.py"
        raw = path.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), "74b9e650d51e38f46db25f26b2018ae4dad2a3d4cbaa086110e0e4fffdbd22de")
        tree = ast.parse(raw)
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in ("printf_tokens", "validate_integrity"):
                nodes.append(node)
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("_BRACE_PLACEHOLDER", "_TAG") for t in node.targets):
                nodes.append(node)
        self.assertEqual(len(nodes), 4)
        namespace = {"re": re, "Counter": Counter, "LocalTranslationError": p.StructuralFailure}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-existing-integrity-guard>", "exec"), namespace)
        guard = namespace["validate_integrity"]
        self.assertEqual(p.restore(self.active(), p.MARKER, guard), FIRST["dst"])
        for output in ("{{LT0}}", p.MARKER + "<x>", p.MARKER + "\n", p.MARKER + "%s"):
            with self.subTest(output=output), self.assertRaises(p.StructuralFailure):
                p.restore(self.active(), output, guard)


if __name__ == "__main__":
    unittest.main()
