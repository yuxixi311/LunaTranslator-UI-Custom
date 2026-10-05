"""Inert grant/denial tests. No source bootstrap, host probe or worker is run."""
from contextlib import ExitStack,contextmanager
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import activation_scope as scope
import actions_entry as entry
import cpu_harness as h
import final_coordinator as coordinator
import guarded_runtime as runtime
import isolated_helper
import kit_worker
import verified_bootstrap as bootstrap
from test_actions_wrapper import binding,metadata,roots,owner_identity

SHA='1'*64

def plan():return entry.assemble_plan(roots(),binding(),metadata(),SHA,'/fake/python',coordinator_identity=owner_identity())

def forbidden(*args,**kwargs):raise AssertionError('native effect reached')

@contextmanager
def invocation(mode='actions',argument='unused',pid=77):
    context=dict(mode=mode,manifest_sha=SHA,source_root=roots()['source'],argument=argument,pid=pid)
    with patch.dict(scope.__dict__,{'_BOOTSTRAP_INVOCATION':context,'_VERIFIED_BOOTSTRAP_SHA':SHA,'_GRANT':None}),\
         patch.object(scope.os,'getpid',lambda:pid):
        yield context


def observations(mode='acquire'):
    p=plan();argument=p['paths']['output']+'/helper_input.json' if mode=='helper' else p['paths']['claim_root']+'/ONE_SHOT_CPU_ATTEMPT.json'
    return dict(mode=mode,argument=argument,manifest_sha=SHA,source_root=roots()['source'],parent_pid=42,
        parent_argv=p['coordinator_argv'],parent_exe='/fake/python',self_exe='/fake/python',cwd=roots()['output'],now=10.)


