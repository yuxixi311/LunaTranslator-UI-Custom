"""Synthetic illustrative evidence only; no fresh-source inference or native I/O."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from test_term_runner import (ROOT, ALIAS, DECLARATIONS, Hooks, TermCore, inventory,
    execute_stage, validate_integrity, LocalTranslationError, h, p)
from term_evidence_validation import validate_final_evidence, replay_policy_offline
from term_public_exports import build_public, finalize_payloads, preflight_receipt, safe_terminal, PUBLIC_FILES


GUARD_BYTES = (ROOT/"audited/myutils/local_translation_integrity.py").read_bytes()


def response_wire(payload):
    raw = h.canonical(payload)
    return raw, b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw


class EvidenceHooks(Hooks):
    """Deterministic in-memory HTTP/clock fixtures, including failed intents."""
    def exchange(self, ledger, kind, row, arm, body, validate):
        ledger.consume(kind, row, arm)
        started = self.clock.ns
        if kind == "health": payload = dict(status="ok")
        elif kind == "models": payload = dict(data=[dict(id=ALIAS)])
        elif kind in ("preflight", "recurring"):
            payload = dict(object="response.input_tokens", input_tokens=self.count(kind, row, arm, body))
        else:
            source = h.strict_json(self.inv.rows[row])["source"]
            output = "{LT0}" if arm == "candidate" and row in self.inv.eligible_ids else source
            if self.output_override: output = self.output_override(row, arm, output)
            count = self.count(kind, row, arm, body)
            payload = dict(model=ALIAS, choices=[dict(message=dict(content=output), finish_reason="stop")],
                usage=dict(prompt_tokens=count, completion_tokens=3, total_tokens=count+3,
                           prompt_tokens_details=dict(cached_tokens=0)))
            if getattr(self, "length_finish", False) and (row, arm) == ("R001", "baseline"):
                payload["choices"][0]["finish_reason"] = "length"
        raw, wire = response_wire(payload)
        self.clock.advance(1_000_000)
        failed = True
        try:
            result = validate(raw)
            failed = False
            return result, self.clock.ns-started
        finally:
            self.transcripts.append(dict(kind=kind, row=row, arm=arm, request_body=body, response_wire=wire,
                request_sha256=h.digest(body) if body is not None else None, response_sha256=h.digest(wire),
                start=started/1e9, validated_end=None if failed else self.clock.ns/1e9,
                deadline=started/1e9+h.ENDPOINTS[kind][3]-.01, request_number=ledger.total,
                attempted=True, status="failed" if failed else "validated", failure="SYNTHETIC" if failed else None))


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = TermCore(h, p)
        cls.inv = inventory(cls.core)
        cls.hooks = EvidenceHooks(cls.inv)
        cls.result = execute_stage(cls.core, cls.inv, ALIAS, DECLARATIONS, cls.hooks,
                                   validate_integrity, LocalTranslationError)
        cls.plans = cls.result["plans"]
        cls.intervals = [record for kind, record in cls.hooks.records if kind == "arm"]

    def reconcile(self, *, transcripts=None, intervals=None, plans=None, guard_bytes=GUARD_BYTES):
        return validate_final_evidence(self.core, self.inv, self.plans if plans is None else plans,
            ALIAS, DECLARATIONS, self.hooks.transcripts if transcripts is None else transcripts,
            self.intervals if intervals is None else intervals, 1e-9, validate_integrity,
            LocalTranslationError, guard_source_bytes=guard_bytes)

    def export(self, observations=None, **kwargs):
        args = dict(consumed_http=378, validated_http=378, accounting_confirmed=True, cleanup_confirmed=True)
        args.update(kwargs)
        return build_public(self.core, self.inv, self.plans,
                            self.result["observations"] if observations is None else observations, **args)

    def finalize(self, payloads=None, **kwargs):
        args = dict(protocol_complete=True, reconciliation=self.reconcile(), helper_samples=self.hooks.helper_samples,
            helper_lifecycle=self.result["helper"]["lifecycle"], runner_peak_rss_bytes=64*h.MIB,
            server_peak_rss_bytes=1024*h.MIB,
            helper_metrics=dict(helper_peak_rss_bytes=self.result["helper"]["owner"]["peak_rss_bytes"],
                helper_render_p95_ns=h.quantiles([r["elapsed_ns"] for r in self.hooks.helper_samples])["p95"]),
            cleanup_confirmed=True, diagnostic=None, clock_resolution_seconds=1e-9)
        args.update(kwargs)
        return finalize_payloads(self.core, self.inv, self.plans, self.result["observations"],
                                 self.export() if payloads is None else payloads, **args)

    def test_exact378_reconciliation_all_four_populations(self):
        report = self.reconcile()
        self.assertEqual(report["reconciled_http"], 378)
        self.assertEqual(report["observed_completions"], 176)
        self.assertEqual(report["tokens"]["count_only_requests"], 200)
        self.assertEqual(report["tokens"]["generation_prompt_tokens"], self.result["totals"]["generation_prompt_tokens"])
        self.assertEqual({k: v["expected_n"] for k, v in report["cost"]["populations"].items()},
                         dict(ALL88=88, FRESH19=19, ACTIVE_ALL=12, ACTIVE_FRESH=12))
        self.assertTrue(report["cost"]["quality_failures_included"])
        self.assertTrue(report["cost"]["no_post_output_exclusions"])
        self.assertTrue(report["original_guard_source_verified"])
        self.assertIsNone(report["semantic_quality_claim"])

    def test_snapshot_cleanup_scope_does_not_override_later_terminal_failure(self):
        snapshot=self.finalize()
        for name in ("accounting.json","metrics.json"):
            self.assertEqual(snapshot[name]["cleanup_scope"],"owned_supervisor_at_snapshot")
            self.assertEqual(snapshot[name]["overall_attempt_status_source"],"terminal_result")
            self.assertTrue(snapshot[name]["protocol_complete"])
        for result in (dict(status="incomplete",protocol_complete=True,cleanup_confirmed=True),
                       dict(status="operationally_complete",protocol_complete=True,cleanup_confirmed=False)):
            terminal=safe_terminal(result)
            self.assertEqual(terminal["cleanup_scope"],"whole_attempt")
            self.assertEqual(terminal["status"],"incomplete")
    def test_final_reconciliation_never_reestablishes_candidate_admission(self):
        with patch.object(p, "prepare", side_effect=AssertionError("no candidate admission replay")), \
             patch.object(p, "apply_token_gate", side_effect=AssertionError("no token-gate replay")):
            self.reconcile()
        self.assertTrue(replay_policy_offline(self.core, self.inv, self.plans, ALIAS, DECLARATIONS))

    def test_wrong_guard_source_rejected_and_fake_without_attestation_identified(self):
        with self.assertRaises(h.TerminalFailure): self.reconcile(guard_bytes=b"wrong source")
        report = self.reconcile(guard_bytes=None)
        self.assertFalse(report["original_guard_source_verified"])
        self.assertIsNone(report["original_guard_sha256"])

    def test_omitted_reordered_extra_transcripts_rejected(self):
        changed = deepcopy(self.hooks.transcripts)
        changed[178], changed[179] = changed[179], changed[178]
        for records in (changed, self.hooks.transcripts[:-1], self.hooks.transcripts+[self.hooks.transcripts[-1]]):
            with self.subTest(length=len(records)), self.assertRaises(h.TerminalFailure):
                self.reconcile(transcripts=records)

    def test_missing_or_reordered_intervals_cannot_drop_quality_failures(self):
        changed = deepcopy(self.intervals)
        changed[0], changed[1] = changed[1], changed[0]
        for records in (changed, self.intervals[:-1]):
            with self.assertRaises(h.TerminalFailure): self.reconcile(intervals=records)

    def test_wire_hash_framing_count_usage_and_number_tampering_rejected(self):
        for mode in ("hash", "trailing", "count", "usage", "number", "status", "deadline"):
            records = deepcopy(self.hooks.transcripts)
            index = 2 if mode == "count" else 178
            record = records[index]
            if mode == "hash": record["response_sha256"] = "0"*64
            elif mode == "trailing":
                record["response_wire"] += b"x"
                record["response_sha256"] = h.digest(record["response_wire"])
            elif mode in ("count", "usage"):
                raw = record["response_wire"].split(b"\r\n\r\n", 1)[1]
                payload = h.strict_json(raw)
                if mode == "count": payload["input_tokens"] += 1
                else: payload["usage"]["prompt_tokens_details"]["cached_tokens"] = 1
                _, record["response_wire"] = response_wire(payload)
                record["response_sha256"] = h.digest(record["response_wire"])
            elif mode == "number": record["request_number"] += 1
            elif mode == "status": record["status"] = "failed"
            else: record["deadline"] = record["validated_end"]
            with self.subTest(mode=mode), self.assertRaises(h.TerminalFailure): self.reconcile(transcripts=records)

    def test_rehashed_sampling_and_template_receipt_drift_rejected(self):
        plan = self.plans[0]
        request = h.strict_json(plan.baseline.body)
        request["temperature"] = .8
        changed = replace(plan, baseline=replace(plan.baseline, body=h.canonical(request)))
        with self.assertRaises(h.TerminalFailure): self.reconcile(plans=(changed, *self.plans[1:]))
        changed = replace(plan, baseline=replace(plan.baseline, template="0"*64))
        with self.assertRaises(h.TerminalFailure): self.reconcile(plans=(changed, *self.plans[1:]))

    def test_forged_token_gate_and_inactive_count_receipts_rejected(self):
        plan = self.plans[69]
        changed = replace(plan, decision=replace(plan.decision, active=False, reason="token_budget",
                          prompt=plan.prepared.baseline_prompt), candidate=plan.baseline)
        with self.assertRaises(h.TerminalFailure):
            self.reconcile(plans=(*self.plans[:69], changed, *self.plans[70:]))
        plan = self.plans[0]
        changed = replace(plan, provisional=replace(plan.provisional, count=41),
                          decision=replace(plan.decision, provisional_tokens=41))
        with self.assertRaises(h.TerminalFailure): self.reconcile(plans=(changed, *self.plans[1:]))

    def test_original_final_receipt_source_usage_and_timing_drift_rejected(self):
        index = next(i for i, value in enumerate(self.intervals)
                     if value["row"] in self.inv.eligible_ids and value["arm"] == "candidate")
        for mode in ("original", "final", "receipt", "source", "usage", "clock", "seconds", "membership", "flags", "components"):
            records = deepcopy(self.intervals)
            record = records[index]
            if mode == "original":
                record["original_output"] = "changed {LT0}"
                record["original_output_sha256"] = h.digest(record["original_output"].encode())
            elif mode == "final":
                record["final_output"] = "changed output"
                record["final_output_sha256"] = h.digest(record["final_output"].encode())
            elif mode == "receipt": record["actual_receipt"]["input_tokens"] += 1
            elif mode == "source": record["source_sha256"] = "0"*64
            elif mode == "usage": record["usage"]["total_tokens"] += 1
            elif mode == "clock": record["total_ns"] += 1
            elif mode == "seconds": record["start"] = record["perf_start_ns"]/1e9+1
            elif mode == "membership": record["preflight_active"] = False
            elif mode == "flags": record["flags"].append("integrity_rejection")
            else: record["components"]["count_ns"] = []
            with self.subTest(mode=mode), self.assertRaises(h.TerminalFailure): self.reconcile(intervals=records)

    def test_structural_and_oversize_rejections_are_complete_retained_observations(self):
        for bad, rejection in (("missing issued marker", "MARKER_OR_STRUCTURE_REJECTED"),
                               ("x"*33000+"{LT0}", "INPUT_FRAME_BOUND"),
                               ("x"*32501+"{LT0}", "OUTPUT_FRAME_BOUND")):
            hooks = EvidenceHooks(self.inv, output_override=lambda row, arm, value:
                bad if row == self.inv.fresh_ids[0] and arm == "candidate" else value)
            result = execute_stage(self.core, self.inv, ALIAS, DECLARATIONS, hooks, validate_integrity, LocalTranslationError)
            intervals = [r for name, r in hooks.records if name == "arm"]
            report = validate_final_evidence(self.core, self.inv, result["plans"], ALIAS, DECLARATIONS,
                hooks.transcripts, intervals, 1e-9, validate_integrity, LocalTranslationError, guard_source_bytes=GUARD_BYTES)
            record = report["all_rows"][69]["arms"]["candidate"]
            self.assertEqual(record["original_output"], bad)
            self.assertIsNone(record["final_output"])
            self.assertEqual(record["restoration_rejection"], rejection)
            self.assertEqual(report["observed_completions"], 176)
            exported = self.export(result["observations"])
            self.assertEqual(exported["accounting.json"]["status"], "complete_observations")
            self.assertEqual(exported["accounting.json"]["structural_failures"], 1)

    def test_empty_and_length_failures_keep_all_cost_denominators(self):
        hooks = EvidenceHooks(self.inv, output_override=lambda row, arm, value:
                              "" if (row, arm) == ("R001", "baseline") else value)
        hooks.length_finish = True
        result = execute_stage(self.core, self.inv, ALIAS, DECLARATIONS, hooks, validate_integrity, LocalTranslationError)
        intervals = [r for name, r in hooks.records if name == "arm"]
        report = validate_final_evidence(self.core, self.inv, result["plans"], ALIAS, DECLARATIONS,
            hooks.transcripts, intervals, 1e-9, validate_integrity, LocalTranslationError, guard_source_bytes=GUARD_BYTES)
        record = report["all_rows"][0]["arms"]["baseline"]
        self.assertEqual(record["flags"], ["empty_output", "length_finish"])
        self.assertTrue(record["scoreable_generation_failure"])
        self.assertEqual(record["final_output"], "")
        self.assertEqual(report["cost"]["populations"]["ALL88"]["observed_n"], 88)
        self.assertEqual(report["observed_completions"], 176)

    def test_public_unknown_accounting_retains_denominator(self):
        result = build_public(self.core, self.inv, (), {}, consumed_http=None, validated_http=None,
            accounting_confirmed=False, cleanup_confirmed=None, execution_kind="reviewed_native_evidence")
        accounting = result["accounting.json"]
        self.assertEqual(accounting["status"], "incomplete")
        self.assertIsNone(accounting["consumed_http"])
        self.assertIsNone(accounting["validated_http"])
        self.assertTrue(all(r["state"] == "unknown" for r in accounting["calls"]))
        self.assertEqual(accounting["unobserved_completions"], 176)
        with self.assertRaises(h.TerminalFailure):
            self.export(consumed_http=None, accounting_confirmed=True)

    def test_public_closed_nested_receipts_reject_path_and_mismatch(self):
        key = self.inv.schedule[0]
        for name, value in (("host_path", "/private/host/secret"), ("runtime", "/private/host/secret"), ("input_tokens", True)):
            observations = deepcopy(self.result["observations"])
            observations[key]["actual_receipt"][name] = value
            with self.subTest(name=name), self.assertRaises(h.TerminalFailure): self.export(observations)

    def test_public_projects_extra_caller_and_usage_fields_without_aliasing(self):
        observations = deepcopy(self.result["observations"])
        key = self.inv.schedule[0]
        record = observations[key]
        record["exception"] = "/private/host/secret"
        record["usage"]["host_path"] = "/private/host/secret"
        record["usage"]["prompt_tokens_details"]["host_path"] = "/private/host/secret"
        result = self.export(observations)
        self.assertNotIn("/private/host/secret", json.dumps(result))
        record["actual_receipt"]["runtime"] = "/later/mutation"
        self.assertNotIn("/later/mutation", json.dumps(result))
        self.assertEqual(result["accounting.json"]["evidence_kind"], "illustrative_fake_only_not_fresh")

    def test_public_rejects_output_hash_state_usage_and_prefix_inconsistency(self):
        key = self.inv.schedule[0]
        for mode in ("hash", "state", "usage", "timing"):
            observations = deepcopy(self.result["observations"])
            record = observations[key]
            if mode == "hash": record["original_output_sha256"] = "0"*64
            elif mode == "state": record["restoration_status"] = "restored"
            elif mode == "usage": record["usage"]["completion_tokens"] = True
            else: record["perf_end_ns"] += 1
            with self.subTest(mode=mode), self.assertRaises(h.TerminalFailure): self.export(observations)
        with self.assertRaises(h.TerminalFailure): self.export(validated_http=377)

    def test_worker_terminal_retains_received_original_and_remaining_unobserved(self):
        hooks = EvidenceHooks(self.inv)
        hooks.backend.state._restore = lambda message: (_ for _ in ()).throw(RuntimeError("synthetic worker failure"))
        with self.assertRaises(h.TerminalFailure):
            execute_stage(self.core, self.inv, ALIAS, DECLARATIONS, hooks, validate_integrity, LocalTranslationError)
        observations = {(r["row"], r["arm"]): r for name, r in hooks.records if name == "arm"}
        result = self.export(observations, consumed_http=hooks.ledger.total,
            validated_http=len([r for r in hooks.transcripts if r["status"] == "validated"]),
            cleanup_confirmed=False)
        record = next(r for r in result["outputs.json"] if r["state"] == "operational_failure")
        self.assertEqual(record["original_output"], "{LT0}")
        self.assertEqual(record["original_output_sha256"], h.digest(b"{LT0}"))
        self.assertIsNone(record["final_output"])
        self.assertEqual(len(result["outputs.json"]), 176)
        self.assertGreater(result["accounting.json"]["unobserved_completions"], 0)
        self.assertEqual(result["accounting.json"]["status"], "incomplete")

    def test_count_failure_before_completion_retains_failed_arm_and_unissued_call(self):
        hooks = EvidenceHooks(self.inv, count_override=lambda kind, row, arm, value:
                              value+1 if kind == "recurring" else value)
        with self.assertRaises(h.TerminalFailure):
            execute_stage(self.core, self.inv, ALIAS, DECLARATIONS, hooks, validate_integrity, LocalTranslationError)
        observations = {(r["row"], r["arm"]): r for name, r in hooks.records if name == "arm"}
        result = self.export(observations, consumed_http=hooks.ledger.total,
            validated_http=len([r for r in hooks.transcripts if r["status"] == "validated"]), cleanup_confirmed=True)
        record = next(r for r in result["outputs.json"] if r["state"] == "operational_failure")
        self.assertEqual((record["id"], record["arm"]), (self.inv.eligible_ids[0], "candidate"))
        self.assertIsNone(record["original_output"])
        self.assertIsNone(record["original_output_sha256"])
        call = next(r for r in result["accounting.json"]["calls"] if
                    (r["kind"], r["id"], r["arm"]) == ("completion", record["id"], record["arm"]))
        self.assertEqual(call["state"], "unissued")
        self.assertGreater(call["number"], hooks.ledger.total)
        self.assertEqual(len(result["outputs.json"]), 176)
        self.assertEqual(result["accounting.json"]["status"], "incomplete")

    def test_preflight_and_terminal_closed_states(self):
        result = preflight_receipt(self.core, self.inv, self.plans, "a"*64, "b"*64)
        self.assertEqual(result["planned_http"], 378)
        self.assertEqual(result["preflight_count_requests"], 176)
        self.assertEqual(result["measured_completions_before_receipt"], 0)
        self.assertEqual(result["coverage_status"], "pass")
        self.assertEqual(len(result["rows"]), 88)
        self.assertLessEqual(len(h.canonical(result)), 65536)
        with self.assertRaises(h.TerminalFailure):
            preflight_receipt(self.core, self.inv, self.plans, "/host/private", "b"*64)
        terminal = safe_terminal(dict(status="operationally_complete", protocol_complete=True,
                                     cleanup_confirmed=None, exception="/private/host/secret"))
        self.assertEqual(terminal["status"], "incomplete")
        self.assertNotIn("/private/host/secret", json.dumps(terminal))
        self.assertEqual(safe_terminal(dict(status="operationally_complete", protocol_complete=True,
                                          cleanup_confirmed=True))["status"], "complete")

    def test_final_closed_artifacts_samples_cost_and_exact_manifest_bytes(self):
        result = self.finalize()
        self.assertEqual(set(result), set(PUBLIC_FILES))
        metrics = result["metrics.json"]
        self.assertTrue(metrics["protocol_complete"])
        self.assertEqual(metrics["protocol_status"], "complete")
        self.assertEqual(metrics["helper_prepare_samples"], self.hooks.helper_samples)
        self.assertEqual(metrics["helper_sample_summary"]["n"], 88)
        self.assertEqual(metrics["helper_sample_summary"]["first_measured_candidate_ns"], self.hooks.helper_samples[0]["elapsed_ns"])
        self.assertEqual(metrics["helper_sample_summary"]["quantiles"]["n"], 88)
        self.assertEqual(set(metrics["cost"]["populations"]), {"ALL88", "FRESH19", "ACTIVE_ALL", "ACTIVE_FRESH"})
        self.assertNotIn("all_rows", metrics["protocol"])
        self.assertNotIn("cost", metrics["protocol"])
        self.assertTrue(result["accounting.json"]["protocol_evidence_reconciled"])
        for item in result["manifest.json"]["files"]:
            raw = h.canonical(result[item["file"]])+b"\n"
            self.assertEqual(item["bytes"], len(raw))
            self.assertEqual(item["sha256"], h.digest(raw))
        self.assertNotIn("manifest.json", [item["file"] for item in result["manifest.json"]["files"]])
        self.assertEqual(result["manifest.json"]["artifact_encoding"], "canonical_json_utf8_plus_lf")

    def test_final_partial_samples_and_unknown_cleanup_remain_explicit(self):
        base = self.export(cleanup_confirmed=None)
        result = self.finalize(base, protocol_complete=False, reconciliation=None, helper_samples=self.hooks.helper_samples[:3],
            helper_lifecycle=None, helper_metrics=None, cleanup_confirmed=None,
            runner_peak_rss_bytes=None, server_peak_rss_bytes=None)
        metrics = result["metrics.json"]
        self.assertIsNone(result["accounting.json"]["cleanup_confirmed"])
        self.assertIsNone(metrics["cleanup_confirmed"])
        self.assertFalse(metrics["protocol_complete"])
        self.assertEqual(metrics["protocol_status"], "incomplete")
        self.assertEqual(metrics["helper_sample_summary"]["n"], 3)
        self.assertFalse(metrics["helper_sample_summary"]["complete"])
        self.assertIsNone(metrics["helper_sample_summary"]["quantiles"])
        self.assertEqual(metrics["helper_prepare_samples"], self.hooks.helper_samples[:3])
        for key in ("helper_lifecycle", "helper_metrics", "runner_peak_rss_bytes", "server_peak_rss_bytes"):
            self.assertIsNone(metrics[key])
        empty = self.finalize(base, protocol_complete=False, reconciliation=None, helper_samples=[],
            helper_lifecycle=None, helper_metrics=None, cleanup_confirmed=None)
        self.assertIsNone(empty["metrics.json"]["helper_sample_summary"]["first_measured_candidate_ns"])

    def test_all_observations_alone_do_not_imply_protocol_completion(self):
        result = self.finalize(protocol_complete=False, reconciliation=None)
        self.assertEqual(result["accounting.json"]["status"], "complete_observations")
        self.assertFalse(result["accounting.json"]["protocol_complete"])
        self.assertEqual(result["accounting.json"]["protocol_status"], "incomplete")
        self.assertIsNone(result["metrics.json"]["protocol"])
        with self.assertRaises(h.TerminalFailure): self.finalize(reconciliation=None)
        result = self.finalize(self.export(cleanup_confirmed=None), cleanup_confirmed=None)
        self.assertFalse(result["accounting.json"]["protocol_complete"])
        self.assertIsNotNone(result["metrics.json"]["protocol"])

    def test_final_rejects_nested_host_sentinels_and_inconsistent_reconciliation(self):
        for mode in ("samples", "lifecycle", "helper", "reconciliation", "cost", "all_rows", "tokens", "rss", "clock", "base"):
            kwargs = {}
            payloads = None
            if mode == "samples":
                kwargs["helper_samples"] = deepcopy(self.hooks.helper_samples)
                kwargs["helper_samples"][0]["host_path"] = "/private/host/sentinel"
            elif mode == "lifecycle":
                kwargs["helper_lifecycle"] = {**self.result["helper"]["lifecycle"], "host_path": "/private/host/sentinel"}
            elif mode == "helper":
                kwargs["helper_metrics"] = dict(helper_peak_rss_bytes=16*h.MIB, helper_render_p95_ns=1,
                                               host_path="/private/host/sentinel")
            elif mode in ("reconciliation", "cost", "all_rows", "tokens"):
                value = self.reconcile()
                if mode == "reconciliation": value["host_path"] = "/private/host/sentinel"
                elif mode in ("cost", "all_rows"): value[mode] = "/private/host/sentinel"
                else: value["tokens"]["generated_tokens"] += 1
                kwargs["reconciliation"] = value
            elif mode == "rss": kwargs["server_peak_rss_bytes"] = "/private/host/sentinel"
            elif mode == "clock": kwargs["clock_resolution_seconds"] = float("nan")
            else:
                payloads = self.export()
                payloads["arbitrary.json"] = {"host_path": "/private/host/sentinel"}
            with self.subTest(mode=mode), self.assertRaises(h.TerminalFailure): self.finalize(payloads, **kwargs)

    def test_final_samples_lifecycle_and_helper_metrics_are_finite_and_bound(self):
        for mode in ("sample_order", "sample_type", "commands", "active", "cpu", "lifetime", "helper_rss", "helper_p95"):
            kwargs = {}
            if mode.startswith("sample"):
                kwargs["helper_samples"] = deepcopy(self.hooks.helper_samples)
                if mode == "sample_order": kwargs["helper_samples"][0]["row"] = self.inv.row_ids[1]
                else: kwargs["helper_samples"][0]["elapsed_ns"] = True
            elif mode in ("commands", "active", "cpu", "lifetime"):
                kwargs["helper_lifecycle"] = dict(self.result["helper"]["lifecycle"])
                key, value = {"commands": ("commands", 215), "active": ("active_work_ns", 15_000_000_001),
                    "cpu": ("worker_cpu_ns", 15_000_000_001), "lifetime": ("lifetime_ns", 600_000_000_001)}[mode]
                kwargs["helper_lifecycle"][key] = value
            else:
                kwargs["helper_metrics"] = dict(helper_peak_rss_bytes=33*h.MIB if mode == "helper_rss" else 16*h.MIB,
                    helper_render_p95_ns=1)
            with self.subTest(mode=mode), self.assertRaises(h.TerminalFailure): self.finalize(**kwargs)

    def test_final_diagnostic_is_validated_and_detached(self):
        import diagnostics
        diagnostic = diagnostics.Trace("a"*64).snapshot()
        result = self.finalize(diagnostic=diagnostic)
        diagnostic["assets"][0]["received_bytes"] = 123
        self.assertIsNone(result["diagnostic.json"]["assets"][0]["received_bytes"])
        diagnostic["host_path"] = "/private/host/sentinel"
        with self.assertRaises(ValueError): self.finalize(diagnostic=diagnostic)

    def test_final_aggregate_cap_applies_after_metrics_diagnostic_and_manifest(self):
        base = self.export()
        base_size = sum(len(h.canonical(value))+1 for value in base.values())
        # Shrink only the public cap in this synthetic test: all three base
        # artifacts fit, while the final additions exceed that same cap.
        with patch("term_public_exports.PUBLIC_EXPORT_CAP", base_size+1):
            with self.assertRaisesRegex(h.TerminalFailure, "final aggregate public artifact byte cap"):
                self.finalize(base)


if __name__ == "__main__": unittest.main()
