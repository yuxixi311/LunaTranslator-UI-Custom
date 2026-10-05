"""Actions port checks: pure fixtures only, no provider/host/network/process probe."""
from copy import deepcopy
from hashlib import sha256
import json
import base64
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import actions_policy as p
import actions_entry as entry
import cpu_harness as h
import final_coordinator as coordinator
import guarded_runtime as runtime
import host_validation_source as host
import public_exports as exports
import verified_bootstrap as bootstrap
from test_cpu_harness import ATTEMPT

A='a'*40;B='b'*40;PARENT='c'*40

def binding():
    return dict(repository=p.REPOSITORY,ref='refs/heads/'+p.BRANCH,event_name='push',private=False,
        created=False,deleted=False,forced=False,before=A,after=B,head_commit=B,source_parent=PARENT,
        checkout_head=B,checkout_parent=A,source_a_parent=PARENT,changed_at_b=[p.WORKFLOW],run_id='123',run_attempt=1,
        workflow_ref=p.REPOSITORY+'/'+p.WORKFLOW+'@refs/heads/'+p.BRANCH,workflow_sha=B,
        runner_environment='github-hosted',runner_os='Linux',runner_arch='X64',runner_label='ubuntu-24.04',
        image_os='ubuntu24',image_version='20261004.1',job_id='sense',job_container=None,container_steps=[],namespace_wrappers=[])

def roots():
    return dict(workspace='/fake/workspace',source='/fake/workspace/'+p.PROJECT,runner_temp='/fake/temp',
                state='/fake/temp/'+p.STATE_NAME,output='/fake/temp/'+p.STATE_NAME+'/attempt')

def owner_identity():
    source=roots()['source']
    return dict(coordinator_pid=42,coordinator_argv=['/usr/bin/python3','-I','-B',source+'/verified_bootstrap.py',
        source+'/KIT_MANIFEST.json','1'*64,'actions','unused'])

def metadata():
    keys=set(h.CLAIM_EXTRA_HASHES)-{'harness_manifest','output_schemas','output_binding_revision'}
    return dict(source_parent=PARENT,attempt_id=ATTEMPT,commitments={key:'1'*64 for key in keys})

def cache(entries=None):
    if entries is None:entries=[(name,'/lib/x86_64-linux-gnu/'+name,0) for name in host.HOST_POLICY['allowed_libraries']]
    first=48+24*len(entries);strings=bytearray();rows=[]
    for name,path,hwcap in entries:
        key=first+len(strings);strings+=name.encode()+b'\0'
        value=first+len(strings);strings+=path.encode()+b'\0'
        rows.append(struct.pack('<iIIIQ',0x303,key,value,0,hwcap))
    head=bytearray(48);head[:20]=b'glibc-ld.so.cache1.1';struct.pack_into('<II',head,20,len(rows),len(strings));head[28]=2
    return bytes(head)+b''.join(rows)+strings

