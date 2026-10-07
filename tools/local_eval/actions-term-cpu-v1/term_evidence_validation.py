"""Pure, bounded final reconciliation of the frozen term-lock protocol.

This module performs no I/O, native operation, inference or semantic grading.
Restoration replay occurs only after the measured stage; admission-policy
replay is a separate explicitly offline function. Supplied
bytes and clocks alone cannot establish that an actual native run occurred.
"""
import math
import re

from term_runner_core import (PAIR_COUNT, COMPLETION_COUNT, MAX_HTTP,
    GENERATION_PROMPT_CAP, GENERATED_CAP, SEEN_IDS, HISTORICAL_IDS, PRIOR_IDS,
    GLOSSARY_IDS, messages)
import term_worker as worker_protocol


RECEIPT_FIELDS = ("request_sha256", "input_tokens", "runtime", "model_tokenizer", "template")
REASONS = frozenset(("active", "token_budget", "scope_not_declared", "scope_glossary_mismatch",
    "marker_namespace_collision", "protected_source", "quoted_source", "no_match",
    "overlapping_matches", "multiple_matches", "globally_unsafe_entry", "unproven_boundary"))
FLAGS = frozenset(("empty_output", "length_finish", "integrity_rejection"))
REJECTIONS = (None, "INPUT_FRAME_BOUND", "OUTPUT_FRAME_BOUND", "MARKER_OR_STRUCTURE_REJECTED")


class MemoryReader:
    def __init__(self, raw):
        self.raw, self.position = raw, 0
    def read(self, n, remaining):
        result = self.raw[self.position:self.position+n]
        self.position += len(result)
        return result
    def close(self):
        pass


def sha_field(h, value):
    h.require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "closed digest field")
    return value


def finite_time(h, value):
    h.require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid timestamp")
    return value


def inventory_projection(core, inventory):
    """Rebind every public nested source/coverage/schedule field, without I/O."""
    h, p = core.h, core.policy
    ids = inventory.row_ids
    h.require(type(ids) is tuple and len(ids) == PAIR_COUNT and ids[:69] == SEEN_IDS and
              all(type(i) is str and 1 <= len(i) <= 64 for i in ids) and len(set(ids)) == PAIR_COUNT and
              set(inventory.rows) == set(ids) and inventory.fresh_ids == ids[69:], "frozen row identities")
    rows = []
    for row_id in ids:
        raw = inventory.rows[row_id]
        h.require(type(raw) is bytes and len(raw) <= 32768, "bounded frozen source")
        row = h.strict_json(raw)
        h.require(type(row) is dict and set(row) == {"id", "source", "scope_id", "glossary", "stratum"} and
                  row["id"] == row_id and type(row["source"]) is str and 1 <= len(row["source"]) <= 4096 and
                  type(row["scope_id"]) is str and len(row["scope_id"]) <= 128 and
                  type(row["glossary"]) is list and len(row["glossary"]) <= 16, "closed source fields")
        p._glossary(row["glossary"])
        expected = ("historical40" if row_id in HISTORICAL_IDS else "prior15" if row_id in PRIOR_IDS else
                    "glossary14" if row_id in GLOSSARY_IDS else "fresh19")
        h.require(row["stratum"] == expected and h.canonical(row) == raw, "source stratum/canonical binding")
        rows.append(row)
    h.require(len(inventory.coverage) == 19 and len(inventory.schedule) == COMPLETION_COUNT and
              tuple(r["id"] for r in inventory.coverage) == inventory.fresh_ids, "coverage/schedule denominator")
    coverage = []
    for item in inventory.coverage:
        h.require(set(item) == {"id", "role", "family", "control_type"} and
                  item["role"] in ("carrier", "control"), "closed coverage")
        coverage.append({k: item[k] for k in ("id", "role", "family", "control_type")})
    schedule = []
    for index, row_id in enumerate(ids):
        pair = inventory.schedule[index*2:index*2+2]
        h.require(pair in (((row_id, "baseline"), (row_id, "candidate")),
                           ((row_id, "candidate"), (row_id, "baseline"))), "paired schedule binding")
        schedule.append(dict(id=row_id, arm_order=["A" if arm == "baseline" else "B" for _, arm in pair]))
    bindings = dict(inventory.bindings)
    h.require(set(bindings) == {"sources", "coverage", "schedule", "declarations"}, "closed input bindings")
    for value in bindings.values(): sha_field(h, value)
    for name, value in (("sources", rows), ("coverage", coverage), ("schedule", schedule)):
        h.require(bindings[name] == h.digest(h.canonical(value)), "public input binding")
    h.require(bindings["declarations"] == p.DECLARATIONS_SHA256 and
              type(inventory.eligible_ids) is tuple and
              inventory.eligible_ids == tuple(i for i in ids if i in inventory.eligible_ids) and
              len(inventory.eligible_ids) <= 22 and type(inventory.request_total) is int and
              inventory.request_total == 354 + 2*len(inventory.eligible_ids) <= MAX_HTTP, "frozen HTTP inventory")
    return rows, coverage, schedule, bindings


