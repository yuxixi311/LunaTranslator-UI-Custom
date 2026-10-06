"""Synthetic bridge failure tests. No native child, fixture, bank or network."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def source_module(name):
    # Test-only explicit local source load; production never uses this loader.
    import sys
    spec = importlib.util.spec_from_file_location(name, ROOT/(name+".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = source_module("usage_policy_worker")
b = source_module("usage_helper_bridge")
e = source_module("usage_worker_entry")


class Clock:
    def __init__(self):
        self.value = 1_000_000_000
    def now(self):
        return self.value
    def advance(self, amount=1_000_000):
        self.value += amount


class FakeBackend:
    closure_sha256 = "a"*64
    def __init__(self, clock):
        self.clock, self.events = clock, []
        self.identity = {"pid": 123, "ppid": 100, "start_ticks": 987, "executable": "/reviewed/python",
                         "closure_sha256": self.closure_sha256}
        self.peak, self.cpu = 12*b.MIB, 10_000_000
        self.sent, self.exited = None, False
        self.stop_result, self.reap_result = True, True
        self.ready_override = self.read_override = None
        self.spawn_error = self.check_error = self.write_error = None
        self.cleanup_deadline_seen = None
        self.closed = False
    def spawn(self, deadline, cleanup):
        self.events.append("spawn")
        self.deadline, self.cleanup = deadline, cleanup
        self.clock.advance()
        if self.spawn_error:
            raise self.spawn_error
        return dict(self.identity)
    def check(self):
        if self.check_error:
            raise self.check_error
    def snapshot(self, *, allow_exit=False):
        return dict(identity=dict(self.identity), peak_rss_bytes=self.peak, cpu_ns=self.cpu, exited=self.exited)
    def write_frame(self, frame, deadline):
        self.events.append(("write", deadline))
        self.clock.advance()
        if self.write_error:
            raise self.write_error
        self.sent = p.decode_frame(frame)
    def read_frame(self, deadline):
        self.events.append(("read", deadline))
        self.clock.advance()
        if self.read_override is not None:
            return self.read_override
        if self.sent is None:
            value = dict(op="READY", policy_sha256=p.POLICY_SHA256, bank_sha256=p.BANK_SHA256,
                         guard_excerpt_sha256=p.GUARD_SHA256, expected_commands=224,
                         worker_identity=dict(self.identity), closure_sha256=self.closure_sha256,
                         peak_rss_bytes=self.peak, cpu_ns=self.cpu)
            if self.ready_override:
                value.update(self.ready_override)
        elif self.sent["op"] == "FINISH":
            value = {"op": "FINISHED", "commands": 224}
        else:
            value = {"op": "PREPARED"}
        return p.encode_frame(value)
    def close_input(self):
        self.events.append("close_input")
    def reap(self, deadline, *, expected_exit=None):
        self.events.append(("reap", deadline, expected_exit))
        self.clock.advance()
        self.exited = self.reap_result
        return self.reap_result
    def stop(self, deadline):
        self.events.append(("stop", deadline))
        self.cleanup_deadline_seen = deadline
        self.exited = self.stop_result
        return self.stop_result
    def close(self):
        self.events.append("close")
        self.closed = True


class BridgeTests(unittest.TestCase):
    def make(self):
        clock = Clock()
        backend = FakeBackend(clock)
        phase = [clock.now()+580_000_000_000]
        bridge = b.BoundedBridge(p, backend, now_ns=clock.now, phase_deadline_ns=lambda: phase[0],
            work_end_ns=clock.now()+780_000_000_000, postready_end_ns=clock.now()+600_000_000_000,
            cleanup_end_ns=clock.now()+800_000_000_000)
        return clock, backend, bridge, phase
    def ready(self):
        values = self.make()
        values[2].start()
        return values
    def test_complete_224_commands_and_reap(self):
        clock, backend, bridge, phase = self.ready()
        for _ in range(223):
            self.assertEqual(bridge.request({"op": "PREPARE"}, lambda v: v["op"]), "PREPARED")
            clock.advance(1_000_000_000)  # Model work is idle for active accounting.
        bridge.request({"op": "FINISH"}, lambda v: v)
        self.assertEqual(bridge.close(), dict(cleanup_confirmed=True, reaped=True, protocol_complete=True))
        self.assertEqual(bridge.timing_metrics()["commands"], 224)
        self.assertLess(bridge.timing_metrics()["active_work_ns"], 1_000_000_000)
        self.assertGreater(bridge.timing_metrics()["lifetime_ns"], 220_000_000_000)
        self.assertEqual(set(bridge.metrics()), {"owner_identity", "policy_in_owner_process", "peak_rss_bytes", "cold_start_ns"})
        self.assertTrue(backend.closed)
    def test_ready_identity_mismatch(self):
        _, backend, bridge, _ = self.make()
        backend.ready_override = {"worker_identity": {"pid": 456}}
        with self.assertRaisesRegex(b.BridgeError, "IDENTITY"):
            bridge.start()
        self.assertTrue(bridge.cleanup_result["reaped"])
    def test_unknown_ready_field_rejected(self):
        _, backend, bridge, _ = self.make()
        backend.ready_override = {"source": "forbidden"}
        with self.assertRaises(b.BridgeError):
            bridge.start()
    def test_validation_is_inside_budget(self):
        clock, backend, bridge, _ = self.ready()
        def slow(value):
            clock.advance(15_000_000_000)
            return value
        with self.assertRaisesRegex(b.BridgeError, "BUDGET"):
            bridge.request({"op": "PREPARE"}, slow)
        self.assertTrue(bridge.cleanup_result["cleanup_confirmed"])
    def test_bootstrap_consumes_budget(self):
        clock, backend, bridge, _ = self.make()
        original = backend.read_frame
        def slow(deadline):
            clock.advance(15_000_000_000)
            return original(deadline)
        backend.read_frame = slow
        with self.assertRaisesRegex(b.BridgeError, "BUDGET"):
            bridge.start()
    def test_short_phase_deadline_wins(self):
        clock, backend, bridge, phase = self.ready()
        phase[0] = clock.now()+1_000_000
        with self.assertRaisesRegex(b.BridgeError, "BUDGET"):
            bridge.request({"op": "PREPARE"}, lambda x: x)
    def test_580_second_no_new_command(self):
        clock, backend, bridge, _ = self.ready()
        clock.value = bridge.budget.launch+580_000_000_000
        with self.assertRaises(b.BridgeError):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        self.assertFalse(any(type(x) is tuple and x[0] == "write" for x in backend.events))
        self.assertEqual(backend.cleanup_deadline_seen, bridge.budget.launch+600_000_000_000)
    def test_inherited_cleanup_ceiling_wins(self):
        clock, backend, bridge, _ = self.ready()
        bridge.budget.cleanup_end = clock.now()+3_000_000_000
        bridge.abort()
        self.assertEqual(backend.cleanup_deadline_seen, bridge.budget.cleanup_end)
    def test_cancelled_parent_is_terminal(self):
        _, backend, bridge, _ = self.ready()
        backend.check_error = b.BridgeError("CANCELLED")
        with self.assertRaisesRegex(b.BridgeError, "CANCELLED"):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        self.assertTrue(bridge.cleanup_result["reaped"])
    def test_parent_interrupt_reaps_and_hides_exception(self):
        _, backend, bridge, _ = self.ready()
        backend.write_error = KeyboardInterrupt("private fixture text")
        with self.assertRaisesRegex(b.BridgeError, "VALIDATION") as caught:
            bridge.request({"op": "PREPARE"}, lambda x: x)
        self.assertNotIn("private", str(caught.exception))
        self.assertTrue(bridge.cleanup_result["cleanup_confirmed"])
    def test_failed_write_consumes_no_retry(self):
        _, backend, bridge, _ = self.ready()
        backend.write_error = OSError("source secret")
        with self.assertRaises(b.BridgeError):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        with self.assertRaises(b.BridgeError):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        self.assertEqual(sum(type(x) is tuple and x[0] == "write" for x in backend.events), 1)
    def test_spawn_unknown_never_claims_cleanup(self):
        _, backend, bridge, _ = self.make()
        backend.spawn_error, backend.stop_result = OSError("unknown spawn"), False
        with self.assertRaises(b.BridgeError):
            bridge.start()
        self.assertFalse(bridge.cleanup_result["cleanup_confirmed"])
    def test_concurrent_command_fails_closed(self):
        _, _, bridge, _ = self.ready()
        bridge.lock.acquire()
        try:
            with self.assertRaisesRegex(b.BridgeError, "STATE"):
                bridge.request({"op": "PREPARE"}, lambda x: x)
        finally:
            bridge.lock.release()
        self.assertEqual(bridge.state, "failed")
    def test_early_finish_rejected_before_write(self):
        _, backend, bridge, _ = self.ready()
        with self.assertRaisesRegex(b.BridgeError, "STATE"):
            bridge.request({"op": "FINISH"}, lambda x: x)
        self.assertEqual(bridge.commands, 0)
    def test_rss_and_cpu_exceedance(self):
        for field, value in (("peak", 32*b.MIB+1), ("cpu", 15_000_000_001)):
            with self.subTest(field=field):
                _, backend, bridge, _ = self.ready()
                setattr(backend, field, value)
                with self.assertRaisesRegex(b.BridgeError, "RESOURCE"):
                    bridge.request({"op": "PREPARE"}, lambda x: x)
    def test_no_cleanup_success_after_deadline(self):
        clock, backend, bridge, _ = self.ready()
        def late_stop(deadline):
            clock.value = deadline
            return True
        backend.stop = late_stop
        self.assertFalse(bridge.abort()["cleanup_confirmed"])
    def test_failed_final_reap_is_incomplete(self):
        _, backend, bridge, _ = self.ready()
        for _ in range(223):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        bridge.request({"op": "FINISH"}, lambda x: x)
        backend.reap_result = backend.stop_result = False
        with self.assertRaisesRegex(b.BridgeError, "CLEANUP"):
            bridge.close()
        self.assertFalse(bridge.cleanup_result["reaped"])
    def test_final_reap_high_water_and_cpu_are_retained(self):
        _, backend, bridge, _ = self.ready()
        for _ in range(223):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        bridge.request({"op": "FINISH"}, lambda x: x)
        original = backend.reap
        def final_reap(deadline, *, expected_exit=None):
            backend.peak, backend.cpu = 24*b.MIB, 230_000_000
            return original(deadline, expected_exit=expected_exit)
        backend.reap = final_reap
        bridge.close()
        self.assertEqual(bridge.metrics()["peak_rss_bytes"], 24*b.MIB)
        self.assertEqual(bridge.timing_metrics()["worker_cpu_ns"], 230_000_000)
    def test_resource_limit_discovered_only_at_final_reap_cannot_pass(self):
        for field, value in (("peak", 32*b.MIB+1), ("cpu", b.ACTIVE_NS+1)):
            with self.subTest(field=field):
                _, backend, bridge, _ = self.ready()
                for _ in range(223):
                    bridge.request({"op": "PREPARE"}, lambda x: x)
                bridge.request({"op": "FINISH"}, lambda x: x)
                original = backend.reap
                def final_reap(deadline, *, expected_exit=None):
                    setattr(backend, field, value)
                    return original(deadline, expected_exit=expected_exit)
                backend.reap = final_reap
                with self.assertRaisesRegex(b.BridgeError, "CLEANUP"):
                    bridge.close()
                self.assertFalse(bridge.cleanup_result["protocol_complete"])
    def test_native_entry_and_all_factories_require_admission(self):
        with patch("subprocess.Popen", side_effect=AssertionError("native process forbidden")):
            for call in (b.run_real, e.run_real, e.native_main,
                         lambda: b.NativeBackend(None, None, None, None, None, closure_sha256="a"*64),
                         lambda: e.load_verified_modules({})):
                with self.subTest(call=call):
                    with self.assertRaisesRegex((b.BridgeError, e.EntryError), "IDENTITY|BINDING"):
                        call()
    def test_parent_setup_included_in_startup_active_wall_and_lifetime(self):
        clock, backend, _, phase = self.make()
        launch = clock.now()
        clock.advance(700_000_000)
        bridge = b.BoundedBridge(p, backend, now_ns=clock.now, phase_deadline_ns=lambda: phase[0],
            work_end_ns=launch+780_000_000_000, postready_end_ns=launch+600_000_000_000,
            cleanup_end_ns=launch+800_000_000_000, launch_ns=launch,
            parent_setup_ns=700_000_000, parent_setup_cpu_ns=120_000_000)
        bridge.start()
        self.assertEqual(bridge.cold_start_ns, 702_000_000)
        self.assertEqual(b.ACTIVE_NS-bridge.budget.remaining, 702_000_000)
        for _ in range(223):
            bridge.request({"op": "PREPARE"}, lambda x: x)
        bridge.request({"op": "FINISH"}, lambda x: x)
        bridge.close()
        timing = bridge.timing_metrics()
        self.assertEqual(timing["parent_setup_ns"], 700_000_000)
        self.assertEqual(timing["parent_setup_cpu_ns"], 120_000_000)
        self.assertEqual(timing["worker_cpu_ns"], backend.cpu)
        self.assertGreaterEqual(timing["active_work_ns"], timing["startup_ns"]+timing["finish_ns"])
    def test_parent_setup_cannot_receive_fresh_fifteen_seconds(self):
        clock, backend, _, phase = self.make()
        launch = clock.now()
        clock.advance(b.ACTIVE_NS)
        bridge = b.BoundedBridge(p, backend, now_ns=clock.now, phase_deadline_ns=lambda: phase[0],
            work_end_ns=launch+780_000_000_000, postready_end_ns=launch+600_000_000_000,
            cleanup_end_ns=launch+800_000_000_000, launch_ns=launch, parent_setup_ns=b.ACTIVE_NS)
        with self.assertRaisesRegex(b.BridgeError, "BUDGET"):
            bridge.start()


class FakePipe:
    def __init__(self, clock, data=b"", chunks=1):
        self.clock, self.data, self.chunks = clock, bytearray(data), chunks
        self.written = bytearray()
        self.block_read = self.block_write = False
        self.waits = []
    def read_some(self, n):
        if self.block_read:
            return None
        chunk = bytes(self.data[:min(n, self.chunks)])
        del self.data[:len(chunk)]
        return chunk
    def write_some(self, data):
        if self.block_write:
            return None
        count = min(len(data), self.chunks)
        self.written.extend(data[:count])
        return count
    def wait(self, direction, deadline):
        self.waits.append((direction, deadline))
        self.clock.advance(2_000_000)


class FramingTests(unittest.TestCase):
    def io(self, data=b"", chunks=1):
        clock = Clock()
        pipe = FakePipe(clock, data, chunks)
        io = b.FrameIO(p, pipe, clock.now, lambda: None)
        return clock, pipe, io
    def test_fragmented_frame_and_partial_writes(self):
        frame = p.encode_frame({"op": "PREPARE", "source": "synthetic 日本語"})
        clock, pipe, io = self.io(frame)
        self.assertEqual(io.read(clock.now()+1_000_000_000), frame)
        io.write(frame, clock.now()+1_000_000_000)
        self.assertEqual(bytes(pipe.written), frame)
    def test_blocked_reads_and_writes_share_absolute_deadline(self):
        for direction in ("read", "write"):
            clock, pipe, io = self.io()
            setattr(pipe, "block_"+direction, True)
            deadline = clock.now()+5_000_000
            with self.assertRaisesRegex(b.BridgeError, "BUDGET"):
                io.read(deadline) if direction == "read" else io.write(p.encode_frame({"op": "X"}), deadline)
            self.assertTrue(pipe.waits)
            self.assertEqual({v[1] for v in pipe.waits}, {deadline})
    def test_zero_oversize_truncated_and_trailing_frames(self):
        frame = p.encode_frame({"op": "X"})
        for bad in ((0).to_bytes(4, "big"), (32769).to_bytes(4, "big"), frame[:-1], frame+b"x"):
            clock, pipe, io = self.io(bad, 4096)
            with self.subTest(bad=bad[:8]):
                with self.assertRaises((b.BridgeError, p.WorkerProtocolError)):
                    io.read(clock.now()+1_000_000_000)
    def test_duplicate_keys_nonfinite_and_invalid_utf8(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":"\xff"}'):
            frame = len(raw).to_bytes(4, "big")+raw
            clock, pipe, io = self.io(frame, 4096)
            with self.assertRaises(p.WorkerProtocolError):
                io.read(clock.now()+1_000_000_000)


class EntryTests(unittest.TestCase):
    def test_entry_binding_exact_rows_and_source_hashes_only(self):
        rows = ["R%03d" % n for n in range(1, 41)]+["S%03d" % n for n in range(1, 16)]+["N%03d" % n for n in range(1, 33)]
        binding = dict(schema=1, parent_pid=100,
            parent_argv=["/usr/bin/python3", "-I", "-B", "/source/verified_bootstrap.py", "/source/KIT_MANIFEST.json", "c"*64, "actions", "unused"],
            python="/python", cwd="/tmp/luna-usage-cpu-20261006-v1/attempt", launch_ns=100, work_end_ns=10**12,
            postready_end_ns=10**12, cleanup_end_ns=10**12, phase_end_ns=10**12,
            row_ids=rows, eligible_ids=rows[:24], source_hashes={row: "a"*64 for row in rows}, closure_sha256="b"*64,
            source_root="/source", source_manifest_sha256="c"*64, claim_path="/tmp/luna-usage-cpu-20261006-v1/ONE_SHOT_CPU_ATTEMPT.json", claim_sha256="d"*64)
        kwargs = dict(parent_pid=100, parent_argv=binding["parent_argv"], python="/python", cwd="/tmp/luna-usage-cpu-20261006-v1/attempt", now_ns=200)
        self.assertIs(e.validate_binding(binding, **kwargs), binding)
        for change in ({"source": "forbidden"}, {"eligible_ids": rows[:23]}, {"parent_pid": 101}):
            with self.assertRaises(e.EntryError):
                e.validate_binding({**binding, **change}, **kwargs)
    def test_closure_hash_rejects_before_any_module_execution(self):
        with self.assertRaises(e.EntryError):
            e.verify_closure(b'{"schema":1,"files":[]}', "0"*64, {})
    def test_worker_loop_never_emits_raw_exception(self):
        class Worker:
            expected_commands = 224
            phase, pending = "preflight", None
            def ready(self):
                return {"op": "READY"}
            def exchange_frame(self, frame):
                raise ValueError("RAW SOURCE PRIVATE TEXT")
        class IO:
            writes = []
            def write(self, frame):
                self.writes.append(frame)
            def read(self):
                return p.encode_frame({"op": "PREPARE"})
        io, worker = IO(), Worker()
        result = e.run_loop(worker, p, io, identity={}, closure_sha256="a"*64,
            observe=lambda: dict(peak_rss_bytes=12*b.MIB, cpu_ns=1), checkpoint=lambda: None)
        self.assertEqual(result, 1)
        self.assertEqual(worker.phase, "failed")
        self.assertEqual(len(io.writes), 1)
        self.assertNotIn(b"PRIVATE", io.writes[0])
    def test_eof_terminates_worker_without_an_extra_command(self):
        from types import SimpleNamespace
        calls = []
        worker = SimpleNamespace(expected_commands=224, phase="preflight", pending=None,
            ready=lambda: {"op": "READY"}, exchange_frame=lambda frame: calls.append(frame))
        def eof():
            raise EOFError("not exported")
        io = SimpleNamespace(read=eof, write=lambda frame: None)
        self.assertEqual(e.run_loop(worker, p, io, identity={}, closure_sha256="a"*64,
            observe=lambda: dict(peak_rss_bytes=12*b.MIB, cpu_ns=1), checkpoint=lambda: None), 1)
        self.assertEqual(calls, [])
        self.assertEqual(worker.phase, "failed")
    def test_bridge_pins_exact_entry_and_literal_bootstrap(self):
        self.assertEqual(sha256((ROOT/"usage_worker_entry.py").read_bytes()).hexdigest(), b.ENTRY_SOURCE_SHA256)
        self.assertEqual(sha256(e.ENTRY_BOOTSTRAP.encode("utf-8")).hexdigest(), b.ENTRY_BOOTSTRAP_SHA256)
    def test_literal_native_bootstrap_only_changed_in_enabled_derivative(self):
        self.assertEqual(e.ENTRY_BOOTSTRAP, e.ENTRY_BOOTSTRAP_BODY)
        self.assertNotIn("SOURCE_ONLY", e.ENTRY_BOOTSTRAP)
        self.assertIn("'_ENTRY_BOOTSTRAP_VERIFIED':(p,h)", e.ENTRY_BOOTSTRAP)
        # Never evaluate enabled literal with real imports/kernel in preparation.
        self.assertTrue(e.ENTRY_BOOTSTRAP.startswith("import os,sys,time,signal\n"))
    def test_child_lifetime_armed_before_source_reads_with_fake_kernel(self):
        import builtins
        import hashlib
        from types import SimpleNamespace
        events = []
        raw = b"def native_main(): return 0\n"
        def read(fd, cap):
            events.append(("read", fd))
            if fd == 0:
                raise BlockingIOError()
            return raw
        def exit(code):
            events.append(("exit", code))
            raise SystemExit(code)
        os_fake = SimpleNamespace(O_RDONLY=1, O_NOFOLLOW=2, open=lambda *a: events.append(("open", a[0])) or 7,
            read=read, fstat=lambda fd: SimpleNamespace(st_mode=1, st_size=len(raw)), close=lambda fd: None,
            set_blocking=lambda *a: None, _exit=exit)
        signal_fake = SimpleNamespace(SIGALRM=14, SIG_DFL=0, SIG_UNBLOCK=1, ITIMER_REAL=0,
            signal=lambda *a: events.append(("signal", a)), pthread_sigmask=lambda *a: None,
            setitimer=lambda *a: events.append(("timer", a)))
        resource_fake = SimpleNamespace(RLIMIT_CPU=0, RLIMIT_CORE=1, RLIM_INFINITY=-1,
            getrlimit=lambda key: (-1, -1), setrlimit=lambda *a: events.append(("rlimit", a)))
        modules = dict(os=os_fake, signal=signal_fake, resource=resource_fake, hashlib=hashlib,
            stat=SimpleNamespace(S_ISREG=lambda mode: True), time=SimpleNamespace(monotonic_ns=lambda: 10_000_000_000),
            sys=SimpleNamespace(argv=["-c", "/entry", hashlib.sha256(raw).hexdigest(), "/closure", "a"*64,
                                      "/binding", "b"*64, "0", "600000000000"]))
        environment = {"__builtins__": {**vars(builtins), "__import__": lambda name, *a, **kw: modules[name]}}
        with self.assertRaises(SystemExit) as result:
            exec(e.ENTRY_BOOTSTRAP_BODY, environment)
        self.assertEqual(result.exception.code, 0)
        timer_index = next(i for i, event in enumerate(events) if event[0] == "timer")
        source_index = next(i for i, event in enumerate(events) if event[0] == "open")
        self.assertLess(timer_index, source_index)
        self.assertEqual(events[timer_index], ("timer", (0, 590.0)))
        self.assertIn(("signal", (14, 0)), events)
    def run_alarm_prefix(self, *, setup_delay_ns=0, arm_delay_ns=0):
        import builtins
        from types import SimpleNamespace
        clock = [10_000_000_000]
        timers = []
        def install(*args):
            clock[0] += setup_delay_ns
        def arm(which, delay):
            timers.append((which, delay))
            clock[0] += arm_delay_ns
        modules = dict(os=SimpleNamespace(), time=SimpleNamespace(monotonic_ns=lambda: clock[0]),
            sys=SimpleNamespace(argv=["-c", "/entry", "a"*64, "/closure", "b"*64,
                                      "/binding", "c"*64, "0", "600000000000"]),
            signal=SimpleNamespace(SIGALRM=14, SIG_DFL=0, SIG_UNBLOCK=1, ITIMER_REAL=0,
                signal=install, pthread_sigmask=lambda *a: None, setitimer=arm))
        environment = {"__builtins__": {**vars(builtins), "__import__": lambda name, *a, **kw: modules[name]}}
        prefix = e.ENTRY_BOOTSTRAP_BODY.split("\nimport resource\n", 1)[0]
        try:
            exec(prefix, environment)
        except AssertionError:
            return timers, False
        return timers, True
    def test_alarm_setup_delay_is_not_added_back(self):
        timers, completed = self.run_alarm_prefix(setup_delay_ns=5_000_000_000)
        self.assertTrue(completed)
        self.assertEqual(timers, [(0, 585.0)])
    def test_alarm_deadline_expiring_during_setup_never_arms(self):
        timers, completed = self.run_alarm_prefix(setup_delay_ns=590_000_000_000)
        self.assertFalse(completed)
        self.assertEqual(timers, [])
    def test_alarm_post_arm_checkpoint_rejects_late_return(self):
        timers, completed = self.run_alarm_prefix(arm_delay_ns=590_000_000_000)
        self.assertFalse(completed)
        self.assertEqual(timers, [(0, 590.0)])
    def test_spec_uses_only_reviewed_isolated_entry(self):
        spec = e.build_spec(python="/python", cwd="/attempt", entry_path="/source/usage_worker_entry.py",
            entry_sha="a"*64, closure_path="/source/closure.json", closure_sha="b"*64,
            binding_path="/attempt/binding.json", binding_sha="c"*64, launch_ns=1, cleanup_end_ns=600000000001)
        self.assertEqual(spec["argv"][:5], ["/python", "-I", "-S", "-B", "-c"])
        self.assertNotIn("PYTHONPATH", spec["env"])
        self.assertNotIn("sys.path", e.ENTRY_BOOTSTRAP)


class OwnedProcessTests(unittest.TestCase):
    def make(self):
        from types import SimpleNamespace
        class Kernel:
            WNOHANG = 1
            def __init__(self):
                self.responses = [(0, 0, None)]
                self.signals, self.wait_calls = [], []
            def wait4(self, pid, flags):
                self.wait_calls.append((pid, flags))
                return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
            def waitstatus_to_exitcode(self, status):
                return status
            def kill(self, pid, signal):
                self.signals.append((pid, signal))
        class Time:
            def __init__(self):
                self.now = 0
            def monotonic(self):
                return self.now
            def sleep(self, amount):
                self.now += amount
        class Timeout(Exception):
            pass
        raw = SimpleNamespace(pid=123, stdin=None, stdout=None, returncode=None, args=["reviewed"])
        kernel, clock = Kernel(), Time()
        return b.OwnedProcess(raw, kernel, clock, Timeout), raw, kernel, clock, Timeout
    def test_preallocated_handle_retained_across_pending_spawn(self):
        process, raw, kernel, clock, timeout = self.make()
        handle = b.OwnedProcess(None, kernel, clock, timeout)
        inherited_cached_handle = handle
        self.assertIsNone(handle.poll())
        inherited_cached_handle.kill()  # Parent cancellation precedes adoption.
        self.assertEqual(kernel.signals, [])
        handle.adopt(raw)
        self.assertIs(handle, inherited_cached_handle)
        self.assertEqual(kernel.signals, [(123, 9)])
        usage = object()
        kernel.responses = [(123, -9, usage)]
        self.assertEqual(inherited_cached_handle.poll(), -9)
        self.assertEqual(handle.poll(), -9)
        self.assertIs(handle.final_usage, usage)
        self.assertEqual(kernel.wait_calls, [(123, kernel.WNOHANG)])
        handle.kill()
        self.assertEqual(kernel.signals, [(123, 9)])
    def test_final_wait4_metrics_survive_repeated_poll(self):
        process, raw, kernel, clock, _ = self.make()
        usage = object()
        kernel.responses = [(123, 0, usage)]
        self.assertEqual(process.poll(), 0)
        self.assertEqual(process.poll(), 0)
        self.assertIs(process.final_usage, usage)
        self.assertEqual(raw.returncode, 0)
        self.assertEqual(kernel.wait_calls, [(123, kernel.WNOHANG)])
    def test_signal_never_targets_reaped_pid(self):
        process, _, kernel, _, _ = self.make()
        process.kill()
        self.assertEqual(kernel.signals, [(123, 9)])
        kernel.responses = [(123, -9, object())]
        process.poll()
        process.kill()
        process.terminate()
        self.assertEqual(kernel.signals, [(123, 9)])
    def test_wait_timeout_never_uses_blocking_wait4(self):
        process, _, kernel, clock, timeout = self.make()
        with self.assertRaises(timeout):
            process.wait(.02)
        self.assertLessEqual(clock.now, .02)
        self.assertTrue(all(flags == kernel.WNOHANG for _, flags in kernel.wait_calls))
    def test_poll_does_not_block_on_reaper_lock(self):
        process, _, kernel, _, _ = self.make()
        process.lock.acquire()
        try:
            self.assertIsNone(process.poll())
        finally:
            process.lock.release()
        self.assertEqual(kernel.wait_calls, [])


class NativeContractTests(unittest.TestCase):
    def test_resource_observer_cannot_sample_half_published_identity(self):
        from types import SimpleNamespace
        calls = []
        state = SimpleNamespace(proc=object(), identity=None, last_snapshot=None,
            finish_expected=False, snapshot=lambda **kw: calls.append(kw))
        self.assertFalse(b.resource_tick(state))
        state.identity = {"pid": 123}  # Deliberately enter the former race window.
        self.assertFalse(b.resource_tick(state))
        self.assertEqual(calls, [])
        state.last_snapshot = {"peak_rss_bytes": 1}
        self.assertTrue(b.resource_tick(state))
        self.assertEqual(calls, [{"allow_exit": False}])
    def test_cleanup_join_cannot_refresh_failure_reserve(self):
        failure_end = 20_000_000_000
        fixed = b.effective_cleanup_deadline(None, failure_end, 600_000_000_000, 800_000_000_000)
        # Later close sees a fresh controller now+20 and broader lifetime caps.
        joined = b.effective_cleanup_deadline(fixed, 600_000_000_000, 39_000_000_000)
        self.assertEqual(joined, failure_end)
        self.assertEqual(b.effective_cleanup_deadline(joined, 19_000_000_000), 19_000_000_000)
    def test_spawn_never_detaches_from_parent_group(self):
        options = b.spawn_options(dict(executable="/python", cwd="/attempt", env={}), pipe=-1, devnull=-3)
        self.assertIs(options["start_new_session"], False)
        self.assertIsNone(options["process_group"])
        self.assertIs(options["shell"], False)
        self.assertNotIn("preexec_fn", options)
        self.assertEqual(options["pass_fds"], ())
    def test_failure_handoff_uses_existing_outer_controller(self):
        from types import SimpleNamespace
        calls = []
        controller = SimpleNamespace(expired=lambda cause: calls.append(cause))
        b.handoff_terminal_failure(controller)
        self.assertEqual(calls, ["helper terminal failure"])
    def test_unknown_spawn_has_no_group_gone_receipt(self):
        case = BridgeTests()
        _, backend, bridge, _ = case.make()
        backend.spawn_error, backend.stop_result = OSError("pending"), False
        with self.assertRaises(b.BridgeError):
            bridge.start()
        self.assertEqual(bridge.cleanup_result, dict(cleanup_confirmed=False, reaped=False, protocol_complete=False))
        self.assertNotIn("group_gone", bridge.cleanup_result)


if __name__ == "__main__":
    unittest.main()