class ProviderTests(unittest.TestCase):
    def test_exact_provider_chain(self):self.assertTrue(p.validate_provider(binding(),source_a=A,source_parent=PARENT))
    def test_context_mutations_stop(self):
        mutations={'repository':'other/repo','private':True,'event_name':'workflow_dispatch','before':B,
            'checkout_parent':PARENT,'source_a_parent':B,'changed_at_b':[p.WORKFLOW,'other'],
            'run_attempt':2,'runner_environment':'self-hosted','runner_label':'ubuntu-slim','image_os':'ubuntu22',
            'job_container':'ubuntu','container_steps':['docker'],'namespace_wrappers':['unshare']}
        for key,value in mutations.items():
            b=binding();b[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_provider(b,source_a=A,source_parent=PARENT)
    def test_unfrozen_commit_stops(self):
        with self.assertRaises(ValueError):p.validate_provider(binding())
    def test_root_derivation(self):self.assertEqual(p.validate_roots(roots())['output'],Path(roots()['output']))
    def test_root_escape_and_overlap_stop(self):
        for key,value in [('source','/fake/elsewhere'),('state','/fake/workspace/state'),('output','/tmp/other'),('runner_temp','/fake/../temp')]:
            r=roots();r[key]=value
            with self.assertRaises(ValueError):p.validate_roots(r)
    def test_complete_plan_and_fixed_science(self):
        plan=entry.assemble_plan(roots(),binding(),metadata(),'1'*64,'/usr/bin/python3',coordinator_identity=owner_identity())
        self.assertTrue(coordinator.validate_kit_plan(plan,'1'*64));self.assertLess(len(h.canonical(plan)),32768)
        self.assertEqual(len(h.SCHEDULE),176);self.assertEqual(len(h.RequestLedger().queue),442)
        self.assertEqual(plan['limits'],h.LIMITS)
        for key in ('sampling','pins','limits'):
            broken=deepcopy(plan);broken[key]={}
            with self.assertRaises(h.TerminalFailure):coordinator.validate_kit_plan(broken,'1'*64)
    def test_private_fields_are_not_accepted(self):
        plan=entry.assemble_plan(roots(),binding(),metadata(),'1'*64,'/usr/bin/python3',coordinator_identity=owner_identity())
        for key in ('private_criteria','private_arm_key','raw_env'):
            broken=deepcopy(plan);broken[key]='secret'
            with self.assertRaises(h.TerminalFailure):coordinator.validate_kit_plan(broken,'1'*64)
    def test_unknown_parent_receipts_stop(self):
        m=metadata();m['commitments']['parent_preregistration']='__PARENT_FROZEN_SHA256__'
        with self.assertRaises(h.TerminalFailure):entry.assemble_plan(roots(),binding(),m,'1'*64,'/usr/bin/python3',coordinator_identity=owner_identity())
    def test_native_entries_hard_disabled(self):
        for operation in (lambda:entry.main('1'*64),lambda:runtime.bind_actions_roots(roots()),
                          lambda:host.resolve_host_libraries(cache(),None),lambda:coordinator.main('','1'*64)):
            with self.assertRaises(h.Disabled):operation()
        with self.assertRaises(RuntimeError):bootstrap.main()
    def test_workflow_only_exact_push_and_outer_cap(self):
        text=(Path(__file__).parent/'WORKFLOW_TEMPLATE.yml.in').read_text()
        self.assertIn('timeout-minutes: 30',text);self.assertIn('github.run_attempt == 1',text)
        self.assertNotIn('workflow_dispatch',text);self.assertNotIn('pull_request',text)
        self.assertNotIn('upload-artifact',text);self.assertIn('__REVIEWED_SOURCE_COMMIT_A__',text)
    def test_preclaim_host_failure_forbids_claim_and_acquisition(self):
        from attempt_control import AttemptControl
        from test_cpu_harness import Clock
        plan=entry.assemble_plan(roots(),binding(),metadata(),'1'*64,'/fake/python',coordinator_identity=owner_identity())
        events=[]
        def fail(*args):events.append('host');raise h.TerminalFailure('synthetic unknown capacity')
        def forbidden(*args):raise AssertionError('claim or download reached')
        with patch.object(runtime,'require_activation',lambda:None),patch.object(runtime,'bind_actions_roots',lambda roots:None),\
             patch.object(runtime,'load_audited_components',lambda:(None,None,None)),\
             patch.object(coordinator.sys,'executable','/fake/python'),patch.object(Path,'resolve',lambda self:self),\
             patch.object(coordinator.os,'getpid',lambda:42),\
             patch.object(coordinator.os.path,'lexists',lambda path:False),patch.object(host,'check_host_before_claim',fail),\
             patch.object(coordinator,'claim_once',forbidden),patch.object(coordinator,'run_worker',forbidden),\
             patch.dict(coordinator.__dict__,{'_VERIFIED_BOOTSTRAP_SHA':'1'*64}):
            with self.assertRaises(h.TerminalFailure):
                coordinator._run_attempt(base64.b64encode(h.canonical(plan)).decode(),'1'*64,AttemptControl(Clock()))
        self.assertEqual(events,['host'])
    def test_worker_root_binding_precedes_fixed_claim_check(self):
        import kit_worker
        text=Path(kit_worker.__file__).read_text()
        self.assertLess(text.index("runtime.bind_actions_roots(plan['roots'])"),text.index("'worker fixed claim'"))
    def test_helper_verified_imports_include_new_core_dependency(self):
        self.assertEqual(bootstrap.HELPER_MODULES,('actions_policy','activation_scope','cpu_harness','frozen_renderer','isolated_helper'))
        self.assertLess(bootstrap.MODULE_ORDER.index('actions_policy'),bootstrap.MODULE_ORDER.index('cpu_harness'))

class HostTests(unittest.TestCase):
    def fixture(self,missing_mount=False,depth=1,mount_root='/'):
        values={'/proc/self/status':('NSpid:\t'+'\t'.join(['123']*depth)+'\n').encode(),'/proc/1/comm':b'systemd\n',
            '/proc/self/mountinfo':b'' if missing_mount else ('1 0 0:1 '+mount_root+' /sys/fs/cgroup rw - cgroup2 cgroup rw\n').encode(),
            '/proc/self/cgroup':b'0::/user.slice/job\n',
            '/proc/1/status':b'Name:\tsystemd\nPid:\t1\nNSpid:\t1\n'}
        return lambda path,cap:values[path],lambda path:path.rsplit('/',1)[-1]+':[123]'
    def test_observed_namespace_supported(self):self.assertEqual(set(host.namespace_observation(*self.fixture())),{'pid','cgroup','mnt'})
    def test_hidden_or_missing_namespace_stops(self):
        for kwargs in ({'missing_mount':True},{'depth':2},{'mount_root':'/tenant/job'}):
            with self.assertRaises(h.TerminalFailure):host.namespace_observation(*self.fixture(**kwargs))
    def test_cross_uid_namespace_dereference_never_requested(self):
        read,link=self.fixture();seen=[]
        def own_only(path):
            seen.append(path)
            if '/proc/1/' in path:raise PermissionError('ptrace denied')
            return link(path)
        host.namespace_observation(read,own_only)
        self.assertEqual(set(seen),{'/proc/self/ns/pid','/proc/self/ns/cgroup','/proc/self/ns/mnt'})
    def test_pid1_status_missing_nested_or_contradictory_stops(self):
        read,link=self.fixture()
        for raw in (b'Name: systemd\nPid: 1\n',b'Name: systemd\nPid: 1\nNSpid: 88 1\n',
                    b'Name: container\nPid: 1\nNSpid: 1\n'):
            with self.assertRaises(h.TerminalFailure):
                host.namespace_observation(lambda path,cap:raw if path=='/proc/1/status' else read(path,cap),link)
    def test_cache_baseline_exact(self):self.assertEqual(set(host.parse_loader_cache(cache())),set(host.HOST_POLICY['allowed_libraries']))
    def test_cache_malformed_endian_offsets_missing_stop(self):
        bad=[b'old-cache',cache()[:60],cache([])]
        x=bytearray(cache());x[28]=3;bad.append(bytes(x))
        x=bytearray(cache());struct.pack_into('<I',x,52,1);bad.append(bytes(x))
        for raw in bad:
            with self.assertRaises(h.TerminalFailure):host.parse_loader_cache(raw)
    def test_relevant_hwcap_and_ambiguity_stop(self):
        rows=[(name,'/lib/x86_64-linux-gnu/'+name,0) for name in host.HOST_POLICY['allowed_libraries']]
        for extra in [(rows[0][0],rows[0][1],1<<62),(rows[0][0],'/usr/lib/x86_64-linux-gnu/'+rows[0][0],0)]:
            with self.assertRaises(h.TerminalFailure):host.parse_loader_cache(cache(rows+[extra]))
    def test_cpu_policy_is_baseline_not_every_optional_variant(self):
        self.assertEqual(host.HOST_POLICY['cpu_flags'],['sse2']);self.assertEqual(host.HOST_POLICY['optional_cpu_backends'],'upstream-dynamic-selection')

class PublicTests(unittest.TestCase):
    def sources(self):return {row:'invented mechanical fixture' for row in h.ROW_IDS}
    def output(self,observations=None,**kw):
        return exports.build_public(self.sources(),observations or {},consumed_http=kw.get('consumed',0),
            validated_http=kw.get('validated',0),accounting_confirmed=True,status='incomplete')
    def test_all_rows_and_calls_present_even_without_outputs(self):
        result=self.output();self.assertEqual(len(result['sources.json']['rows']),88)
        self.assertEqual(len(result['translations.json']['records']),176);self.assertEqual(len(result['accounting.json']['calls']),442)
        self.assertEqual({r['state'] for r in result['translations.json']['records']},{'unobserved'})
    def test_failed_and_later_unissued_calls(self):
        result=self.output({h.SCHEDULE[0]:dict(status='operational_failure',failure='/secret/path token=secret')},consumed=179,validated=178)
        states=[c['state'] for c in result['accounting.json']['calls']]
        self.assertEqual(states[178:180],['consumed_unvalidated','unissued'])
        self.assertNotIn('secret',json.dumps(result));self.assertEqual(result['translations.json']['records'][0]['state'],'operational_failure')
    def test_unknown_accounting_never_becomes_zero(self):
        result=exports.build_public(self.sources(),{},consumed_http=None,validated_http=None,accounting_confirmed=False,status='incomplete')
        self.assertEqual({c['state'] for c in result['accounting.json']['calls']},{'unknown'})
        self.assertIsNone(result['accounting.json']['consumed_http'])
    def test_success_allowlist_discards_raw_extras(self):
        item=dict(status='observed',output='synthetic translation',usage=dict(prompt_tokens=20,completion_tokens=3,total_tokens=23,
            prompt_tokens_details={'cached_tokens':0},secret='CANARY'),flags=[],total_ns=123,headers='CANARY',raw_env='CANARY',path='CANARY')
        result=self.output({h.SCHEDULE[0]:item});self.assertNotIn('CANARY',json.dumps(result))
        self.assertEqual(result['translations.json']['records'][0]['text'],'synthetic translation')
    def test_empty_and_length_remain_scoreable(self):
        item=dict(status='observed',output='',usage=dict(prompt_tokens=20,completion_tokens=0,total_tokens=20,
            prompt_tokens_details={'cached_tokens':0}),flags=['empty_output','length_finish','integrity_rejection'],total_ns=5)
        self.assertEqual(len(self.output({h.SCHEDULE[0]:item})['translations.json']['records'][0]['generation_failure_flags']),3)
    def test_raw_resources_and_exception_terminal_rejected(self):
        with self.assertRaises(h.TerminalFailure):exports.build_public(self.sources(),{},consumed_http=0,validated_http=0,
            accounting_confirmed=True,status='incomplete',resource_metrics={'raw_host':'CANARY'})
        self.assertNotIn('CANARY',json.dumps(exports.safe_terminal(dict(status='incomplete',failure='CANARY',unresolved=['CANARY']))))
    def test_no_guaranteed_blinding_and_public_manifest(self):
        result=self.output();self.assertFalse(result['manifest.json']['guaranteed_treatment_blinding'])
        self.assertTrue(result['manifest.json']['treatment_identities_public'])
        for entry in result['manifest.json']['files']:self.assertEqual(entry['sha256'],h.digest(h.canonical(result[entry['name']])))
    def test_reconciled_cost_and_numeric_components_are_closed(self):
        rows=[dict(id=row,active=row in h.ELIGIBLE_IDS,complete=True,baseline=1.,candidate=1.1) for row in h.ROW_IDS]
        cost=h.paired_cost(rows,1e-9);cost['status']='inconclusive_pending_order_and_noise_review';cost['secret']='CANARY'
        protocol=dict(status='validated_complete_protocol_evidence',cost=cost,tokens=dict(count_only_requests=264,
            count_only_input_tokens=5280,generation_prompt_tokens=3520,generated_tokens=176,secret='CANARY'),secret='CANARY')
        item=dict(status='observed',output='fixture',usage=dict(prompt_tokens=20,completion_tokens=1,total_tokens=21,
            prompt_tokens_details={'cached_tokens':0}),flags=[],total_ns=100,components=dict(token_counter_ns=[2,3],
            renderer_ns=8,construction_ns=0,completion_ns=80,integrity_ns=4,secret='CANARY'))
        result=exports.build_public(self.sources(),{pair:deepcopy(item) for pair in h.SCHEDULE},consumed_http=442,validated_http=442,
            accounting_confirmed=True,status='complete',protocol=protocol,
            resource_metrics=dict(helper_peak_rss_bytes=20*h.MIB,helper_render_p95_ns=1000))
        selected=result['metrics.json']['reconciled_protocol']
        self.assertEqual(set(selected['row_ratio_groups']),{'all_new','active_new','all_rows','all_active'})
        self.assertEqual({k:v['n'] for k,v in selected['order_strata'].items()},{'AB':44,'BA':44})
        self.assertEqual(result['metrics.json']['raw_arm_timings'][0]['components']['token_counter_ns'],[2,3])
        self.assertNotIn('CANARY',json.dumps(result))
    def test_public_scientific_protocol_carries_unchanged_gates(self):
        text=(Path(__file__).parent/'SCIENTIFIC_PROTOCOL.md').read_text()
        for fragment in ('179908ab59331b8fac13b8248d0849832b06beccf9236aba2ee43dbb6f0e84fc',
            '≥2 qualifying fixes on ≥2 distinct headwords','zero new','across ALL 88 rows','≥18/24',
            '≥8/12','Material\nuncertainty','median and P95 ≤1.25','nearest rank'):
            self.assertIn(fragment,text)
    def test_preflight_publication_precedes_seal_and_has_no_outputs(self):
        from test_cpu_harness import plans
        records=[];ledger=coordinator.KitLedger(lambda event:None,lambda items:records.append(exports.preflight_receipt(items,'1'*64,'2'*64)))
        ledger.total=178;ledger.seal_preflight(plans())
        self.assertTrue(ledger.preflight_sealed);self.assertEqual(len(records),1)
        self.assertEqual(records[0]['measured_completions_before_receipt'],0)
        self.assertEqual(records[0]['coverage_status'],'pass');self.assertEqual(len(records[0]['rows']),88)
        self.assertEqual(records[0]['coverage']['active_contrasts'],24)
        self.assertNotIn('source',records[0]['rows'][0]);self.assertNotIn('output',records[0]['rows'][0])
    def test_partial_preflight_cannot_publish_completed_receipt(self):
        from test_cpu_harness import plans
        with self.assertRaises(h.TerminalFailure):exports.preflight_receipt(plans()[:-1],'1'*64,'2'*64)
    def test_coverage_failure_published_then_blocks_generation(self):
        from test_cpu_harness import plans
        from dataclasses import replace
        records=[];items=[replace(plan,active=False) for plan in plans()]
        ledger=coordinator.KitLedger(lambda event:None,lambda items:records.append(exports.preflight_receipt(items,'1'*64,'2'*64)))
        ledger.total=178
        with self.assertRaises(h.TerminalFailure):ledger.seal_preflight(items)
        self.assertEqual(records[0]['coverage_status'],'fail');self.assertFalse(ledger.preflight_sealed)
        with self.assertRaises(h.TerminalFailure):ledger.consume('completion',*h.SCHEDULE[0])
    def test_preflight_publication_failure_blocks_seal(self):
        from test_cpu_harness import plans
        def fail(items):raise h.TerminalFailure('synthetic output failure')
        ledger=coordinator.KitLedger(lambda event:None,fail);ledger.total=178
        with self.assertRaises(h.TerminalFailure):ledger.seal_preflight(plans())
        self.assertFalse(ledger.preflight_sealed)
    def budget_fallback_plans(self,number):
        from test_cpu_harness import plans,source_for,ALIAS,LEXICON,LEXICON_SHA,fake_count
        import frozen_renderer
        rows=plans();changed=0
        for i,plan in enumerate(rows):
            if plan.row_id.startswith('N') and int(plan.row_id[1:])<=36 and int(plan.row_id[1:])%3!=0 and changed<number:
                rows[i]=h.preflight_pair(plan.row_id,source_for(plan.row_id),ALIAS,LEXICON,LEXICON_SHA,frozen_renderer,
                    lambda body:380 if fake_count(body)==20 else 390)
                self.assertFalse(rows[i].active);self.assertEqual(rows[i].reason,'token_budget');changed+=1
        return rows
    def test_valid_overbudget_provisional_receipt_keeps_passing_coverage(self):
        rows=self.budget_fallback_plans(1);receipt=exports.preflight_receipt(rows,'1'*64,'2'*64)
        self.assertEqual(receipt['coverage_status'],'pass');self.assertEqual(receipt['coverage']['active_contrasts'],23)
        counts=receipt['rows'][0]['requests']
        self.assertEqual([counts[k]['input_tokens'] for k in ('baseline','provisional','candidate')],[380,390,380])
        records=[];ledger=coordinator.KitLedger(lambda event:None,lambda items:records.append(exports.preflight_receipt(items,'1'*64,'2'*64)))
        ledger.total=178;ledger.seal_preflight(rows);self.assertTrue(ledger.preflight_sealed)
    def test_budget_fallback_coverage_failure_is_reported_and_stops(self):
        rows=self.budget_fallback_plans(7);records=[]
        ledger=coordinator.KitLedger(lambda event:None,lambda items:records.append(exports.preflight_receipt(items,'1'*64,'2'*64)))
        ledger.total=178
        with self.assertRaises(h.TerminalFailure):ledger.seal_preflight(rows)
        self.assertEqual(records[0]['coverage_status'],'fail');self.assertEqual(records[0]['coverage']['active_contrasts'],17)
        self.assertFalse(ledger.preflight_sealed);self.assertIsNotNone(ledger.terminal)
    def test_claim_only_charged_no_key(self):
        evidence=runtime.EvidenceFiles('/fake',initial_claim_size=100)
        self.assertEqual(evidence.budget.retained,100)
        with self.assertRaises(h.TerminalFailure):runtime.EvidenceFiles('/fake',initial_claim_size=100,initial_arm_key_size=1)

if __name__=='__main__':unittest.main()
