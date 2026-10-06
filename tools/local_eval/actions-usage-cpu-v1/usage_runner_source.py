"""Inert stage orchestration with explicit injected, verified adapter hooks.

No transport, filesystem, process, or activation adapter is implemented here.
Tests inject deterministic fakes. A native bridge needs separate review/release.
"""
from usage_runner_core import (ROW_IDS, GENERATION_PROMPT_CAP, GENERATED_CAP)
from usage_helper_source import validate_helper_result, validate_owner_metrics


def execute_stage(core, inventory, alias, bank_bytes, hooks, integrity, expected_error):
    """Readiness -> all preflight/coverage -> exactly paired completion, with nested helper timing.

    hooks.exchange must use the unchanged checked/recorded exchange and consume
    the supplied ledger exactly once before any send. It owns unchanged absolute
    deadline/watchdog/wire handling. hooks.record persists only after arm timing.
    Native ownership/host/acquisition/cleanup never originates from this module.
    """
    h = core.h
    ledger = core.ledger(inventory, hooks.event)
    hooks.ledger = ledger
    if hasattr(hooks, "owner"):
        hooks.owner.public_ledger = ledger
    observations, plans, helper_samples = {}, [], []
    hooks.helper_samples = helper_samples
    totals = dict(generation_prompt_tokens=0, generated_tokens=0,
                  measured_count_requests=0, measured_count_input_tokens=0)

    def check():
        hooks.check()
        return (validate_owner_metrics(core, hooks.worker.metrics(), hooks.worker.owner_identity)
                if hooks.worker.started else None)

    def exchange(kind, row, arm, body, validate):
        check()
        before = ledger.total
        result, elapsed = hooks.exchange(ledger, kind, row, arm, body, validate)
        h.require(ledger.total == before + 1 and type(elapsed) is int and elapsed >= 0,
                  "exactly one accounted exchange")
        return result, elapsed

    try:
        hooks.ready_marker()  # Local readiness only; it must make no HTTP call.
        exchange("health", None, None, None, lambda raw: h.readiness_response("health", raw, alias))
        exchange("models", None, None, None, lambda raw: h.readiness_response("models", raw, alias))
        hooks.postready_limit(600)
        hooks.phase("preflight", 60)
        hooks.worker.start()
        for row in ROW_IDS:
            sides = iter(("baseline", "second"))
            def count(body):
                return exchange("preflight", row, next(sides), body, h.token_response)[0]
            plans.append(core.preflight_pair(row, inventory.sources[row], alias, bank_bytes, count, worker=hooks.worker))
        try:
            coverage = core.validate_preflight(inventory, plans)
        except h.TerminalFailure:
            coverage = None
        hooks.record("preflight", dict(eligible=list(inventory.eligible_ids), request_total=inventory.request_total,
                     source_digest=inventory.source_digest, metadata_digest=inventory.metadata_digest,
                     schedule_digest=inventory.schedule_digest, coverage=coverage,
                     coverage_status="pass" if coverage is not None else "fail",
                     rows=[dict(id=p.row_id, eligible=p.eligible, active=p.active, reason=p.reason,
                                baseline=p.baseline.binding, prospective=p.provisional.binding,
                                actual_candidate=p.candidate.binding) for p in plans]))
        hooks.publish_preflight(plans)
        ledger.seal_preflight(plans)
        hooks.worker.seal(h.digest(h.canonical([dict(row=p.row_id, baseline=p.baseline.binding,
            prospective=p.provisional.binding, actual=p.candidate.binding) for p in plans])))
        hooks.resume_postready_limit()
        by_id = {plan.row_id: plan for plan in plans}
        for row, arm in inventory.schedule:
            check()
            plan, source = by_id[row], inventory.sources[row]
            started = hooks.now_ns()
            start = started/1e9
            parts = dict(token_counter_ns=[], renderer_ns=0, construction_ns=0, completion_ns=0, integrity_ns=0)
            try:
                if arm == "baseline":
                    before = hooks.now_ns()
                    body = h.serialize_request(core.policy.baseline_messages(source), alias)
                    h.require(body == plan.baseline.body, "measured baseline drift")
                    parts["construction_ns"] = hooks.now_ns() - before
                    receipt = plan.baseline
                else:
                    sides = iter(("baseline", "provisional"))
                    def count(body):
                        value, elapsed = exchange("recurring", row, next(sides), body, h.token_response)
                        parts["token_counter_ns"].append(elapsed)
                        totals["measured_count_requests"] += 1
                        totals["measured_count_input_tokens"] += value
                        return value
                    before = hooks.now_ns()
                    def on_prepared():
                        helper_samples.append(dict(row=row, elapsed_ns=hooks.now_ns()-before))
                    body = core.measured_candidate(plan, source, alias, bank_bytes, count, on_prepared, worker=hooks.worker)
                    parts["renderer_ns"] = hooks.now_ns() - before
                    receipt = plan.candidate  # Actual B on fallback, never prospective C.
                def validate(raw):
                    def timed_guard(raw_source, text):
                        before = hooks.now_ns()
                        try:
                            return integrity(raw_source, text)
                        finally:
                            parts["integrity_ns"] = hooks.now_ns() - before
                    return h.completion_response(raw, alias, receipt, source, timed_guard, expected_error)
                result, elapsed = exchange("completion", row, arm, body, validate)
                h.require(elapsed >= parts["integrity_ns"], "completion/guard timer consistency")
                parts["completion_ns"] = elapsed - parts["integrity_ns"]
                finished = hooks.now_ns()
                end = finished/1e9
                h.require(finished > started and end > start, "positive measured interval")
                result.pop("raw_response")
                record = dict(status="observed", row=row, arm=arm, total_ns=finished-started,
                              perf_start_ns=started, perf_end_ns=finished, start=start, end=end,
                              components=parts, request_sha256=h.digest(body), actual_receipt=receipt.binding,
                              prospective_receipt=plan.provisional.binding if arm == "candidate" else None,
                              preflight_active=plan.active, **result)
                observations[(row, arm)] = record
                totals["generation_prompt_tokens"] += result["usage"]["prompt_tokens"]
                totals["generated_tokens"] += result["usage"]["completion_tokens"]
                h.require(totals["generation_prompt_tokens"] <= GENERATION_PROMPT_CAP and
                          totals["generated_tokens"] <= GENERATED_CAP, "narrow generation token ceilings")
            except BaseException as exc:
                finished = hooks.now_ns()
                end = finished/1e9
                record = dict(status="operational_failure", row=row, arm=arm, failure=type(exc).__name__,
                              total_ns=finished-started, perf_start_ns=started, perf_end_ns=finished,
                              start=start, end=end, timing_scoreable=False, preflight_active=plan.active)
                observations[(row, arm)] = record
                ledger.fail("measured_arm_failure")
                hooks.record("arm", record)
                raise
            hooks.record("arm", record)  # Evidence writing excluded identically for both arms.
        ledger.assert_complete()
        check()
        hooks.worker.finish()
        owner_metrics = validate_owner_metrics(core, hooks.worker.metrics(), hooks.worker.owner_identity)
        helper_result = validate_helper_result(core, helper_samples, owner_metrics, hooks.clock_resolution_seconds)
        timing = hooks.worker.timing_metrics()
        h.require(set(timing) == {"active_work_ns", "worker_cpu_ns", "lifetime_ns", "startup_ns", "finish_ns", "commands",
                                 "parent_setup_ns", "parent_setup_cpu_ns"} and
                  all(type(v) is int and v >= 0 for v in timing.values()) and timing["commands"] == 224 and
                  0 < timing["active_work_ns"] <= 15_000_000_000 and timing["worker_cpu_ns"] <= 15_000_000_000 and
                  0 < timing["lifetime_ns"] <= 600_000_000_000 and timing["startup_ns"] == owner_metrics["cold_start_ns"] and
                  timing["startup_ns"] + timing["finish_ns"] <= timing["active_work_ns"] and
                  timing["parent_setup_ns"] <= timing["startup_ns"], "complete helper lifecycle facts")
        helper_result["lifecycle"] = timing
        hooks.record("helper", helper_result)
        h.require(totals["measured_count_requests"] == 2 * len(inventory.eligible_ids), "all measured count costs retained")
        return dict(status="synthetic_or_unreleased_stage_complete", inventory=inventory, plans=tuple(plans),
                    observations=observations, totals=totals, ledger=ledger, helper=helper_result, semantic_quality_claim=None)
    except BaseException:
        ledger.fail("stage_terminal_failure")
        cleanup = hooks.worker.abort()
        hooks.record("helper_terminal", {
            key: cleanup.get(key) if type(cleanup) is dict and type(cleanup.get(key)) is bool else None
            for key in ("cleanup_confirmed", "reaped", "protocol_complete")})
        raise
    finally:
        hooks.record("all_rows", core.all_row_accounting(inventory, observations))


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE ONLY: native adapter/claim/bootstrap wiring is not released")


if __name__ == "__main__":
    run_real()
