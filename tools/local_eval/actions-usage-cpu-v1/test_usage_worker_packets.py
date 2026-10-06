"""Complete packet bytes and derivative admission with exclusively fake native I/O."""
import ast
import builtins
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import unittest

import usage_helper_bridge as bridge
import usage_worker_entry as entry
import usage_worker_packets as packets

ROOT = Path(__file__).resolve().parent
ROWS = ["R%03d" % n for n in range(1, 41)]+["S%03d" % n for n in range(1, 16)]+["N%03d" % n for n in range(1, 33)]


def fixture():
    payloads, paths, pins, members = {}, {}, {}, []
    for name in packets.SOURCE_NAMES:
        relative = ("policy/" if name in entry.SOURCE_NAMES and name != "usage_policy_worker.py" else "")+name
        raw = (ROOT/relative).read_bytes()  # Read bytes only; never execute policy/bank.
        payloads[name], paths[name] = raw, "/source/"+relative
        pins[name] = dict(bytes=len(raw), sha256=sha256(raw).hexdigest())
        members.append(dict(path=relative, **pins[name]))
    manifest_raw = packets.canonical(dict(files=members))
    manifest_sha = sha256(manifest_raw).hexdigest()
    argv = ["/usr/bin/python3", "-I", "-B", "/source/verified_bootstrap.py", "/source/KIT_MANIFEST.json",
            manifest_sha, "actions", "unused"]
    claim = dict(coordinator_pid=100, coordinator_argv=argv, absolute_python="/python",
        component_manifest_sha256=manifest_sha, commitments=dict(harness_manifest=manifest_sha),
        roots=dict(source="/source", state="/tmp/luna-usage-cpu-20261006-v1"), paths=dict(output="/tmp/luna-usage-cpu-20261006-v1/attempt"),
        claimed_monotonic=0, outer_deadline_monotonic=1000)
    claim_raw = packets.canonical(claim)
    sources = {row: "synthetic "+row for row in ROWS}
    fields = dict(schema=1, parent_pid=100, parent_argv=argv, python="/python", cwd="/tmp/luna-usage-cpu-20261006-v1/attempt",
        launch_ns=1_000_000_000, work_end_ns=780_000_000_000, postready_end_ns=601_000_000_000,
        cleanup_end_ns=601_000_000_000, phase_end_ns=60_000_000_000, row_ids=ROWS, eligible_ids=ROWS[:24],
        source_hashes={row: sha256(sources[row].encode()).hexdigest() for row in ROWS},
        source_root="/source", source_manifest_sha256=manifest_sha,
        claim_path="/tmp/luna-usage-cpu-20261006-v1/ONE_SHOT_CPU_ATTEMPT.json", claim_sha256=sha256(claim_raw).hexdigest())
    return SimpleNamespace(payloads=payloads, paths=paths, pins=pins, manifest_raw=manifest_raw,
        manifest_sha=manifest_sha, argv=argv, claim=claim, claim_raw=claim_raw, sources=sources, fields=fields)


class PacketBytesTests(unittest.TestCase):
    def test_full_packet_bytes_bind_all_five_sources_and_claim(self):
        f = fixture()
        spec, closure_raw, binding_raw = packets.assemble_packets(f.payloads, f.paths, f.pins, f.fields)
        self.assertLessEqual(len(closure_raw), 32768)
        self.assertLessEqual(len(binding_raw), 32768)
        binding = entry.strict_json(binding_raw)
        self.assertTrue(entry.validate_parent_claim(binding, f.claim_raw, f.manifest_raw, closure_raw,
            entry_sha=bridge.ENTRY_SOURCE_SHA256, now_ns=f.fields["launch_ns"]+1))
        self.assertEqual(spec["argv"][5], entry.ENTRY_BOOTSTRAP)
        self.assertEqual(spec["argv"][6:12], [f.paths["usage_worker_entry.py"], bridge.ENTRY_SOURCE_SHA256,
            "/tmp/luna-usage-cpu-20261006-v1/attempt/helper_closure.json", sha256(closure_raw).hexdigest(),
            "/tmp/luna-usage-cpu-20261006-v1/attempt/helper_binding.json", sha256(binding_raw).hexdigest()])
        self.assertEqual(spec["argv"][12:], ["1000000000", "601000000000"])
        self.assertEqual(binding["source_hashes"], f.fields["source_hashes"])
        self.assertNotIn(b"synthetic", binding_raw+closure_raw)
        self.assertEqual(packets.canonical(entry.strict_json(binding_raw)), binding_raw)
        self.assertEqual(packets.canonical(entry.strict_json(closure_raw)), closure_raw)

    def test_every_source_tamper_rejected_including_rehashed_protocol(self):
        f = fixture()
        for name in packets.SOURCE_NAMES:
            with self.subTest(name=name):
                payloads = {**f.payloads, name: f.payloads[name]+b"\n"}
                pins = {**f.pins, name: dict(bytes=len(payloads[name]), sha256=sha256(payloads[name]).hexdigest())}
                with self.assertRaises(entry.EntryError):
                    packets.assemble_packets(payloads, f.paths, pins, f.fields)

    def test_closure_identity_claim_and_manifest_drift_rejected(self):
        f = fixture()
        _, closure_raw, binding_raw = packets.assemble_packets(f.payloads, f.paths, f.pins, f.fields)
        binding = entry.strict_json(binding_raw)
        for change in (dict(parent_pid=101), dict(python="/other/python"), dict(cwd="/elsewhere"),
                       dict(source_root="/alternate"), dict(claim_sha256="0"*64), dict(source_manifest_sha256="0"*64)):
            with self.subTest(change=change), self.assertRaises(entry.EntryError):
                entry.validate_parent_claim({**binding, **change}, f.claim_raw, f.manifest_raw, closure_raw,
                    entry_sha=bridge.ENTRY_SOURCE_SHA256, now_ns=f.fields["launch_ns"]+1)
        with self.assertRaises(entry.EntryError):
            entry.validate_parent_claim(binding, f.claim_raw, f.manifest_raw, closure_raw+b" ",
                entry_sha=bridge.ENTRY_SOURCE_SHA256, now_ns=f.fields["launch_ns"]+1)

    def test_arbitrary_equal_parent_argv_does_not_admit(self):
        f = fixture()
        _, _, raw = packets.assemble_packets(f.payloads, f.paths, f.pins, f.fields)
        binding = entry.strict_json(raw)
        for argv in (["/python", "-c", "pass"], [*f.argv[:6], "validate", "unused"],
                     [*f.argv[:3], "/other/verified_bootstrap.py", *f.argv[4:]]):
            with self.subTest(argv=argv), self.assertRaises(entry.EntryError):
                entry.validate_binding({**binding, "parent_argv": argv}, parent_pid=100, parent_argv=argv,
                    python="/python", cwd="/tmp/luna-usage-cpu-20261006-v1/attempt", now_ns=f.fields["launch_ns"]+1)


