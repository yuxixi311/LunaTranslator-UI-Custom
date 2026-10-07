"""Closed public fictional-source and observed-output projection.

No host paths, arbitrary nested maps, raw wire, logs, identities, private
criteria or quality claims are copied. These functions return objects only.
"""
from term_runner_core import PAIR_COUNT, COMPLETION_COUNT, MAX_HTTP, GENERATION_PROMPT_CAP, GENERATED_CAP
from term_evidence_validation import (inventory_projection, receipt_projection,
    observation_projection, validate_plans, sha_field, finite_time)


DEFAULT_EXECUTION_KIND = "illustrative_fake_only_not_fresh"
PUBLIC_EXPORT_CAP = 16*1024*1024
PUBLIC_FILES = ("sources.json", "outputs.json", "accounting.json", "metrics.json", "diagnostic.json", "manifest.json")
LIFECYCLE_FIELDS = ("active_work_ns", "worker_cpu_ns", "lifetime_ns", "startup_ns",
                    "finish_ns", "commands", "parent_setup_ns", "parent_setup_cpu_ns")


def build_public(core, inventory, plans, observations, *, consumed_http, validated_http,
                 accounting_confirmed, cleanup_confirmed, execution_kind=DEFAULT_EXECUTION_KIND):
    h = core.h
    h.require(execution_kind in (DEFAULT_EXECUTION_KIND, "reviewed_native_evidence"), "explicit evidence kind")
    source_rows, _, _, bindings = inventory_projection(core, inventory)
    validate_plans(core, inventory, plans)
    h.require(type(accounting_confirmed) is bool and
              (cleanup_confirmed is None or type(cleanup_confirmed) is bool), "confirmed finite states")
    for value in (consumed_http, validated_http):
        h.require(value is None or (type(value) is int and 0 <= value <= inventory.request_total <= MAX_HTTP),
                  "finite request accounting bounds")
    if accounting_confirmed:
        h.require(consumed_http is not None and validated_http is not None, "confirmed accounting requires counters")
    if consumed_http is not None and validated_http is not None:
        h.require(validated_http <= consumed_http, "validated request prefix")
    h.require(type(observations) is dict and set(observations) <= set(inventory.schedule), "exact observation identities")
    plan_by_id = {plan.row_id: plan for plan in plans}
    translated, prompt_total, generated_total = [], 0, 0
    for row_id in inventory.row_ids:
        for arm in ("baseline", "candidate"):
            observed = observations.get((row_id, arm))
            if observed is None:
                result = dict(id=row_id, arm=arm, state="unobserved", original_output=None,
                              original_output_sha256=None, final_output=None, final_output_sha256=None)
            else:
                h.require(row_id in plan_by_id, "observed arm requires sealed plan")
                result = observation_projection(core, inventory, plan_by_id[row_id], observed, row_id, arm)
                if result["state"] == "observed":
                    prompt_total += result["usage"]["prompt_tokens"]
                    generated_total += result["usage"]["completion_tokens"]
            translated.append(result)
    h.require(prompt_total <= GENERATION_PROMPT_CAP and generated_total <= GENERATED_CAP, "public generation token ceilings")
    ledger = core.ledger(inventory)
    calls = []
    for number, (kind, row, arm) in enumerate(ledger.queue, 1):
        state = ("validated" if validated_http is not None and number <= validated_http else
                 "consumed_unvalidated" if consumed_http is not None and number <= consumed_http and validated_http is not None else
                 "consumed_validation_unknown" if consumed_http is not None and number <= consumed_http else
                 "unissued" if consumed_http is not None else "unknown")
        calls.append(dict(number=number, kind=kind, id=row, arm=arm, state=state))
        observed = observations.get((row, arm)) if kind == "completion" else None
        # An arm can fail during rendering/IPC or recurring counts, before its
        # completion request is issued. Preserve that operational failure;
        # only a received output requires a consumed completion slot.
        if observed is not None and consumed_http is not None and (
                observed["status"] == "observed" or observed.get("original_output") is not None):
            h.require(number <= consumed_http, "observation outside consumed request prefix")
        if observed is not None and observed["status"] == "observed" and validated_http is not None:
            h.require(number <= validated_http, "observation outside validated request prefix")
    # Completed observations retain structural/length/empty-output failures.
    # They make no claim about semantic fidelity or the value of the policy.
    complete = (accounting_confirmed and cleanup_confirmed is True and
        consumed_http == validated_http == inventory.request_total and len(plans) == PAIR_COUNT and
        len(observations) == COMPLETION_COUNT and all(r["state"] == "observed" for r in translated))
    if complete: core.validate_preflight(inventory, plans)
    result = {"sources.json": source_rows, "outputs.json": translated,
        "accounting.json": dict(schema=1, status="complete_observations" if complete else "incomplete",
            evidence_kind=execution_kind, expected_pairs=PAIR_COUNT, expected_completions=COMPLETION_COUNT,
            expected_http=inventory.request_total, consumed_http=consumed_http, validated_http=validated_http,
            eligible_ids=list(inventory.eligible_ids), input_bindings=bindings,
            observed_completions=sum(r["state"] == "observed" for r in translated),
            operational_failures=sum(r["state"] == "operational_failure" for r in translated),
            unobserved_completions=sum(r["state"] == "unobserved" for r in translated),
            structural_failures=sum("integrity_rejection" in r.get("flags", []) for r in translated),
            generation_prompt_tokens=prompt_total, generated_tokens=generated_total,
            calls=calls, accounting_confirmed=accounting_confirmed, cleanup_confirmed=cleanup_confirmed,
            quality_failures_retained=True, no_post_output_exclusions=True,
            semantic_fidelity="REVIEW_PENDING", canonical_compliance="REVIEW_PENDING",
            incremental_benefit="NOT_ESTABLISHED", semantic_quality_claim=None)}
    h.require(sum(len(h.canonical(value)) for value in result.values()) <= PUBLIC_EXPORT_CAP, "public export byte cap")
    return result


