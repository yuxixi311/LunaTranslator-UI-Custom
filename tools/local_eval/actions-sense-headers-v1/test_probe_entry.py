"""Entirely fake admission, transport, owner, resource and privacy verification."""
import ast
import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import socket
import ssl
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import bootstrap
import header_logic as logic
import probe_entry as p

SHA='1'*64;SOURCE='a'*40;WORKFLOW='b'*40;SECRET='CANARY https://secret.invalid/path?signature=private'
CLASSES=dict(logic.EXACT_HOST_CLASSES)


class Clock:
    def __init__(self):self.value=0.
    def __call__(self):return self.value
    def advance(self,n):self.value+=n


def binding():return dict(protocol_sha256=p.PROTOCOL_SHA,source_manifest_sha256=SHA,source_commit=SOURCE,
    workflow_commit=WORKFLOW,run_id='123456',run_attempt=1,request_sha256=p.REQUEST_SHA)
def context():return dict(binding=binding(),parent_pid=42,owner_argv=['/usr/bin/python3','-I','-B',
    '/fake/workspace/'+p.PROJECT+'/bootstrap.py','owner',SHA,'unused'],workspace='/fake/workspace',work_end=20.,outer_end=30.)
def grant(role):return patch.object(p,'_GRANT',dict(role=role,pid=os.getpid(),parent_pid=os.getppid()))