def receipt_projection(h, receipt):
    h.require(type(receipt.body) is bytes and 0 < len(receipt.body) <= 32768 and
              type(receipt.count) is int and receipt.count > 0 and
              (receipt.runtime, receipt.model_tokenizer, receipt.template) ==
              (h.PINS["server"], h.PINS["model"], h.PINS["template"]), "count receipt provenance")
    request = h.strict_json(receipt.body)
    h.require(type(request) is dict and set(request) == {"model", "messages", *h.SAMPLING}, "closed request schema")
    h.require(h.serialize_request(request["messages"], request["model"]) == receipt.body, "template/sampling/body binding")
    return dict(request_sha256=h.digest(receipt.body), input_tokens=receipt.count,
                runtime=receipt.runtime, model_tokenizer=receipt.model_tokenizer, template=receipt.template)


def matched_receipt(h, value, receipt):
    expected = receipt_projection(h, receipt)
    h.require(type(value) is dict and set(value) == set(RECEIPT_FIELDS) and
              type(value.get("input_tokens")) is int and value == expected, "closed plan-matched actual receipt")
    return expected


def validate_plans(core, inventory, plans, *, complete=False):
    h = core.h
    h.require(type(plans) in (list, tuple) and len(plans) <= PAIR_COUNT and
              tuple(plan.row_id for plan in plans) == inventory.row_ids[:len(plans)] and
              (not complete or len(plans) == PAIR_COUNT), "ordered retained preflight plans")
    alias = None
    for plan in plans:
        h.require(type(plan.eligible) is bool and type(plan.active) is bool and plan.reason in REASONS and
                  plan.eligible == (plan.row_id in inventory.eligible_ids) and (not plan.active or plan.eligible),
                  "sealed membership/reason")
        row = core.row(inventory, plan.row_id)
        core.validate_prompt_binding(plan.prepared, inventory.prompt_bindings[plan.row_id])
        h.require(plan.prepared.source == row["source"] and plan.prepared.scope_id == row["scope_id"] and
                  plan.decision.plan == plan.prepared and type(plan.decision.baseline_tokens) is int and
                  type(plan.decision.provisional_tokens) is int and
                  (plan.decision.baseline_tokens, plan.decision.provisional_tokens) ==
                  (plan.baseline.count, plan.provisional.count), "source/decision/count binding")
        if plan.eligible:
            # Destination and masked-source hash are frozen together by the
            # source audit; parent reconciliation never masks a new source.
            h.require(type(plan.prepared.destination) is str and 1 <= len(plan.prepared.destination) <= 64,
                      "frozen destination field")
        else:
            h.require(plan.prepared.destination is None and plan.prepared.masked_source == row["source"], "abstention source binding")
        for receipt in (plan.baseline, plan.provisional, plan.candidate):
            receipt_projection(h, receipt)
            current = h.strict_json(receipt.body)["model"]
            alias = current if alias is None else alias
            h.require(current == alias, "single owned request alias")
        h.require(plan.baseline.count <= 384 and plan.candidate.count <= 384 and
                  plan.candidate == (plan.provisional if plan.active else plan.baseline), "actual prompt receipt")
        a, b = plan.baseline.count, plan.provisional.count
        if plan.eligible:
            active = b <= 384 and b-a <= min(16, (2*a)//5)
            h.require(plan.active is active and plan.reason == ("active" if active else "token_budget"),
                      "sealed token arithmetic/decision consistency")
        else:
            h.require(b == a and plan.provisional.body == plan.baseline.body and
                      plan.reason == plan.prepared.reason, "inactive receipt/decision identity")
        h.require(h.serialize_request(messages(plan.prepared.baseline_prompt), alias) == plan.baseline.body and
                  h.serialize_request(messages(plan.prepared.provisional_prompt), alias) == plan.provisional.body and
                  h.serialize_request(messages(plan.decision.prompt), alias) == plan.candidate.body, "sealed prompt/request binding")
        h.require(h.serialize_request(core.baseline_messages(row), alias) == plan.baseline.body,
                  "source/baseline binding")
    return alias


def observation_projection(core, inventory, plan, observed, row_id, arm):
    """Validate, then construct a fresh closed object; never copy caller maps."""
    h = core.h
    row = core.row(inventory, row_id)
    h.require(type(observed) is dict and observed.get("row") == row_id and observed.get("arm") == arm and
              observed.get("status") in ("observed", "operational_failure") and
              type(observed.get("preflight_active")) is bool and observed["preflight_active"] == plan.active,
              "observation identity/state/membership")
    start, end, total = (observed.get(k) for k in ("perf_start_ns", "perf_end_ns", "total_ns"))
    h.require(all(type(v) is int for v in (start, end, total)) and 0 <= start <= end and total == end-start and
              (observed["status"] != "observed" or total > 0), "authoritative arm timing")
    for name, value in (("start", start/1e9), ("end", end/1e9)):
        if name in observed: h.require(finite_time(h, observed[name]) == value, "clock coordinate binding")
    result = dict(id=row_id, arm=arm, state=observed["status"], active=plan.active,
        total_ns=total, perf_start_ns=start, perf_end_ns=end,
        original_output=None, original_output_sha256=None, final_output=None, final_output_sha256=None)
    original = observed.get("original_output")
    if original is not None:
        h.require(type(original) is str and len(original.encode()) <= 65536 and
                  observed.get("original_output_sha256") == h.digest(original.encode()), "original output binding")
        result.update(original_output=original, original_output_sha256=h.digest(original.encode()))
    else:
        h.require(observed.get("original_output_sha256") is None, "unreceived output hash")
    if observed["status"] == "operational_failure":
        h.require(observed.get("failure") == "ARM_FAILURE" and observed.get("timing_scoreable") is False and
                  observed.get("final_output") is None and observed.get("final_output_sha256") is None,
                  "closed operational failure")
        result.update(failure="ARM_FAILURE", timing_scoreable=False)
        return result
    h.require(original is not None, "observed original output required")
    receipt = plan.baseline if arm == "baseline" else plan.candidate
    actual = matched_receipt(h, observed.get("actual_receipt"), receipt)
    if arm == "candidate": matched_receipt(h, observed.get("prospective_receipt"), plan.provisional)
    else: h.require(observed.get("prospective_receipt") is None, "baseline prospective receipt")
    h.require(observed.get("request_sha256") == actual["request_sha256"] and
              observed.get("source_sha256") == h.digest(row["source"].encode()), "request/source binding")
    usage = observed.get("usage")
    h.require(type(usage) is dict and type(usage.get("prompt_tokens_details")) is dict, "usage evidence")
    prompt, completion, total_tokens = (usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    cached = usage["prompt_tokens_details"].get("cached_tokens")
    h.require(all(type(v) is int for v in (prompt, completion, total_tokens, cached)) and
              prompt == receipt.count and 1 <= prompt <= 384 and 0 <= completion <= 512 and
              total_tokens == prompt+completion and cached == 0, "usage/count/cache binding")
    flags = observed.get("flags")
    h.require(type(flags) is list and all(type(v) is str for v in flags) and
              len(flags) == len(set(flags)) and set(flags) <= FLAGS and
              (("empty_output" in flags) == (not original.strip())), "closed output flags")
    h.require(observed.get("scoreable_generation_failure") is bool(flags) and
              observed.get("definite_faithful_pass_eligible") is (not flags), "generation failure state")
    status, rejection = observed.get("restoration_status"), observed.get("restoration_rejection")
    rejected = "integrity_rejection" in flags
    h.require(status == ("rejected" if rejected else "restored" if arm == "candidate" and plan.active else "ordinary_guard_pass") and
              rejection in REJECTIONS, "restoration state/flags consistency")
    h.require((arm == "candidate" and plan.active and rejected and rejection is not None) or
              (not (arm == "candidate" and plan.active and rejected) and rejection is None), "restoration rejection consistency")
    final = observed.get("final_output")
    h.require((rejected and final is None and observed.get("final_output_sha256") is None) or
              (not rejected and type(final) is str and len(final.encode()) <= 65536 and
               observed.get("final_output_sha256") == h.digest(final.encode())), "restored output binding")
    if not rejected and not (arm == "candidate" and plan.active):
        h.require(final == original, "ordinary guard cannot rewrite")
    elif not rejected:
        h.require(original.count(core.policy.MARKER) == 1 and core.policy.NAMESPACE.findall(original) == [core.policy.MARKER] and
                  final == original.replace(core.policy.MARKER, plan.prepared.destination, 1), "exact sealed restoration")
    parts = observed.get("components")
    h.require(type(parts) is dict and set(parts) == {"render_and_ipc_ns", "count_ns", "completion_ns", "restoration_and_guard_ns"},
              "closed timing components")
    count_ns = parts["count_ns"]
    h.require(type(count_ns) is list and len(count_ns) == (2 if arm == "candidate" and plan.eligible else 0) and
              all(type(v) is int and 0 <= v <= total for v in count_ns), "measured recurring count timing")
    for name in ("render_and_ipc_ns", "completion_ns", "restoration_and_guard_ns"):
        h.require(type(parts[name]) is int and 0 <= parts[name] <= total, "measured timing component")
    h.require(sum(count_ns) <= parts["render_and_ipc_ns"] and
              sum(parts[k] for k in ("render_and_ipc_ns", "completion_ns", "restoration_and_guard_ns")) <= total,
              "nested timing containment")
    result.update(final_output=final, final_output_sha256=h.digest(final.encode()) if final is not None else None,
        request_sha256=actual["request_sha256"], actual_receipt=actual,
        prospective_receipt=receipt_projection(h, plan.provisional) if arm == "candidate" else None,
        source_sha256=h.digest(row["source"].encode()), flags=list(flags),
        restoration_status=status, restoration_rejection=rejection,
        scoreable_generation_failure=bool(flags), definite_faithful_pass_eligible=not flags,
        usage=dict(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total_tokens, cached_tokens=0),
        components=dict(render_and_ipc_ns=parts["render_and_ipc_ns"], count_ns=list(count_ns),
            completion_ns=parts["completion_ns"], restoration_and_guard_ns=parts["restoration_and_guard_ns"]))
    return result


def replay_policy_offline(core, inventory, plans, alias, declaration_bytes):
    """Explicit after-run pure replay of frozen policy; never a model callback."""
    h, p = core.h, core.policy
    h.validate_alias(alias)
    rows, coverage, schedule, bindings = inventory_projection(core, inventory)
    rebuilt = core.freeze_inventory(rows, coverage, schedule, declaration_bytes, bindings=bindings)
    h.require(rebuilt == inventory, "offline frozen inventory replay")
    h.require(validate_plans(core, inventory, plans, complete=True) == alias, "frozen alias binding")
    for plan in plans:
        row = core.row(inventory, plan.row_id)
        prepared = p.prepare(row["source"], row["scope_id"], row["glossary"], declaration_bytes)
        decision = p.apply_token_gate(prepared, plan.baseline.count, plan.provisional.count)
        h.require(prepared == plan.prepared and decision == plan.decision and
                  h.serialize_request(messages(prepared.baseline_prompt), alias) == plan.baseline.body and
                  h.serialize_request(messages(prepared.provisional_prompt), alias) == plan.provisional.body and
                  h.serialize_request(messages(decision.prompt), alias) == plan.candidate.body,
                  "offline frozen policy/source/request replay")
    core.validate_preflight(inventory, plans)
    return True


def _restore_offline(core, plan, arm, original, integrity, errors):
    h, p = core.h, core.policy
    if arm != "candidate" or not plan.active:
        try:
            integrity(plan.prepared.source, original)
            return original, "ordinary_guard_pass", None
        except errors:
            return None, "rejected", None
    original_sha = h.digest(original.encode())
    request = dict(op="RESTORE", row=plan.row_id, original_output=original,
        original_output_sha256=original_sha, input_frame_bound_rejection=False)
    if len(worker_protocol.canonical(request)) > worker_protocol.FRAME_CAP:
        return None, "rejected", "INPUT_FRAME_BOUND"
    try:
        final = p.restore(plan.decision, original, integrity)
        rejection = None
    except errors:
        final, rejection = None, "MARKER_OR_STRUCTURE_REJECTED"
    response = dict(op="RESTORED", row=plan.row_id, original_output_sha256=original_sha,
        final_output=final, final_output_sha256=h.digest(final.encode()) if final is not None else None,
        rejection=rejection)
    if len(worker_protocol.canonical(response)) > worker_protocol.FRAME_CAP:
        final, rejection = None, "OUTPUT_FRAME_BOUND"
    return final, "restored" if rejection is None else "rejected", rejection


def validate_final_evidence(core, inventory, plans, alias, declaration_bytes, transcripts, intervals,
                            clock_resolution_seconds, integrity, expected_error, *, guard_source_bytes=None):
    """Reconcile every request and original/restored observation, without drops."""
    h, p = core.h, core.policy
    h.require(callable(integrity), "injected original guard required")
    errors = expected_error if type(expected_error) is tuple else (expected_error,)
    h.require(bool(errors) and all(isinstance(e, type) and issubclass(e, Exception) for e in errors), "guard exception types")
    errors = (*errors, p.StructuralFailure)
    guard_verified = guard_source_bytes is not None
    if guard_verified:
        h.require(type(guard_source_bytes) is bytes and len(guard_source_bytes) <= 262144 and
                  h.digest(guard_source_bytes) == worker_protocol.GUARD_SHA256 == h.PINS["integrity"], "original guard source binding")
    h.validate_alias(alias)
    inventory_projection(core, inventory)
    p.load_declarations(declaration_bytes)
    h.require(validate_plans(core, inventory, plans, complete=True) == alias, "final frozen request alias")
    core.validate_preflight(inventory, plans)
    h.require(type(transcripts) is list and len(transcripts) == inventory.request_total and
              type(intervals) is list and len(intervals) == COMPLETION_COUNT, "exact final evidence denominator")
    by_id = {plan.row_id: plan for plan in plans}
    projected, by_arm, previous_end = {}, {}, 0
    for expected, record in zip(inventory.schedule, intervals):
        row, arm = expected
        value = observation_projection(core, inventory, by_id[row], record, row, arm)
        h.require(value["state"] == "observed" and value["perf_start_ns"] >= previous_end, "complete ordered nonoverlapping arm evidence")
        previous_end = value["perf_end_ns"]
        projected[expected], by_arm[expected] = value, record
    ledger = core.ledger(inventory)
    retained, previous_end = 0, 0
    totals = dict(generation_prompt_tokens=0, generated_tokens=0, count_only_requests=0, count_only_input_tokens=0)
    for index, (expected, record) in enumerate(zip(ledger.queue, transcripts)):
        if index == 178: ledger.seal_preflight(plans)
        kind, row, arm = expected
        h.require(type(record) is dict and (record.get("kind"), record.get("row"), record.get("arm")) == expected,
                  "exact transcript order")
        h.require(record.get("status", "validated") == "validated" and record.get("failure") is None and
                  record.get("attempted", True) is True, "validated request state")
        if "request_number" in record:
            h.require(type(record["request_number"]) is int and record["request_number"] == index+1, "request number binding")
        body, wire = record.get("request_body"), record.get("response_wire")
        h.require(type(wire) is bytes and len(wire) <= 98304 and
                  (body is None or (type(body) is bytes and len(body) <= 32768)), "bounded wire/request bytes")
        retained += len(wire) + (len(body) if body is not None else 0)
        h.require(retained <= 64*h.MIB and record.get("request_sha256") == (h.digest(body) if body is not None else None) and
                  record.get("response_sha256") == h.digest(wire), "wire/request hash and retained byte cap")
        start, end, deadline = (finite_time(h, record.get(k)) for k in ("start", "validated_end", "deadline"))
        h.require(start >= previous_end and start <= end < deadline and deadline-start <= h.ENDPOINTS[kind][3],
                  "ordered absolute request deadline")
        previous_end = end
        reader = MemoryReader(wire)
        raw = h.BoundedWire(reader, h.Deadline(lambda: 0, 1)).response(h.ENDPOINTS[kind][2])
        h.require(reader.position == len(wire), "unconsumed response wire bytes")
        if kind in ("health", "models"):
            h.require(body is None, "readiness GET body")
            h.readiness_response(kind, raw, alias)
        else:
            plan = by_id[row]
            receipt = ((plan.baseline if arm == "baseline" else plan.provisional)
                       if kind in ("preflight", "recurring") else (plan.baseline if arm == "baseline" else plan.candidate))
            h.require(body == receipt.body, "actual request receipt binding")
            if kind == "preflight":
                h.require(end <= intervals[0]["perf_start_ns"]/1e9, "all preflight counts before measured arms")
            if kind in ("preflight", "recurring"):
                value = h.token_response(raw)
                h.require(value == receipt.count, "full-template count receipt binding")
                totals["count_only_requests"] += 1
                totals["count_only_input_tokens"] += value
            else:
                restored = {}
                def guarded(source, output):
                    final, status, rejection = _restore_offline(core, plan, arm, output, integrity, errors)
                    restored.update(final_output=final, restoration_status=status, restoration_rejection=rejection)
                    if status == "rejected": raise p.StructuralFailure("retained restoration rejection")
                result = h.completion_response(raw, alias, receipt, core.row(inventory, row)["source"], guarded, errors)
                observed = by_arm[(row, arm)]
                h.require(result["output"] == observed["original_output"] and result["usage"] == observed["usage"] and
                          all(result[k] == observed.get(k) for k in ("flags", "scoreable_generation_failure", "definite_faithful_pass_eligible")) and
                          all(observed.get(k) == value for k, value in restored.items()), "wire/original/restored evidence reconciliation")
                totals["generation_prompt_tokens"] += result["usage"]["prompt_tokens"]
                totals["generated_tokens"] += result["usage"]["completion_tokens"]
            if kind in ("recurring", "completion"):
                observed = by_arm[(row, "candidate" if kind == "recurring" else arm)]
                h.require(observed["perf_start_ns"]/1e9 <= start and end <= observed["perf_end_ns"]/1e9,
                          "request validation/restoration inside measured arm")
        ledger.consume(kind, row, arm)
    ledger.assert_complete()
    h.require(totals["count_only_requests"] == 176 + 2*len(inventory.eligible_ids) and
              totals["generation_prompt_tokens"] <= GENERATION_PROMPT_CAP and totals["generated_tokens"] <= GENERATED_CAP,
              "exact final token accounting")
    rows = [dict(id=row, active=by_id[row].active, complete=True,
                 baseline=by_arm[(row, "baseline")]["total_ns"]/1e9,
                 candidate=by_arm[(row, "candidate")]["total_ns"]/1e9) for row in inventory.row_ids]
    return dict(status="validated_complete_protocol_evidence", tokens=totals,
        expected_pairs=PAIR_COUNT, observed_completions=COMPLETION_COUNT, reconciled_http=ledger.total,
        input_bindings=dict(inventory.bindings), frozen_plan_bindings_verified=True, restoration_replay_verified=True,
        original_guard_source_verified=guard_verified,
        original_guard_sha256=worker_protocol.GUARD_SHA256 if guard_verified else None,
        cost=core.paired_cost(inventory, plans, rows, clock_resolution_seconds),
        all_rows=[dict(id=row, arms={arm: projected[(row, arm)] for arm in ("baseline", "candidate")}) for row in inventory.row_ids],
        semantic_quality_claim=None)


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE_ONLY_NATIVE_DISABLED")