def _bounded_integer(h, value, maximum, label, *, minimum=0, nullable=False):
    h.require((nullable and value is None) or
              (type(value) is int and minimum <= value <= maximum), label)
    return value


def _helper_projection(h, inventory, samples, lifecycle, metrics):
    projected_samples = summary = None
    if samples is not None:
        h.require(type(samples) is list and len(samples) <= PAIR_COUNT, "helper sample prefix bound")
        projected_samples = []
        for row_id, sample in zip(inventory.row_ids, samples):
            h.require(type(sample) is dict and set(sample) == {"row", "elapsed_ns"} and sample["row"] == row_id,
                      "closed ordered helper sample prefix")
            elapsed = _bounded_integer(h, sample["elapsed_ns"], 600_000_000_000, "helper sample duration", minimum=1)
            projected_samples.append(dict(row=row_id, elapsed_ns=elapsed))
        full = len(projected_samples) == PAIR_COUNT
        summary = dict(n=len(projected_samples), complete=full,
            first_measured_candidate_ns=projected_samples[0]["elapsed_ns"] if projected_samples else None,
            first_measured_candidate_is_not_assumed_cold=True,
            quantiles=h.quantiles([r["elapsed_ns"] for r in projected_samples]) if full else None)
    projected_lifecycle = None
    if lifecycle is not None:
        h.require(type(lifecycle) is dict and set(lifecycle) == set(LIFECYCLE_FIELDS), "closed helper lifecycle")
        projected_lifecycle = {}
        for name in LIFECYCLE_FIELDS:
            maximum = (178+3*len(inventory.eligible_ids) if name == "commands" else
                       600_000_000_000 if name == "lifetime_ns" else 15_000_000_000)
            projected_lifecycle[name] = _bounded_integer(h, lifecycle[name], maximum, "bounded helper lifecycle")
        h.require(lifecycle["startup_ns"] + lifecycle["finish_ns"] <= lifecycle["active_work_ns"] and
                  lifecycle["parent_setup_ns"] <= lifecycle["startup_ns"] and
                  lifecycle["active_work_ns"] <= lifecycle["lifetime_ns"], "helper lifecycle containment")
    projected_metrics = None
    if metrics is not None:
        h.require(type(metrics) is dict and set(metrics) == {"helper_peak_rss_bytes", "helper_render_p95_ns"},
                  "closed helper metrics")
        projected_metrics = dict(
            helper_peak_rss_bytes=_bounded_integer(h, metrics["helper_peak_rss_bytes"], 32*h.MIB, "helper RSS bound", minimum=1),
            helper_render_p95_ns=_bounded_integer(h, metrics["helper_render_p95_ns"], 5_000_000, "helper p95 bound", minimum=1))
        if summary is not None and summary["complete"]:
            h.require(projected_metrics["helper_render_p95_ns"] == summary["quantiles"]["p95"], "helper metric/sample binding")
    return projected_samples, summary, projected_lifecycle, projected_metrics


