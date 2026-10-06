"""Pure new-scope evidence reconciliation using unchanged upstream validators."""
import math
from usage_runner_core import ROW_IDS, GENERATION_PROMPT_CAP, GENERATED_CAP


class MemoryReader:
    def __init__(self, raw):
        self.raw, self.position = raw, 0
    def read(self, n, remaining):
        chunk = self.raw[self.position:self.position+n]
        self.position += len(chunk)
        return chunk
    def close(self):
        pass


def validate_final_evidence(core, inventory, plans, alias, bank_bytes, transcripts, intervals,
                            clock_resolution_seconds, integrity, expected_error):
    h = core.h
    h.validate_alias(alias)
    core.validate_preflight(inventory, plans)
    h.require(type(transcripts) is list and len(transcripts) == inventory.request_total and
              type(intervals) is list and len(intervals) == 174, "exact evidence denominator")
    by_id = {plan.row_id: plan for plan in plans}
    for plan in plans:
        # Shared baseline construction is allowed in the parent. Full matcher /
        # admission replay belongs to the explicit offline routine below.
        expected_body = h.serialize_request(core.policy.baseline_messages(inventory.sources[plan.row_id]), alias)
        h.require(plan.baseline.body == expected_body, "source/baseline binding")
    def finite(value):
        h.require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid timestamp")
        return value
    by_arm, previous_end, previous_perf_end = {}, 0, 0
    for expected, record in zip(inventory.schedule, intervals):
        h.require((record.get("row"), record.get("arm")) == expected, "interval order")
        start, end = (finite(record.get(k)) for k in ("start", "end"))
        pstart, pend, total = (record.get(k) for k in ("perf_start_ns", "perf_end_ns", "total_ns"))
        h.require(end > start >= previous_end and all(type(v) is int for v in (pstart, pend, total)) and
                  pend > pstart >= previous_perf_end and total == pend-pstart and
                  start == pstart/1e9 and end == pend/1e9, "monotonic consistent interval")
        by_arm[expected] = (start, end, total)
        previous_end, previous_perf_end = end, pend
    ledger = core.ledger(inventory)
    observations, retained, previous_end = {}, 0, 0
    totals = dict(generation_prompt_tokens=0, generated_tokens=0, count_only_requests=0, count_only_input_tokens=0)
    for index, (expected, record) in enumerate(zip(ledger.queue, transcripts)):
        if index == 176:
            ledger.seal_preflight(plans)
        kind, row, arm = expected
        h.require((record.get("kind"), record.get("row"), record.get("arm")) == expected, "transcript order")
        body, wire = record.get("request_body"), record.get("response_wire")
        h.require(type(wire) is bytes and len(wire) <= 98304 and
                  (body is None or (type(body) is bytes and len(body) <= 32768)), "wire/request byte caps")
        retained += len(wire) + (len(body) if body is not None else 0)
        h.require(retained <= 64*h.MIB and record.get("request_sha256") == (h.digest(body) if body is not None else None) and
                  record.get("response_sha256") == h.digest(wire), "wire binding/global cap")
        start, end, deadline = (finite(record.get(k)) for k in ("start", "validated_end", "deadline"))
        h.require(start >= previous_end and start <= end < deadline and deadline-start <= h.ENDPOINTS[kind][3],
                  "unchanged absolute request deadline")
        previous_end = end
        reader = MemoryReader(wire)
        raw = h.BoundedWire(reader, h.Deadline(lambda: 0, 1)).response(h.ENDPOINTS[kind][2])
        h.require(reader.position == len(wire), "unconsumed wire bytes")
        if kind in ("health", "models"):
            h.require(body is None, "readiness GET body")
            h.readiness_response(kind, raw, alias)
        else:
            plan = by_id[row]
            receipt = ((plan.baseline if arm == "baseline" else plan.provisional)
                       if kind in ("preflight", "recurring") else
                       (plan.baseline if arm == "baseline" else plan.candidate))
            h.require(body == receipt.body, "actual request receipt binding")
            if kind == "preflight":
                h.require(end <= intervals[0]["start"], "preflight must precede every completion")
            if kind in ("preflight", "recurring"):
                value = h.token_response(raw)
                h.require(value == receipt.count, "actual count receipt binding")
                totals["count_only_requests"] += 1
                totals["count_only_input_tokens"] += value
            else:
                result = h.completion_response(raw, alias, receipt, inventory.sources[row], integrity, expected_error)
                totals["generation_prompt_tokens"] += result["usage"]["prompt_tokens"]
                totals["generated_tokens"] += result["usage"]["completion_tokens"]
                result.pop("raw_response")
                observations[(row, arm)] = dict(status="observed", **result)
            if kind in ("recurring", "completion"):
                interval = by_arm[(row, "candidate" if kind == "recurring" else arm)]
                h.require(interval[0] <= start and end <= interval[1], "counts/validation inside measured arm")
        ledger.consume(kind, row, arm)
    ledger.assert_complete()
    h.require(totals["count_only_requests"] == 174 + 2*len(inventory.eligible_ids) and
              totals["generation_prompt_tokens"] <= GENERATION_PROMPT_CAP and totals["generated_tokens"] <= GENERATED_CAP,
              "exact final token accounting")
    rows = [dict(id=row, active=by_id[row].active, complete=True,
                 baseline=by_arm[(row, "baseline")][2]/1e9, candidate=by_arm[(row, "candidate")][2]/1e9)
            for row in ROW_IDS]
    return dict(status="validated_complete_protocol_evidence", tokens=totals,
                cost=core.paired_cost(inventory, rows, clock_resolution_seconds), all_rows=core.all_row_accounting(inventory, observations),
                semantic_quality_claim=None)


def replay_policy_offline(core, inventory, plans, alias, bank_bytes):
    """Optional SOURCE-ONLY/OFFLINE review; never called by native execution."""
    for plan in plans:
        counts = iter((plan.baseline.count, plan.provisional.count))
        replay = core.preflight_pair(plan.row_id, inventory.sources[plan.row_id], alias, bank_bytes, lambda _: next(counts))
        core.h.require(replay == plan, "offline frozen policy/source replay")
    return True