class GrantTests(unittest.TestCase):
    def test_bare_environment_flags_never_grant_runtime(self):
        with patch.dict(os.environ,{'LUNA_ENABLE':'1','APPROVED':'true','EXECUTION_ENABLED':'true','GITHUB_ACTIONS':'true'}),\
             patch.object(scope,'_GRANT',None):
            with self.assertRaises(h.Disabled):runtime.require_activation()
            with self.assertRaises(h.Disabled):isolated_helper.raise_if_not_released()
    def test_matching_service_environment_is_not_a_runtime_grant(self):
        b=binding();env=dict(GITHUB_ACTIONS='true',GITHUB_RUN_ATTEMPT='1',LUNA_MANIFEST_SHA=SHA,
            GITHUB_REPOSITORY=b['repository'],GITHUB_REF=b['ref'],GITHUB_SHA=b['after'],
            LUNA_SOURCE_COMMIT=b['before'],GITHUB_WORKFLOW_SHA=b['workflow_sha'],GITHUB_WORKFLOW_REF=b['workflow_ref'],
            RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',RUNNER_ARCH='X64',ImageOS='ubuntu24',ImageVersion='20261004.1')
        with patch.dict(os.environ,env),patch.object(scope,'_GRANT',None):
            with self.assertRaises(h.Disabled):runtime.require_activation()
            with self.assertRaises(h.Disabled):isolated_helper.raise_if_not_released()
    def test_source_read_gate_is_distinct_from_runtime(self):
        with invocation():
            self.assertEqual(scope.require_actions_guard()['mode'],'actions')
            with self.assertRaises(h.Disabled):runtime.require_activation()
    def test_missing_bootstrap_blocks_source_guard_before_read(self):
        with patch.dict(scope.__dict__,{'_BOOTSTRAP_INVOCATION':None,'_GRANT':None}),\
             patch.object(scope.os,'open',forbidden):
            with self.assertRaises(scope.Denied):scope.read_guard_file('/fake',100)
            with self.assertRaises(scope.Denied):scope.accept_actions(binding(),metadata(),roots(),SHA)
    def test_source_guard_failure_cannot_install_release(self):
        def failed(*args):raise h.TerminalFailure('synthetic source mismatch')
        with invocation(),patch.object(entry,'inspect_source',failed),patch.object(scope,'accept_actions',forbidden):
            with self.assertRaises(h.TerminalFailure):entry.main(SHA)
    def test_process_or_manifest_marker_drift_rejected(self):
        with invocation() as context:
            for key,value in [('pid',88),('manifest_sha','2'*64),('mode','coordinator')]:
                original=context[key];context[key]=value
                with self.assertRaises(scope.Denied):scope.require_actions_guard()
                context[key]=original
    def test_owner_grant_uses_structured_reviewed_process_argv(self):
        raw=('\0'.join(owner_identity()['coordinator_argv'])+'\0').encode()
        with invocation(pid=42),patch.object(scope,'read_guard_file',lambda path,cap:raw):
            scope.accept_actions(binding(),metadata(),roots(),SHA)
            self.assertEqual(scope.owner_identity(),owner_identity());self.assertEqual(runtime.require_activation()['role'],'actions')
            with self.assertRaises(scope.Denied):scope.require_actions_guard()
    def test_bad_event_cannot_grant_even_with_bootstrap(self):
        wrong=binding();wrong['run_attempt']=2
        with invocation(),patch.object(scope,'read_guard_file',forbidden):
            with self.assertRaises(ValueError):scope.accept_actions(wrong,metadata(),roots(),SHA)
            with self.assertRaises(h.Disabled):runtime.require_activation()
    def test_boolean_or_wrong_role_grant_rejected(self):
        with invocation(),patch.object(scope,'_GRANT',True):
            with self.assertRaises(scope.Denied):scope.require_role('actions')
        with invocation(),patch.object(scope,'_GRANT',dict(role='helper',pid=77,manifest_sha=SHA,source_root=roots()['source'])):
            with self.assertRaises(h.Disabled):runtime.require_activation()
    def test_native_permission_is_bound_to_current_process(self):
        with invocation(),patch.object(scope,'_GRANT',dict(role='actions',pid=78,manifest_sha=SHA,source_root=roots()['source'])):
            with self.assertRaises(h.Disabled):runtime.require_activation()
    def test_generic_claim_and_runner_stay_disabled_after_owner_grant(self):
        raw=('\0'.join(owner_identity()['coordinator_argv'])+'\0').encode()
        with invocation(pid=42),patch.object(scope,'read_guard_file',lambda path,cap:raw):
            scope.accept_actions(binding(),metadata(),roots(),SHA)
            for operation in (lambda:h.run_real(approved=True),lambda:runtime.claim_once({}),runtime.main,isolated_helper.raise_if_not_released):
                with self.assertRaises(h.Disabled):operation()


class WorkerTests(unittest.TestCase):
    def test_three_exact_owned_roles(self):
        for mode in ('acquire','validate','helper'):
            self.assertTrue(scope.validate_worker_plan(plan(),**observations(mode)))
    def test_worker_wrong_parent_executable_cwd_or_manifest_stops(self):
        mutations={'parent_pid':43,'parent_exe':'/other/python','self_exe':'/other/python','cwd':'/other',
            'manifest_sha':'2'*64,'source_root':'/other','argument':'/other/ONE_SHOT_CPU_ATTEMPT.json','mode':'coordinator',
            'now':1475.}
        for key,value in mutations.items():
            o=observations();o[key]=value
            with self.subTest(key=key),self.assertRaises((scope.Denied,h.TerminalFailure)):scope.validate_worker_plan(plan(),**o)
    def test_substring_parent_command_never_suffices(self):
        for argv in (['prefix']+owner_identity()['coordinator_argv'],owner_identity()['coordinator_argv']+['extra'],
                     [*owner_identity()['coordinator_argv'][:6],'acquire','unused']):
            o=observations();o['parent_argv']=argv
            with self.assertRaises(scope.Denied):scope.validate_worker_plan(plan(),**o)
    def test_worker_cannot_substitute_alternate_plan_or_limits(self):
        for key,value in [('execution_policy','true'),('coordinator_pid',True),('sampling',{}),('pins',{}),('limits',{})]:
            p=plan();p[key]=value
            with self.assertRaises((scope.Denied,h.TerminalFailure)):scope.validate_worker_plan(p,**observations())
    def test_helper_cannot_substitute_other_input_or_claim(self):
        for value in (roots()['state']+'/ONE_SHOT_CPU_ATTEMPT.json',roots()['output']+'/other.json'):
            o=observations('helper');o['argument']=value
            with self.assertRaises(scope.Denied):scope.validate_worker_plan(plan(),**o)
    def test_empty_or_unstructured_parent_argv_rejected(self):
        for raw in (b'',b'no-final-nul',b'python\0\0',b'x'*8193+b'\0'):
            with self.assertRaises(scope.Denied):scope.structured_cmdline(raw)
    def test_owned_worker_claim_validation_with_inert_observations(self):
        for mode in ('acquire','validate','helper'):
            p=plan();o=observations(mode);raw=h.canonical(p)
            def fake_read(path,cap):return raw if str(path).endswith('ONE_SHOT_CPU_ATTEMPT.json') else ('\0'.join(p['coordinator_argv'])+'\0').encode()
            def fake_stat(path):return SimpleNamespace(st_uid=1000,st_mode=(0o40700 if str(path)==roots()['state'] else 0o100600),st_nlink=1)
            with invocation(mode,o['argument']),patch.object(scope,'read_guard_file',fake_read),\
                 patch.object(Path,'lstat',fake_stat),patch.object(Path,'resolve',lambda self,**kw:self),\
                 patch.object(scope.os,'geteuid',lambda:1000),patch.object(scope.os,'getppid',lambda:42),\
                 patch.object(scope.os,'readlink',lambda path:'/fake/python'),patch.object(scope.sys,'executable','/fake/python'),\
                 patch.object(scope.os,'getcwd',lambda:roots()['output']),patch.object(scope.time,'monotonic',lambda:10.):
                scope.accept_worker(mode,o['argument'],SHA)
                self.assertEqual(scope.require_role(mode)['claim_sha256'],h.digest(raw))
                with self.assertRaises(scope.Denied):scope.accept_worker(mode,o['argument'],SHA)
                if mode=='helper':
                    self.assertEqual(isolated_helper.raise_if_not_released()['role'],'helper')
                    with self.assertRaises(h.Disabled):runtime.require_activation()
                else:
                    self.assertEqual(runtime.require_activation()['role'],mode)
                    with self.assertRaises(scope.Denied):coordinator.main('',SHA)
    def test_worker_changed_claim_bytes_stop_before_any_stage(self):
        with patch.object(runtime,'require_activation',lambda:None),patch.object(runtime,'bounded_file',lambda *args:b'{}'),\
             patch.object(scope,'require_role',lambda *roles:dict(claim_sha256='0'*64)),\
             patch.object(runtime,'bind_actions_roots',forbidden):
            with self.assertRaises(h.TerminalFailure):kit_worker.main('acquire','/fake',SHA)
    def test_worker_wrong_role_rejected_before_claim_read(self):
        for actual in ('acquire','validate','helper'):
            for requested in ('acquire','validate','helper'):
                if actual==requested:continue
                with invocation(actual,'/fake'),patch.object(Path,'lstat',forbidden):
                    with self.assertRaises(scope.Denied):scope.accept_worker(requested,'/fake',SHA)


class BootstrapTests(unittest.TestCase):
    def test_no_general_coordinator_or_enable_cli(self):
        root=Path(bootstrap.__file__).parent
        for mode in ('coordinator','run','enable','--approved'):
            with patch.object(bootstrap.sys,'argv',[str(root/'verified_bootstrap.py'),str(root/'KIT_MANIFEST.json'),SHA,mode,'unused']):
                with self.assertRaises(RuntimeError):bootstrap.require_bootstrap_activation()
    def test_env_boolean_only_never_produces_runtime_grant(self):
        root=Path(bootstrap.__file__).parent
        with patch.object(bootstrap.sys,'argv',[str(root/'verified_bootstrap.py'),str(root/'KIT_MANIFEST.json'),SHA,'actions','unused']),\
             patch.dict(os.environ,{'LUNA_ENABLE':'true'},clear=True):
            with self.assertRaises(RuntimeError):bootstrap.require_bootstrap_activation()
        with self.assertRaises(h.Disabled):runtime.require_activation()
    def test_helper_import_set_stays_minimal(self):
        self.assertEqual(bootstrap.HELPER_MODULES,('actions_policy','activation_scope','cpu_harness','frozen_renderer','isolated_helper'))
        self.assertFalse(set(bootstrap.HELPER_MODULES)&{'guarded_runtime','acquisition_source','host_validation_source','actions_entry'})
    def test_runtime_guard_not_removed_by_source_read_context(self):
        with invocation(),patch.object(runtime.os,'open',forbidden),patch.object(runtime.subprocess,'Popen',forbidden):
            with self.assertRaises(h.Disabled):runtime.bounded_file('/fake',10)
            with self.assertRaises(h.Disabled):coordinator.main('',SHA)

if __name__=='__main__':unittest.main()