def _observed_cost(core, inventory, plans, output_rows, resolution):
    """Derive all four fixed groups from retained arm timings, never caller cost."""
    h = core.h
    if resolution is not None:
        h.require(finite_time(h, resolution) > 0, "measured clock resolution")
    if len(plans) != PAIR_COUNT or resolution is None:
        return None
    try:
        coverage = core.validate_preflight(inventory, plans)
    except h.TerminalFailure:
        return None
    by_arm = {(row["id"], row["arm"]): row for row in output_rows}
    records = []
    for plan in plans:
        baseline, candidate = (by_arm[(plan.row_id, arm)] for arm in ("baseline", "candidate"))
        records.append(dict(id=plan.row_id, active=plan.active,
            complete=baseline["state"] == candidate["state"] == "observed",
            baseline=baseline["total_ns"]/1e9 if baseline["state"] == "observed" else None,
            candidate=candidate["total_ns"]/1e9 if candidate["state"] == "observed" else None))
    cost = core.paired_cost(inventory, plans, records, resolution)
    h.require(type(cost) is dict and set(cost) == {"status", "populations", "raw_rows", "quality_failures_included",
              "no_post_output_exclusions", "semantic_quality_claim"} and cost["status"] in ("pass", "fail", "inconclusive") and
              type(cost["populations"]) is dict and set(cost["populations"]) == set(coverage["populations"]) and
              cost["quality_failures_included"] is True and cost["no_post_output_exclusions"] is True and
              cost["semantic_quality_claim"] is None and cost["raw_rows"] == records, "derived closed cost")
    populations = {}
    for name, ids in coverage["populations"].items():
        group = cost["populations"][name]
        h.require(type(group) is dict and set(group) == {"expected_n", "observed_n", "ratios", "status"} and
                  group["expected_n"] == len(ids) and group["status"] in ("pass", "fail", "inconclusive"), "closed latency group")
        observed = _bounded_integer(h, group["observed_n"], len(ids), "latency observed denominator")
        q = group["ratios"]
        ratios = None
        if q is not None:
            h.require(type(q) is dict and set(q) == {"n", "median", "p95"} and
                      type(q["n"]) is int and q["n"] == len(ids) == observed, "latency ratio denominator")
            ratios = dict(n=q["n"], median=finite_time(h, q["median"]), p95=finite_time(h, q["p95"]))
        populations[name] = dict(expected_n=len(ids), observed_n=observed, ratios=ratios, status=group["status"])
    return dict(status=cost["status"], populations=populations, raw_rows=records,
                quality_failures_included=True, no_post_output_exclusions=True, semantic_quality_claim=None)


