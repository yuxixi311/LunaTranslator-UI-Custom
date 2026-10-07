"""NEW inert reconstruction over exact frozen policy and recovered CPU core.

No native I/O, model, tokenizer or private criteria. Offline freeze may execute
the policy; live parent preparation validates already-frozen prompt bindings.
"""
from collections import Counter
from dataclasses import dataclass
import math
from types import MappingProxyType

PAIR_COUNT = 88
COMPLETION_COUNT = PREFLIGHT_COUNT = 176
MAX_ELIGIBLE, MAX_HTTP = 22, 398
GENERATION_PROMPT_CAP, GENERATED_CAP = 67584, 90112
HISTORICAL_IDS = tuple(f"R{i:03d}" for i in range(1,41))
PRIOR_IDS = tuple(f"S{i:03d}" for i in range(1,16))
GLOSSARY_IDS = ("person-01","person-03",*(f"participant-{i:02d}" for i in range(1,7)),"entity-02",*(f"negative-{i:02d}" for i in range(1,5)),"nomatch-01")
SEEN_IDS = HISTORICAL_IDS + PRIOR_IDS + GLOSSARY_IDS
CONTROL_REASONS = dict(globally_unsafe_homograph="globally_unsafe_entry",subword="unproven_boundary",quoted_source="quoted_source",
    missing_or_foreign_scope="scope_not_declared",marker_collision="marker_namespace_collision",protected_syntax="protected_source",no_match="no_match")

@dataclass(frozen=True)
class Inventory:
    rows: object
    row_ids: tuple
    fresh_ids: tuple
    coverage: tuple
    eligible_ids: tuple
    schedule: tuple
    bindings: object
    request_total: int
    prompt_bindings: object

@dataclass(frozen=True)
class PairPlan:
    row_id: str
    prepared: object
    decision: object
    baseline: object
    provisional: object
    candidate: object
    @property
    def eligible(self): return self.prepared.eligible
    @property
    def active(self): return self.decision.active
    @property
    def reason(self): return self.decision.reason

def messages(prompt): return [{"role":"user","content":prompt}]

