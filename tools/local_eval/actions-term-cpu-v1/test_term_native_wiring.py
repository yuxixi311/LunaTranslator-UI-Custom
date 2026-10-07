"""NEW complete wiring tests; pure synthetic plans and fully injected fakes."""
from copy import deepcopy
from hashlib import sha256
import ast,importlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/"policy"))
import cpu_harness as h
import term_lock_policy as p
import actions_policy,activation_scope,verified_bootstrap as bootstrap
import term_runtime_inventory as runtime_inventory
import term_worker_entry as entry
import usage_helper_bridge as bridge

class Tests(unittest.TestCase):
    def test_verified_bootstrap_closure_imports(self):
        for name in bootstrap.MODULE_ORDER:importlib.import_module(name)
    def test_runtime_loader_never_runs_parent_candidate_policy(self):
        raw={n:(ROOT/"inputs"/n).read_bytes() for n in runtime_inventory.RAW_PINS}
        declarations=(ROOT/"policy/global_declarations.json").read_bytes()
        with patch.object(p,"prepare",side_effect=AssertionError("parent admission")),patch.object(p,"apply_token_gate",side_effect=AssertionError("parent token policy")):
            _,inv,_=runtime_inventory.load_from_bytes(raw,declarations)
        self.assertEqual(len(inv.row_ids),88);self.assertEqual(inv.schedule,h.SCHEDULE);self.assertEqual(inv.request_total,378)
    def test_prepared_identity_is_metadata_only(self):
        metadata=json.loads((ROOT/"INPUT_COMMITMENTS.json").read_bytes())
        self.assertTrue(actions_policy.validate_release_metadata(metadata))
        plan=json.loads((ROOT/"SOURCE_PLAN.json").read_bytes())
        self.assertEqual(plan["attempt_id"],metadata["attempt_id"])
        self.assertIsNone(plan["source_commit"]);self.assertIsNone(plan["trigger_commit"])
        self.assertFalse(plan["claim_authorized"]);self.assertFalse(plan["publication_authorized"])
        self.assertFalse(any(ROOT.rglob("ONE_SHOT_CPU_ATTEMPT.json")))
    def test_all_native_entry_guards_deny(self):
        import term_native_adapter,term_worker_packets,guarded_runtime,final_coordinator,actions_entry,kit_worker
        calls=[bootstrap.require_bootstrap_activation,activation_scope.require_actions_guard,lambda:activation_scope.require_role("actions"),guarded_runtime.require_activation,
            term_native_adapter.require_native_release,bridge.require_native_release,term_worker_packets.require_native_release,entry.require_native_release,
            lambda:actions_entry.main("a"*64),lambda:final_coordinator.main("","a"*64),lambda:kit_worker.main("acquire","/synthetic","a"*64)]
        for call in calls:
            with self.assertRaises(Exception):call()
    def test_current_entry_worker_bootstrap_byte_pins(self):
        self.assertEqual(sha256((ROOT/"term_worker_entry.py").read_bytes()).hexdigest(),bridge.ENTRY_SOURCE_SHA256)
        self.assertEqual(sha256((ROOT/"term_worker.py").read_bytes()).hexdigest(),entry.WORKER_PIN)
        self.assertEqual(sha256(entry.ENTRY_BOOTSTRAP.encode()).hexdigest(),bridge.ENTRY_BOOTSTRAP_SHA256)
    def test_bootstrap_rejects_a_changed_module(self):
        payloads={bootstrap.MODULE_PATHS[n]:(ROOT/bootstrap.MODULE_PATHS[n]).read_bytes() for n in bootstrap.MODULE_ORDER}
        manifest=dict(files=[dict(path=n,bytes=len(raw),sha256=sha256(raw).hexdigest()) for n,raw in payloads.items()])
        raw=json.dumps(manifest).encode();pin=sha256(raw).hexdigest()
        self.assertEqual(set(bootstrap.verify_payloads(raw,pin,payloads)),set(bootstrap.MODULE_ORDER))
        payloads["term_runner_source.py"]+=b"\n"
        with self.assertRaises(ValueError):bootstrap.verify_payloads(raw,pin,payloads)
    def test_helper_raw_handle_adopted_before_reporting_and_exit_never_overwritten(self):
        tree=ast.parse((ROOT/"usage_helper_bridge.py").read_bytes())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="NativeBackend")
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="spawn")
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        popen=next(n.lineno for n in calls if n.func.attr=="Popen");adopt=next(n.lineno for n in calls if n.func.attr=="adopt")
        self.assertGreater(adopt,popen)
        for call in calls:
            if call.func.attr=="child" and call.lineno>popen:
                self.assertGreater(call.lineno,adopt);self.assertNotIn("exit",{k.arg for k in call.keywords})
        from diagnostics import Trace
        trace=Trace("a"*64);trace.child("helper",exit="EXITED",exit_code=0);trace.child("helper",launch="RETURNED",adopted=True)
        self.assertEqual((trace.children["helper"]["exit"],trace.children["helper"]["exit_code"]),("EXITED",0))
    def test_pure_prospective_plan_is_fully_wired(self):
        import actions_entry,final_coordinator
        a,b,parent="a"*40,"b"*40,"c"*40
        provider=dict(repository=actions_policy.REPOSITORY,ref="refs/heads/"+actions_policy.BRANCH,event_name="push",private=False,created=False,deleted=False,forced=False,
            before=a,after=b,head_commit=b,source_parent=parent,checkout_head=b,checkout_parent=a,source_a_parent=parent,changed_at_b=[actions_policy.WORKFLOW],run_id="12345",run_attempt=1,
            workflow_ref=actions_policy.REPOSITORY+"/"+actions_policy.WORKFLOW+"@refs/heads/"+actions_policy.BRANCH,workflow_sha=b,runner_environment="github-hosted",runner_os="Linux",runner_arch="X64",
            runner_label="ubuntu-24.04",image_os="ubuntu24",image_version="20261001.1.0",job_id="term_lock",job_container=None,container_steps=[],namespace_wrappers=[])
        roots=dict(workspace="/synthetic/workspace",source="/synthetic/workspace/"+actions_policy.PROJECT,runner_temp="/synthetic/temp",state="/synthetic/temp/"+actions_policy.STATE_NAME,output="/synthetic/temp/"+actions_policy.STATE_NAME+"/attempt")
        metadata=json.loads((ROOT/"INPUT_COMMITMENTS.json").read_bytes());metadata.update(source_parent=parent,attempt_id="11111111111141118111111111111111")
        pin="d"*64;argv=["/usr/bin/python3","-I","-B",roots["source"]+"/verified_bootstrap.py",roots["source"]+"/KIT_MANIFEST.json",pin,"actions","unused"]
        plan=actions_entry.assemble_plan(roots,provider,metadata,pin,"/usr/bin/python3",coordinator_identity=dict(coordinator_pid=123,coordinator_argv=argv))
        self.assertTrue(final_coordinator.validate_kit_plan(plan,pin));self.assertEqual(plan["limits"]["planned_http"],378)
        plan["limits"]["completions"]=174
        with self.assertRaises(h.TerminalFailure):final_coordinator.validate_kit_plan(plan,pin)
    def test_controller_cancellation_cannot_erase_received_raw_output(self):
        import final_coordinator as coordinator
        from attempt_control import AttemptControl
        from test_term_runner import inventory,TermCore,ALIAS,DECLARATIONS,execute_stage,validate_integrity,LocalTranslationError
        from test_term_evidence import EvidenceHooks
        from term_public_exports import build_public
        class CancelledLogging(EvidenceHooks):
            def __init__(self,inv):
                super().__init__(inv)
                self.control=AttemptControl(now=lambda:self.clock.ns/1e9)
                original=self.backend.stop
                def stop(deadline):
                    self.control.expired("helper terminal failure")
                    return original(deadline)
                self.backend.stop=stop
            def record(self,name,value):
                self.control.checkpoint()
                return super().record(name,value)
        core=TermCore(h,p);inv=inventory(core);hooks=CancelledLogging(inv)
        hooks.backend.state._restore=lambda message:(_ for _ in ()).throw(RuntimeError("synthetic worker failure"))
        with self.assertRaises(h.TerminalFailure):execute_stage(core,inv,ALIAS,DECLARATIONS,hooks,validate_integrity,LocalTranslationError)
        persisted=deepcopy([r for name,r in hooks.records if name=="arm"])
        key=(inv.fresh_ids[0],"candidate")
        self.assertNotIn(key,{(r["row"],r["arm"]) for r in persisted})
        self.assertEqual(hooks.observations[key]["original_output"],"{LT0}")
        hooks.control.begin_cleanup()
        retained=coordinator.merge_retained_observations(core,inv,persisted,hooks.observations)
        hooks.record("all_rows",core.all_row_accounting(inv,retained))
        public=build_public(core,inv,hooks.plans,retained,consumed_http=None,validated_http=None,
            accounting_confirmed=False,cleanup_confirmed=None)
        record=next(r for r in public["outputs.json"] if (r["id"],r["arm"])==key)
        self.assertEqual(record["original_output"],"{LT0}");self.assertEqual(record["state"],"operational_failure")
        self.assertEqual(public["accounting.json"]["status"],"incomplete")
        bad=deepcopy(persisted);bad[0]["total_ns"]+=1
        with self.assertRaises(h.TerminalFailure):coordinator.merge_retained_observations(core,inv,bad,hooks.observations)
    def test_native_hook_and_final_snapshot_use_fakes_only(self):
        import term_native_adapter,final_coordinator as coordinator
        from test_term_runner import inventory,TermCore,ALIAS,DECLARATIONS,validate_integrity,LocalTranslationError
        from test_term_evidence import EvidenceHooks,GUARD_BYTES
        class Hooks(EvidenceHooks):
            @property
            def intervals(self):return [v for k,v in self.records if k=="arm"]
        core=TermCore(h,p);inv=inventory(core);hooks=Hooks(inv);saved={}
        hooks.runtime=SimpleNamespace(AUDITED=ROOT/"audited",pinned_file=lambda *args:GUARD_BYTES)
        hooks.evidence=SimpleNamespace(create=lambda n:saved.setdefault(n,None),json=lambda n,v:saved.__setitem__(n,v))
        with patch.object(term_native_adapter,"require_native_release",return_value={"synthetic":True}):
            result,report=term_native_adapter.generation_stage(core,inv,ALIAS,DECLARATIONS,hooks,validate_integrity,LocalTranslationError)
        self.assertEqual(report["reconciled_http"],378);self.assertEqual(saved["protocol_reconciliation.json"],report)
        raw={"results.jsonl":b"".join(h.canonical(v)+b"\n" for v in hooks.intervals),"wire.jsonl":b"".join(h.canonical({k:v for k,v in row.items() if k not in ("request_body","response_wire")})+b"\n" for row in hooks.transcripts)}
        saved={};sent=[];evidence=SimpleNamespace(file_bytes={k:len(v) for k,v in raw.items()},create=lambda n:saved.setdefault(n,None),json=lambda n,v:saved.__setitem__(n,v))
        owner=SimpleNamespace(usage_hooks=hooks,peak_runner_rss=20*h.MIB,peak_server_rss=h.GIB,public_reconciliation=report,public_helper_lifecycle=result["helper"]["lifecycle"],public_helper_metrics=dict(helper_peak_rss_bytes=16*h.MIB,helper_render_p95_ns=h.quantiles([v["elapsed_ns"] for v in hooks.helper_samples])["p95"]),diagnostic=None)
        stdout=SimpleNamespace(buffer=SimpleNamespace(write=sent.append,flush=lambda:None))
        with patch.object(coordinator.runtime,"require_activation"),patch.object(coordinator.runtime,"persistence_checkpoint"),patch.object(coordinator.term_runtime_inventory,"load",return_value=(core,inv,DECLARATIONS)),patch.object(coordinator.runtime,"bounded_file",side_effect=lambda path,cap:raw[path.name]),patch.object(coordinator.os,"mkdir") as mkdir,patch.object(coordinator.sys,"stdout",stdout):
            coordinator.emit_public_snapshot(dict(paths=dict(output="/synthetic/not-created")),owner,evidence,True,True)
            self.assertEqual(len(saved),6);self.assertEqual(saved["public/metrics.json"]["helper_prepare_samples"][0]["row"],inv.row_ids[0])
            saved.clear();sent.clear();mkdir.reset_mock()
            with patch.object(coordinator.public_exports,"finalize_payloads",side_effect=h.TerminalFailure("aggregate cap")):
                with self.assertRaises(h.TerminalFailure):coordinator.emit_public_snapshot(dict(paths=dict(output="/synthetic/not-created")),owner,evidence,True,None)
            self.assertEqual(saved,{});self.assertEqual(sent,[]);mkdir.assert_not_called()

if __name__=="__main__":unittest.main()
