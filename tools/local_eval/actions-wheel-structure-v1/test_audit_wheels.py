"""Synthetic-only tests. Network access is disabled even if accidentally invoked."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import stat
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit_wheels',ROOT/'audit_wheels.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):
        super().__init__(data); self.status=status; self.headers=headers or {}

def synthetic(directory,name='demo',version='1.0',extra=None,metadata=None,omit=(),record_mutation=None,foreign=False,compression=zipfile.ZIP_DEFLATED,info_overrides=None):
    base=name.replace('-','_')+'-'+version
    dist=('foreign-9' if foreign else base)+'.dist-info'
    meta=metadata or ('Metadata-Version: 2.5\nName: '+name+'\nVersion: '+version+'\nLicense-File: LICENSE\nImport-Name: '+name.replace('-','_')+'\n\nSynthetic fixture only.\n').encode()
    files={dist+'/METADATA':meta,dist+'/WHEEL':b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',dist+'/licenses/LICENSE':b'Synthetic license fixture.',name.replace('-','_')+'/__init__.py':b'raise RuntimeError("MUST NEVER IMPORT")\n'}
    if extra: files.update(extra)
    for key in omit: files.pop(key,None)
    record=dist+'/RECORD'; lines=[]
    import csv
    out=io.StringIO(newline=''); writer=csv.writer(out)
    for path,data in files.items():
        if path.endswith('/'): continue
        writer.writerow([path,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(),str(len(data))])
    writer.writerow([record,'',''])
    data=out.getvalue().encode()
    if record_mutation: data=record_mutation(data)
    if record not in omit: files[record]=data
    path=Path(directory)/(base+'-py3-none-any.whl')
    with zipfile.ZipFile(path,'w',compression=compression) as archive:
        for member,data in files.items():
            if info_overrides and member in info_overrides:
                info=zipfile.ZipInfo(member); info.compress_type=compression
                info.external_attr=info_overrides[member]<<16
                archive.writestr(info,data)
            else: archive.writestr(member,data)
    raw=path.read_bytes()
    row={'name':name,'version':version,'wheel':{'filename':path.name,'bytes':len(raw),'sha256':a.digest(raw),'core_metadata_sha256':a.digest(meta),'url':'https://files.pythonhosted.org/packages/synthetic/'+path.name}}
    return path,row

class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Any accidental network route fails before creating a socket.
        cls.net=patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden in fake tests'))
        cls.net.start()
    @classmethod
    def tearDownClass(cls): cls.net.stop()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='luna-structure-fake-'); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def run_one(self,path,row,**kwargs): return a.audit_one(path,row,time.monotonic()+10,**kwargs)
    def assert_stop(self,code,func,*args,**kwargs):
        with self.assertRaises(a.Stop) as cm: func(*args,**kwargs)
        self.assertEqual(cm.exception.code,code)
    def test_complete_integrity_without_package_execution(self):
        path,row=synthetic(self.root); facts,total,dests,imports=self.run_one(path,row)
        self.assertEqual(facts['integrity'],'verified'); self.assertEqual(facts['findings'],[])
        self.assertTrue(total); self.assertEqual(imports,[('demo',True)])
        self.assertEqual(facts['declared_notices'][0]['modern_placement'],True)
    def test_all_relocation_schemes_collected(self):
        extra={'demo-1.0.data/'+s+'/a'+str(i)+'.py':b'#!python\nprint(1)\n' for i,s in enumerate(a.SCHEMES[:-1])}
        extra['demo-1.0.data/new_scheme/thing']=b'unknown'
        path,row=synthetic(self.root,extra=extra); facts,_,_,_=self.run_one(path,row)
        self.assertEqual(set(facts['relocation']),{s+x for s in a.SCHEMES for x in ('_members','_bytes')})
        self.assertEqual(facts['scripts'][0]['shebang'],'wheel_python')
        self.assertIn('relocation_scheme_unsupported',facts['findings']); self.assertIn('relocation_scheme_unknown',facts['findings'])
        self.assertNotIn('new_scheme',json.dumps(facts))
    def test_script_content_not_executed_or_revealed(self):
        path,row=synthetic(self.root,extra={'demo-1.0.data/scripts/run':b'#!python\nSECRET_SENTINEL\n'})
        facts,*_=self.run_one(path,row)
        self.assertNotIn('SECRET_SENTINEL',json.dumps(facts)); self.assertNotIn('scripts/run',json.dumps(facts))
    def test_root_mapped_collision_is_compatibility(self):
        path,row=synthetic(self.root,extra={'demo-1.0.data/purelib/demo/__init__.py':b'other'})
        facts,*_=self.run_one(path,row); self.assertIn('destination_collision',facts['findings'])
    def test_mapped_file_directory_collision(self):
        path,row=synthetic(self.root,extra={'demo-1.0.data/purelib/demo':b'file'})
        facts,*_=self.run_one(path,row); self.assertIn('destination_file_directory_collision',facts['findings'])
    def test_raw_casefold_collision_is_hard(self):
        path,row=synthetic(self.root,extra={'DEMO/__init__.py':b'x'})
        self.assert_stop('zip_duplicate',self.run_one,path,row)
    def test_raw_file_directory_collision_is_hard(self):
        path,row=synthetic(self.root,extra={'demo':b'file'})
        self.assert_stop('zip_duplicate',self.run_one,path,row)
    def test_traversal_is_hard(self):
        path,row=synthetic(self.root,extra={'../escape':b'x'})
        self.assert_stop('zip_path',self.run_one,path,row)
    def test_symlink_is_hard(self):
        path,row=synthetic(self.root,extra={'link':b'target'},info_overrides={'link':stat.S_IFLNK|0o777})
        self.assert_stop('zip_type',self.run_one,path,row)
    def test_special_permissions_are_hard(self):
        path,row=synthetic(self.root,extra={'file':b'x'},info_overrides={'file':stat.S_IFREG|stat.S_ISUID|0o755})
        self.assert_stop('zip_permissions',self.run_one,path,row)
    def test_missing_record_is_hard(self):
        path,row=synthetic(self.root,omit=('demo-1.0.dist-info/RECORD',))
        self.assert_stop('record_missing',self.run_one,path,row)
    def test_multiple_record_roots_are_hard(self):
        path,row=synthetic(self.root,extra={'foreign-1.dist-info/RECORD':b''})
        self.assert_stop('record_ambiguous',self.run_one,path,row)
    def test_foreign_record_is_audited_then_classified(self):
        path,row=synthetic(self.root,foreign=True)
        facts,*_=self.run_one(path,row)
        self.assertIn('foreign_dist_info',facts['findings']); self.assertIn('required_metadata_missing',facts['findings'])
    def test_foreign_metadata_mismatch_is_hard(self):
        path,row=synthetic(self.root,foreign=True); row['wheel']['core_metadata_sha256']='0'*64
        self.assert_stop('metadata_hash',self.run_one,path,row)
    def test_bad_record_hash_is_hard(self):
        path,row=synthetic(self.root,record_mutation=lambda d:d.replace(b'sha256=',b'sha256=X',1))
        self.assert_stop('record_digest',self.run_one,path,row)
    def test_missing_record_coverage_is_hard(self):
        path,row=synthetic(self.root,record_mutation=lambda d:b'\n'.join(d.split(b'\n')[1:]))
        self.assert_stop('record_coverage',self.run_one,path,row)
    def test_record_self_hash_is_hard(self):
        path,row=synthetic(self.root,record_mutation=lambda d:d.replace(b'RECORD,,',b'RECORD,abc,0'))
        self.assert_stop('record_self',self.run_one,path,row)
    def test_archive_hash_mismatch_is_hard(self):
        path,row=synthetic(self.root); row['wheel']['sha256']='0'*64
        self.assert_stop('archive_hash',self.run_one,path,row)
    def test_archive_size_mismatch_is_hard(self):
        path,row=synthetic(self.root); row['wheel']['bytes']+=1
        self.assert_stop('archive_size',self.run_one,path,row)
    def test_metadata_hash_mismatch_is_hard(self):
        path,row=synthetic(self.root); row['wheel']['core_metadata_sha256']='0'*64
        self.assert_stop('metadata_hash',self.run_one,path,row)
    def test_archive_comment_is_hard(self):
        path,row=synthetic(self.root)
        with zipfile.ZipFile(path,'a') as z: z.comment=b'comment'
        raw=path.read_bytes(); row['wheel'].update(bytes=len(raw),sha256=a.digest(raw))
        self.assert_stop('zip_envelope',self.run_one,path,row)
    def test_symlink_archive_is_hard(self):
        path,row=synthetic(self.root); other=self.root/'actual'; path.rename(other); path.symlink_to(other)
        self.assert_stop('archive_type',self.run_one,path,row)
    def test_aggregate_bytes_prechecked(self):
        path,row=synthetic(self.root)
        self.assert_stop('zip_bounds',self.run_one,path,row,remaining_bytes=1)
    def test_aggregate_members_prechecked(self):
        path,row=synthetic(self.root)
        self.assert_stop('zip_bounds',self.run_one,path,row,remaining_members=1)
    def test_deadline(self):
        path,row=synthetic(self.root)
        self.assert_stop('deadline',a.audit_one,path,row,time.monotonic()-1)
    def test_startup_inventory_and_forbidden_flags(self):
        extra={'hook.pth':b'import forbidden\n','sitecustomize.py':b'forbidden','demo/code.pyc':b'bytes'}
        path,row=synthetic(self.root,extra=extra); facts,*_=self.run_one(path,row)
        self.assertEqual({r['kind'] for r in facts['startup']},{'pth','customization','bytecode'})
        self.assertTrue({'startup_pth_forbidden','startup_customization_forbidden','startup_bytecode_forbidden'}<=set(facts['findings']))
    def test_missing_notice_is_compatibility(self):
        path,row=synthetic(self.root,omit=('demo-1.0.dist-info/licenses/LICENSE',))
        facts,*_=self.run_one(path,row); self.assertIn('notice_declared_missing',facts['findings'])
    def test_nonmodern_notice_retained(self):
        path,row=synthetic(self.root,omit=('demo-1.0.dist-info/licenses/LICENSE',),extra={'LICENSE':b'notice'})
        facts,*_=self.run_one(path,row)
        self.assertIn('notice_modern_placement_absent',facts['findings']); self.assertNotIn('notice_declared_missing',facts['findings'])
    def test_import_absence_vs_explicit_empty(self):
        for extra,state in ((b'', 'absent_unknown'),(b'Import-Name: \n','explicit_empty')):
            meta=b'Metadata-Version: 2.5\nName: demo\nVersion: 1.0\n'+extra+b'\n'
            path,row=synthetic(self.root,metadata=meta); facts,*_=self.run_one(path,row)
            self.assertEqual(facts['imports']['names_state'],state)
    def test_unknown_metadata_version_is_compatibility(self):
        meta=b'Metadata-Version: 2.6\nName: demo\nVersion: 1.0\n\n'
        path,row=synthetic(self.root,metadata=meta); facts,*_=self.run_one(path,row)
        self.assertIn('metadata_version_unsupported',facts['findings'])
    def test_full49_continue_after_compatibility(self):
        records=[]
        for i in range(49):
            name='demo'+str(i)
            _,row=synthetic(self.root,name=name,extra={name+'-1.0.data/scripts/run'+str(i):b'#!python\n'})
            records.append(row)
        report=a.initial_report(records)
        for row in report['rows']: row['acquisition']='verified'
        a.audit(records,self.root,report,time.monotonic()+10)
        self.assertEqual(len(report['rows']),49); self.assertTrue(all(r['audit']=='verified' for r in report['rows']))
        self.assertEqual(report['status'],'structurally_complete_with_findings')
    def test_hard_stop_leaves_remaining_explicit(self):
        records=[]
        for i in range(3):
            _,row=synthetic(self.root,name='demo'+str(i)); records.append(row)
        records[1]['wheel']['sha256']='0'*64; report=a.initial_report(records)
        self.assert_stop('archive_hash',a.audit,records,self.root,report,time.monotonic()+10)
        self.assertEqual([r['audit'] for r in report['rows']],['verified','failed','not_attempted'])
        self.assertIsNone(report['rows'][1]['facts'])
    def test_cross_wheel_import_overlap(self):
        records=[]
        for i in range(2):
            name='demo'+str(i); meta=('Metadata-Version: 2.5\nName: '+name+'\nVersion: 1.0\nImport-Name: shared\n\n').encode()
            _,row=synthetic(self.root,name=name,metadata=meta); records.append(row)
        report=a.initial_report(records); a.audit(records,self.root,report,time.monotonic()+10)
        self.assertIn('import_ownership_collision',report['compatibility_findings'])
    def test_fake_acquisition_success(self):
        path,row=synthetic(self.root); raw=path.read_bytes(); path.unlink(); report=a.initial_report([row]); calls=[]
        def transport(url,timeout): calls.append(url); return Response(raw,headers={'Content-Length':str(len(raw))})
        a.acquire([row],self.root,report,time.monotonic()+10,transport)
        self.assertEqual(calls,[row['wheel']['url']]); self.assertEqual(report['rows'][0]['acquisition'],'verified')
    def test_fake_acquisition_denial_never_retries(self):
        _,row=synthetic(self.root); report=a.initial_report([row,row]); calls=[]
        def transport(url,timeout): calls.append(url); a.fail('access_denied')
        self.assert_stop('access_denied',a.acquire,[row,row],self.root,report,time.monotonic()+10,transport)
        self.assertEqual(len(calls),1); self.assertEqual([r['acquisition'] for r in report['rows']],['failed','not_attempted'])
    def test_fake_redirect_is_terminal(self):
        self.assert_stop('redirect_denied',a.NoRedirect().redirect_request,None,None,302,'untrusted',{},'https://evil.invalid/private')
    def test_fake_acquisition_wrong_content_length(self):
        _,row=synthetic(self.root); report=a.initial_report([row])
        self.assert_stop('response_size',a.acquire,[row],self.root,report,time.monotonic()+10,lambda *args:Response(b'x',headers={'Content-Length':'1'}))
    def test_fake_acquisition_compressed_response(self):
        _,row=synthetic(self.root); report=a.initial_report([row])
        self.assert_stop('response_encoding',a.acquire,[row],self.root,report,time.monotonic()+10,lambda *args:Response(b'x',headers={'Content-Encoding':'gzip'}))
    def test_exception_projection_never_raw(self):
        self.assertEqual(a.Stop('SECRET PATH HEADER').code,'internal_error')
    def test_manifest_pin(self):
        records=a.read_manifest(ROOT/'WHEELS49.frozen.json')
        self.assertEqual(len(records),49); self.assertEqual(sum(r['wheel']['bytes'] for r in records),207406351)
        bad=self.root/'manifest.json'; bad.write_text('{}')
        self.assert_stop('manifest_pin',a.read_manifest,bad)
    def test_closed_public_projection(self):
        path,row=synthetic(self.root,extra={'private_spelling_marker':b'private_content_marker'})
        facts,*_=self.run_one(path,row); body=json.dumps(facts)
        for marker in ('private_spelling_marker','private_content_marker','/workspace/','demo/__init__.py','License-File'):
            self.assertNotIn(marker,body)
    def test_finite_fact_and_output_caps(self):
        self.assert_stop('fact_limit',a.bounded,[1,2],1)
        self.assert_stop('fact_limit',a.write_json,self.root/'report.json',{'x':'a'*(a.REPORT_CAP+1)})
    def test_cleanup_owned_directory(self):
        owned=self.root/'owned'; owned.mkdir(); (owned/'wheel.whl').write_bytes(b'synthetic')
        untouched=self.root/'untouched'; untouched.write_bytes(b'keep')
        self.assertTrue(a.bounded_cleanup(owned)); self.assertEqual(untouched.read_bytes(),b'keep')

    def test_one_shot_claim_cannot_change_output(self):
        pack=self.root/'pack'; pack.mkdir()
        helper=pack/'audit_wheels.py'; helper.write_bytes(b'synthetic-helper')
        protocol=pack/'PROTOCOL.md'; protocol.write_bytes(b'synthetic-protocol')
        frozen={'helper_sha256':a.digest(helper.read_bytes()),'protocol_sha256':a.digest(protocol.read_bytes())}
        (pack/'SOURCE_FREEZE.json').write_text(json.dumps(frozen))
        with patch.object(a,'__file__',str(helper)):
            path,receipt=a.claim_attempt()
            self.assertEqual(path,pack/'ATTEMPT.json')
            self.assertEqual(receipt['manifest_sha256'],a.MANIFEST_SHA256)
            self.assertEqual(len(receipt['interpreter_sha256']),64)
            self.assert_stop('attempt_exists',a.claim_attempt)
    def test_source_change_blocks_claim(self):
        pack=self.root/'pack'; pack.mkdir(); helper=pack/'audit_wheels.py'; helper.write_bytes(b'changed')
        (pack/'PROTOCOL.md').write_bytes(b'protocol')
        (pack/'SOURCE_FREEZE.json').write_text(json.dumps({'helper_sha256':'0'*64,'protocol_sha256':a.digest(b'protocol')}))
        with patch.object(a,'__file__',str(helper)):
            self.assert_stop('source_pin',a.claim_attempt)
        self.assertFalse((pack/'ATTEMPT.json').exists())
    def test_rlimits_are_separate_and_finite(self):
        for phase,cpu,memory,wall in (('acquisition',120,512*a.MIB,230),('audit',480,1024*a.MIB,590)):
            calls=[]
            with patch.object(a.resource,'setrlimit',side_effect=lambda key,value:calls.append((key,value))),patch.object(a.signal,'signal'),patch.object(a.signal,'alarm') as alarm:
                a.enforce_limits(phase)
            self.assertIn((a.resource.RLIMIT_CPU,(cpu,cpu)),calls)
            self.assertIn((a.resource.RLIMIT_AS,(memory,memory)),calls)
            self.assertIn((a.resource.RLIMIT_NOFILE,(64,64)),calls)
            alarm.assert_called_once_with(wall)
    def test_supervisor_timeout_reaps_owned_process(self):
        from unittest.mock import Mock
        captured=[]
        def fake_init(process,*args,**kwargs):
            process.pid=12345;process.returncode=None;captured.append((process,kwargs))
            waits=[a.subprocess.TimeoutExpired('fake',1),a.subprocess.TimeoutExpired('fake',2),-9]
            def wait(timeout):
                result=waits.pop(0)
                if isinstance(result,Exception):raise result
                process.returncode=result;return result
            process.wait=Mock(side_effect=wait)
        with patch.object(a.subprocess.Popen,'__init__',autospec=True,side_effect=fake_init),patch.object(a.os,'killpg') as kill,patch.object(a,'process_group_exists',return_value=False),patch.object(a.signal,'setitimer'):
            code,failure=a.run_child('audit',self.root/'manifest',self.root,self.root/'state',time.monotonic()+600)
        self.assertEqual((code,failure),(None,'deadline'))
        self.assertEqual(kill.call_args_list[0].args,(12345,a.signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args,(12345,a.signal.SIGKILL))
        self.assertEqual(captured[0][0].wait.call_count,3)
        self.assertTrue(captured[0][1]['start_new_session'])
        self.assertEqual(captured[0][1]['stderr'],a.subprocess.DEVNULL)
    def test_fake_supervised_terminal_failure_retains_receipt_and_cleans(self):
        _,record=synthetic(self.root)
        attempt=self.root/'attempt.json'; receipt={'status':'claimed','failure':None,'cleanup':'pending'}
        def child(phase,manifest,directory,state,deadline):
            report=json.loads(state.read_bytes()); report['phase']=phase
            report['rows'][0]['acquisition']='in_progress'
            (directory/'partial.whl').write_bytes(b'synthetic partial')
            a.write_json(state,report)
            return None,'deadline'
        with patch.object(a,'read_manifest',return_value=[record]),patch.object(a,'claim_attempt',return_value=(attempt,receipt)),patch.object(a,'run_child',side_effect=child):
            result=a.run_approved(self.root/'fake-manifest',self.root/'report.json')
        self.assertEqual(result,1)
        report=json.loads((self.root/'report.json').read_bytes())
        self.assertEqual(report['cleanup'],'verified')
        self.assertEqual(report['rows'][0]['acquisition'],'unobserved_after_termination')
        self.assertEqual(json.loads(attempt.read_bytes())['status'],'incomplete')
        self.assertEqual(list(self.root.glob('luna-exact49-owned-*')),[])
    def test_zip64_extra_rejected(self):
        self.assert_stop('zip_encoding',a.check_extra,struct.pack('<HHQ',1,8,1))
    def test_untrusted_header_exception_is_projected(self):
        _,row=synthetic(self.root); report=a.initial_report([row]); called=[]
        def transport(*args): called.append(1); raise OSError('/private/path SECRET_RAW_ERROR')
        self.assert_stop('access_denied',a.acquire,[row],self.root,report,time.monotonic()+10,transport)
        self.assertNotIn('SECRET_RAW_ERROR',json.dumps(report)); self.assertEqual(len(called),1)

    def test_directory_members_participate_in_inventory(self):
        path,row=synthetic(self.root)
        before,*_=self.run_one(path,row)
        path,row=synthetic(self.root,extra={'empty/':b''})
        after,*_=self.run_one(path,row)
        self.assertNotEqual(before['inventory_sha256'],after['inventory_sha256'])
        self.assertEqual(after['member_kinds']['directories'],1)
    def test_foreign_metadata_remains_observable(self):
        path,row=synthetic(self.root,foreign=True)
        facts,*_=self.run_one(path,row)
        self.assertEqual(facts['metadata_version'],'2.5')
        self.assertEqual(facts['core_metadata_sha256'],row['wheel']['core_metadata_sha256'])
        self.assertEqual(facts['dist_info_root_count'],1)
        self.assertIn('foreign_dist_info',facts['findings'])

    def mutate_archive(self,path,row,mutation):
        data=bytearray(path.read_bytes());mutation(data);path.write_bytes(data)
        row['wheel'].update(bytes=len(data),sha256=a.digest(data))
    def central_offsets(self,data):
        cd=struct.unpack_from('<I',data,len(data)-6)[0];cursor=cd;headers=[]
        while data[cursor:cursor+4]==b'PK\x01\x02':
            headers.append(cursor);n,x,c=struct.unpack_from('<3H',data,cursor+28);cursor+=46+n+x+c
        return cd,headers
    def test_central_nonzero_disk_is_hard(self):
        path,row=synthetic(self.root)
        self.mutate_archive(path,row,lambda data:struct.pack_into('<H',data,self.central_offsets(data)[1][0]+34,1))
        self.assert_stop('zip_encoding',self.run_one,path,row)
    def test_central_comment_overrun_is_hard(self):
        path,row=synthetic(self.root)
        self.mutate_archive(path,row,lambda data:struct.pack_into('<H',data,self.central_offsets(data)[1][-1]+32,65535))
        self.assert_stop('zip_envelope',self.run_one,path,row)
    def test_local_version_mismatch_is_hard(self):
        path,row=synthetic(self.root)
        self.mutate_archive(path,row,lambda data:struct.pack_into('<H',data,4,65535))
        self.assert_stop('zip_local_header',self.run_one,path,row)
    def test_compressed_trailing_bytes_are_hard(self):
        for compression in (zipfile.ZIP_DEFLATED,zipfile.ZIP_STORED):
            path,row=synthetic(self.root,compression=compression)
            def change(data):
                cd,headers=self.central_offsets(data);last=headers[-1]
                local=struct.unpack_from('<I',data,last+42)[0];old=struct.unpack_from('<I',data,last+20)[0]
                extra=b'SYNTHETIC_UNCONSUMED_DATA'
                struct.pack_into('<I',data,local+18,old+len(extra));struct.pack_into('<I',data,last+20,old+len(extra))
                struct.pack_into('<I',data,len(data)-6,cd+len(extra));data[cd:cd]=extra
            self.mutate_archive(path,row,change)
            self.assert_stop('zip_read',self.run_one,path,row)
    def test_closed_report_rejects_unknown_and_changed_identity(self):
        _,row=synthetic(self.root);report=a.initial_report([row])
        a.validate_report(report,[row])
        report['PRIVATE_HEADER']='raw';self.assert_stop('report_invalid',a.validate_report,report,[row]);del report['PRIVATE_HEADER']
        report['rows'][0]['name']='PRIVATE_PATH';self.assert_stop('report_invalid',a.validate_report,report,[row])
    def test_closed_report_checks_completion(self):
        _,row=synthetic(self.root);report=a.initial_report([row]);report['status']='structurally_complete'
        self.assert_stop('report_invalid',a.validate_report,report,[row])
    def test_complete_realshape_fake_report_passes_projector(self):
        path,row=synthetic(self.root);report=a.initial_report([row]);report['rows'][0]['acquisition']='verified';report['acquired_bytes']=row['wheel']['bytes']
        a.audit([row],self.root,report,time.monotonic()+10)
        a.validate_report(report,[row]);report['audited_member_count']+=1
        self.assert_stop('report_invalid',a.validate_report,report,[row])
    def test_bounded_state_read_rejects_size_duplicate_keys_and_symlink(self):
        path=self.root/'state';path.write_text('x'*100)
        self.assert_stop('report_invalid',a.safe_json_read,path,10)
        path.write_text('{"schema":1,"schema":2}')
        self.assert_stop('report_invalid',a.safe_json_read,path)
        link=self.root/'link';link.symlink_to(path)
        with self.assertRaises(OSError):a.safe_json_read(link)
    def test_final_output_is_exclusive(self):
        _,row=synthetic(self.root);report=a.initial_report([row]);path=self.root/'report';path.write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):a.write_final(path,report,[row])
        self.assertEqual(path.read_bytes(),b'KEEP')
    def test_redirect_response_is_closed(self):
        response=Response(b'PRIVATE')
        self.assert_stop('redirect_denied',a.NoRedirect().redirect_request,None,response,302,'',{},'https://example.invalid')
        self.assertTrue(response.closed)
    def test_phase_watchdog_covers_spawn_and_reserve(self):
        with patch.object(a.signal,'getitimer',return_value=(0.0,0.0)),patch.object(a.signal,'getsignal'),patch.object(a.signal,'signal'),patch.object(a.signal,'setitimer') as timer:
            with a.PhaseWatchdog(240) as watch:watch.reserve()
        self.assertEqual(timer.call_args_list[0].args,(a.signal.ITIMER_REAL,230))
        self.assertEqual(timer.call_args_list[-1].args,(a.signal.ITIMER_REAL,0))

    def test_oversized_valid_complete_report_has_small_explicit_fallback(self):
        _,row=synthetic(self.root);report=a.initial_report([row]);report['rows'][0]['acquisition']='verified';report['acquired_bytes']=row['wheel']['bytes']
        a.audit([row],self.root,report,time.monotonic()+10)
        fact={'path_sha256':'a'*64,'content_sha256':'b'*64,'bytes':0}
        facts=report['rows'][0]['facts'];facts['notice_candidates']=[fact.copy() for _ in range(4096)];facts['native_libraries']=[fact.copy() for _ in range(4096)]
        facts['scripts']=[dict(fact,executable=False,shebang='none') for _ in range(4096)]
        self.assertGreater(len(json.dumps(report)),a.REPORT_CAP)
        safe,data=a.prepare_final(report,[row])
        self.assertLess(len(data),10000);self.assertEqual(safe['failure'],'fact_limit')
        self.assertEqual(safe['acquired_bytes'],row['wheel']['bytes'])
        self.assertEqual(safe['rows'][0]['audit'],'facts_omitted_due_to_report_limit')
        a.validate_report(safe,[row])
    def test_initialization_failure_is_guarded_and_cleans(self):
        _,row=synthetic(self.root);attempt=self.root/'attempt.json';receipt={'status':'claimed','failure':None,'cleanup':'pending'}
        original=a.write_json
        def write(path,obj):
            if Path(path).name=='state.json':raise OSError('synthetic initialization denial')
            return original(path,obj)
        with patch.object(a,'read_manifest',return_value=[row]),patch.object(a,'claim_attempt',return_value=(attempt,receipt)),patch.object(a,'write_json',side_effect=write),patch.object(a,'run_child') as child:
            self.assertEqual(a.run_approved(self.root/'manifest',self.root/'result'),1)
        child.assert_not_called()
        report=json.loads((self.root/'result').read_bytes());self.assertEqual(report['cleanup'],'verified')
        self.assertEqual(list(self.root.glob('luna-exact49-owned-*')),[])
    def test_unknown_checkpoint_marks_every_row_unobserved(self):
        _,row=synthetic(self.root);records=[row,row];prior=a.initial_report(records)
        report=a.uncertain_phase_report(records,prior,'acquisition','report_invalid')
        a.validate_report(report,records)
        self.assertTrue(all(r['acquisition']=='unobserved_after_termination' for r in report['rows']))

    def test_boolean_index_is_rejected(self):
        _,row=synthetic(self.root);report=a.initial_report([row]);report['rows'][0]['index']=False
        self.assert_stop('report_invalid',a.validate_report,report,[row])

if __name__=='__main__': unittest.main(verbosity=2)
