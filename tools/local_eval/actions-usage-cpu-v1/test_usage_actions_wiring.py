"""Source-only admission/routing tests. All native operations are replaced.

Synthetic SHA/UUID/path fixtures below are test data, never release bindings.
No bootstrap entry, child, pipe, socket, model, tokenizer, or claim is executed.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import actions_policy as policy
import activation_scope
import verified_bootstrap


def synthetic_provider():
    a,b,parent='a'*40,'b'*40,'c'*40
    return dict(repository=policy.REPOSITORY,ref='refs/heads/'+policy.BRANCH,event_name='push',
        private=False,created=False,deleted=False,forced=False,before=a,after=b,head_commit=b,
        source_parent=parent,checkout_head=b,checkout_parent=a,source_a_parent=parent,
        changed_at_b=[policy.WORKFLOW],run_id='12345',run_attempt=1,
        workflow_ref=policy.REPOSITORY+'/'+policy.WORKFLOW+'@refs/heads/'+policy.BRANCH,
        workflow_sha=b,runner_environment='github-hosted',runner_os='Linux',runner_arch='X64',
        runner_label='ubuntu-24.04',image_os='ubuntu24',image_version='20261001.1.0',
        job_id='usage',job_container=None,container_steps=[],namespace_wrappers=[])


def synthetic_metadata():
    return dict(source_parent='c'*40,attempt_id='11111111111141118111111111111111',
        commitments={'test_only':'d'*64})


def synthetic_roots():
    return dict(workspace='/synthetic/workspace',source='/synthetic/workspace/'+policy.PROJECT,
        runner_temp='/synthetic/temp',state='/synthetic/temp/'+policy.STATE_NAME,
        output='/synthetic/temp/'+policy.STATE_NAME+'/attempt')


class AdmissionTests(unittest.TestCase):
    def test_exact_new_identity_and_original_branch(self):
        b=synthetic_provider()
        self.assertTrue(policy.validate_provider(b,source_a=b['before'],source_parent=b['source_parent']))
        self.assertEqual(policy.BRANCH,'experiment/luna-actions-lexical-20261005')
        self.assertEqual(policy.PROJECT,'tools/local_eval/actions-usage-cpu-v1')
        self.assertEqual(policy.WORKFLOW,'.github/workflows/luna-usage-cpu-v1.yml')
        self.assertEqual(policy.STATE_NAME,'luna-usage-cpu-20261006-v1')

    def test_provider_scope_changes_fail(self):
        wrong={'repository':'unreviewed/repository','ref':'refs/heads/main','event_name':'workflow_dispatch',
            'private':True,'created':True,'deleted':True,'forced':True,'before':'d'*40,
            'checkout_parent':'d'*40,'source_a_parent':'d'*40,'checkout_head':'d'*40,
            'workflow_sha':'d'*40,'changed_at_b':[policy.WORKFLOW,'extra.py'],'run_attempt':2,
            'runner_environment':'self-hosted','runner_os':'Windows','runner_arch':'ARM64',
            'runner_label':'ubuntu-latest','image_os':'ubuntu22','job_id':'sense',
            'job_container':{},'container_steps':['container'],'namespace_wrappers':['unshare']}
        for key,value in wrong.items():
            with self.subTest(key=key):
                b=synthetic_provider();b[key]=value
                with self.assertRaises(policy.PolicyError):
                    policy.validate_provider(b,source_a='a'*40,source_parent='c'*40)

    def test_unresolved_release_bindings_fail(self):
        self.assertTrue(policy.validate_release_metadata(synthetic_metadata()))
        for key,value in [('source_parent','__REVIEWED_SOURCE_PARENT__'),
                          ('attempt_id','__REVIEWED_ATTEMPT_UUID_V4__'),
                          ('commitments',{'test_only':'__REVIEWED_COMMITMENT__'})]:
            with self.subTest(key=key):
                data=synthetic_metadata();data[key]=value
                with self.assertRaises(policy.PolicyError):policy.validate_release_metadata(data)
        with self.assertRaises(policy.PolicyError):policy.validate_provider(synthetic_provider())

    def test_host_image_version_is_observed_without_prior_pin(self):
        for version in ('20261001.1.0','20261002.1.0'):
            provider=synthetic_provider();provider['image_version']=version
            self.assertTrue(policy.validate_provider(provider,source_a='a'*40,source_parent='c'*40))
        provider=synthetic_provider();provider['image_version']=''
        with self.assertRaises(policy.PolicyError):
            policy.validate_provider(provider,source_a='a'*40,source_parent='c'*40)
        self.assertEqual(set(synthetic_metadata()),{'source_parent','attempt_id','commitments'})

    def test_fixed_roots_and_direct_owner(self):
        roots=synthetic_roots();manifest='d'*64
        self.assertEqual(str(policy.validate_roots(roots)['source']),roots['source'])
        argv=['/usr/bin/python3','-I','-B',roots['source']+'/verified_bootstrap.py',
              roots['source']+'/KIT_MANIFEST.json',manifest,'actions','unused']
        self.assertTrue(activation_scope.validate_owner_argv(argv,roots,manifest))
        for index,value in ((0,'python3'),(2,'-S'),(3,'/other/verified_bootstrap.py'),(6,'helper')):
            bad=list(argv);bad[index]=value
            with self.assertRaises(activation_scope.Denied):activation_scope.validate_owner_argv(bad,roots,manifest)
        bad=dict(roots);bad['state']='/synthetic/temp/luna-sense-cpu-20261005-v5'
        with self.assertRaises(policy.PolicyError):policy.validate_roots(bad)

    def test_unadmitted_import_cannot_release_native_role(self):
        self.assertEqual(activation_scope.ROLES,('actions','acquire','validate'))
        with self.assertRaises(activation_scope.Denied):activation_scope.require_role('actions')
        with self.assertRaises(activation_scope.Denied):activation_scope.require_actions_guard()

    def test_bootstrap_verifies_new_module_closure(self):
        required={'usage_runner_core','usage_runtime_inventory','usage_public_exports','usage_native_adapter',
                  'usage_worker_packets','usage_helper_bridge','usage_worker_entry'}
        self.assertTrue(required<=set(verified_bootstrap.MODULE_ORDER))
        self.assertFalse({'public_exports','isolated_helper'}&set(verified_bootstrap.MODULE_ORDER))
        payloads={name+'.py':b'"synthetic unexecuted source"\n' for name in verified_bootstrap.MODULE_ORDER}
        manifest={'files':[dict(path=name,bytes=len(raw),sha256=sha256(raw).hexdigest()) for name,raw in payloads.items()]}
        raw=json.dumps(manifest).encode();digest=sha256(raw).hexdigest()
        self.assertEqual(len(verified_bootstrap.verify_payloads(raw,digest,payloads)),len(payloads))
        missing=dict(payloads);missing.pop('usage_native_adapter.py')
        with self.assertRaises(ValueError):verified_bootstrap.verify_payloads(raw,digest,missing)
        changed=dict(payloads);changed['usage_worker_packets.py']+=b'# mutation'
        with self.assertRaises(ValueError):verified_bootstrap.verify_payloads(raw,digest,changed)

    def test_workflow_is_source_template_and_fixed_one_shot(self):
        root=Path(__file__).resolve().parent
        template=(root/'WORKFLOW_TEMPLATE.yml.in').read_text()
        self.assertIn("branches: ['experiment/luna-actions-lexical-20261005']",template)
        self.assertIn("paths: ['.github/workflows/luna-usage-cpu-v1.yml']",template)
        for literal in ('timeout-minutes: 30','runs-on: ubuntu-24.04','github.run_attempt == 1',
                        "LUNA_SOURCE_COMMIT: '__REVIEWED_SOURCE_COMMIT_A__'",'persist-credentials: false',
                        '"$GITHUB_WORKSPACE/$LUNA_PROJECT/verified_bootstrap.py"'):
            self.assertIn(literal,template)
        for denied in ('workflow_dispatch:','schedule:','container:','actions/upload-artifact','actions/cache'):
            self.assertNotIn(denied,template)
        self.assertFalse((root/'.github/workflows/luna-usage-cpu-v1.yml').exists())


class RoutingTests(unittest.TestCase):
    def test_preflight_publication_requires_all_counts_and_no_completion(self):
        import final_coordinator as coordinator
        ledger=SimpleNamespace(total=176,terminal=None,preflight_sealed=False,counts={'completion':0})
        owner=SimpleNamespace(check=Mock(),usage_hooks=SimpleNamespace(ledger=ledger),
            usage_core=object(),usage_inventory=object(),evidence=Mock(),
            plan=dict(component_manifest_sha256='d'*64,commitments={'source_plan':'e'*64}))
        stream=SimpleNamespace(buffer=Mock())
        with patch.object(coordinator.runtime,'require_activation'), \
             patch.object(coordinator.public_exports,'preflight_receipt',return_value={'completion_count':0}), \
             patch.object(coordinator.sys,'stdout',stream):
            coordinator.KitSupervisor.publish_preflight(owner,[])
            self.assertTrue(stream.buffer.write.call_args.args[0].startswith(b'LUNA_PREFLIGHT_JSON '))
            self.assertFalse(ledger.preflight_sealed)
            for count,completion,sealed in ((175,0,False),(177,1,False),(176,0,True)):
                ledger.total=count;ledger.counts={'completion':completion};ledger.preflight_sealed=sealed
                with self.assertRaises(coordinator.h.TerminalFailure):
                    coordinator.KitSupervisor.publish_preflight(owner,[])

    def test_controller_does_not_accept_cancelled_success(self):
        from attempt_control import AttemptControl
        control=AttemptControl(now=lambda:10.)
        control.worker=Mock();control.worker.is_alive.return_value=False
        control.result=dict(status='operationally_complete',cleanup_confirmed=True,protocol_complete=True)
        control.expired('synthetic unknown spawn')
        control.done.set()
        result=control.poll()
        self.assertEqual(result['status'],'incomplete')
        self.assertFalse(result['cleanup_confirmed'])
        self.assertFalse(result['protocol_complete'])
        control.worker.join.assert_called_once_with(timeout=0)

    def test_plan_and_worker_admission_bind_same_attempt(self):
        import actions_entry
        import final_coordinator as coordinator
        h=coordinator.h
        roots=synthetic_roots();metadata=synthetic_metadata();manifest='d'*64
        metadata['commitments']={key:'e'*64 for key in set(h.CLAIM_EXTRA_HASHES)-
            {'harness_manifest','output_schemas','output_binding_revision'}}
        argv=['/usr/bin/python3','-I','-B',roots['source']+'/verified_bootstrap.py',
              roots['source']+'/KIT_MANIFEST.json',manifest,'actions','unused']
        with patch.object(coordinator,'KIT_CONTRACT_SHA256','f'*64):
            plan=actions_entry.assemble_plan(roots,synthetic_provider(),metadata,manifest,'/usr/bin/python3.12',
                coordinator_identity=dict(coordinator_pid=12345,coordinator_argv=argv))
            self.assertTrue(coordinator.validate_kit_plan(plan,manifest))
        args=dict(mode='acquire',argument=roots['state']+'/ONE_SHOT_CPU_ATTEMPT.json',manifest_sha=manifest,
            source_root=roots['source'],parent_pid=12345,parent_argv=argv,parent_exe='/usr/bin/python3.12',
            self_exe='/usr/bin/python3.12',cwd=roots['output'],now=1.)
        self.assertTrue(activation_scope.validate_worker_plan(plan,**args))
        for key,value in [('parent_pid',12346),('parent_argv',argv[:-1]+['changed']),
                          ('self_exe','/usr/bin/other'),('cwd','/synthetic/other'),
                          ('now',1475.),('mode','helper'),('argument','/synthetic/other')]:
            with self.subTest(key=key):
                bad={**args,key:value}
                with self.assertRaises(activation_scope.Denied):activation_scope.validate_worker_plan(plan,**bad)
        self.assertEqual(plan['limits']['pairs'],87)
        self.assertEqual(len(plan['eligibility']),24)

    def test_coordinator_routes_new_stage_and_never_legacy_rows(self):
        import final_coordinator as coordinator
        owner=Mock();owner.diagnostic=None
        evidence=Mock();control=object();core=object();inventory=object();bank=b'synthetic-bank'
        hooks=SimpleNamespace(ledger=SimpleNamespace(total=398))
        plan=dict(attempt_id='synthetic',alias='synthetic',component_manifest_sha256='d'*64,
            preclaim_host_evidence={},paths=dict(acquisition='/synthetic/staging',extraction='/synthetic/runtime',
            output='/synthetic/output'),host_compatibility={'archive_library_dirs':['llama-b11349']},
            absolute_python='/usr/bin/python3',coordinator_argv=['synthetic-owner'],port=18080)
        manifest=b'{}'
        validated=dict(member_manifest_sha256=coordinator.h.digest(manifest),runtime=dict(
            server='/synthetic/runtime/server',library_dirs=['/synthetic/runtime/llama-b11349']))
        worker=Mock(side_effect=[{'synthetic_acquisition':True},validated])
        lifecycle=dict(active_work_ns=1000,worker_cpu_ns=100,lifetime_ns=2000,startup_ns=100,
                       finish_ns=100,commands=224,parent_setup_ns=50,parent_setup_cpu_ns=10)
        result=dict(helper=dict(peak_rss_bytes=100,render_ns={'p95':10},lifecycle=lifecycle),totals={'synthetic_total':174})
        reconcile=dict(status='validated_complete_protocol_evidence',cost={'status':'inconclusive'})
        def bounded(path,cap):
            return b'build 11349, commit fb4b2737a' if str(path).endswith('version.log') else manifest
        with patch.object(coordinator.runtime,'require_activation'), \
             patch.object(coordinator.os,'mkdir') as mkdir, \
             patch.object(coordinator,'run_worker',worker), \
             patch.object(coordinator,'wait_owned') as wait_owned, \
             patch.object(coordinator.runtime,'bounded_file',side_effect=bounded), \
             patch.object(coordinator.runtime,'pinned_file',return_value=b'synthetic-template'), \
             patch.object(coordinator,'recheck_launch_resources',return_value={}), \
             patch.object(coordinator.usage_runtime_inventory,'load',return_value=(core,inventory,bank)), \
             patch.object(coordinator.usage_worker_packets,'create_worker_packet_factory',return_value='factory') as factory, \
             patch.object(coordinator.usage_native_adapter,'bind_native_hooks',return_value=hooks) as bind, \
             patch.object(coordinator.usage_native_adapter,'generation_stage',return_value=(result,reconcile)) as generation, \
             patch.object(coordinator.h,'server_spec',return_value={'env':{}}), \
             patch.object(coordinator.runtime,'load_source_only_rows',side_effect=AssertionError('legacy rows')), \
             patch.object(coordinator.runtime,'execute_generation_stage',side_effect=AssertionError('legacy stage')):
            actual=coordinator.run_stages(plan,owner,evidence,object(),ValueError,object(),control)
        self.assertEqual(actual,dict(protocol_complete=True,semantic_quality_claim=None))
        self.assertEqual([call.args[2] for call in worker.call_args_list],['acquire','validate'])
        self.assertEqual([call.args[0] for call in owner.launch.call_args_list],['version','server'])
        self.assertIs(bind.call_args.args[3],control)
        self.assertEqual(bind.call_args.args[7],'factory')
        self.assertNotIn('source_paths',factory.call_args.kwargs)
        self.assertNotIn('source_pins',factory.call_args.kwargs)
        self.assertEqual(generation.call_args.args[:4],(core,inventory,'synthetic',bank))
        self.assertIs(owner.usage_hooks,hooks)
        self.assertIs(owner.public_reconciliation,reconcile)
        self.assertEqual(owner.public_helper_lifecycle,lifecycle)
        self.assertEqual(mkdir.call_args.args,('/synthetic/staging',448))

    def test_missing_stage_ledger_keeps_public_counters_unknown(self):
        import final_coordinator as coordinator
        owner=SimpleNamespace(usage_hooks=SimpleNamespace(),peak_runner_rss=0,peak_server_rss=0,diagnostic=None)
        evidence=SimpleNamespace(file_bytes={})
        inventory=SimpleNamespace(sources={'synthetic':'source'},request_total=398)
        with patch.object(coordinator.runtime,'require_activation'), \
             patch.object(coordinator.runtime,'persistence_checkpoint'), \
             patch.object(coordinator.usage_runtime_inventory,'load',return_value=(object(),inventory,b'bank')), \
             patch.object(coordinator.public_exports,'build_public',return_value={}) as project, \
             patch.object(coordinator.os,'mkdir'):
            coordinator.emit_public_snapshot({'paths':{'output':'/synthetic/output'}},owner,evidence,False)
        self.assertFalse(project.call_args.kwargs['accounting_confirmed'])
        self.assertIsNone(project.call_args.kwargs['consumed_http'])
        self.assertIsNone(project.call_args.kwargs['validated_http'])


if __name__=='__main__':unittest.main()