class FakeFactoryTests(unittest.TestCase):
    def make(self):
        f = fixture()
        events, clock = [], [1_000_000_000]
        def now():
            clock[0] += 1000
            return clock[0]
        fake_time = SimpleNamespace(monotonic_ns=now, process_time_ns=now)
        def require(ok, reason):
            if not ok:
                raise RuntimeError(reason)
        grant = dict(owner_pid=100, manifest_sha=f.manifest_sha, source_root="/source")
        fake_scope = SimpleNamespace(require=require, require_role=lambda *roles: grant if roles == ("actions",) else None)
        class PathFake(PurePosixPath):
            def resolve(self):
                return self
        class Lock:
            def __enter__(self): pass
            def __exit__(self, *args): pass
        class Evidence:
            output = PathFake("/tmp/luna-usage-cpu-20261006-v1/attempt")
            def __init__(self):
                self.files, self.file_bytes, self.contents, self.lock = {}, {}, {}, Lock()
            def create(self, name):
                require(name not in self.contents, "exclusive file")
                events.append(("create", name))
                self.files[name], self.file_bytes[name], self.contents[name] = len(self.contents)+7, 0, b""
            def append(self, name, raw):
                events.append(("append", name))
                self.contents[name] += raw
                self.file_bytes[name] += len(raw)
        evidence = Evidence()
        owner = SimpleNamespace(evidence=evidence, plan=f.claim, phase_end=60.0, work_end=780.0,
            postready_end=601.0, outer_end=1000.0, lifecycle_end=800.0)
        def checkpoint():
            require(now() < int(owner.phase_end*1e9), "fake inherited independent deadline")
            events.append(("checkpoint", owner.phase_end))
        owner.check = checkpoint
        files = {**{f.paths[name]: raw for name, raw in f.payloads.items()},
            "/source/KIT_MANIFEST.json": f.manifest_raw, "/tmp/luna-usage-cpu-20261006-v1/ONE_SHOT_CPU_ATTEMPT.json": f.claim_raw}
        def read(path, cap):
            events.append(("read", str(path)))
            require(len(files[str(path)]) <= cap, "bounded source")
            return files[str(path)]
        def pinned(path, pin, cap):
            raw = read(path, cap)
            require(sha256(raw).hexdigest() == pin, "pinned source")
            return raw
        runtime = SimpleNamespace(bounded_file=read, pinned_file=pinned, persistence_checkpoint=checkpoint)
        os_fake = SimpleNamespace(getpid=lambda: 100, fsync=lambda fd: events.append(("fsync", fd)),
                                  close=lambda fd: events.append(("close", fd)))
        replacements = dict(activation_scope=fake_scope, os=os_fake, time=fake_time,
            pathlib=SimpleNamespace(Path=PathFake), sys=SimpleNamespace(executable="/python"),
            usage_worker_entry=entry, usage_helper_bridge=bridge)
        allowed = {"hashlib", "json"}
        def fake_import(name, *args, **kwargs):
            if name in replacements:
                return replacements[name]
            require(name in allowed, "unexpected native dependency")
            return builtins.__import__(name, *args, **kwargs)
        namespace = dict(__name__="verified_fake_packets", _VERIFIED_BOOTSTRAP_SHA=f.manifest_sha,
            __builtins__={**vars(builtins), "__import__": fake_import})
        exec(compile((ROOT/"usage_worker_packets.py").read_bytes(), "<fake native packets>", "exec"), namespace)
        factory = namespace["create_worker_packet_factory"](SimpleNamespace(h=SimpleNamespace(require=require,
            canonical=packets.canonical)), SimpleNamespace(sources=f.sources, eligible_ids=ROWS[:24]), runtime,
            owner, evidence, python="/python", cwd="/tmp/luna-usage-cpu-20261006-v1/attempt", parent_argv=f.argv, now_ns=now)
        return SimpleNamespace(factory=factory, fixture=f, evidence=evidence, owner=owner, events=events,
                               os=os_fake, clock=clock)

    def test_complete_concrete_factory_uses_only_fake_os_and_seals_once(self):
        state = self.make()
        spec, closure_sha, timing = state.factory()
        self.assertEqual(set(state.evidence.contents), set(packets.PACKET_NAMES))
        self.assertEqual(state.evidence.files, {})
        self.assertEqual(sha256(state.evidence.contents["helper_closure.json"]).hexdigest(), closure_sha)
        self.assertEqual(sha256(state.evidence.contents["helper_binding.json"]).hexdigest(), spec["argv"][11])
        self.assertGreater(timing["parent_setup_ns"], 0)
        self.assertGreater(timing["parent_setup_cpu_ns"], 0)
        self.assertEqual(timing["inherited_phase_end_ns"], 60_000_000_000)
        self.assertEqual(state.owner.phase_end, (timing["launch_ns"]+15_000_000_000)/1e9)
        self.assertEqual(len([v for v in state.events if v[0] == "fsync"]), 2)
        self.assertEqual(len([v for v in state.events if v[0] == "close"]), 2)
        prior = list(state.events)
        with self.assertRaisesRegex(RuntimeError, "already consumed"):
            state.factory()
        self.assertEqual(state.events, prior)

    def test_failed_seal_never_retries_or_returns_launch_spec(self):
        state = self.make()
        def fail(_): raise OSError("fake seal failure")
        state.os.fsync = fail
        with self.assertRaises(OSError): state.factory()
        self.assertIn("helper_closure.json", state.evidence.files)
        self.assertNotIn("helper_binding.json", state.evidence.contents)
        with self.assertRaisesRegex(RuntimeError, "already consumed"): state.factory()

    def test_ambiguous_close_cannot_be_retried_by_inherited_evidence_cleanup(self):
        state = self.make()
        calls = []
        def fail(fd):
            calls.append(fd)
            raise OSError("fake ambiguous close")
        state.os.close = fail
        with self.assertRaises(OSError): state.factory()
        self.assertNotIn("helper_closure.json", state.evidence.files)
        self.assertGreater(state.evidence.file_bytes["helper_closure.json"], 0)
        with self.assertRaisesRegex(RuntimeError, "already consumed"): state.factory()
        self.assertEqual(len(calls), 1)

    def test_slow_fake_source_read_cannot_refresh_bootstrap_budget(self):
        state = self.make()
        state.clock[0] = 59_000_000_000
        # Original inherited phase wins even though setup begins later.
        spec, _, timing = state.factory()
        self.assertEqual(state.owner.phase_end, 60.0)
        self.assertEqual(int(spec["argv"][12]), timing["launch_ns"])