class FrameTests(unittest.TestCase):
    def test_exact_bound_frame_and_budget(self):
        value=p.new_frame(binding());self.assertIs(p.validate_frame(value,binding(),CLASSES),value)
        self.assertLessEqual(len(p.canonical(value))+1,2048);self.assertIsNone(value['host_class'])
    def test_binding_type_and_identity_drift_rejected(self):
        for key,value in [('run_id','0'),('run_attempt',True),('source_commit',WORKFLOW),('request_sha256','2'*64)]:
            changed=binding();changed[key]=value
            with self.subTest(key=key),self.assertRaises(logic.ProbeFailure):p.validate_binding(changed)
        for key in p.BINDING_KEYS:
            value=p.new_frame(binding());value[key]='unexpected'
            with self.subTest(key=key),self.assertRaises(logic.ProbeFailure):p.validate_frame(value,binding(),CLASSES)
    def test_arbitrary_fields_enums_and_counters_cannot_escape(self):
        for key,bad in [('extra',SECRET),('host_class',SECRET),('status',SECRET),('failure',SECRET),('cleanup',SECRET),
                        ('application_body_read_calls',1),('redirects_followed',True),('initial_exchange_intents',2),('request_send_complete',1)]:
            value=p.new_frame(binding());value[key]=bad
            with self.subTest(key=key),self.assertRaises(logic.ProbeFailure):p.validate_frame(value,binding(),CLASSES)
    def test_unknown_progress_does_not_become_zero(self):
        value=p.new_frame(binding());value.update(initial_exchange_intents=None,request_send_complete=None,header_block_complete=None)
        p.validate_frame(value,binding(),CLASSES);self.assertIsNone(value['initial_exchange_intents'])
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):p.strict_json(raw)


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        root=Path('/fake/workspace')/p.PROJECT
        payloads={'bootstrap.py':b'# inert', 'WORKFLOW_TEMPLATE.yml.in':(Path(__file__).parent/'WORKFLOW_TEMPLATE.yml.in').read_bytes()}
        paths=sorted([p.PROJECT+'/'+n for n in payloads]+[p.PROJECT+'/KIT_MANIFEST.json'])
        env=dict(GITHUB_ACTIONS='true',GITHUB_EVENT_NAME='push',GITHUB_RUN_ATTEMPT='1',GITHUB_REPOSITORY=p.REPOSITORY,
            GITHUB_REF='refs/heads/'+p.BRANCH,LUNA_SOURCE_COMMIT=SOURCE,GITHUB_SHA=WORKFLOW,GITHUB_WORKFLOW_SHA=WORKFLOW,
            GITHUB_WORKFLOW_REF=p.REPOSITORY+'/'+p.WORKFLOW+'@refs/heads/'+p.BRANCH,RUNNER_ENVIRONMENT='github-hosted',
            RUNNER_OS='Linux',RUNNER_ARCH='X64',ImageOS='ubuntu24',GITHUB_JOB='headers',GITHUB_WORKSPACE='/fake/workspace',GITHUB_RUN_ID='123456')
        event=dict(repository=dict(full_name=p.REPOSITORY,private=False),created=False,deleted=False,forced=False,
            before=SOURCE,after=WORKFLOW,head_commit=dict(id=WORKFLOW),ref=env['GITHUB_REF'])
        rendered=payloads['WORKFLOW_TEMPLATE.yml.in'].replace(b'__SOURCE_COMMIT__',SOURCE.encode()).replace(b'__MANIFEST_SHA256__',SHA.encode()).replace(b'__BOOTSTRAP_SHA256__',p.sha256(payloads['bootstrap.py']).hexdigest().encode())
        replies={('rev-parse','HEAD'):(WORKFLOW+'\n').encode(),('show','-s','--format=%P','HEAD'):(SOURCE+'\n').encode(),
            ('show','-s','--format=%P',SOURCE):(p.SOURCE_PARENT+'\n').encode(),
            ('diff-tree','--no-commit-id','--name-only','-r','HEAD'):(p.WORKFLOW+'\n').encode(),
            ('ls-tree','-r','--name-only','HEAD','--',p.PROJECT):('\n'.join(paths)+'\n').encode(),
            ('diff-tree','--no-commit-id','--name-only','-r',SOURCE):('\n'.join(paths)+'\n').encode(),
            ('status','--porcelain','--untracked-files=all'):b'',('show','HEAD:'+p.WORKFLOW):rendered}
        return root,payloads,env,event,replies,context()['owner_argv']
    def admitted(self,data):
        root,payloads,env,event,replies,argv=data
        return p.admit_owner(env,event,lambda *a:replies[a],root,SHA,payloads,argv)
    def test_exact_source_and_workflow_chain_is_admitted(self):self.assertEqual(self.admitted(self.fixture()),binding())
    def test_dispatch_rerun_private_force_and_wrong_runner_denied(self):
        for where,key,bad in [('env','GITHUB_EVENT_NAME','workflow_dispatch'),('env','GITHUB_RUN_ATTEMPT','2'),
            ('env','GITHUB_REPOSITORY','other/repo'),('env','RUNNER_ENVIRONMENT','self-hosted'),('env','ImageOS','ubuntu22'),
            ('event','created',True),('event','forced',True),('event','deleted',True)]:
            data=self.fixture();data[2 if where=='env' else 3][key]=bad
            with self.subTest(key=key),self.assertRaises(logic.ProbeFailure):self.admitted(data)
        data=self.fixture();data[3]['repository']['private']=True
        with self.assertRaises(logic.ProbeFailure):self.admitted(data)
    def test_source_parent_extra_path_and_dirty_checkout_denied(self):
        for command,bad in [(('show','-s','--format=%P',SOURCE),b'c'*40),
            (('diff-tree','--no-commit-id','--name-only','-r','HEAD'),(p.WORKFLOW+'\nextra\n').encode()),
            (('diff-tree','--no-commit-id','--name-only','-r',SOURCE),b'partial\n'),
            (('status','--porcelain','--untracked-files=all'),b'?? extra\n')]:
            data=self.fixture();data[4][command]=bad
            with self.subTest(command=command),self.assertRaises(logic.ProbeFailure):self.admitted(data)
    def test_workflow_bytes_are_not_whitespace_normalized(self):
        for prefix,suffix in [(b' ',b''),(b'',b'\n'),(b'',b' '),(b'\n',b'')]:
            data=self.fixture();key=('show','HEAD:'+p.WORKFLOW);data[4][key]=prefix+data[4][key]+suffix
            with self.subTest(prefix=prefix,suffix=suffix),self.assertRaises(logic.ProbeFailure):self.admitted(data)
    def test_import_or_cli_arguments_alone_cannot_arm_native_work(self):
        with patch.object(p,'_GRANT',None):
            for role in ('owner','worker'):
                with self.assertRaises(logic.ProbeFailure):p.require_role(role)
            with self.assertRaises(logic.ProbeFailure):p.observe_one(context(),CLASSES)
            with self.assertRaises(logic.ProbeFailure):p.owner_admission('unused')
    def test_worker_requires_exact_owned_parent_source_and_live_deadline(self):
        c=context();root=Path(c['workspace'])/p.PROJECT
        p.validate_worker_context(c,root,SHA,42,c['owner_argv'],'/fake/python','/fake/python',0.)
        mutations=[('parent_pid',43),('work_end',21.),('outer_end',31.),('workspace','/other')]
        for key,bad in mutations:
            changed=deepcopy(c);changed[key]=bad
            with self.subTest(key=key),self.assertRaises(logic.ProbeFailure):p.validate_worker_context(changed,root,SHA,42,c['owner_argv'],'/fake/python','/fake/python',0.)
        with self.assertRaises(logic.ProbeFailure):p.validate_worker_context(c,root,SHA,42,c['owner_argv'],'/fake/python','/fake/python',20.)
        with self.assertRaises(logic.ProbeFailure):p.validate_worker_context(c,root,SHA,42,['wrong'],'/fake/python','/fake/python',0.)
    def test_worker_stops_if_owner_is_gone(self):
        with grant('worker'),patch.object(p.os,'getppid',lambda:999999):
            with self.assertRaises(logic.ProbeFailure):p.require_role('worker')
    def test_bootstrap_post_admission_failure_never_claims_denied_or_zero_requests(self):
        tree=ast.parse(Path(bootstrap.__file__).read_bytes());tail=tree.body[-1];out=io.StringIO()
        def started_then_failed():raise RuntimeError(SECRET)
        with self.assertRaises(SystemExit):exec(compile(ast.Module(body=[tail],type_ignores=[]),'tail','exec'),{'__name__':'__main__','main':started_then_failed,'sys':SimpleNamespace(stdout=out)})
        result=json.loads(out.getvalue());self.assertEqual(result['reason'],'SOURCE_OR_EXECUTION_BLOCKED')
        self.assertNotIn('admission',result);self.assertNotIn('CANARY',out.getvalue());self.assertNotIn('initial_exchange_intents',result)


