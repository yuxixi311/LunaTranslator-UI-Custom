"""Activation-only synthetic tests. Real target/network/process work is forbidden."""
import base64
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

g=load('event_guard');a=load('audit_wheels');w=load('actions_audit');b=load('source_bootstrap')

def inventory_sha():return hashlib.sha256((ROOT/'PREPARATION_INVENTORY.json').read_bytes()).hexdigest()

def event_environment():
    env={'LUNA_SOURCE_COMMIT':'a'*40,'GITHUB_SHA':'b'*40,'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'push',
        'GITHUB_REPOSITORY':g.REPOSITORY,'GITHUB_REF':'refs/heads/'+g.BRANCH,'GITHUB_RUN_ATTEMPT':'1',
        'RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','GITHUB_RUN_ID':'1234567',
        'GITHUB_WORKFLOW_REF':g.REPOSITORY+'/'+g.WORKFLOW+'@refs/heads/'+g.BRANCH,'GITHUB_WORKFLOW_SHA':'b'*40,
        'ImageOS':'ubuntu24','ImageVersion':'20261005.1','LUNA_INVENTORY_SHA':inventory_sha()}
    event={'repository':{'full_name':g.REPOSITORY,'private':False},'ref':env['GITHUB_REF'],
        'before':'a'*40,'after':'b'*40,'created':False,'deleted':False,'forced':False,'head_commit':{'id':'b'*40}}
    return event,env

def host():return {'implementation':'CPython','python':'3.12.14','system':'Linux','machine':'x86_64','interpreter':w.INTERPRETER_PIN}

def fake_complete_report(records):
    # Simulated trusted-helper output for wrapper flow tests, not archive evidence.
    report=a.initial_report(records);report.update(status='structurally_complete',phase='finished',cleanup='verified',
        acquired_bytes=sum(r['wheel']['bytes'] for r in records),audited_member_count=3*len(records),audited_uncompressed_bytes=10*len(records))
    for result,record in zip(report['rows'],records):
        result.update(acquisition='verified',audit='verified',facts={
            'integrity':'verified','member_count':3,'record_rows':3,'record_signature_exemptions':0,
            'inventory_sha256':'a'*64,'root_inventory_sha256':'b'*64,'dist_info_root_count':1,'data_root_count':0,
            'layout':{'dist_info_members':3,'dist_info_bytes':10},'relocation':{},'unknown_scheme_sha256':[],
            'member_kinds':{'other_files':3},'scripts':[],'startup':[],'entry_metadata':[],
            'notice_candidates':[],'native_libraries':[],'notice_inventory':'heuristic_nonexhaustive',
            'metadata_version':'2.5','core_metadata_sha256':record['wheel']['core_metadata_sha256'],
            'metadata_field_commitment':'c'*64,'dynamic_count':0,'dependency_count':0,'imports':None,
            'declared_notices':[],'wheel_version':'1.0','root_is_purelib':'true','findings':[]})
    return report

