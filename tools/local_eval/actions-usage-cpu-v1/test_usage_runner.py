"""All sources, clocks, transport, counts, completions and OS metrics are fake."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from test_support import H, P, BANK, ALIAS, fake_inputs, fake_inventory
from usage_runner_core import UsageCore, ROW_IDS, FRESH_IDS
from usage_policy_worker import PolicyWorker, ActiveBudget, WorkerProtocolError, encode_frame, decode_frame
from usage_worker_client import WorkerClient
from usage_runner_source import execute_stage, run_real
from usage_evidence_validation import validate_final_evidence
from usage_helper_source import validate_owner_metrics, validate_helper_result
from usage_native_adapter import StageHooks


class FakeClock:
    def __init__(self): self.ns = 1_000_000_000
    def advance(self, ns): self.ns += ns


class FakeBridge:
    def __init__(self, inventory, clock):
        self.state = PolicyWorker(P, BANK, ROW_IDS, inventory.eligible_ids,
                                 {row: sha256(source.encode()).hexdigest() for row, source in inventory.sources.items()})
        self.clock, self.owner_identity = clock, "synthetic-policy-worker"
        self.aborted = self.closed = False
        self.requests = []
        self.bad_response = None
    def start(self):
        self.clock.advance(500_000)
        return decode_frame(encode_frame(self.state.ready()))
    def request(self, request, validate):
        self.requests.append(deepcopy(request))
        self.clock.advance(100_000)
        response = decode_frame(self.state.exchange_frame(encode_frame(request)))
        if self.bad_response: self.bad_response(response)
        result = validate(response)
        self.clock.advance(100_000)
        return result
    def close(self): self.closed = True
    def abort(self): self.aborted = True
    def metrics(self):
        return dict(owner_identity=self.owner_identity, policy_in_owner_process=True,
                    peak_rss_bytes=16*1024*1024, cold_start_ns=500_000)
    def timing_metrics(self):
        return dict(active_work_ns=50_000_000, worker_cpu_ns=20_000_000, lifetime_ns=5_000_000_000,
                    startup_ns=500_000, finish_ns=100_000, commands=224, parent_setup_ns=100_000, parent_setup_cpu_ns=50_000)


class ExpectedGuardError(Exception): pass


class FakeHooks:
    clock_resolution_seconds = 1e-9
    def __init__(self, inventory, count_override=None, guard_failure=False):
        self.clock = FakeClock()
        self.bridge = FakeBridge(inventory, self.clock)
        self.worker = WorkerClient(self.bridge, inventory.eligible_ids)
        self.count_override = count_override
        self.guard_failure = guard_failure
        self.records, self.events, self.transcripts = [], [], []
        self.ledger = None
    def now_ns(self): return self.clock.ns
    def now_seconds(self): return self.clock.ns/1e9
    def check(self): pass
    def ready_marker(self): pass
    def postready_limit(self, seconds): assert seconds == 600
    def phase(self, name, seconds): assert (name, seconds) == ("preflight", 60)
    def resume_postready_limit(self): pass
    def event(self, event): self.events.append(event)
    def record(self, name, record): self.records.append((name, record))
    def publish_preflight(self, plans): pass
    def counted(self, kind, row, side, body):
        messages = json.loads(body)["messages"]
        value = 48 if messages[0]["content"].startswith("译例：") else 40
        return self.count_override(kind, row, side, value) if self.count_override else value
    def exchange(self, ledger, kind, row, arm, body, validate):
        self.ledger = ledger
        ledger.consume(kind, row, arm)
        start_ns, start = self.clock.ns, self.now_seconds()
        if kind == "health": payload = {"status": "ok"}
        elif kind == "models": payload = {"data": [{"id": ALIAS}]}
        elif kind in ("preflight", "recurring"):
            payload = {"object": "response.input_tokens", "input_tokens": self.counted(kind, row, arm, body)}
        else:
            count = self.counted("completion", row, arm, body)
            payload = {"model": ALIAS, "choices": [{"message": {"content": "synthetic output"}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": count, "completion_tokens": 3, "total_tokens": count+3,
                                 "prompt_tokens_details": {"cached_tokens": 0}}}
        raw = H.canonical(payload)
        wire = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw
        self.clock.advance(5_000_000 if kind != "completion" else 10_000_000)
        result = validate(raw)
        end = self.now_seconds()
        self.transcripts.append(dict(kind=kind, row=row, arm=arm, request_body=body, response_wire=wire,
            request_sha256=H.digest(body) if body is not None else None, response_sha256=H.digest(wire),
            start=start, validated_end=end, deadline=start+H.ENDPOINTS[kind][3]-.01))
        return result, self.clock.ns-start_ns


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.core = UsageCore(H, P)
        self.inventory = fake_inventory(self.core)
    def run_fake(self, hooks=None, guard=lambda source, text: text):
        hooks = hooks or FakeHooks(self.inventory)
        result = execute_stage(self.core, self.inventory, ALIAS, BANK, hooks, guard, ExpectedGuardError)
        return result, hooks

    def test_complete_exact398_http224_ipc_and_no_extra_helper_loop(self):
        result, hooks = self.run_fake()
        self.assertEqual(result["ledger"].total, 398)
        self.assertEqual(result["ledger"].counts["completion"], 174)
        self.assertEqual(result["ledger"].counts["preflight"], 174)
        self.assertEqual(result["ledger"].counts["recurring"], 48)
        self.assertEqual(len(hooks.bridge.requests), 224)
        self.assertEqual(sum(r["op"] == "PREPARE" for r in hooks.bridge.requests), 174)
        self.assertEqual(sum(r["op"] == "GATE" for r in hooks.bridge.requests), 48)
        self.assertTrue(hooks.bridge.closed)
        self.assertFalse(hooks.bridge.aborted)
        self.assertEqual(len(result["helper"]["samples"]), 87)
        self.assertEqual(result["helper"]["render_ns"]["n"], 87)
        self.assertEqual(len(result["observations"]), 174)
        self.assertIsNone(result["semantic_quality_claim"])

    def test_all_preflight_counts_and_metadata_before_first_completion(self):
        result, hooks = self.run_fake()
        first = next(i for i, r in enumerate(hooks.transcripts) if r["kind"] == "completion")
        self.assertGreaterEqual(first, 176)
        self.assertEqual(sum(r["kind"] == "preflight" for r in hooks.transcripts[:first]), 174)
        self.assertTrue(result["ledger"].preflight_sealed)
        self.assertEqual(hooks.records[0][0], "preflight")

    def test_inactive_missing_invalid_or_unequal_counts_never_seal_or_generate(self):
        for bad in (None, True, 0, -1, 41):
            hooks = FakeHooks(self.inventory, lambda kind, row, side, value:
                              bad if (kind, row, side) == ("preflight", "R001", "second") else value)
            with self.subTest(bad=bad), self.assertRaises(H.TerminalFailure):
                self.run_fake(hooks)
            self.assertFalse(hooks.ledger.preflight_sealed)
            self.assertEqual(hooks.ledger.counts["completion"], 0)
            self.assertFalse(any(r["op"] == "SEAL" for r in hooks.bridge.requests))
            self.assertTrue(hooks.bridge.aborted)

    def test_carrier_or_challenge_coverage_failure_has_zero_generation(self):
        for ids in ({f"N{i:03d}" for i in (1, 5, 9, 13, 17)}, {"N003"}):
            hooks = FakeHooks(self.inventory, lambda kind, row, side, value:
                              57 if row in ids and value == 48 else value)
            with self.subTest(ids=ids), self.assertRaises(H.TerminalFailure): self.run_fake(hooks)
            self.assertEqual(hooks.ledger.counts["preflight"], 174)
            self.assertEqual(hooks.ledger.counts["completion"], 0)
            self.assertFalse(any(r["op"] == "SEAL" for r in hooks.bridge.requests))

    def test_budget_fallback_uses_actual_B_and_keeps_two_measured_counts(self):
        hooks = FakeHooks(self.inventory, lambda kind, row, side, value: 57 if row == "N001" and value == 48 else value)
        result, hooks = self.run_fake(hooks)
        plan = next(p for p in result["plans"] if p.row_id == "N001")
        self.assertFalse(plan.active)
        self.assertEqual(plan.provisional.count, 57)
        self.assertEqual(plan.candidate.count, 40)
        record = result["observations"][("N001", "candidate")]
        self.assertEqual(record["usage"]["prompt_tokens"], 40)
        self.assertEqual(record["prospective_receipt"]["input_tokens"], 57)
        self.assertEqual(sum(r["kind"] == "recurring" and r["row"] == "N001" for r in hooks.transcripts), 2)
        self.assertEqual(result["totals"]["generation_prompt_tokens"], 174*40 + 23*8)

    def test_valid_negative_delta_remains_admissible(self):
        result, _ = self.run_fake(FakeHooks(self.inventory,
            lambda kind, row, side, value: 39 if row == "N001" and value == 48 else value))
        plan = next(p for p in result["plans"] if p.row_id == "N001")
        self.assertTrue(plan.active)
        self.assertEqual(plan.candidate.count, 39)

    def test_measured_count_drift_stops_before_that_candidate_generation(self):
        hooks = FakeHooks(self.inventory, lambda kind, row, side, value:
                          49 if (kind, row, side) == ("recurring", "N001", "provisional") else value)
        with self.assertRaises(H.TerminalFailure): self.run_fake(hooks)
        self.assertFalse(any(r["kind"] == "completion" and (r["row"], r["arm"]) == ("N001", "candidate") for r in hooks.transcripts))
        self.assertTrue(hooks.bridge.aborted)
        self.assertEqual(len(next(value for name, value in hooks.records if name == "all_rows")), 87)

    def test_output_guard_failures_keep_active_membership_and_timing(self):
        def guard(source, text):
            if source == self.inventory.sources["N001"]: raise ExpectedGuardError()
            return text
        result, _ = self.run_fake(guard=guard)
        record = result["observations"][("N001", "candidate")]
        self.assertIn("integrity_rejection", record["flags"])
        self.assertTrue(record["preflight_active"])
        self.assertGreater(record["total_ns"], 0)
        self.assertEqual(len(result["observations"]), 174)

    def test_complete_evidence_replay_and_reordered_pair_rejection(self):
        result, hooks = self.run_fake()
        intervals = [r for kind, r in hooks.records if kind == "arm"]
        replay = validate_final_evidence(self.core, self.inventory, result["plans"], ALIAS, BANK,
            hooks.transcripts, intervals, 1e-9, lambda s, t: t, ExpectedGuardError)
        self.assertEqual(replay["tokens"]["count_only_requests"], 222)
        self.assertEqual(replay["tokens"]["generation_prompt_tokens"], result["totals"]["generation_prompt_tokens"])
        changed = deepcopy(intervals)
        changed[0], changed[1] = changed[1], changed[0]
        with self.assertRaises(H.TerminalFailure):
            validate_final_evidence(self.core, self.inventory, result["plans"], ALIAS, BANK,
                hooks.transcripts, changed, 1e-9, lambda s, t: t, ExpectedGuardError)

    def test_evidence_rejects_inconsistent_clock_coordinates(self):
        result, hooks = self.run_fake()
        intervals = [deepcopy(r) for kind, r in hooks.records if kind == "arm"]
        intervals[-1]["perf_end_ns"] += 1000000
        intervals[-1]["total_ns"] += 1000000
        with self.assertRaises(H.TerminalFailure):
            validate_final_evidence(self.core, self.inventory, result["plans"], ALIAS, BANK,
                hooks.transcripts, intervals, 1e-9, lambda s, t: t, ExpectedGuardError)

    def test_request_ledger_cannot_generate_before_preflight_or_overrun(self):
        ledger = self.core.ledger(self.inventory)
        with self.assertRaises(H.TerminalFailure): ledger.consume("completion", "R001", "baseline")
        self.assertEqual(ledger.total, 0)
        result, _ = self.run_fake()
        with self.assertRaises(H.TerminalFailure): result["ledger"].consume("health")
        self.assertEqual(result["ledger"].total, 398)

    def test_source_schema_rejects_answers_and_missing_primary_challenge(self):
        source_rows, metadata, order = fake_inputs()
        source_rows[0]["answer"] = "forbidden"
        with self.assertRaises(H.TerminalFailure): fake_inventory(self.core, source_rows=source_rows)
        metadata[2]["challenge_type"] = None
        with self.assertRaises(H.TerminalFailure): fake_inventory(self.core, metadata=metadata)
        order[0], order[1] = order[1], order[0]
        with self.assertRaises(H.TerminalFailure): fake_inventory(self.core, schedule=order)

    def test_cost_uses_row_ratios_all_populations_and_retains_valid_variance(self):
        rows = [dict(id=row, active=row in self.inventory.eligible_ids, complete=True, baseline=1., candidate=1.1) for row in ROW_IDS]
        report = self.core.paired_cost(self.inventory, rows, 1e-9)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["order_strata"]["AB"]["expected_n"], 44)
        self.assertEqual(report["order_strata"]["BA"]["expected_n"], 43)
        self.assertEqual(report["groups"]["active_fresh"]["expected_n"], 24)
        for row in rows:
            if row["id"] in FRESH_IDS: row["candidate"] = 1.5
        rows[0]["complete"] = False
        report = self.core.paired_cost(self.inventory, rows, 1e-9)
        self.assertEqual(report["status"], "fail")  # Definite fresh failure wins over missing old row.
        self.assertEqual(report["groups"]["all"]["expected_n"], 87)
        self.assertEqual(report["groups"]["all"]["ratios"], None)
        self.assertEqual(report["groups"]["fresh"]["ratios"]["n"], 32)

    def test_actual_policy_process_RSS_and_all87_helper_samples_required(self):
        result, _ = self.run_fake()
        metrics = {k: result["helper"][k] for k in ("owner_identity", "policy_in_owner_process", "peak_rss_bytes", "cold_start_ns")}
        metrics["peak_rss_bytes"] = 37_064_704
        with self.assertRaises(H.TerminalFailure): validate_owner_metrics(self.core, metrics, metrics["owner_identity"])
        with self.assertRaises(H.TerminalFailure):
            validate_helper_result(self.core, result["helper"]["samples"][:-1], metrics, 1e-9)

    def test_worker_response_corruption_aborts(self):
        hooks = FakeHooks(self.inventory)
        hooks.bridge.bad_response = lambda reply: reply.update(row="wrong") if reply["op"] == "PREPARED" else None
        with self.assertRaises(WorkerProtocolError): self.run_fake(hooks)
        self.assertTrue(hooks.bridge.aborted)
        self.assertEqual(hooks.ledger.counts["completion"], 0)

    def test_final_owner_metrics_include_finish_and_reaping(self):
        hooks = FakeHooks(self.inventory)
        original_metrics = hooks.bridge.metrics
        def metrics():
            result = original_metrics()
            if hooks.bridge.closed: result["peak_rss_bytes"] = 32*1024*1024+1
            return result
        hooks.bridge.metrics = metrics
        with self.assertRaises(H.TerminalFailure): self.run_fake(hooks)
        self.assertTrue(hooks.bridge.closed)
        self.assertEqual(hooks.ledger.counts["completion"], 174)
        self.assertTrue(hooks.bridge.aborted)

    def test_closed_public_projection_keeps_exact_scope_and_excludes_private_fields(self):
        from usage_public_exports import build_public
        result, hooks = self.run_fake()
        intervals = [r for kind, r in hooks.records if kind == "arm"]
        reconciliation = validate_final_evidence(self.core, self.inventory, result["plans"], ALIAS, BANK,
            hooks.transcripts, intervals, 1e-9, lambda s, t: t, ExpectedGuardError)
        result["observations"][("R001", "baseline")]["private_criteria"] = "never export this"
        public = build_public(self.core, self.inventory, dict(self.inventory.sources), result["observations"],
            consumed_http=398, validated_http=398, accounting_confirmed=True, status="complete", protocol=reconciliation,
            helper_lifecycle=result['helper']['lifecycle'],cleanup_confirmed=True,helper_samples=result['helper']['samples'])
        self.assertEqual(public["accounting.json"]["expected_http"], 398)
        self.assertEqual(public["accounting.json"]["expected_rows"], 87)
        self.assertEqual(len(public["translations.json"]["records"]), 174)
        self.assertNotIn("never export this", json.dumps(public))
        self.assertNotIn("owner_identity", json.dumps(public))
        self.assertEqual(public['metrics.json']['helper_lifecycle'],result['helper']['lifecycle'])
        self.assertTrue(public['accounting.json']['cleanup_confirmed'])
        self.assertEqual(public['metrics.json']['helper_prepare_samples'],result['helper']['samples'])
        self.assertEqual(public['metrics.json']['helper_sample_summary']['quantiles']['n'],87)
        self.assertEqual(public['metrics.json']['helper_sample_summary']['first_measured_candidate_ns'],
                         result['helper']['samples'][0]['elapsed_ns'])
        from usage_public_exports import safe_terminal
        self.assertEqual(safe_terminal(dict(status='operationally_complete',protocol_complete=True,cleanup_confirmed=None))['status'],'incomplete')
        unsafe={**result['helper']['lifecycle'],'private_dump':'must reject'}
        with self.assertRaises(H.TerminalFailure):
            build_public(self.core,self.inventory,dict(self.inventory.sources),{},consumed_http=0,validated_http=0,
                         accounting_confirmed=True,status='incomplete',helper_lifecycle=unsafe)
        with self.assertRaises(H.TerminalFailure):
            build_public(self.core,self.inventory,dict(self.inventory.sources),{},consumed_http=0,validated_http=0,
                         accounting_confirmed=True,status='incomplete',helper_samples=[{'row':'R001','elapsed_ns':1,'source':'private'}])

    def test_generic_unadmitted_entry_still_denied(self):
        with self.assertRaises(RuntimeError): run_real()
        with self.assertRaises(H.Disabled): self.core.run_real()

    def test_native_stage_hooks_with_fake_owner_transport_and_private_evidence(self):
        clock = FakeClock()
        class Loaded:
            def is_set(self): return True
        class Owner:
            loaded = Loaded()
            work_end, outer_end, phase_end, postready_end = 780., 1475., 780., None
            def check(self): pass
            def set_phase(self, name, seconds): self.phase_end = clock.ns/1e9+seconds
            def record(self, value): pass
            def publish_preflight(self, plans): pass
        class Watchdog:
            def cancel(self): pass
            def join(self, timeout): pass
            def is_alive(self): return False
        class Reader:
            def __init__(self, raw): self.raw, self.index = raw, 0
            def read(self, n, remaining):
                clock.advance(10_000)
                result = self.raw[self.index:self.index+n]
                self.index += len(result)
                return result
            def close(self): pass
        class Transport:
            def arm_watchdog(self, deadline): self.deadline = deadline; return Watchdog()
            def send(self, method, endpoint, body, remaining, **options):
                if endpoint == "/health": payload = {"status": "ok"}
                elif endpoint == "/v1/models": payload = {"data": [{"id": ALIAS}]}
                else:
                    message = json.loads(body)["messages"][0]["content"]
                    count = 48 if message.startswith("译例：") else 40
                    if endpoint.endswith("input_tokens"): payload = {"object": "response.input_tokens", "input_tokens": count}
                    else: payload = {"model": ALIAS, "choices": [{"message": {"content": "fake"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": count, "completion_tokens": 1, "total_tokens": count+1,
                                  "prompt_tokens_details": {"cached_tokens": 0}}}
                raw = H.canonical(payload)
                return Reader(b"HTTP/1.1 200 OK\r\nContent-Length: "+str(len(raw)).encode()+b"\r\n\r\n"+raw)
        class Capture:
            def __init__(self): self.raw = bytearray()
            def retain(self, data):
                H.require(len(self.raw)+len(data) <= 98304, "cap")
                self.raw.extend(data)
        class Runtime: WireCapture = Capture
        class Evidence:
            def __init__(self): self.items = []
            def json(self, name, value): self.items.append((name, value))
        evidence = Evidence()
        bridge = FakeBridge(self.inventory, clock)
        hooks = StageHooks(self.core, Runtime, Owner(), Transport(), evidence, WorkerClient(bridge, self.inventory.eligible_ids),
                           now_ns=lambda: clock.ns, clock_resolution_seconds=1e-9)
        result = execute_stage(self.core, self.inventory, ALIAS, BANK, hooks, lambda s, t: t, ExpectedGuardError)
        self.assertEqual(len(hooks.transcripts), 398)
        self.assertEqual(len(hooks.intervals), 174)
        self.assertEqual(sum(name == "wire.jsonl" for name, _ in evidence.items), 398)
        self.assertFalse(any("request_body" in record for name, record in evidence.items if name == "wire.jsonl"))
        validate_final_evidence(self.core, self.inventory, result["plans"], ALIAS, BANK,
            hooks.transcripts, hooks.intervals, 1e-9, lambda s, t: t, ExpectedGuardError)


class FrameAndBudgetTests(unittest.TestCase):
    def test_frames_duplicate_keys_caps_truncation_nonfinite_and_no_raw_errors(self):
        self.assertEqual(decode_frame(encode_frame({"source": "line1\nline2"})), {"source": "line1\nline2"})
        for payload in (b'{"op":1,"op":2}', b'{"n":NaN}', b'\xff', b'[]', b'{"x":"\\ud800"}', b'{"x":1e9999}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(WorkerProtocolError, "^FRAME$"):
                decode_frame(len(payload).to_bytes(4, "big")+payload)
        for frame in (b"", b"\0\0\0\0", encode_frame({"x": 1})[:-1], encode_frame({"x": 1})+b"x"):
            with self.assertRaises(WorkerProtocolError): decode_frame(frame)
        with self.assertRaises(WorkerProtocolError): encode_frame({"x": "a"*32768})

    def test_active_budget_does_not_reset_for_idle_or_new_command(self):
        b = ActiveBudget(0, 800_000_000_000, 600_000_000_000, 800_000_000_000)
        b.finish_roundtrip(1_000_000_000)
        self.assertEqual(b.remaining, 14_000_000_000)
        self.assertEqual(b.begin_roundtrip(100_000_000_000, 600_000_000_000), 114_000_000_000)
        b.finish_roundtrip(101_000_000_000)
        self.assertEqual(b.remaining, 13_000_000_000)
        with self.assertRaises(WorkerProtocolError): b.begin_roundtrip(580_000_000_000, 600_000_000_000)
        self.assertEqual(b.emergency_deadline(590_000_000_000), 600_000_000_000)

    def test_state_rejects_wrong_row_duplicate_gate_early_seal_and_extra_command(self):
        core = UsageCore(H, P)
        inv = fake_inventory(core)
        for bad in ({"op": "SEAL", "preflight_digest": "0"*64, "eligible_ids": list(inv.eligible_ids)},
                    {"op": "FINISH"}, {"op": "GATE"}, {"op": "PREPARE", "row": "R002"}):
            worker = PolicyWorker(P, BANK, ROW_IDS, inv.eligible_ids,
                                  {r: sha256(s.encode()).hexdigest() for r, s in inv.sources.items()})
            worker.ready()
            with self.assertRaisesRegex(WorkerProtocolError, "^PROTOCOL$"): worker.exchange_frame(encode_frame(bad))
            self.assertEqual(worker.phase, "failed")
            with self.assertRaises(WorkerProtocolError): worker.handle({"op": "FINISH"})


if __name__ == "__main__": unittest.main()