class TermCore:
    def __init__(self, legacy, policy): self.h,self.policy=legacy,policy

    def prompt_binding(self, plan):
        h=self.h
        return dict(baseline_prompt_sha256=h.digest(plan.baseline_prompt.encode()),provisional_prompt_sha256=h.digest(plan.provisional_prompt.encode()),
            eligible=plan.eligible,reason=plan.reason,entry_id=plan.entry_id,destination=plan.destination,
            masked_source_sha256=h.digest(plan.masked_source.encode()),glossary_digest=plan.glossary_digest)

    def validate_prompt_binding(self, plan, expected):
        self.h.require(self.prompt_binding(plan)==dict(expected),"frozen source prompt/admission binding")

    def freeze_inventory(self, rows, coverage, schedule, declaration_bytes, *, bindings):
        h,p=self.h,self.policy
        h.require(type(rows) is list and len(rows)==88 and all(type(r) is dict and set(r)=={"id","source","scope_id","glossary","stratum"} for r in rows),"closed88 source schema")
        ids=tuple(r["id"] for r in rows)
        h.require(all(type(i) is str and 1<=len(i)<=64 for i in ids) and len(set(ids))==88 and ids[:69]==SEEN_IDS,"exact retained source identities")
        fresh=ids[69:]
        h.require(type(coverage) is list and len(coverage)==19 and all(type(r) is dict and set(r)=={"id","role","family","control_type"} for r in coverage) and tuple(r["id"] for r in coverage)==fresh,"source-only coverage schema")
        declarations=p.load_declarations(declaration_bytes)
        families={r["id"] for r in declarations["entries"] if r["lock_safe"]}
        carriers=[r for r in coverage if r["role"]=="carrier"];controls=[r for r in coverage if r["role"]=="control"]
        h.require(len(carriers)==12 and Counter(r["family"] for r in carriers)==Counter({f:2 for f in families}) and all(r["control_type"] is None for r in carriers),"six two-row families")
        h.require(len(controls)==7 and {r["control_type"] for r in controls}==set(CONTROL_REASONS) and all(r["family"] is None for r in controls),"seven distinct controls")
        h.require(type(bindings) is dict and set(bindings)=={"sources","coverage","schedule","declarations"},"closed input bindings")
        for name,value in (("sources",rows),("coverage",coverage),("schedule",schedule)):
            h.require(bindings[name]==h.digest(h.canonical(value)),"canonical input binding")
        h.require(bindings["declarations"]==p.DECLARATIONS_SHA256,"declaration binding")
        h.require(type(schedule) is list and len(schedule)==88 and all(type(r) is dict and set(r)=={"id","arm_order"} for r in schedule) and
            tuple(r["id"] for r in schedule)==ids and all(r["arm_order"] in (["A","B"],["B","A"]) for r in schedule),"prospective88 schedule")
        first={r["id"]:r["arm_order"][0] for r in schedule}
        h.require(Counter(first.values())==Counter(A=44,B=44),"all88 order balance")
        groups=[HISTORICAL_IDS,PRIOR_IDS,GLOSSARY_IDS,fresh,[r["id"] for r in carriers],[r["id"] for r in controls]]
        groups += [[r["id"] for r in carriers if r["family"]==f] for f in families]
        groups += [[i for i in GLOSSARY_IDS if i.startswith(prefix+"-")] for prefix in ("person","participant","entity","negative","nomatch")]
        for group in groups:
            counts=Counter(first[i] for i in group)
            h.require(abs(counts["A"]-counts["B"])<=1,"stratum order balance")
        expected={r["id"]:r for r in coverage};frozen={};prompts={};eligible=[]
        for row in rows:
            i=row["id"];stratum="historical40" if i in HISTORICAL_IDS else "prior15" if i in PRIOR_IDS else "glossary14" if i in GLOSSARY_IDS else "fresh19"
            h.require(row["stratum"]==stratum,"stratum binding")
            plan=p.prepare(row["source"],row["scope_id"],row["glossary"],declaration_bytes)
            if i in SEEN_IDS:
                h.require(row["scope_id"]!=p.SCOPE_ID and not plan.eligible and plan.baseline_prompt==plan.provisional_prompt,"seen scope abstention")
            elif expected[i]["role"]=="carrier":
                h.require(plan.eligible and plan.entry_id==expected[i]["family"],"carrier source admission")
            else:
                h.require(not plan.eligible and plan.reason==CONTROL_REASONS[expected[i]["control_type"]],"control source abstention")
            if plan.eligible:eligible.append(i)
            frozen[i]=h.canonical(row);prompts[i]=MappingProxyType(self.prompt_binding(plan))
        h.require(len(eligible)<=22,"request budget no pruning")
        return Inventory(MappingProxyType(frozen),ids,fresh,tuple(MappingProxyType(dict(r)) for r in coverage),tuple(eligible),
            tuple((r["id"],"baseline" if a=="A" else "candidate") for r in schedule for a in r["arm_order"]),
            MappingProxyType(dict(bindings)),354+2*len(eligible),MappingProxyType(prompts))

    def row(self, inventory, row_id): return self.h.strict_json(inventory.rows[row_id])

    def baseline_messages(self, row):
        p=self.policy
        p._require(type(row["source"]) is str and 1<=len(row["source"])<=4096,"source bound")
        entries=p._glossary(row["glossary"])
        return messages(p._prompt(row["source"],entries,p._occurrences(row["source"],entries)))

    def inactive_decision(self, prepared, a, b):
        self.h.require(not prepared.eligible and prepared.provisional_prompt==prepared.baseline_prompt and
            type(a) is int and type(b) is int and 1<=a<=384 and b==a,"inactive receipt identity")
        return self.policy.Decision(prepared,False,prepared.reason,prepared.baseline_prompt,a,b)

    def preflight_pair(self, row_id, row, alias, declaration_bytes, count, worker, expected):
        h=self.h;prepared=worker.prepare("preflight",row_id,row)
        self.validate_prompt_binding(prepared,expected)
        h.require(messages(prepared.baseline_prompt)==self.baseline_messages(row),"worker existing-baseline binding")
        a,b=(h.serialize_request(messages(text),alias) for text in (prepared.baseline_prompt,prepared.provisional_prompt))
        ac,bc=count(a),count(b)
        decision=worker.gate("preflight",row_id,prepared,ac,bc) if prepared.eligible else self.inactive_decision(prepared,ac,bc)
        ra,rb=h.CountReceipt(a,ac),h.CountReceipt(b,bc);actual=rb if decision.active else ra
        h.require(h.serialize_request(messages(decision.prompt),alias)==actual.body,"actual preflight receipt")
        return PairPlan(row_id,prepared,decision,ra,rb,actual)

    def measured_candidate(self, plan, row, alias, declaration_bytes, count, worker, on_prepared=lambda:None):
        h=self.h;prepared=worker.prepare("measured",plan.row_id,row);on_prepared()
        h.require(prepared==plan.prepared,"measured plan drift")
        bodies=tuple(h.serialize_request(messages(t),alias) for t in (prepared.baseline_prompt,prepared.provisional_prompt))
        h.require(bodies==(plan.baseline.body,plan.provisional.body),"measured request drift")
        if prepared.eligible:
            a,b=count(bodies[0]),count(bodies[1])
            h.require((a,b)==(plan.baseline.count,plan.provisional.count),"recurring count drift")
            decision=worker.gate("measured",plan.row_id,prepared,a,b)
        else:decision=self.inactive_decision(prepared,plan.baseline.count,plan.provisional.count)
        h.require(decision==plan.decision,"preflight membership drift")
        body=h.serialize_request(messages(decision.prompt),alias)
        h.require(body==plan.candidate.body,"candidate receipt drift")
        return body

    def validate_preflight(self, inventory, plans):
        h=self.h
        h.require(tuple(p.row_id for p in plans)==inventory.row_ids and tuple(p.row_id for p in plans if p.eligible)==inventory.eligible_ids,"complete preflight membership")
        expected={r["id"]:r for r in inventory.coverage}
        for plan in plans:
            self.validate_prompt_binding(plan.prepared,inventory.prompt_bindings[plan.row_id])
            row=self.row(inventory,plan.row_id)
            h.require(messages(plan.prepared.baseline_prompt)==self.baseline_messages(row),"preflight baseline parity")
            meta=expected.get(plan.row_id)
            if meta and meta["role"]=="carrier":h.require(plan.eligible and plan.prepared.entry_id==meta["family"],"preflight family binding")
            elif meta:h.require(not plan.eligible and plan.reason==CONTROL_REASONS[meta["control_type"]],"preflight control reason")
            for receipt in (plan.baseline,plan.provisional,plan.candidate):
                h.require(type(receipt.count) is int and receipt.count>0 and (receipt.runtime,receipt.model_tokenizer,receipt.template)==(h.PINS["server"],h.PINS["model"],h.PINS["template"]),"count provenance")
            h.require(plan.baseline.count<=384 and plan.candidate.count<=384 and plan.candidate==(plan.provisional if plan.active else plan.baseline),"actual prompt cap")
        active={p.row_id for p in plans if p.active}
        carriers={r["id"] for r in inventory.coverage if r["role"]=="carrier"};controls={r["id"] for r in inventory.coverage if r["role"]=="control"}
        h.require(len(carriers)==12 and carriers<=active,"term carrier coverage failed")
        h.require(not(controls & active) and not(controls & set(inventory.eligible_ids)),"term control abstention failed")
        h.require(not(set(SEEN_IDS)&active),"historical active drift")
        return dict(active_carriers=12,abstaining_controls=7,populations=dict(ALL88=list(inventory.row_ids),FRESH19=list(inventory.fresh_ids),
            ACTIVE_ALL=[i for i in inventory.row_ids if i in active],ACTIVE_FRESH=[i for i in inventory.fresh_ids if i in active]))

    def ledger(self, inventory, persist=lambda event:None):
        core,h=self,self.h
        class Ledger(h.RequestLedger):
            def __init__(self):
                self.persist,self.counts,self.total=persist,Counter(),0
                self.terminal,self.cleanup_errors,self.preflight_sealed=None,[],False
                self.queue=[("health",None,None),("models",None,None)]
                self.queue += [("preflight",i,a) for i in inventory.row_ids for a in ("baseline","second")]
                for i,arm in inventory.schedule:
                    if arm=="candidate" and i in inventory.eligible_ids:self.queue += [("recurring",i,a) for a in ("baseline","provisional")]
                    self.queue.append(("completion",i,arm))
                h.require(len(self.queue)==inventory.request_total<=398,"exact request inventory")
            def consume(self,kind,row=None,arm=None):
                if self.total>=len(self.queue):
                    self.fail("exact_inventory_exhausted");raise h.TerminalFailure("no extra request allowance")
                return super().consume(kind,row,arm)
            def seal_preflight(self,plans):
                try:
                    h.require(self.terminal is None and self.total==178 and not self.preflight_sealed,"all counts before generation")
                    coverage=core.validate_preflight(inventory,plans)
                    self.persist(dict(event="preflight_sealed",coverage=coverage,request_bindings_sha256=h.digest(h.canonical([
                        dict(id=p.row_id,baseline=p.baseline.binding,prospective=p.provisional.binding,actual=p.candidate.binding,active=p.active,reason=p.reason) for p in plans]))))
                    self.plans,self.preflight_sealed=tuple(plans),True
                except BaseException:self.fail("preflight_validation_or_journal_failure");raise
            def assert_complete(self):
                h.require(self.terminal is None and self.total==inventory.request_total and self.counts==Counter(health=1,models=1,preflight=176,recurring=2*len(inventory.eligible_ids),completion=176),"exact completed request accounting")
        return Ledger()

    def paired_cost(self,inventory,plans,records,clock_resolution_seconds):
        h=self.h;coverage=self.validate_preflight(inventory,plans)
        h.require(type(clock_resolution_seconds) in (int,float) and math.isfinite(clock_resolution_seconds) and clock_resolution_seconds>0,"clock evidence")
        h.require(type(records) is list and tuple(r["id"] for r in records)==inventory.row_ids,"all88 cost denominator")
        active={p.row_id for p in plans if p.active}
        for r in records:h.require(r.get("active") is (r["id"] in active),"fixed active membership")
        valid={r["id"] for r in records if r.get("complete") is True and all(type(r.get(k)) in (int,float) and math.isfinite(r[k]) and r[k]>0 for k in ("baseline","candidate"))}
        by_id={r["id"]:r for r in records};groups={}
        for name,ids in coverage["populations"].items():
            complete=bool(ids) and set(ids)<=valid
            ratios=h.quantiles([by_id[i]["candidate"]/by_id[i]["baseline"] for i in ids]) if complete else None
            failed=bool(ratios and (ratios["median"]>1.25 or ratios["p95"]>1.25))
            groups[name]=dict(expected_n=len(ids),observed_n=len(set(ids)&valid),ratios=ratios,status="fail" if failed else "pass" if complete else "inconclusive")
        status="fail" if any(g["status"]=="fail" for g in groups.values()) else "pass" if all(g["status"]=="pass" for g in groups.values()) else "inconclusive"
        return dict(status=status,populations=groups,raw_rows=records,quality_failures_included=True,no_post_output_exclusions=True,semantic_quality_claim=None)

    def all_row_accounting(self,inventory,observations):
        self.h.require(set(observations)<=set(inventory.schedule),"unexpected arm")
        return [dict(id=i,arms={a:observations.get((i,a),{"status":"unobserved"}) for a in ("baseline","candidate")}) for i in inventory.row_ids]

    def run_real(self,*args,**kwargs):raise self.h.Disabled("SOURCE_ONLY_NATIVE_DISABLED")