def _reconciliation_projection(core, inventory, plans, reconciliation, base, cost):
    if reconciliation is None:
        return None
    h = core.h
    fields = {"status", "tokens", "expected_pairs", "observed_completions", "reconciled_http", "input_bindings",
        "frozen_plan_bindings_verified", "restoration_replay_verified", "original_guard_source_verified",
        "original_guard_sha256", "cost", "all_rows", "semantic_quality_claim"}
    h.require(type(reconciliation) is dict and set(reconciliation) == fields and
              reconciliation["status"] == "validated_complete_protocol_evidence" and
              reconciliation["frozen_plan_bindings_verified"] is True and reconciliation["restoration_replay_verified"] is True and
              type(reconciliation["original_guard_source_verified"]) is bool and reconciliation["semantic_quality_claim"] is None,
              "closed reconciled protocol schema")
    for name, expected in (("expected_pairs", PAIR_COUNT), ("observed_completions", COMPLETION_COUNT),
                           ("reconciled_http", inventory.request_total)):
        h.require(type(reconciliation[name]) is int and reconciliation[name] == expected, "reconciled protocol denominator")
    accounting = base["accounting.json"]
    h.require(len(plans) == PAIR_COUNT and accounting["observed_completions"] == COMPLETION_COUNT and
              reconciliation["input_bindings"] == dict(inventory.bindings), "reconciliation/source/observation binding")
    for name in ("consumed_http", "validated_http"):
        if accounting[name] is not None:
            h.require(accounting[name] == inventory.request_total, "reconciliation/accounting binding")
    expected_tokens = dict(
        generation_prompt_tokens=accounting["generation_prompt_tokens"], generated_tokens=accounting["generated_tokens"],
        count_only_requests=176+2*len(inventory.eligible_ids),
        count_only_input_tokens=sum(p.baseline.count+p.provisional.count for p in plans) +
            sum(p.baseline.count+p.provisional.count for p in plans if p.eligible))
    tokens = reconciliation["tokens"]
    h.require(type(tokens) is dict and set(tokens) == set(expected_tokens) and
              all(type(value) is int and value >= 0 for value in tokens.values()) and tokens == expected_tokens,
              "reconciled token totals")
    verified = reconciliation["original_guard_source_verified"]
    guard_sha = reconciliation["original_guard_sha256"]
    h.require(guard_sha == (h.PINS["integrity"] if verified else None) and
              (accounting["evidence_kind"] != "reviewed_native_evidence" or verified), "reconciled original guard provenance")
    by_arm = {(r["id"], r["arm"]): r for r in base["outputs.json"]}
    expected_rows = [dict(id=row, arms={arm: by_arm[(row, arm)] for arm in ("baseline", "candidate")}) for row in inventory.row_ids]
    h.require(cost is not None and reconciliation["cost"] == cost and reconciliation["all_rows"] == expected_rows,
              "reconciliation/derived cost/output binding")
    return dict(status="validated_complete_protocol_evidence", tokens=expected_tokens, expected_pairs=PAIR_COUNT,
        observed_completions=COMPLETION_COUNT, reconciled_http=inventory.request_total, input_bindings=dict(inventory.bindings),
        frozen_plan_bindings_verified=True, restoration_replay_verified=True,
        original_guard_source_verified=verified, original_guard_sha256=guard_sha, semantic_quality_claim=None)


def finalize_payloads(core, inventory, plans, observations, payloads, *, protocol_complete, reconciliation,
                      helper_samples, helper_lifecycle, runner_peak_rss_bytes, server_peak_rss_bytes,
                      helper_metrics, cleanup_confirmed, diagnostic, clock_resolution_seconds=None):
    """Finish all six closed artifacts, then bound their exact JSON-plus-LF bytes."""
    h = core.h
    h.require(type(payloads) is dict and set(payloads) == set(PUBLIC_FILES[:3]) and
              type(payloads.get("accounting.json")) is dict and type(protocol_complete) is bool and
              (cleanup_confirmed is None or type(cleanup_confirmed) is bool), "final public inputs")
    old_accounting = payloads["accounting.json"]
    base = build_public(core, inventory, plans, observations,
        consumed_http=old_accounting.get("consumed_http"), validated_http=old_accounting.get("validated_http"),
        accounting_confirmed=old_accounting.get("accounting_confirmed"), cleanup_confirmed=cleanup_confirmed,
        execution_kind=old_accounting.get("evidence_kind"))
    h.require(payloads == base, "unchanged closed base public artifacts")
    samples, sample_summary, lifecycle, helper = _helper_projection(h, inventory, helper_samples, helper_lifecycle, helper_metrics)
    runner_rss = _bounded_integer(h, runner_peak_rss_bytes, (1<<63)-1, "runner RSS telemetry", nullable=True)
    server_rss = _bounded_integer(h, server_peak_rss_bytes, (1<<63)-1, "server RSS telemetry", nullable=True)
    cost = _observed_cost(core, inventory, plans, base["outputs.json"], clock_resolution_seconds)
    protocol = _reconciliation_projection(core, inventory, plans, reconciliation, base, cost)
    h.require(not protocol_complete or protocol is not None, "completed protocol requires reconciliation")
    complete = (protocol_complete and protocol is not None and cleanup_confirmed is True and
        base["accounting.json"]["status"] == "complete_observations" and
        lifecycle is not None and lifecycle["commands"] == 178+3*len(inventory.eligible_ids) and
        lifecycle["active_work_ns"] > 0 and lifecycle["lifetime_ns"] > 0 and lifecycle["startup_ns"] > 0 and
        sample_summary is not None and sample_summary["complete"] and helper is not None)
    protocol_status = "complete" if complete else "incomplete"
    base["accounting.json"].update(protocol_complete=complete, protocol_status=protocol_status,
                                    protocol_evidence_reconciled=protocol is not None,
                                    cleanup_scope="owned_supervisor_at_snapshot", overall_attempt_status_source="terminal_result")
    base["metrics.json"] = dict(schema=1, protocol_complete=complete, protocol_status=protocol_status,
        cleanup_confirmed=cleanup_confirmed, cleanup_scope="owned_supervisor_at_snapshot",
        overall_attempt_status_source="terminal_result", protocol=protocol, cost=cost,
        clock_resolution_seconds=clock_resolution_seconds, helper_prepare_samples=samples,
        helper_sample_summary=sample_summary, helper_lifecycle=lifecycle,
        runner_peak_rss_bytes=runner_rss, server_peak_rss_bytes=server_rss,
        helper_metrics=helper, semantic_quality_claim=None)
    if diagnostic is None:
        base["diagnostic.json"] = None
    else:
        import diagnostics
        checked = diagnostics.validate_public(diagnostic)
        base["diagnostic.json"] = h.strict_json(h.canonical(checked))
    # Evidence.json writes exactly canonical JSON UTF-8 followed by one LF.
    # The manifest binds those artifact bytes, not a differently sized payload.
    files = []
    for name in PUBLIC_FILES[:-1]:
        raw = h.canonical(base[name])+b"\n"
        files.append(dict(file=name, bytes=len(raw), sha256=h.digest(raw)))
    base["manifest.json"] = dict(schema=1, files=files, excludes_own_digest=True,
                                 artifact_encoding="canonical_json_utf8_plus_lf")
    h.require(set(base) == set(PUBLIC_FILES) and
              sum(len(h.canonical(base[name]))+1 for name in PUBLIC_FILES) <= PUBLIC_EXPORT_CAP,
              "final aggregate public artifact byte cap")
    return base