class TransportTests(unittest.TestCase):
    def run_fake(self,raw,*,delay=None,addresses=None,close_error=False,tls_valid=True,partial_send=False):
        clock=Clock();calls=[];position=[0];sent=bytearray();delay=delay or {}
        def step(name):calls.append(name);clock.advance(delay.get(name,0))
        class Connection:
            def settimeout(self,remaining):self.remaining=remaining
            def connect(self,address):step('connect')
            def send(self,data):
                step('send');n=min(7,len(data)) if partial_send else len(data);sent.extend(data[:n]);return n
            def recv(self,n):
                step('recv');self_n=n
                if self_n!=1:raise AssertionError('only one header byte per application read')
                data=raw[position[0]:position[0]+n];position[0]+=len(data);return data
            def close(self):
                step('close')
                if close_error:raise OSError(SECRET)
        connection=Connection()
        def dns(*args,**kw):step('dns');return addresses if addresses is not None else [(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',('8.8.8.8',443))]
        def create(*args):step('socket');return connection
        class TLS:
            check_hostname=tls_valid;verify_mode=ssl.CERT_REQUIRED
            def wrap_socket(self,raw,server_hostname):
                self.assert_host=server_hostname
                if server_hostname!=p.INITIAL_HOST:raise AssertionError('wrong TLS hostname')
                step('tls');return connection
        with grant('worker'):result=p.observe_one(context(),CLASSES,clock=clock,dns=dns,socket_factory=create,tls_factory=TLS)
        self.assertNotIn('CANARY',p.canonical(result).decode());return result,calls,position[0],bytes(sent),clock
    def test_200_header_observation_never_reads_body(self):
        head=b'HTTP/1.1 200 OK\r\nContent-Length: 1133080448\r\n\r\n';body=b'CANARY-model-body'
        result,calls,position,sent,_=self.run_fake(head+body)
        self.assertEqual(result['status'],'HTTP_200');self.assertEqual(result['failure'],'NONE')
        self.assertEqual(position,len(head));self.assertEqual(sent,p.REQUEST);self.assertEqual(calls.count('dns'),1)
        self.assertEqual(calls.count('socket'),1);self.assertEqual(calls.count('close'),1)
    def test_redirect_is_classified_and_never_followed(self):
        head=b'HTTP/1.1 302 Found\r\nLocation: https://us.aws.cdn.hf.co/object?signature=CANARY\r\n\r\n'
        result,calls,position,sent,_=self.run_fake(head+b'body')
        self.assertEqual(result['host_class'],'HF_META_US_AWS_CDN_HF_CO');self.assertEqual(result['current_policy_outcome'],'REJECTS_HOST')
        self.assertEqual(calls.count('dns'),1);self.assertEqual(calls.count('socket'),1);self.assertEqual(result['redirects_followed'],0)
        self.assertEqual(position,len(head))
    def test_partial_send_is_one_request_not_a_retry(self):
        result,calls,position,sent,_=self.run_fake(b'HTTP/1.1 200 OK\r\n\r\n',partial_send=True)
        self.assertGreater(calls.count('send'),1);self.assertEqual(sent,p.REQUEST);self.assertEqual(calls.count('dns'),1)
    def test_empty_nonpublic_and_unsupported_dns_never_connect(self):
        bad=[[],[(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',('127.0.0.1',443))],
             [(999,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',('8.8.8.8',443))],[(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_TCP,'',('8.8.8.8',443))]]
        for addresses in bad:
            result,calls,*_=self.run_fake(b'',addresses=addresses)
            self.assertEqual(result['failure'],'DNS_FAILURE');self.assertNotIn('socket',calls)
    def test_all_addresses_must_be_public_and_no_fallback(self):
        rows=[(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',(host,443)) for host in ('8.8.8.8','127.0.0.1')]
        result,calls,*_=self.run_fake(b'',addresses=rows);self.assertEqual(result['failure'],'DNS_FAILURE');self.assertEqual(calls,['dns'])
    def test_dns_family_shape_and_ancillary_inconsistencies_never_connect(self):
        bad=[(socket.AF_INET,('2001:4860:4860::8888',443)),
             (socket.AF_INET6,('8.8.8.8',443,0,0)),(socket.AF_INET,('8.8.8.8',443,0,0)),
             (socket.AF_INET6,('2001:4860:4860::8888',443)),
             (socket.AF_INET6,('2001:4860:4860::8888',443,True,0)),
             (socket.AF_INET6,('2001:4860:4860::8888',443,0,3))]
        for family,address in bad:
            result,calls,*_=self.run_fake(b'',addresses=[(family,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',address)])
            self.assertEqual(result['failure'],'DNS_FAILURE');self.assertEqual(calls,['dns'])
        rows=[(socket.AF_INET6,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',('2001:4860:4860::8888',443,0,0))]
        self.assertEqual(p.public_address(rows),rows[0])
    def test_delayed_dns_connect_tls_and_send_cannot_start_later_phase(self):
        for stage,forbidden in [('dns','socket'),('connect','tls'),('tls','send'),('send','recv')]:
            result,calls,*_=self.run_fake(b'HTTP/1.1 200 OK\r\n\r\n',delay={stage:21.})
            with self.subTest(stage=stage):
                self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertNotIn(forbidden,calls)
    def test_tls_verification_cannot_be_disabled(self):
        result,calls,*_=self.run_fake(b'',tls_valid=False);self.assertEqual(result['failure'],'TLS_FAILURE');self.assertNotIn('tls',calls);self.assertNotIn('send',calls)
    def test_late_read_does_not_accept_header_or_read_again(self):
        result,calls,*_=self.run_fake(b'HTTP/1.1 200 OK\r\n\r\n',delay={'recv':21.})
        self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertEqual(calls.count('recv'),1);self.assertFalse(result['header_block_complete'])
    def test_eof_and_cleanup_error_preserve_first_failure(self):
        result,calls,*_=self.run_fake(b'HTTP/1.1',close_error=True)
        self.assertEqual(result['failure'],'HTTP_EOF_OR_INVALID_READ');self.assertEqual(result['cleanup'],'UNCONFIRMED')
    def test_close_return_after_outer_deadline_remains_unconfirmed(self):
        result,calls,*_=self.run_fake(b'HTTP/1.1 200 OK\r\n\r\n',delay={'close':31.})
        self.assertEqual(result['cleanup'],'UNCONFIRMED');self.assertEqual(result['failure'],'DEADLINE_EXPIRED')


class FakeServices:
    def __init__(self,clock,raw,*,ready=1.,pending=False,memory=True,delay_method=None,delay=31.,ignore_stop=False,launch_error=False):
        self.clock,self.raw,self.ready=clock,bytearray(raw),ready
        self.pending,self.memory,self.delay_method,self.delay=pending,memory,delay_method,delay
        self.ignore_stop,self.error=ignore_stop,launch_error;self.calls=[];self.stopped=False;self.delayed=False
    def event(self,name):
        self.calls.append((name,self.clock()))
        if name==self.delay_method and not self.delayed:self.delayed=True;self.clock.advance(self.delay)
    def launch(self):self.event('launch')
    def process(self):return None if self.pending or self.error else self
    def launch_error(self):return self.error
    def launcher_done(self):return not self.pending
    def memory_ok(self):self.event('memory');return self.memory
    def read(self,cap):
        self.event('read')
        if self.stopped:return b''
        if self.clock()<self.ready:return None
        result=bytes(self.raw[:cap]);del self.raw[:cap];return result
    def poll(self):self.event('poll');return -15 if self.stopped else 0 if self.clock()>=self.ready else None
    def terminate(self):self.event('terminate');self.stopped=not self.ignore_stop
    def kill(self):self.event('kill');self.stopped=not self.ignore_stop
    def close(self):self.event('close')
    def pause(self):self.clock.advance(.25)


class OwnerTests(unittest.TestCase):
    def successful(self):
        value=p.new_frame(binding());value.update(status='HTTP_200',location_form='ABSENT',host_class='NO_LOCATION',
            current_policy_outcome='NOT_A_REDIRECT',initial_exchange_intents=1,request_send_complete=True,header_block_complete=True,cleanup='CONFIRMED')
        return value
    def execute(self,raw=None,**kwargs):
        clock=Clock();services=FakeServices(clock,p.canonical(self.successful())+b'\n' if raw is None else raw,**kwargs)
        with grant('owner'):result=p.supervise(binding(),CLASSES,services,0.,clock=clock)
        return result,services,clock
    def test_one_valid_timely_bound_frame_is_accepted(self):
        result,services,clock=self.execute();self.assertEqual(result,self.successful());self.assertLess(clock(),20)
        self.assertEqual([n for n,_ in services.calls].count('launch'),1);self.assertEqual([n for n,_ in services.calls].count('close'),1)
    def test_late_worker_result_is_not_accepted(self):
        result,services,clock=self.execute(ready=21.)
        self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertIsNone(result['header_block_complete']);self.assertIsNone(result['initial_exchange_intents'])
    def test_pending_launch_and_stuck_stop_remain_unconfirmed_at30(self):
        for kwargs in ({'pending':True},{'ready':100.,'ignore_stop':True}):
            result,services,clock=self.execute(**kwargs)
            self.assertEqual(result['cleanup'],'UNCONFIRMED');self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertEqual(clock(),30.)
            self.assertTrue(all(at<30 for _,at in services.calls))
    def test_resource_cap_triggers_cleanup_without_accepting_worker(self):
        result,services,_=self.execute(memory=False,ready=100.)
        self.assertEqual(result['failure'],'RESOURCE_CAP');self.assertIn('terminate',[n for n,_ in services.calls])
    def test_oversized_raw_output_is_never_emitted(self):
        result,services,_=self.execute(raw=(SECRET*100).encode())
        self.assertEqual(result['failure'],'RESOURCE_CAP');self.assertNotIn('CANARY',p.canonical(result).decode())
    def test_unbound_duplicate_malformed_and_extra_output_rejected(self):
        bad=self.successful();bad['run_id']='999'
        for raw in [p.canonical(bad)+b'\n',b'{}\n',p.canonical(self.successful())+b'\nextra\n',b'{"schema":1,"schema":1}\n']:
            result,_,_=self.execute(raw=raw);self.assertEqual(result['failure'],'UNKNOWN_FAILURE')
    def test_slow_native_callbacks_cannot_cause_followup_after30(self):
        for method in ('memory','read','poll','close','terminate'):
            options=dict(delay_method=method)
            if method=='terminate':options.update(ready=100.,memory=False)
            result,services,clock=self.execute(**options)
            with self.subTest(method=method):
                self.assertEqual(result['cleanup'],'UNCONFIRMED')
                self.assertTrue(all(at<30 for _,at in services.calls));self.assertEqual(services.calls[-1][0],method)
    def test_slow_memory_check_crossing_work_deadline_rejects_result(self):
        result,_,_=self.execute(delay_method='memory',delay=21.)
        self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertIsNone(result['header_block_complete'])
    def test_launch_exception_never_claims_no_child_created(self):
        result,_,_=self.execute(launch_error=True)
        self.assertEqual(result['cleanup'],'UNCONFIRMED');self.assertIsNone(result['initial_exchange_intents'])
    def test_slow_validation_cannot_accept_a_result_after20(self):
        clock=Clock();services=FakeServices(clock,p.canonical(self.successful())+b'\n');original=p.validate_frame;delayed=[]
        def slow(value,bound,classes):
            result=original(value,bound,classes)
            if value['header_block_complete'] is True and not delayed:delayed.append(True);clock.advance(21.)
            return result
        with grant('owner'),patch.object(p,'validate_frame',slow):result=p.supervise(binding(),CLASSES,services,0.,clock=clock)
        self.assertEqual(result['failure'],'DEADLINE_EXPIRED');self.assertIsNone(result['header_block_complete'])
        self.assertIsNone(result['initial_exchange_intents'])
    def test_unreleased_supervisor_has_no_effects(self):
        clock=Clock();services=FakeServices(clock,b'')
        with patch.object(p,'_GRANT',None),self.assertRaises(logic.ProbeFailure):p.supervise(binding(),CLASSES,services,0.,clock=clock)
        self.assertEqual(services.calls,[])


if __name__=='__main__':unittest.main()
