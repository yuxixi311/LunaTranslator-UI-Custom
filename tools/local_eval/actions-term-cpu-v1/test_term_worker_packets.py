"""Source-only worker closure/packet tests with synthetic observations and rows.

No process, model, tokenizer, claim acquisition, or packet persistence is run.
The retained row identifiers test the frozen boundary; every source is synthetic.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import term_worker_entry as e
import term_worker_packets as packets

ROOT = Path(__file__).resolve().parent


def supplied_sources():
    payloads = {name: (ROOT/name).read_bytes() for name in packets.SOURCE_NAMES}
    paths = {name: "/synthetic-inert-source/"+name for name in packets.SOURCE_NAMES}
    pins = {name: dict(bytes=len(raw), sha256=sha256(raw).hexdigest()) for name, raw in payloads.items()}
    return payloads, paths, pins


def fake_binding():
    root = "/synthetic-inert-source"
    cwd = "/synthetic-state/"+e.STATE_NAME+"/attempt"
    pin = "0"*64
    return dict(schema=1, parent_pid=12345,
        parent_argv=["/usr/bin/python3", "-I", "-B", root+"/verified_bootstrap.py", root+"/KIT_MANIFEST.json", pin, "actions", "unused"],
        python="/usr/bin/python3", cwd=cwd, launch_ns=1_000_000_000, work_end_ns=601_000_000_000,
        postready_end_ns=601_000_000_000, cleanup_end_ns=601_000_000_000, phase_end_ns=61_000_000_000,
        row_ids=list(e.ROW_IDS), eligible_ids=list(e.ELIGIBLE_IDS),
        source_hashes={row: "1"*64 for row in e.ROW_IDS}, source_root=root,
        source_manifest_sha256=pin, claim_path=cwd.rsplit("/", 1)[0]+"/ONE_SHOT_CPU_ATTEMPT.json", claim_sha256="2"*64)


def assemble_fake(payloads=None, paths=None, pins=None, fields=None):
    originals = supplied_sources()
    payloads, paths, pins = (payloads if payloads is not None else originals[0],
                             paths if paths is not None else originals[1],
                             pins if pins is not None else originals[2])
    # Expected entry pins are injected observations for the pure assembly seam.
    # Native creation remains unconditionally disabled; no bridge pin is changed.
    with patch.object(packets.bridge, "ENTRY_SOURCE_SHA256", originals[2]["term_worker_entry.py"]["sha256"]), \
         patch.object(packets.bridge, "ENTRY_BOOTSTRAP_SHA256", sha256(e.ENTRY_BOOTSTRAP.encode()).hexdigest()):
        return packets.assemble_packets(payloads, paths, pins, fields or fake_binding())


class WorkerClosureTests(unittest.TestCase):
    def setUp(self):
        self.payloads, self.paths, self.pins = supplied_sources()
        self.closure_payloads = {name: self.payloads[name] for name in e.SOURCE_NAMES}

    def test_exact_guard_and_minimal_dependency_byte_ast_identity(self):
        excerpt = e.verified_error_class(self.closure_payloads)
        self.assertEqual(excerpt, e.ERROR_CLASS_BYTES)
        self.assertEqual(sha256(excerpt).hexdigest(), e.ERROR_CLASS_BYTE_PIN)
        node = ast.parse(excerpt).body[0]
        self.assertEqual(sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(), e.ERROR_CLASS_AST_PIN)
        self.assertEqual(sha256(self.payloads[e.GUARD_NAME]).hexdigest(), e.GUARD_FILE_PIN)
        self.assertEqual(sha256(ast.dump(ast.parse(self.payloads[e.GUARD_NAME]), include_attributes=False).encode()).hexdigest(), e.GUARD_AST_PIN)

    def test_pure_loader_omits_full_application_and_restores_module_table(self):
        names = ("myutils.local_translation", "myutils.local_translation_integrity", "term_lock_policy", "term_worker")
        absent = object()
        prior = {name: sys.modules.get(name, absent) for name in names}
        modules = e.load_pure_modules(self.closure_payloads)
        self.assertEqual({k for k in vars(modules[names[0]]) if not k.startswith("__")}, {"LocalTranslationError"})
        self.assertIs(modules[names[1]].LocalTranslationError, modules[names[0]].LocalTranslationError)
        self.assertTrue(issubclass(modules[names[0]].LocalTranslationError, Exception))
        for name in names:
            self.assertIs(sys.modules.get(name, absent), prior[name])

    def test_each_closure_member_tamper_rejected_before_execution(self):
        for name in e.SOURCE_NAMES:
            with self.subTest(name=name):
                changed = dict(self.closure_payloads)
                changed[name] += b" "
                with self.assertRaises(e.EntryError):
                    e.load_pure_modules(changed)

    def test_source_binding_includes_scope_and_whole_glossary(self):
        row = dict(source="synthetic", scope_id="scope", glossary=[dict(src="x", dst="y")])
        modules = e.load_pure_modules(self.closure_payloads)
        self.assertEqual(e.source_input_digest(row), modules["term_worker"].digest(row))
        self.assertNotEqual(e.source_input_digest(row), sha256(row["source"].encode()).hexdigest())
        for key, value in (("scope_id", "different"), ("glossary", [])):
            changed = dict(row, **{key: value})
            self.assertNotEqual(e.source_input_digest(row), e.source_input_digest(changed))
        reordered = {key: row[key] for key in ("glossary", "source", "scope_id")}
        self.assertEqual(e.source_input_digest(row), e.source_input_digest(reordered))

    def test_packet_closure_exact_paths_and_pins(self):
        spec, closure, binding_raw = assemble_fake()
        binding = e.strict_json(binding_raw)
        self.assertEqual(e.verify_closure(closure, binding["closure_sha256"], self.closure_payloads), self.closure_payloads)
        self.assertEqual([v["file"] for v in e.strict_json(closure)["files"]], list(e.SOURCE_NAMES))
        self.assertLessEqual(len(closure), 32768)
        self.assertLessEqual(len(binding_raw), 32768)
        self.assertEqual(spec["argv"][1:5], ["-I", "-S", "-B", "-c"])
        self.assertEqual(spec["argv"][5], e.ENTRY_BOOTSTRAP)
        self.assertEqual(spec["argv"][6], self.paths["term_worker_entry.py"])
        self.assertTrue(e.ENTRY_BOOTSTRAP.startswith("import os,sys,time,signal\n"))
        self.assertEqual(spec["env"], {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})

    def test_packet_rejects_wrong_root_missing_source_and_updated_false_pin(self):
        paths = dict(self.paths)
        paths[e.GUARD_NAME] = "/elsewhere/"+e.GUARD_NAME
        with self.assertRaises(e.EntryError): assemble_fake(paths=paths)
        payloads = dict(self.payloads)
        del payloads[e.DEPENDENCY_NAME]
        with self.assertRaises(e.EntryError): assemble_fake(payloads=payloads)
        payloads, pins = dict(self.payloads), deepcopy(self.pins)
        payloads[e.GUARD_NAME] += b" "
        pins[e.GUARD_NAME] = dict(bytes=len(payloads[e.GUARD_NAME]), sha256=sha256(payloads[e.GUARD_NAME]).hexdigest())
        with self.assertRaises(e.EntryError): assemble_fake(payloads=payloads, pins=pins)

    def test_binding_rejects_legacy_ids_eligible_drift_and_expired_deadline(self):
        _, _, raw = assemble_fake()
        valid = e.strict_json(raw)
        def validate(binding, now=None):
            return e.validate_binding(binding, parent_pid=12345, parent_argv=binding["parent_argv"],
                python=binding["python"], cwd=binding["cwd"], now_ns=valid["launch_ns"] if now is None else now)
        self.assertEqual(validate(valid), valid)
        for key, value in (("row_ids", valid["row_ids"][:-1]+["N032"]),
                           ("eligible_ids", valid["eligible_ids"][:-1]),
                           ("source_hashes", {i: "1"*64 for i in valid["row_ids"][:-1]})):
            changed = dict(valid, **{key: value})
            with self.assertRaises(e.EntryError): validate(changed)
        with self.assertRaises(e.EntryError): validate(valid, valid["launch_ns"]+15_000_000_000)

    def test_duplicate_json_nonfinite_and_oversize_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e309}', b'{"x":"\\ud800"}', b" "*32769):
            with self.subTest(raw=raw[:40]), self.assertRaises(e.EntryError):
                e.strict_json(raw)

    def test_native_entry_paths_deny_without_exact_bootstrap_or_role(self):
        calls = ((e.require_native_release, ()), (e.require_child_admission, ()),
            (e.load_verified_modules, ({},)), (e._read_file, ("/never-read", 10)),
            (e.native_main, ()), (e.run_real, ()), (packets.require_native_release, ()),
            (packets._seal_packet, (None, None, "never")),
            (packets.create_worker_packet_factory, (None,)*5), (packets.sys_executable, ()))
        with patch.object(e, "_ENTRY_BOOTSTRAP_VERIFIED", ("forged", "forged"), create=True), \
             patch.object(e, "_CHILD_ADMITTED", True, create=True), \
             patch.object(e, "__name__", "verified_term_entry"), \
             patch.object(packets, "_VERIFIED_BOOTSTRAP_SHA", "forged", create=True):
            for fn, args in calls:
                kwargs = dict(python="forged", cwd="forged", parent_argv=[], now_ns=lambda: 0) if fn is packets.create_worker_packet_factory else {}
                with self.subTest(fn=fn.__name__), self.assertRaises(Exception):
                    fn(*args, **kwargs)
        import ast
        body=ast.parse(e.ENTRY_BOOTSTRAP).body
        self.assertIsInstance(body[0],ast.Import)
        self.assertIn("_ENTRY_BOOTSTRAP_VERIFIED",e.ENTRY_BOOTSTRAP)
        self.assertIn("hashlib.sha256(b).hexdigest()==h",e.ENTRY_BOOTSTRAP)

    def test_synthetic_claim_cross_binding_and_missing_member_rejected(self):
        fields = fake_binding()
        manifest = packets.canonical(dict(files=[dict(path=name, **self.pins[name]) for name in packets.SOURCE_NAMES]))
        manifest_sha = sha256(manifest).hexdigest()
        fields["source_manifest_sha256"] = manifest_sha
        fields["parent_argv"][5] = manifest_sha
        claim = dict(coordinator_pid=fields["parent_pid"], coordinator_argv=fields["parent_argv"],
            absolute_python=fields["python"], component_manifest_sha256=manifest_sha,
            commitments=dict(harness_manifest=manifest_sha), roots=dict(source=fields["source_root"],
                state=fields["cwd"].rsplit("/", 1)[0]), paths=dict(output=fields["cwd"]),
            claimed_monotonic=1, outer_deadline_monotonic=601)
        claim_raw = json.dumps(claim, ensure_ascii=False, separators=(",", ":")).encode()
        fields["claim_sha256"] = sha256(claim_raw).hexdigest()
        _, closure, raw_binding = assemble_fake(fields=fields)
        binding = e.strict_json(raw_binding)
        self.assertTrue(e.validate_parent_claim(binding, claim_raw, manifest, closure,
            entry_sha=self.pins["term_worker_entry.py"]["sha256"], now_ns=fields["launch_ns"]))
        damaged = e.strict_json(closure)
        damaged["files"].pop()
        changed_closure = packets.canonical(damaged)
        binding["closure_sha256"] = sha256(changed_closure).hexdigest()
        with self.assertRaises(e.EntryError):
            e.validate_parent_claim(binding, claim_raw, manifest, changed_closure,
                entry_sha=self.pins["term_worker_entry.py"]["sha256"], now_ns=fields["launch_ns"])


class PureWorkerLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        all_payloads, _, _ = supplied_sources()
        cls.payloads = {name: all_payloads[name] for name in e.SOURCE_NAMES}
        modules = e.load_pure_modules(cls.payloads)
        cls.p, cls.w = modules["term_lock_policy"], modules["term_worker"]
        cls.guard = staticmethod(modules["myutils.local_translation_integrity"].validate_integrity)
        cls.error = modules["myutils.local_translation"].LocalTranslationError
        cls.declarations = cls.payloads[e.DECLARATIONS_NAME]
        terms = json.loads(cls.declarations)["entries"]
        cls.glossary = [{k: term[k] for k in ("src", "dst")} for term in terms]
        cls.rows = {}
        for row_id in e.ROW_IDS:
            if row_id in e.ELIGIBLE_IDS:
                src = terms[(int(row_id[-2:])-1)//2]["src"]+"、合成例。"
                cls.rows[row_id] = dict(source=src, scope_id=cls.p.SCOPE_ID, glossary=deepcopy(cls.glossary))
            else:
                cls.rows[row_id] = dict(source="synthetic-only-"+row_id, scope_id="synthetic-unapproved-scope", glossary=[])
        cls.bindings = {row: e.source_input_digest(value) for row, value in cls.rows.items()}

    def make_worker(self, guard=None):
        return self.w.PolicyWorker(self.p, self.declarations, list(e.ROW_IDS), list(e.ELIGIBLE_IDS),
            self.bindings, guard or self.guard, self.error)

    def messages(self):
        for phase in ("preflight", "measured"):
            for row_id in e.ROW_IDS:
                row = self.rows[row_id]
                yield dict(op="PREPARE", phase=phase, row=row_id, source_input=row)
                if row_id in e.ELIGIBLE_IDS:
                    plan = self.p.prepare(row["source"], row["scope_id"], row["glossary"], self.declarations)
                    yield dict(op="GATE", phase=phase, row=row_id, plan_sha256=self.w.digest(asdict(plan)),
                        baseline_tokens=30, provisional_tokens=32)
                    if phase == "measured":
                        output = "{LT0}，合成例。"
                        yield dict(op="RESTORE", row=row_id, original_output=output,
                            original_output_sha256=sha256(output.encode()).hexdigest(), input_frame_bound_rejection=False)
            if phase == "preflight":
                yield dict(op="SEAL", preflight_digest="a"*64, eligible_ids=list(e.ELIGIBLE_IDS), active_ids=list(e.ELIGIBLE_IDS))
        yield dict(op="FINISH")

    def active_worker(self, guard=None):
        worker = self.make_worker(guard)
        worker.ready()
        row_id = e.ELIGIBLE_IDS[0]
        row = self.rows[row_id]
        plan = self.p.prepare(row["source"], row["scope_id"], row["glossary"], self.declarations)
        worker.phase = "measured"
        worker.pending_restore = (row_id, self.p.apply_token_gate(plan, 30, 32))
        return worker, row_id

    def restore_message(self, row_id, output):
        return dict(op="RESTORE", row=row_id, original_output=output,
            original_output_sha256=sha256(output.encode()).hexdigest(), input_frame_bound_rejection=False)

    def test_complete_214_command_loop_all88_prepare_each_phase(self):
        worker = self.make_worker()
        requests = list(self.messages())
        self.assertEqual(len(requests), 178+2*12+12)
        queue, replies = iter(requests), []
        io = SimpleNamespace(read=lambda: self.w.encode_frame(next(queue)), write=lambda frame: replies.append(self.w.decode_frame(frame)))
        rc = e.run_loop(worker, self.w, io, identity={"synthetic": True}, closure_sha256="a"*64,
            observe=lambda: dict(peak_rss_bytes=16*1024**2, cpu_ns=100_000), checkpoint=lambda: None)
        self.assertEqual(rc, 0)
        self.assertEqual(worker.phase, "finished")
        self.assertEqual(worker.commands, e.EXPECTED_COMMANDS)
        self.assertEqual(replies[-1], dict(op="FINISHED", commands=214))
        for phase in ("preflight", "measured"):
            self.assertEqual([r["row"] for r in requests if r["op"] == "PREPARE" and r["phase"] == phase], list(e.ROW_IDS))
        self.assertEqual(sum(r["op"] == "RESTORE" for r in requests), 12)
        self.assertLessEqual(len(self.w.canonical(worker.receipts)), self.w.RECEIPT_CAP)

    def test_successful_restore_invokes_both_exact_guards_and_binds_final(self):
        calls = []
        def guard(source, output):
            calls.append((source, output))
            return self.guard(source, output)
        worker, row_id = self.active_worker(guard)
        original = "{LT0}，合成例。"
        response = self.w.decode_frame(worker.exchange_frame(self.w.encode_frame(self.restore_message(row_id, original))))
        final = "吕泽尔，合成例。"
        self.assertEqual(calls, [("{LT0}、合成例。", original), ("リュゼル、合成例。", final)])
        self.assertEqual(response["original_output_sha256"], sha256(original.encode()).hexdigest())
        self.assertEqual(response["final_output"], final)
        self.assertEqual(response["final_output_sha256"], sha256(final.encode()).hexdigest())
        self.assertIsNone(response["rejection"])
        self.assertIsNone(worker.pending_restore)

    def test_marker_and_structure_rejections_are_retained_once(self):
        for output in ("合成例。", "{LT0}{LT0}", "{LT1}", "{LT0}<b>x</b>", "{LT0}\n"):
            with self.subTest(output=output):
                worker, row_id = self.active_worker()
                request = self.restore_message(row_id, output)
                response = self.w.decode_frame(worker.exchange_frame(self.w.encode_frame(request)))
                self.assertEqual(response["rejection"], "MARKER_OR_STRUCTURE_REJECTED")
                self.assertIsNone(response["final_output"])
                self.assertIsNone(response["final_output_sha256"])
                self.assertIsNone(worker.pending_restore)
                with self.assertRaises(self.w.WorkerProtocolError): worker.exchange_frame(self.w.encode_frame(request))

    def test_output_frame_bound_rejection_is_explicit_no_truncation_or_retry(self):
        worker, row_id = self.active_worker()
        request = self.restore_message(row_id, "{LT0}")
        padding = self.w.FRAME_CAP-len(self.w.canonical(request))
        request = self.restore_message(row_id, "x"*padding+"{LT0}")
        self.assertEqual(len(self.w.canonical(request)), self.w.FRAME_CAP)
        response = self.w.decode_frame(worker.exchange_frame(self.w.encode_frame(request)))
        self.assertEqual(response["rejection"], "OUTPUT_FRAME_BOUND")
        self.assertIsNone(response["final_output"])
        self.assertIsNone(response["final_output_sha256"])
        self.assertIsNone(worker.pending_restore)
        with self.assertRaises(self.w.WorkerProtocolError): worker.exchange_frame(self.w.encode_frame(request))

    def test_loop_fails_closed_without_emitting_error_frame(self):
        worker, _ = self.active_worker()
        worker.ready_sent = False
        worker.commands = 0
        frames = []
        io = SimpleNamespace(read=lambda: b"bad-frame", write=frames.append)
        rc = e.run_loop(worker, self.w, io, identity={"synthetic": True}, closure_sha256="a"*64,
            observe=lambda: dict(peak_rss_bytes=16*1024**2, cpu_ns=100_000), checkpoint=lambda: None)
        self.assertEqual(rc, 1)
        self.assertEqual(len(frames), 1)  # READY only.
        self.assertEqual(worker.phase, "failed")
        self.assertIsNone(worker.pending)
        self.assertIsNone(worker.pending_restore)

    def test_unusable_resource_observation_fails_before_ready_output(self):
        for metrics in (dict(peak_rss_bytes=0, cpu_ns=1), dict(peak_rss_bytes=33554433, cpu_ns=1),
                        dict(peak_rss_bytes=1, cpu_ns=15_000_000_001)):
            worker = self.make_worker()
            frames = []
            rc = e.run_loop(worker, self.w, SimpleNamespace(write=frames.append),
                identity={"synthetic": True}, closure_sha256="a"*64, observe=lambda: metrics, checkpoint=lambda: None)
            self.assertEqual(rc, 1)
            self.assertEqual(frames, [])


if __name__ == "__main__":
    unittest.main()