def preflight_receipt(core, inventory, plans, manifest_sha, source_plan_sha):
    """Finite complete-count commitment, including a failed coverage decision."""
    h = core.h
    _, _, _, bindings = inventory_projection(core, inventory)
    validate_plans(core, inventory, plans, complete=True)
    sha_field(h, manifest_sha)
    sha_field(h, source_plan_sha)
    rows = []
    for plan in plans:
        requests = {}
        for name, receipt in (("baseline", plan.baseline), ("prospective", plan.provisional), ("actual_candidate", plan.candidate)):
            checked = receipt_projection(h, receipt)
            requests[name] = {key: checked[key] for key in ("request_sha256", "input_tokens")}
        rows.append(dict(id=plan.row_id, eligible=plan.eligible, active=plan.active, reason=plan.reason,
                         requests=requests))
    try:
        coverage = core.validate_preflight(inventory, plans)
        coverage_status = "pass"
    except h.TerminalFailure:
        coverage, coverage_status = None, "fail"
    result = dict(schema=1, component_manifest_sha256=manifest_sha, source_plan_sha256=source_plan_sha,
        input_bindings=bindings, expected_pairs=PAIR_COUNT, expected_completions=COMPLETION_COUNT,
        planned_http=inventory.request_total, maximum_http=MAX_HTTP,
        receipt_assets=dict(runtime=h.PINS["server"], model_tokenizer=h.PINS["model"], template=h.PINS["template"]),
        preflight_count_requests=176, readiness_requests=2, token_preflight_complete=True,
        measured_completions_before_receipt=0, coverage_status=coverage_status, coverage=coverage, rows=rows)
    h.require(len(h.canonical(result)) <= 65536, "closed preflight receipt byte cap")
    return result


def safe_terminal(result):
    """Project finite status only; arbitrary messages/causes never escape."""
    data = result if type(result) is dict else {}
    complete = (data.get("status") == "operationally_complete" and
                data.get("cleanup_confirmed") is True and data.get("protocol_complete") is True)
    value = dict(schema=1, status="complete" if complete else "incomplete",
        cleanup_scope="whole_attempt",
        cleanup_confirmed=data.get("cleanup_confirmed") is True,
        protocol_complete=data.get("protocol_complete") is True,
        reason_code="COMPLETE" if complete else "OPERATIONAL_FAILURE",
        semantic_quality_claim=None)
    if data.get("diagnostic") is not None:
        import diagnostics
        # Validation is closed recursively. Re-parse to avoid aliasing caller
        # dictionaries after a checked diagnostic has been returned.
        import json
        value["diagnostic"] = json.loads(diagnostics.encode(diagnostics.validate_public(data["diagnostic"])))
    return value


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE_ONLY_NATIVE_DISABLED")
