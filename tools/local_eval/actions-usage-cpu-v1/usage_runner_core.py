"""Source-only experiment integration; native execution is not provided.

Verified dependencies are injected, never resolved from an ambient workspace.
No private criteria, grades, reference answers, network, processes or I/O here.
"""
from collections import Counter
from dataclasses import dataclass
import math
from types import MappingProxyType, SimpleNamespace


FRESH_IDS = tuple(f"N{i:03d}" for i in range(1, 33))
HISTORICAL_IDS = tuple(f"R{i:03d}" for i in range(1, 41))
SEEN_IDS = tuple(f"S{i:03d}" for i in range(1, 16))
ROW_IDS = HISTORICAL_IDS + SEEN_IDS + FRESH_IDS
FAMILIES = tuple(f"wb{i:02d}" for i in range(1, 9))
CHALLENGE_TYPES = frozenset(("literal", "metalinguistic", "polarity", "participant_assignment", "source_ambiguity", "otherwise_inappropriate"))
SURFACE_REASONS = frozenset(("surface_eligible", "no_match", "competing_full_anchors", "repeated_anchor",
                           "selected_focus_outside_anchor", "protected_structure", "source_over_4096_chars"))
PAIR_COUNT = 87
COMPLETION_COUNT = 174
PREFLIGHT_COUNT = 174
MAX_ELIGIBLE = 46
MAX_HTTP = 442
GENERATION_PROMPT_CAP = 66816
GENERATED_CAP = 89088


@dataclass(frozen=True)
class CoverageRow:
    id: str
    family: str
    role: str
    challenge_type: object
    expected_surface_reasons: tuple[str, ...]


@dataclass(frozen=True)
class Inventory:
    sources: object
    coverage: tuple[CoverageRow, ...]
    eligible_ids: tuple[str, ...]
    source_digest: str
    metadata_digest: str
    bank_digest: str
    schedule: tuple
    schedule_digest: str
    request_total: int


@dataclass(frozen=True)
class PairPlan:
    row_id: str
    baseline: object
    provisional: object
    candidate: object
    eligible: bool
    active: bool
    reason: str
    record_id: object


