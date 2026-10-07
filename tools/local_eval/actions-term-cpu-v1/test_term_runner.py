"""NEW synthetic control-flow tests. These rows are illustrative, never fresh19."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"policy"));sys.path.insert(0,str(ROOT/"audited"))
import term_lock_policy as p
import cpu_harness as h
import term_worker as w
from term_runner_core import TermCore,SEEN_IDS,HISTORICAL_IDS,PRIOR_IDS,GLOSSARY_IDS,CONTROL_REASONS
from term_runner_source import execute_stage
from usage_helper_bridge import BoundedBridge,BridgeError
from myutils.local_translation_integrity import validate_integrity
from myutils.local_translation import LocalTranslationError
DECLARATIONS=(ROOT/"policy/global_declarations.json").read_bytes()
ENTRIES=json.loads(DECLARATIONS)["entries"];GLOSSARY=[{k:e[k] for k in ("src","dst")} for e in ENTRIES]
ALIAS=h.alias_for("11111111111141118111111111111111")

def fake_inputs():
    rows=[dict(id=i,source="illustrative_not_fresh_"+i,scope_id="illustrative-old-scope",glossary=[],stratum="historical40" if i in HISTORICAL_IDS else "prior15" if i in PRIOR_IDS else "glossary14") for i in SEEN_IDS]
    coverage=[]
    for n,e in enumerate(ENTRIES[:6]):
        for scenario in range(2):
            i=f"FAKE-NOT-FRESH-{2*n+scenario:02d}"
            rows.append(dict(id=i,source=e["src"]+"、例。"+str(scenario),scope_id=p.SCOPE_ID,glossary=deepcopy(GLOSSARY),stratum="fresh19"))
            coverage.append(dict(id=i,role="carrier",family=e["id"],control_type=None))
    controls=[("光、例。",p.SCOPE_ID),("リュゼル群",p.SCOPE_ID),("「リュゼル」",p.SCOPE_ID),("リュゼル、例。","foreign"),
        ("{LT7}リュゼル",p.SCOPE_ID),("リュゼル、30%。",p.SCOPE_ID),("例。",p.SCOPE_ID)]
    for n,((source,scope),control) in enumerate(zip(controls,CONTROL_REASONS)):
        i=f"FAKE-NOT-FRESH-C{n}";rows.append(dict(id=i,source=source,scope_id=scope,glossary=deepcopy(GLOSSARY),stratum="fresh19"))
        coverage.append(dict(id=i,role="control",family=None,control_type=control))
    first={}
    for group in (HISTORICAL_IDS,PRIOR_IDS):first.update({i:"A" if n%2==0 else "B" for n,i in enumerate(group)})
    for prefix in ("person","participant","entity","negative","nomatch"):
        first.update({i:"B" if prefix=="nomatch" else "A" if n%2==0 else "B" for n,i in enumerate(i for i in GLOSSARY_IDS if i.startswith(prefix+"-"))})
    for n,r in enumerate(rows[69:]):first[r["id"]]=("A" if n%2==0 else "B") if n<12 else ("B" if n%2==0 else "A")
    schedule=[dict(id=r["id"],arm_order=[first[r["id"]],"B" if first[r["id"]]=="A" else "A"]) for r in rows]
    return rows,coverage,schedule

def inventory(core,inputs=None):
    rows,coverage,schedule=inputs or fake_inputs()
    bindings={k:h.digest(h.canonical(v)) for k,v in (("sources",rows),("coverage",coverage),("schedule",schedule))};bindings["declarations"]=p.DECLARATIONS_SHA256
    return core.freeze_inventory(rows,coverage,schedule,DECLARATIONS,bindings=bindings)

class Clock:
    def __init__(self):self.ns=1_000_000_000
    def now(self):self.ns+=100;return self.ns
    def advance(self,n=20_000):self.ns+=n

class Backend:
    closure_sha256="a"*64
    def __init__(self,inv,clock):
        self.clock=clock;self.identity={"synthetic":"illustrative-not-fresh"}
        bindings={i:w.digest({k:h.strict_json(inv.rows[i])[k] for k in ("source","scope_id","glossary")}) for i in inv.row_ids}
        self.state=w.PolicyWorker(p,DECLARATIONS,inv.row_ids,inv.eligible_ids,bindings,validate_integrity,LocalTranslationError)
        self.sent=None;self.exited=False;self.stop_result=True;self.reap_result=True;self.rss=16*h.MIB;self.cpu=100_000;self.requests=[]
    def spawn(self,*args):self.clock.advance();return self.identity
    def check(self):pass
    def snapshot(self,**kwargs):return dict(identity=self.identity,peak_rss_bytes=self.rss,cpu_ns=self.cpu,exited=self.exited)
    def write_frame(self,frame,deadline):self.clock.advance();self.sent=frame;self.requests.append(w.decode_frame(frame))
    def read_frame(self,deadline):
        self.clock.advance()
        if self.sent is None:
            value=self.state.ready();value.update(worker_identity=self.identity,closure_sha256=self.closure_sha256,peak_rss_bytes=self.rss,cpu_ns=self.cpu)
            return w.encode_frame(value)
        frame,self.sent=self.sent,None
        return self.state.exchange_frame(frame)
    def close_input(self):pass
    def reap(self,*args,**kwargs):self.clock.advance();self.exited=self.reap_result;return self.reap_result
    def stop(self,*args):self.exited=self.stop_result;return self.stop_result
    def close(self):pass

class Hooks:
    clock_resolution_seconds=1e-9
    def __init__(self,inv,count_override=None,output_override=None):
        self.inv,self.clock=inv,Clock();self.backend=Backend(inv,self.clock)
        self.bridge=BoundedBridge(w,self.backend,now_ns=self.clock.now,phase_deadline_ns=lambda:self.clock.ns+60_000_000_000,
            work_end_ns=self.clock.ns+780_000_000_000,postready_end_ns=self.clock.ns+600_000_000_000,cleanup_end_ns=self.clock.ns+800_000_000_000,
            expected_commands=178+3*len(inv.eligible_ids))
        self.worker=w.WorkerClient(self.bridge,p,inv.eligible_ids);self.records=[];self.events=[];self.transcripts=[]
        self.count_override,self.output_override=count_override,output_override
        from diagnostics import Trace
        self.owner=SimpleNamespace(diagnostic=Trace("a"*64));self.owner.diagnostic.enter("preflight")
    def now_ns(self):return self.clock.now()
    def check(self):pass
    def ready_marker(self):pass
    def postready_limit(self,value):assert value==600
    def phase(self,name,seconds):assert(name,seconds)==("preflight",60)
    def resume_postready_limit(self):pass
    def event(self,event):self.events.append(event)
    def record(self,name,value):self.records.append((name,value))
    def publish_preflight(self,plans):self.plans=plans
    def count(self,kind,row,arm,body):
        value=42 if "{LT0}" in json.loads(body)["messages"][0]["content"] else 40
        return self.count_override(kind,row,arm,value) if self.count_override else value
    def exchange(self,ledger,kind,row,arm,body,validate):
        ledger.consume(kind,row,arm);started=self.clock.ns
        if kind=="health":payload=dict(status="ok")
        elif kind=="models":payload=dict(data=[dict(id=ALIAS)])
        elif kind in ("preflight","recurring"):payload=dict(object="response.input_tokens",input_tokens=self.count(kind,row,arm,body))
        else:
            source=h.strict_json(self.inv.rows[row])["source"];output="{LT0}" if arm=="candidate" and row in self.inv.eligible_ids else source
            if self.output_override:output=self.output_override(row,arm,output)
            count=self.count(kind,row,arm,body)
            payload=dict(model=ALIAS,choices=[dict(message=dict(content=output),finish_reason="stop")],usage=dict(prompt_tokens=count,completion_tokens=3,total_tokens=count+3,prompt_tokens_details=dict(cached_tokens=0)))
        self.clock.advance(1_000_000);result=validate(h.canonical(payload));self.transcripts.append((kind,row,arm));return result,self.clock.ns-started

class Tests(unittest.TestCase):
    def setUp(self):self.core=TermCore(h,p);self.inv=inventory(self.core)
    def run_fake(self,hooks=None):
        hooks=hooks or Hooks(self.inv)
        return execute_stage(self.core,self.inv,ALIAS,DECLARATIONS,hooks,validate_integrity,LocalTranslationError),hooks
    def test_exact_inventory_and_child_restore(self):
        result,hooks=self.run_fake()
        self.assertEqual(result["ledger"].total,378);self.assertEqual(len(result["observations"]),176)
        self.assertEqual(len(hooks.backend.requests),214);self.assertEqual(sum(m["op"]=="RESTORE" for m in hooks.backend.requests),12)
        self.assertEqual(len(hooks.helper_samples),88);self.assertIsNone(result["semantic_quality_claim"])
    def test_all_preflight_counts_before_generation(self):
        _,hooks=self.run_fake();first=next(n for n,v in enumerate(hooks.transcripts) if v[0]=="completion")
        self.assertEqual(first,178)
    def test_marker_failures_retain_all_completions(self):
        for bad in ("missing","{LT0}{LT0}","{LT1}","{LT0}{LT9}","x"*33000+"{LT0}"):
            hooks=Hooks(self.inv,output_override=lambda row,arm,value:bad if row==self.inv.fresh_ids[0] and arm=="candidate" else value)
            result,_=self.run_fake(hooks);record=result["observations"][(self.inv.fresh_ids[0],"candidate")]
            self.assertEqual(record["original_output"],bad);self.assertIsNone(record["final_output"])
            self.assertIn("integrity_rejection",record["flags"]);self.assertEqual(result["ledger"].total,378)
    def test_received_raw_survives_worker_failure(self):
        hooks=Hooks(self.inv);hooks.backend.state._restore=lambda message:(_ for _ in ()).throw(RuntimeError("synthetic"))
        with self.assertRaises(h.TerminalFailure):self.run_fake(hooks)
        rows=hooks.records[-1][1];record=next(r["arms"]["candidate"] for r in rows if r["id"]==self.inv.fresh_ids[0])
        self.assertEqual(record["original_output"],"{LT0}");self.assertTrue(any(a["status"]=="unobserved" for r in rows for a in r["arms"].values()))
    def test_token_failure_stops_before_generation_and_keeps_first_diagnostic(self):
        hooks=Hooks(self.inv,count_override=lambda kind,row,arm,value:57 if row==self.inv.fresh_ids[0] and value==42 else value)
        with self.assertRaises(h.TerminalFailure):self.run_fake(hooks)
        self.assertEqual(hooks.ledger.counts["preflight"],176);self.assertEqual(hooks.ledger.counts["completion"],0)
        hooks.owner.diagnostic.fail(code="OWNER_FAILURE")
        self.assertEqual(hooks.owner.diagnostic.first["value"]["code"],"PREFLIGHT_CARRIER_COVERAGE_REJECTED")
    def test_bad_inactive_or_recurring_counts_fail(self):
        for kind,changed in (("preflight",lambda k,r,a,v:0 if(k,r,a)==("preflight","R001","second") else v),("recurring",lambda k,r,a,v:v+1 if k=="recurring" else v)):
            hooks=Hooks(self.inv,count_override=changed)
            with self.assertRaises(h.TerminalFailure):self.run_fake(hooks)
            self.assertLess(hooks.ledger.counts["completion"],176)
    def test_worker_prompt_destination_reason_bound_before_any_generation(self):
        for field,value in (("baseline_prompt","forged"),("provisional_prompt","forged"),("destination","forged"),("entry_id","name_2"),("reason","forged")):
            hooks=Hooks(self.inv);original=hooks.worker.prepare
            def changed(phase,row_id,row):
                result=original(phase,row_id,row)
                return replace(result,**{field:value}) if row_id==self.inv.fresh_ids[0] else result
            hooks.worker.prepare=changed
            with self.assertRaises(h.TerminalFailure):self.run_fake(hooks)
            self.assertEqual(hooks.ledger.counts["completion"],0)
    def test_source_schema_and_complete_glossary_fail_closed(self):
        for mutation in (lambda v:v[0][-1].update(gold="forbidden"),lambda v:v[0][69].update(glossary=GLOSSARY[:1]),lambda v:v[2][-1].update(arm_order=["A","B"])):
            values=fake_inputs();mutation(values)
            with self.assertRaises(h.TerminalFailure):inventory(self.core,values)
    def test_parent_token_validation_never_executes_policy_gate(self):
        row=self.core.row(self.inv,self.inv.fresh_ids[0]);plan=p.prepare(row["source"],row["scope_id"],row["glossary"],DECLARATIONS)
        class Bridge:
            def request(self,request,validate):return validate(dict(op="GATED",phase="preflight",row="x",active=True,reason="active",prompt_sha256=w.digest(plan.provisional_prompt),baseline_tokens=40,provisional_tokens=42))
        with patch.object(p,"apply_token_gate",side_effect=AssertionError("parent policy forbidden")):
            self.assertTrue(w.WorkerClient(Bridge(),p,("x",)).gate("preflight","x",plan,40,42).active)
    def test_helper_resource_bound_is_not_relaxed(self):
        hooks=Hooks(self.inv);hooks.backend.rss=33*h.MIB
        with self.assertRaises(BridgeError):self.run_fake(hooks)
        self.assertEqual(hooks.ledger.counts["completion"],0)
    def test_latency_four_fixed_populations_keep_missing_and_negative_rows(self):
        result,_=self.run_fake();rows=[dict(id=i,baseline=100,candidate=125,active=i in self.inv.eligible_ids,complete=True) for i in self.inv.row_ids]
        self.assertEqual(self.core.paired_cost(self.inv,result["plans"],rows,1e-9)["status"],"pass")
        rows[-1]["complete"]=False;self.assertEqual(self.core.paired_cost(self.inv,result["plans"],rows,1e-9)["status"],"inconclusive")
        rows[69]["candidate"]=200;self.assertEqual(self.core.paired_cost(self.inv,result["plans"],rows,1e-9)["status"],"fail")

if __name__=="__main__":unittest.main()