class GuardTests(unittest.TestCase):
    def test_exact_public_event(self):
        event,env=event_environment();binding=g.validate_event(event,env)
        self.assertEqual(binding['source_parent'],'eb9769ceaecdec84acb7882bb4027a3adc545d48')
        self.assertEqual(binding['source_commit'],'a'*40);self.assertEqual(binding['trigger_commit'],'b'*40)
    def test_wrong_event_identity_and_rerun_rejected(self):
        event,env=event_environment()
        for key,value in {'GITHUB_RUN_ATTEMPT':'2','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REPOSITORY':'other/repo',
            'GITHUB_REF':'refs/heads/main','GITHUB_WORKFLOW_SHA':'c'*40,'GITHUB_RUN_ID':'../bad','LUNA_SOURCE_COMMIT':'__REVIEWED_SOURCE_COMMIT_S__',
            'ImageOS':'ubuntu22','RUNNER_ENVIRONMENT':'self-hosted'}.items():
            with self.subTest(key=key),self.assertRaises(ValueError):g.validate_event(event,{**env,key:value})
        for key in ('created','deleted','forced'):
            with self.assertRaises(ValueError):g.validate_event({**event,key:True},env)
        with self.assertRaises(ValueError):g.validate_event({**event,'repository':{'full_name':g.REPOSITORY,'private':True}},env)
    def test_source_inventory_and_six_core_pins(self):
        inv=g.verify_sources(inventory_sha());self.assertEqual(inv['files']['audit_wheels.py']['sha256'],w.HELPER_SHA)
        self.assertEqual(inv['files']['PROTOCOL.md']['sha256'],w.PROTOCOL_SHA)
        self.assertEqual(inv['files']['SOURCE_FREEZE.json']['sha256'],w.FREEZE_SHA)
        self.assertEqual(inv['files']['WHEELS49.frozen.json']['sha256'],a.MANIFEST_SHA256)
        verified=b.verify_sources(ROOT,inventory_sha(),'actions_audit.py');self.assertIn('audit_wheels.py',verified)
        with self.assertRaises(ValueError):b.verify_sources(ROOT,inventory_sha(),'audit_wheels.py')
    def test_workflow_limits_scope_and_pins(self):
        text=(ROOT/'WORKFLOW_TEMPLATE.yml.in').read_text()
        for value in ('timeout-minutes: 20','timeout-minutes: 2','timeout-minutes: 1','timeout-minutes: 16',
            '930s','--kill-after=5s','github.run_attempt == 1','__REVIEWED_SOURCE_COMMIT_S__',g.WORKFLOW,
            w.INTERPRETER_PIN['sha256'],'3d3c42e5aac5ba805825da76410c181273ba90b1','persist-credentials: false'):
            self.assertIn(value,text)
        for value in ('setup-python','workflow_dispatch','schedule:','upload-artifact','actions/cache','secrets.','pip install','ner_entry'):
            self.assertNotIn(value,text)
    def inspection(self,bad=None):
        event,env=event_environment();inv=g.verify_sources(inventory_sha())
        expected={g.SOURCE_DIR+'/'+name for name in inv['files']}|{g.SOURCE_DIR+'/PREPARATION_INVENTORY.json'}
        with tempfile.TemporaryDirectory(prefix='luna-activation-fake-') as directory:
            repo=Path(directory);workflow=repo/g.WORKFLOW;workflow.parent.mkdir(parents=True)
            template=(ROOT/'WORKFLOW_TEMPLATE.yml.in').read_text()
            for key,value in {'__REVIEWED_SOURCE_COMMIT_S__':'a'*40,'__SOURCE_INVENTORY_SHA256__':inventory_sha(),
                '__EVENT_GUARD_SHA256__':inv['files']['event_guard.py']['sha256'],'__SOURCE_BOOTSTRAP_SHA256__':inv['files']['source_bootstrap.py']['sha256']}.items():template=template.replace(key,value)
            workflow.write_text(template+('# fake mutation\n' if bad=='render' else ''))
            event_path=repo/'event.json';event_path.write_text(json.dumps(event));env['GITHUB_EVENT_PATH']=str(event_path)
            responses={('rev-parse','HEAD'):'b'*40,('show','-s','--format=%P','HEAD'):'c'*40 if bad=='trigger_parent' else 'a'*40,
                ('show','-s','--format=%P','a'*40):'c'*40 if bad=='source_parent' else g.SOURCE_PARENT,
                ('diff-tree','--no-commit-id','--name-only','-r','HEAD'):'other.yml' if bad=='workflow' else g.WORKFLOW,
                ('status','--porcelain','--untracked-files=all'):'?? unknown' if bad=='dirty' else '',
                ('ls-tree','-r','--name-only','HEAD','--',g.SOURCE_DIR):'\n'.join(sorted(expected)),
                ('diff-tree','--no-commit-id','--name-only','-r','a'*40):'\n'.join(sorted(expected|({'unreviewed.py'} if bad=='allowlist' else set())))}
            with patch.object(g,'REPO_ROOT',repo),patch.object(g,'git',side_effect=lambda *args:responses[args]):
                return g.inspect_event(env)
    def test_sole_parent_S_T_exact_allowlist_and_render(self):self.inspection()
    def test_wrong_ancestry_allowlist_tree_render_rejected(self):
        for bad in ('trigger_parent','source_parent','workflow','dirty','allowlist','render'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.inspection(bad)
    def test_expected_owned_attempt_only(self):
        with tempfile.TemporaryDirectory(prefix='luna-activation-fake-') as directory:
            root=Path(directory)
            for path in ROOT.iterdir():shutil.copyfile(path,root/path.name)
            (root/'ATTEMPT.json').write_text('{}')
            with self.assertRaises(ValueError):g.verify_sources(inventory_sha(),root=root)
            g.verify_sources(inventory_sha(),root=root,allow_attempt=True)
            (root/'extra.py').write_text('')
            with self.assertRaises(ValueError):g.verify_sources(inventory_sha(),root=root,allow_attempt=True)

class ActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network=patch.object(socket.socket,'connect',side_effect=AssertionError('Real network forbidden'))
        cls.network.start()
    @classmethod
    def tearDownClass(cls):cls.network.stop()
    def fake_flow(self,case=None):
        temporary=tempfile.TemporaryDirectory(prefix='luna-activation-fake-');self.addCleanup(temporary.cleanup)
        base=Path(temporary.name);root=base/'source';root.mkdir()
        for path in ROOT.iterdir():shutil.copyfile(path,root/path.name)
        runner_temp=base/'runner';runner_temp.mkdir();work=runner_temp/g.CLAIM_NAME;work.mkdir()
        event,env=event_environment();event_path=base/'event.json';event_path.write_text(json.dumps(event))
        env.update(GITHUB_EVENT_PATH=str(event_path),RUNNER_TEMP=str(runner_temp),RUNNER_TOOL_CACHE='/PRIVATE_HOST_PATH_SENTINEL')
        binding=g.validate_event(event,env);g.write_exclusive(work/'EVENT_BINDING.json',binding)
        records=a.read_manifest(ROOT/'WHEELS49.frozen.json');calls=[]
        def fake_helper(manifest,output):
            calls.append('helper');report=fake_complete_report(records)
            receipt={'schema':'exact49-attempt-v1','status':report['status'],'failure':None,'manifest_sha256':a.MANIFEST_SHA256,
                'protocol_sha256':w.PROTOCOL_SHA,'helper_sha256':w.HELPER_SHA,'interpreter_sha256':w.INTERPRETER_PIN['sha256'],
                'cleanup':'verified','owner_pid':os.getpid(),'directory_sha256':'d'*64}
            if case=='incomplete':
                report=a.initial_report(records);report.update(phase='acquisition',failure='access_denied',cleanup='verified')
                report['rows'][0].update(acquisition='failed',failure='access_denied');receipt.update(status='incomplete',failure='access_denied')
            if case=='receipt':receipt['helper_sha256']='0'*64
            g.write_exclusive(root/'ATTEMPT.json',receipt)
            if case!='missing':
                if case=='report':report['PRIVATE_PATH_SENTINEL']='PRIVATE_RAW_SECRET'
                g.write_exclusive(output,report)
            if case=='exception':raise RuntimeError('PRIVATE_EXCEPTION_SENTINEL')
            return 1 if case=='incomplete' else 0
        output=io.StringIO();failure=None
        with patch.object(w,'ROOT',root),patch.object(w,'runtime_identity',return_value=(host(),Path('/PRIVATE_HOST_PATH_SENTINEL/python'))),\
             patch.object(w,'clean_runtime_probe',side_effect=ActivationErrorForTest() if case=='runtime' else lambda *args:None),\
             patch.object(a,'run_approved',side_effect=fake_helper),redirect_stdout(output):
            try:code=w.control(inventory_sha(),env)
            except BaseException as error:code=1;failure=error
            with self.assertRaises(w.ActivationError):w.control(inventory_sha(),env)
        return {'code':code,'failure':failure,'output':output.getvalue(),'calls':calls,'work':work,'root':root,'records':records}
    def test_one_helper_call_and_full_bound_frame(self):
        result=self.fake_flow();self.assertEqual(result['code'],0);self.assertEqual(result['calls'],['helper'])
        data=w.decode_frame(result['output'].splitlines());value=json.loads(data)
        self.assertEqual(value['state'],'complete');self.assertEqual(len(value['report']['rows']),49)
        self.assertEqual(value['event']['source_parent'],g.SOURCE_PARENT)
        self.assertEqual(value['bindings']['audit_helper_sha256'],w.HELPER_SHA)
        self.assertEqual(data,(result['work']/'PUBLIC_RESULT.json').read_bytes())
        self.assertNotIn('PRIVATE_',data.decode());self.assertNotIn('.whl',data.decode())
    def test_incomplete_audit_stays_incomplete(self):
        result=self.fake_flow('incomplete');self.assertEqual(result['code'],1)
        value=json.loads(w.decode_frame(result['output'].splitlines()))
        self.assertEqual(value['failure'],{'origin':'audit','code':'access_denied'})
        self.assertEqual(value['report']['rows'][1]['acquisition'],'not_attempted')
    def test_missing_report_is_explicit(self):
        result=self.fake_flow('missing');value=json.loads(w.decode_frame(result['output'].splitlines()))
        self.assertEqual(value['state'],'incomplete');self.assertIsNone(value['report'])
        self.assertEqual(value['failure']['code'],'helper_report_missing')
    def test_unknown_report_fields_never_escape(self):
        result=self.fake_flow('report');value=json.loads(w.decode_frame(result['output'].splitlines()))
        self.assertIsNone(value['report']);self.assertEqual(value['failure']['code'],'helper_report_invalid')
        self.assertNotIn('PRIVATE_RAW_SECRET',result['output'])
    def test_exception_never_escapes(self):
        result=self.fake_flow('exception');value=json.loads(w.decode_frame(result['output'].splitlines()))
        self.assertEqual(value['state'],'incomplete');self.assertNotIn('PRIVATE_EXCEPTION_SENTINEL',result['output'])
    def test_changed_helper_receipt_fails(self):
        result=self.fake_flow('receipt');self.assertEqual(result['code'],1);self.assertIsInstance(result['failure'],w.ActivationError)
    def test_runtime_failure_prevents_helper_claim_and_get(self):
        result=self.fake_flow('runtime');self.assertEqual(result['calls'],[])
        self.assertFalse((result['root']/'ATTEMPT.json').exists());self.assertFalse((result['work']/'RUN_CLAIM.json').exists())
    def test_frame_mutation_and_reordering_rejected(self):
        data,lines=w.frame_lines({'synthetic':'x'*20000});self.assertEqual(w.decode_frame(lines),data)
        changed=[lines[0],lines[2],lines[1],*lines[3:]]
        for bad in (lines[:-1],lines+[lines[-1]],changed,[lines[0],*lines[1:-1],lines[1],lines[-1]]):
            with self.assertRaises(w.ActivationError):w.decode_frame(bad)
    def test_frame_caps(self):
        with self.assertRaises(w.ActivationError):w.frame_lines({'synthetic':'x'*(w.JSON_CAP+1)})
        _,lines=w.frame_lines({'synthetic':'x'*(a.REPORT_CAP)})
        self.assertLessEqual(sum(len(x)+1 for x in lines),w.FRAME_CAP)
    def test_unknown_exception_code_is_closed(self):self.assertEqual(w.ActivationError('PRIVATE_SECRET').code,'internal_error')

    def test_fallback_errors_have_one_bounded_frame(self):
        for error,code in ((w.ActivationError('event_binding_failed'),'event_binding_failed'),(a.PhaseTimeout(),'wrapper_deadline'),(RuntimeError('PRIVATE_SENTINEL'),'internal_error')):
            output=io.StringIO()
            with patch.object(w,'control',side_effect=error),redirect_stdout(output):self.assertEqual(w.main(['--inventory-sha256','0'*64]),1)
            value=json.loads(w.decode_frame(output.getvalue().splitlines()))
            self.assertEqual(value['state'],'incomplete');self.assertIsNone(value['report']);self.assertEqual(value['failure'],code)
            self.assertNotIn('PRIVATE_SENTINEL',output.getvalue())
    def test_partial_frame_never_gets_a_second_frame(self):
        output=io.StringIO()
        def broken_control(sha):
            w._FRAME_STARTED=True
            print(w.PREFIX+'_BEGIN {}')
            raise RuntimeError('PRIVATE_SENTINEL')
        with patch.object(w,'control',side_effect=broken_control),redirect_stdout(output):self.assertEqual(w.main(['--inventory-sha256','0'*64]),1)
        self.assertEqual(output.getvalue().count(w.PREFIX+'_BEGIN'),1)
        self.assertNotIn(w.PREFIX+'_END',output.getvalue())
        with self.assertRaises(w.ActivationError):w.decode_frame(output.getvalue().splitlines())
    def test_helper_report_digest_uses_validated_buffer(self):
        original=g.digest
        def digest(path):
            if Path(path).name=='ARCHIVE_REPORT.json':raise AssertionError('Report must not be read again for hashing')
            return original(path)
        with patch.object(g,'digest',side_effect=digest):result=self.fake_flow()
        self.assertEqual(result['code'],0)
        value=json.loads(w.decode_frame(result['output'].splitlines()))
        raw=(result['work']/'ARCHIVE_REPORT.json').read_bytes()
        self.assertEqual(value['bindings']['helper_report'],{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def test_cached_interpreter_symlink_is_resolved_and_confined(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix='luna-runtime-fake-') as directory:
            cache=Path(directory);runtime=cache/'Python/3.12.14/x64';(runtime/'bin').mkdir(parents=True)
            (runtime.parent/'x64.complete').write_bytes(b'');binary=runtime/'bin/python3.12';binary.write_bytes(b'synthetic binary')
            link=runtime/'bin/python';link.symlink_to('python3.12')
            with patch.object(sys,'base_prefix',str(runtime)),patch.object(sys,'executable',str(link)),patch.object(sys,'flags',SimpleNamespace(isolated=1,no_site=1)),patch.object(g,'digest',return_value=w.INTERPRETER_PIN):
                value,observed=w.runtime_identity({'RUNNER_TOOL_CACHE':str(cache)})
                self.assertEqual(observed,binary);self.assertEqual(value,host())
                outside=cache/'outside';outside.write_bytes(b'synthetic binary');link.unlink();link.symlink_to(outside)
                with self.assertRaises(w.ActivationError):w.runtime_identity({'RUNNER_TOOL_CACHE':str(cache)})
        text=(ROOT/'WORKFLOW_TEMPLATE.yml.in').read_text()
        self.assertEqual(text.count('readlink -f --'),2)
        self.assertEqual(text.count('${runtime_executable%/*}'),2)
    def test_clean_probe_binds_helper_and_full_import_surface(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        commands=[]
        def initialize(process,args,**kwargs):
            commands.append((args,kwargs));process.pid=12345;process.returncode=0;process.stdout=io.BytesIO(b'LUNA_FIXED49_IMPORTS_OK\n');process.wait=Mock(return_value=0)
        watch=SimpleNamespace(deadline=w.time.monotonic()+30,reserve=lambda:None)
        with patch.object(w.subprocess.Popen,'__init__',autospec=True,side_effect=initialize),patch.object(a,'stop_owned',return_value=True):
            w.clean_runtime_probe(Path('/synthetic/python'),Path('/synthetic/work'),watch)
        args,kwargs=commands[0]
        self.assertEqual(args[-3:],[str(ROOT/'audit_wheels.py'),w.HELPER_SHA,str(w.HELPER_BYTES)])
        self.assertEqual(kwargs['env'],w.CLEAN_ENV);self.assertNotIn('LD_LIBRARY_PATH',kwargs['env'])
        self.assertIn("'__name__':'_luna_inert_source_probe'",w.PROBE_CODE)
        self.assertNotIn('run_approved(',w.PROBE_CODE)
    def test_import_failure_in_probe_stops_without_claim(self):
        import builtins
        from types import SimpleNamespace
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name=='ssl':raise ImportError('PRIVATE_MISSING_EXTENSION_SENTINEL')
            return original(name,*args,**kwargs)
        with patch.object(sys,'argv',['-c',str(ROOT/'audit_wheels.py'),w.HELPER_SHA,str(w.HELPER_BYTES)]),patch.object(sys,'flags',SimpleNamespace(isolated=1,no_site=1)),patch.object(builtins,'__import__',side_effect=guarded):
            with self.assertRaises(ImportError):exec(compile(w.PROBE_CODE,'<synthetic-stdlib-probe>','exec'),{})
        self.assertFalse((ROOT/'ATTEMPT.json').exists())

class ActivationErrorForTest(w.ActivationError):
    def __init__(self):super().__init__('runtime_probe_failed')

if __name__=='__main__':unittest.main(verbosity=2)