class UsageCore:
    """Adapter over exact independently verified upstream core and policy.

    The future source assembler supplies modules after verifying their complete
    dependency closure. An arbitrary module is not a valid execution binding.
    Pure tests use the separately hash-verifying test loader.
    """
    def __init__(self, legacy, policy):
        self.h, self.policy = legacy, policy

    def freeze_inventory(self, source_rows, metadata_rows, bank_bytes, *, source_digest, metadata_digest,
                         schedule_rows, schedule_digest):
        # OFFLINE SOURCE ASSEMBLY ONLY: native stages load the separately pinned
        # runtime inventory; all live matching happens inside the owned worker.
        h = self.h
        h.require(type(source_rows) is list and len(source_rows) == PAIR_COUNT, "87 source-only rows")
        h.require(all(type(r) is dict and set(r) == {"id", "source"} for r in source_rows), "id/source schema only")
        h.require(len({r["id"] for r in source_rows}) == PAIR_COUNT and
                  {r["id"] for r in source_rows} == set(ROW_IDS), "exact source identities")
        h.require(all(type(r["source"]) is str and 0 < len(r["source"]) <= 4096 for r in source_rows), "source strings/cap")
        h.require(source_digest == h.digest(h.canonical(source_rows)), "source-only canonical binding")
        h.require(metadata_digest == h.digest(h.canonical(metadata_rows)), "metadata canonical binding")
        keys = {"id", "family", "role", "challenge_type", "expected_surface_reasons"}
        h.require(type(metadata_rows) is list and len(metadata_rows) == 32 and
                  all(type(r) is dict and set(r) == keys for r in metadata_rows), "fresh coverage-only schema")
        h.require({r["id"] for r in metadata_rows} == set(FRESH_IDS), "fresh metadata identities")
        for row in metadata_rows:
            h.require(row["family"] in FAMILIES and row["role"] in ("carrier", "challenge", "control"), "coverage family/role")
            h.require(type(row["expected_surface_reasons"]) is list and bool(row["expected_surface_reasons"]) and
                      all(type(reason) is str and reason in SURFACE_REASONS for reason in row["expected_surface_reasons"]) and
                      len(set(row["expected_surface_reasons"])) == len(row["expected_surface_reasons"]), "source-only surface expectations")
            h.require((row["challenge_type"] in CHALLENGE_TYPES if row["role"] == "challenge"
                       else row["challenge_type"] is None), "one challenge type only")
        for family in FAMILIES:
            group = [r for r in metadata_rows if r["family"] == family]
            h.require(Counter(r["role"] for r in group) == Counter(carrier=2, challenge=1, control=1), "four rows per family")
        type_counts = Counter(r["challenge_type"] for r in metadata_rows if r["role"] == "challenge")
        h.require(set(type_counts) == CHALLENGE_TYPES and sorted(type_counts.values()) == [1, 1, 1, 1, 2, 2],
                  "six challenge types and two predeclared repeats")
        h.require(type(schedule_rows) is list and len(schedule_rows) == 87 and
                  all(type(r) is dict and set(r) == {"id", "arm_order"} for r in schedule_rows) and
                  tuple(r["id"] for r in schedule_rows) == ROW_IDS, "frozen source order")
        h.require(schedule_digest == h.digest(h.canonical(schedule_rows)), "exact arm-order binding")
        h.require(all(r["arm_order"] in (["A", "B"], ["B", "A"]) for r in schedule_rows), "pair arm order")
        orders = {r["id"]: r["arm_order"][0] for r in schedule_rows}
        h.require(Counter(orders.values()) == Counter(A=44, B=43), "44 AB / 43 BA")
        h.require(Counter(orders[r] for r in FRESH_IDS) == Counter(A=16, B=16), "fresh order balance")
        for role, half in (("carrier", 8), ("challenge", 4), ("control", 4)):
            h.require(Counter(orders[r["id"]] for r in metadata_rows if r["role"] == role) == Counter(A=half, B=half),
                      "frozen role order balance")
        for family in FAMILIES:
            h.require(Counter(orders[r["id"]] for r in metadata_rows if r["family"] == family) == Counter(A=2, B=2),
                      "frozen family order balance")
        schedule = tuple((r["id"], "baseline" if arm == "A" else "candidate")
                         for r in schedule_rows for arm in r["arm_order"])
        self.policy.load_frozen_bank(bank_bytes)
        sources = {r["id"]: r["source"] for r in source_rows}
        eligible = []
        expected = {r["id"]: r["expected_surface_reasons"] for r in metadata_rows}
        for row in ROW_IDS:
            plan = self.policy.prepare_candidate(sources[row], self.policy.baseline_messages(sources[row]),
                                                 bank_bytes, baseline_in_scope=True)
            if row in expected:
                h.require(plan.reason in expected[row], "frozen surface expectation mismatch")
            if plan.surface_eligible:
                eligible.append(row)
        h.require(len(eligible) <= MAX_ELIGIBLE and 350 + 2 * len(eligible) <= MAX_HTTP, "scope/request conflict; no pruning")
        return Inventory(MappingProxyType(sources), tuple(CoverageRow(**{**r, "expected_surface_reasons": tuple(r["expected_surface_reasons"])}) for r in metadata_rows),
                         tuple(eligible), source_digest, metadata_digest, self.policy.FROZEN_BANK_SHA256,
                         schedule, schedule_digest, 350 + 2 * len(eligible))

    def preflight_pair(self, row_id, source, alias, bank_bytes, count, worker=None):
        h, p = self.h, self.policy
        baseline_messages = p.baseline_messages(source)
        prepared = (worker.prepare("preflight", row_id, source, baseline_messages) if worker else
                    p.prepare_candidate(source, baseline_messages, bank_bytes, baseline_in_scope=True))
        baseline_body = h.serialize_request(baseline_messages, alias)
        provisional_body = h.serialize_request(prepared.messages, alias)
        # Both counted bodies are independently sent, even when byte-identical.
        b = count(baseline_body)
        h.require(type(b) is int and 1 <= b <= 384, "invalid baseline complete-chat count")
        c = count(provisional_body)
        if prepared.surface_eligible:
            try:
                decision = (worker.gate("preflight", row_id, prepared, b, c) if worker else
                            p.apply_token_gate(prepared, baseline_tokens=b, candidate_tokens=c))
            except p.PolicyError as exc:
                raise h.TerminalFailure("terminal count/policy failure") from exc
        else:
            h.require(type(c) is int and c > 0 and c == b, "inactive preflight positive/equal count invariant")
            h.require(provisional_body == baseline_body, "inactive baseline identity")
            decision = SimpleNamespace(messages=baseline_messages, example_active=False,
                                       reason=prepared.reason, record_id=prepared.record_id)
        baseline, provisional = h.CountReceipt(baseline_body, b), h.CountReceipt(provisional_body, c)
        actual = provisional if decision.example_active else baseline
        h.require(h.serialize_request(decision.messages, alias) == actual.body, "actual request receipt drift")
        return PairPlan(row_id, baseline, provisional, actual, prepared.surface_eligible,
                        decision.example_active, decision.reason, decision.record_id)

    def measured_candidate(self, plan, source, alias, bank_bytes, count, on_prepared=lambda: None, worker=None):
        h, p = self.h, self.policy
        baseline = p.baseline_messages(source)
        prepared = (worker.prepare("measured", plan.row_id, source, baseline) if worker else
                    p.prepare_candidate(source, baseline, bank_bytes, baseline_in_scope=True))
        on_prepared()  # Nested lookup/render sample ends before any measured count.
        h.require(prepared.surface_eligible == plan.eligible, "surface eligibility drift")
        bodies = (h.serialize_request(baseline, alias), h.serialize_request(prepared.messages, alias))
        h.require(bodies == (plan.baseline.body, plan.provisional.body), "prepared request drift before measured count")
        if plan.eligible:
            counts = []
            for body, receipt in zip(bodies, (plan.baseline, plan.provisional)):
                value = count(body)
                h.require(type(value) is int and value > 0 and value == receipt.count, "measured count binding drift")
                counts.append(value)
        else:
            counts = [plan.baseline.count, plan.provisional.count]
        if plan.eligible:
            try:
                decision = (worker.gate("measured", plan.row_id, prepared, counts[0], counts[1]) if worker else
                            p.apply_token_gate(prepared, baseline_tokens=counts[0], candidate_tokens=counts[1]))
            except p.PolicyError as exc:
                raise h.TerminalFailure("terminal measured policy failure") from exc
        else:
            h.require(type(counts[0]) is int and 1 <= counts[0] <= 384 and counts[1] == counts[0],
                      "inactive measured preflight receipt invariant")
            decision = SimpleNamespace(messages=baseline, example_active=False,
                                       reason=prepared.reason, record_id=prepared.record_id)
        h.require((decision.example_active, decision.reason, decision.record_id) ==
                  (plan.active, plan.reason, plan.record_id), "preflight admission drift")
        body = h.serialize_request(decision.messages, alias)
        h.require(body == plan.candidate.body, "actual measured request drift")
        return body

    def validate_preflight(self, inventory, plans):
        h = self.h
        h.require(tuple(plan.row_id for plan in plans) == ROW_IDS, "all 87 preflight rows retained")
        h.require(tuple(plan.row_id for plan in plans if plan.eligible) == inventory.eligible_ids, "eligibility inventory drift")
        for plan in plans:
            h.require(type(plan.active) is bool and type(plan.eligible) is bool and
                      (not plan.active or plan.eligible), "preflight membership flags")
            for receipt in (plan.baseline, plan.provisional, plan.candidate):
                h.require(type(receipt.body) is bytes and len(receipt.body) <= 32768 and
                          type(receipt.count) is int and receipt.count > 0 and
                          (receipt.runtime, receipt.model_tokenizer, receipt.template) ==
                          (h.PINS["server"], h.PINS["model"], h.PINS["template"]), "count receipt identity")
            h.require(plan.baseline.count <= 384 and plan.candidate.count <= 384, "actual generation prompt cap")
            h.require(plan.candidate == (plan.provisional if plan.active else plan.baseline), "prospective/actual binding")
        active = {plan.row_id for plan in plans if plan.active}
        carriers = [r for r in inventory.coverage if r.role == "carrier"]
        complete_families = [family for family in FAMILIES if
                             {r.id for r in carriers if r.family == family} <= active]
        active_types = {r.challenge_type for r in inventory.coverage if r.role == "challenge" and r.id in active}
        h.require(sum(r.id in active for r in carriers) >= 12 and len(complete_families) >= 6, "carrier coverage failed")
        h.require(active_types == CHALLENGE_TYPES, "challenge type coverage failed")
        by_id = {plan.row_id: plan for plan in plans}
        for row in inventory.coverage:
            if "surface_eligible" not in row.expected_surface_reasons:
                plan = by_id[row.id]
                h.require(not plan.eligible and not plan.active and plan.reason in row.expected_surface_reasons,
                          "prescribed surface abstention failed")
            elif by_id[row.id].eligible:
                h.require(by_id[row.id].record_id == row.family, "fresh family/matched record mismatch")
        return dict(active_carriers=sum(r.id in active for r in carriers),
                    complete_carrier_families=complete_families, active_challenge_types=sorted(active_types))

    def ledger(self, inventory, persist=lambda event: None):
        core, h = self, self.h

        class Ledger(h.RequestLedger):
            def __init__(self):
                self.persist, self.counts, self.total = persist, Counter(), 0
                self.terminal, self.cleanup_errors, self.preflight_sealed = None, [], False
                self.queue = [("health", None, None), ("models", None, None)]
                self.queue += [("preflight", row, side) for row in ROW_IDS for side in ("baseline", "second")]
                for row, arm in inventory.schedule:
                    if arm == "candidate" and row in inventory.eligible_ids:
                        self.queue += [("recurring", row, side) for side in ("baseline", "provisional")]
                    self.queue.append(("completion", row, arm))
                h.require(len(self.queue) == inventory.request_total <= MAX_HTTP, "fixed exact request inventory")

            def consume(self, kind, row=None, arm=None):
                if self.total >= len(self.queue):
                    self.fail("exact_inventory_exhausted")
                    raise h.TerminalFailure("no extra request allowance")
                return super().consume(kind, row, arm)

            def seal_preflight(self, plans):
                try:
                    h.require(self.terminal is None and self.total == 176 and not self.preflight_sealed,
                              "complete preflight request phase required")
                    coverage = core.validate_preflight(inventory, plans)
                    self.persist(dict(event="preflight_sealed", eligibility=list(inventory.eligible_ids),
                                      active=[p.row_id for p in plans if p.active], coverage=coverage,
                                      request_bindings_sha256=h.digest(h.canonical([
                                          dict(row=p.row_id, baseline=p.baseline.binding, provisional=p.provisional.binding,
                                               candidate=p.candidate.binding, active=p.active, reason=p.reason) for p in plans]))))
                    self.plans, self.preflight_sealed = tuple(plans), True
                except BaseException:
                    self.fail("preflight_validation_or_journal_failure")
                    raise

            def assert_complete(self):
                h.require(self.terminal is None and self.total == inventory.request_total and self.counts ==
                          Counter(health=1, models=1, preflight=PREFLIGHT_COUNT,
                                  recurring=2 * len(inventory.eligible_ids), completion=COMPLETION_COUNT), "incomplete exact requests")

        return Ledger()

    def paired_cost(self, inventory, rows, clock_resolution_seconds):
        h = self.h
        h.require(type(rows) is list and tuple(row["id"] for row in rows) == ROW_IDS, "87-row cost denominator")
        h.require(type(clock_resolution_seconds) in (int, float) and math.isfinite(clock_resolution_seconds) and
                  clock_resolution_seconds > 0, "clock evidence")
        invalid = []
        valid = []
        for row in rows:
            h.require(type(row.get("active")) is bool, "frozen active membership")
            values = (row.get("baseline"), row.get("candidate"))
            good = row.get("complete") is True and all(type(v) in (int, float) and math.isfinite(v) and
                                                       v > 0 for v in values)
            (valid if good else invalid).append(row)
        groups = {"fresh": [r for r in rows if r["id"] in FRESH_IDS],
                  "active_fresh": [r for r in rows if r["id"] in FRESH_IDS and r["active"]],
                  "all": rows, "all_active": [r for r in rows if r["active"]]}
        reports, definite_failure, incomplete = {}, False, bool(invalid)
        for name, group in groups.items():
            usable = [r for r in group if r in valid]
            complete = bool(group) and len(usable) == len(group)
            # Partial populations are retained but never reported as full gates.
            quantiles = h.quantiles([r["candidate"] / r["baseline"] for r in usable]) if complete else None
            failed = bool(quantiles and (quantiles["median"] > 1.25 or quantiles["p95"] > 1.25))
            definite_failure |= failed
            incomplete |= not complete
            reports[name] = dict(expected_n=len(group), observed_n=len(usable), ratios=quantiles,
                                 status="fail" if failed else "pass" if complete else "inconclusive")
        strata = {}
        for name, first_arm in (("AB", "baseline"), ("BA", "candidate")):
            order_rows = {row for row, arm in inventory.schedule[::2] if arm == first_arm}
            group = [r for r in rows if r["id"] in order_rows]
            usable = [r for r in group if r in valid]
            strata[name] = dict(expected_n=len(group), observed_n=len(usable),
                                ratios=h.quantiles([r["candidate"] / r["baseline"] for r in usable])
                                if len(usable) == len(group) else None)
        status = "fail" if definite_failure else "inconclusive" if incomplete else "pass"
        return dict(status=status, groups=reports, order_strata=strata, raw_rows=rows,
                    invalid_row_ids=[r["id"] for r in invalid], quality_failures_included=True,
                    active_membership_fixed_before_generation=True, semantic_quality_claim=None)

    def all_row_accounting(self, inventory, observations):
        self.h.require(set(observations) <= set(inventory.schedule), "unexpected arm")
        return [dict(id=row, arms={arm: observations.get((row, arm), {"status": "unobserved"})
                                  for arm in ("baseline", "candidate")}) for row in ROW_IDS]

    def run_real(self, *args, **kwargs):
        raise self.h.Disabled("SOURCE ONLY: no native bridge, publication, claim or execution release")