class DerivativeGuardsTests(unittest.TestCase):
    def test_parent_native_gates_require_exact_actions_and_verified_source(self):
        for name in ("usage_helper_bridge.py", "usage_native_adapter.py", "usage_worker_packets.py"):
            raw = (ROOT/name).read_text()
            module = ast.parse(raw)
            guard = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "require_native_release")
            text = ast.get_source_segment(raw, guard)
            self.assertIn('require_role("actions")', text)
            self.assertIn('_VERIFIED_BOOTSTRAP_SHA', text)
            self.assertNotIn('environ', text)
            self.assertNotIn('SOURCE_ONLY', text)

    def test_original_source_only_manifest_and_policy_are_unchanged(self):
        original = ROOT.parent/"luna-usage-example-runner-20261006"
        self.assertEqual(sha256((original/"SOURCE_MANIFEST.json").read_bytes()).hexdigest(),
                         "cc31b90572b1003700067ecc848755c53fcbecbf9bb36b67edf5441ce8dc0cce")
        original_entry = (original/"usage_worker_entry.py").read_text()
        self.assertIn("ENTRY_BOOTSTRAP = 'raise RuntimeError(\"SOURCE_ONLY\")\\n' + ENTRY_BOOTSTRAP_BODY", original_entry)
        for name, pin in (("usage_example_policy.py", entry.POLICY_PIN), ("_integrity_guard.py", entry.GUARD_FILE_PIN),
                          ("runtime_bank.frozen.json", entry.BANK_PIN)):
            self.assertEqual((ROOT/"policy"/name).read_bytes(), (original/"policy"/name).read_bytes())
            self.assertEqual(sha256((ROOT/"policy"/name).read_bytes()).hexdigest(), pin)


if __name__ == "__main__":
    unittest.main()
