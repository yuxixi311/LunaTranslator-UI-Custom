"""Entirely inert failure-boundary checks. No host, socket, child or real claim."""
import ast
from contextlib import ExitStack
from hashlib import sha256
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import acquisition_source as a
import cpu_harness as h
import diagnostics as d
import final_coordinator as kit
import guarded_runtime as runtime
import public_exports
import activation_scope
import kit_worker
import host_validation_source as host
from test_actions_wrapper import cache
import verified_bootstrap as bootstrap
from attempt_control import AttemptControl
from test_cpu_harness import Clock,Reader,response
from test_guarded_adapters import doubles,supervisor,NativeChild,FakeEvidence
from test_final_kit import kit_plan

SHA='1'*64
SECRET='CANARY /private/path https://private.example/?signed=secret'

class ProjectionTests(unittest.TestCase):
    def test_first_failure_is_latched_and_raw_canary_never_emitted(self):
        t=d.Trace(SHA,'a'*32);t.enter('CLAIM_WRITE');t.fail(OSError(13,SECRET));t.enter('CLEANUP');t.fail(TypeError(SECRET))
        self.assertEqual(t.snapshot()['first_failure'],dict(stage='CLAIM_WRITE',code='OS_ACCESS_DENIED'))
        self.assertNotIn('CANARY',d.encode(t.snapshot()).decode())
    def test_unknown_worker_preserves_unknown_asset_counters(self):
        value=d.Trace(SHA).snapshot()
        for asset in value['assets']:self.assertTrue(all(v is None for v in asset.values()))
    def test_worker_projection_rejects_raw_and_wrong_source(self):
        child=d.Trace(SHA,role='acquire');child.start_assets();value=child.worker_snapshot();owner=d.Trace(SHA)
        self.assertTrue(owner.merge_worker(value))
        value['raw_error']=SECRET
        with self.assertRaises(ValueError):owner.merge_worker(value)
        del value['raw_error'];value['source_manifest_sha256']='2'*64
        self.assertFalse(owner.merge_worker(value))
    def test_all_five_child_roles_are_present_and_bounded(self):
        t=d.Trace(SHA);self.assertEqual(set(t.snapshot()['children']),set(d.ROLES))
        t.child('server',exit_code=9999)
        with self.assertRaises(ValueError):t.snapshot()
    def test_terminal_projection_keeps_only_finite_diagnostic(self):
        t=d.Trace(SHA,'a'*32);t.enter('ASSET_TLS');t.fail(OSError(SECRET))
        result=public_exports.safe_terminal(dict(status='incomplete',failure=SECRET,diagnostic=t.snapshot()))
        self.assertEqual(result['diagnostic']['first_failure']['stage'],'ASSET_TLS');self.assertNotIn('CANARY',json.dumps(result))
    def test_injected_child_or_claim_text_cannot_reach_public_schema(self):
        for key in ('claim_state','journal_state','stage'):
            value=d.Trace(SHA).snapshot();value[key]=SECRET
            with self.assertRaises(ValueError):d.validate_public(value)
    def test_invalid_counter_values_rejected(self):
        for key,value in [('attempts',2),('exchange_intents',5),('received_bytes',True),('written_bytes',-1)]:
            t=d.Trace(SHA,role='acquire');t.start_assets();result=t.worker_snapshot();result['assets'][0][key]=value
            with self.assertRaises(ValueError):d.validate_worker(result)

class ClaimAndCleanupTests(unittest.TestCase):
    def run_claim(self,mode):
        trace=d.Trace(SHA);closed=[];opened=[];syncs=[];clock=Clock()
        def opening(path,*args,**kw):
            opened.append(str(path));index=len(opened)
            if (mode=='root_open' and index==1) or (mode=='claim_open' and index==2) or (mode=='journal_open' and index==3):raise OSError(13,SECRET)
            return 10+index
        def persist(fd,raw):
            if mode=='claim_write':raise OSError(28,SECRET)
        def sync(fd):
            syncs.append(fd)
            if (mode=='claim_sync' and len(syncs)==1) or (mode=='journal_sync' and len(syncs)==2):raise OSError(9,SECRET)
        with doubles(clock),patch.object(kit.os,'open',opening),patch.object(kit.os,'close',closed.append),\
             patch.object(kit.os,'fsync',sync),patch.object(runtime,'persistent_write',persist):
            try:kit.claim_once(kit_plan(),SHA,trace)
            except OSError as exc:trace.fail(exc)
        return trace,opened,closed
    def test_every_claim_boundary_retains_finite_progress(self):
        expected={'root_open':('CLAIM_CREATE','NOT_ENTERED','NOT_ENTERED'),
            'claim_open':('CLAIM_CREATE','CREATE_PENDING','NOT_ENTERED'),
            'claim_write':('CLAIM_WRITE','CREATED','NOT_ENTERED'),
            'claim_sync':('CLAIM_SYNC','CREATED','NOT_ENTERED'),
            'journal_open':('JOURNAL_CREATE','DURABLE','CREATE_PENDING'),
            'journal_sync':('JOURNAL_SYNC','DURABLE','OPEN')}
        for mode,(stage,claim,journal) in expected.items():
            with self.subTest(mode=mode):
                t,opened,closed=self.run_claim(mode);value=t.snapshot()
                self.assertEqual(value['first_failure']['stage'],stage);self.assertEqual(value['claim_state'],claim);self.assertEqual(value['journal_state'],journal)
                self.assertNotIn('CANARY',d.encode(value).decode())
    def test_open_journal_is_closed_when_final_claim_sync_fails(self):
        t,opened,closed=self.run_claim('journal_sync');self.assertIn(13,closed)
        self.assertEqual(t.snapshot()['claim_state'],'DURABLE')
    def test_root_close_failure_cannot_cancel_an_unclosed_journal_handoff(self):
        trace=d.Trace(SHA);opened=[];closed=[]
        def opening(*args,**kw):opened.append(len(opened)+11);return opened[-1]
        def closing(fd):
            closed.append(fd)
            if fd==11:raise OSError(9,SECRET)
        with doubles(Clock()),patch.object(kit.os,'open',opening),patch.object(kit.os,'close',closing),\
             patch.object(kit.os,'fsync',lambda fd:None),patch.object(runtime,'persistent_write',lambda *args:None):
            with self.assertRaises(OSError):kit.claim_once(kit_plan(),SHA,trace)
        self.assertEqual(closed,[12,11,13]);self.assertEqual(len(closed),len(set(closed)))
        self.assertEqual(trace.snapshot()['first_failure'],dict(stage='CLAIM_DIRECTORY_CLOSE',code='OS_BAD_DESCRIPTOR'))
        self.assertIn('CLAIM_DIRECTORY_CLOSE_FAILED',trace.cleanup)
    def test_write_failure_survives_claim_and_root_close_failures(self):
        trace=d.Trace(SHA);opened=[];closed=[]
        def opening(*args,**kw):opened.append(len(opened)+11);return opened[-1]
        def write(*args):raise OSError(28,SECRET)
        def closing(fd):closed.append(fd);raise OSError(9,SECRET)
        with doubles(Clock()),patch.object(kit.os,'open',opening),patch.object(kit.os,'close',closing),\
             patch.object(kit.os,'fsync',lambda fd:None),patch.object(runtime,'persistent_write',write):
            with self.assertRaises(OSError) as caught:kit.claim_once(kit_plan(),SHA,trace)
        self.assertEqual(caught.exception.errno,28);self.assertEqual(closed,[12,11])
        self.assertEqual(trace.snapshot()['first_failure'],dict(stage='CLAIM_WRITE',code='OS_STORAGE_FULL'))
        self.assertEqual(set(trace.cleanup),{'CLAIM_FILE_CLOSE_FAILED','CLAIM_DIRECTORY_CLOSE_FAILED'})
    def test_failed_journal_close_is_recorded_once_without_retry(self):
        trace=d.Trace(SHA);opened=[];closed=[]
        def opening(*args,**kw):opened.append(len(opened)+11);return opened[-1]
        def closing(fd):
            closed.append(fd)
            if fd in (11,13):raise OSError(9,SECRET)
        with doubles(Clock()),patch.object(kit.os,'open',opening),patch.object(kit.os,'close',closing),\
             patch.object(kit.os,'fsync',lambda fd:None),patch.object(runtime,'persistent_write',lambda *args:None):
            with self.assertRaises(OSError):kit.claim_once(kit_plan(),SHA,trace)
        self.assertEqual(closed,[12,11,13]);self.assertIn('JOURNAL_CLOSE_FAILED',trace.cleanup)
        self.assertEqual(trace.snapshot()['first_failure']['stage'],'CLAIM_DIRECTORY_CLOSE')
    def test_missing_journal_can_fail_evidence_cleanup_without_any_child(self):
        clock=Clock();owner=supervisor(clock);owner.diagnostic=d.Trace(SHA)
        def failed_record(event):raise TypeError('synthetic missing journal')
        owner.record=failed_record
        with doubles(clock):result=owner.finalize()
        self.assertFalse(result['cleanup_confirmed']);self.assertEqual(owner.intents,{})
        self.assertIn('EVIDENCE_FINALIZE_FAILED',owner.diagnostic.snapshot()['cleanup_categories'])
    def test_child_launch_exit_and_cleanup_are_separate(self):
        clock=Clock();child=NativeChild();owner=supervisor(clock);owner.diagnostic=d.Trace(SHA)
        with doubles(clock),patch.object(runtime.subprocess,'Popen',lambda *args,**kw:child):
            owner.launch('acquire',h.child_spec('/fake/python',[], '/fake'),600,'validation.log')
            owner.finalize()
        state=owner.diagnostic.snapshot()['children']['acquire']
        self.assertEqual(state['launch'],'RETURNED');self.assertTrue(state['adopted']);self.assertEqual(state['cleanup'],'CONFIRMED')
    def test_pending_launch_and_join_failure_remain_unconfirmed(self):
        clock=Clock();owner=supervisor(clock);owner.diagnostic=d.Trace(SHA)
        owner.intents['acquire']=runtime.Intent('acquire',{},600)
        owner.diagnostic.child('acquire',launch='PENDING')
        owner.readers=[SimpleNamespace(name='reader',join=lambda **kw:(_ for _ in ()).throw(RuntimeError(SECRET)))]
        with doubles(clock):result=owner.finalize()
        self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(set(owner.diagnostic.cleanup),{'PENDING_LAUNCH','THREAD_JOIN_UNCONFIRMED'})
    def test_missing_log_receipt_does_not_fabricate_assets(self):
        t=d.Trace(SHA);evidence=SimpleNamespace(file_bytes={'validation.log':1},output=Path('/fake'))
        with patch.object(runtime,'bounded_file',lambda *args:b'partial invalid line'):
            kit.collect_worker_diagnostics(SimpleNamespace(),evidence,t)
        self.assertIsNone(t.assets[0]['attempts'])

class AssetBoundaryTests(unittest.TestCase):
    def test_dns_and_tls_failures_are_phase_categories_not_raw_causes(self):
        for stage in ('ASSET_DNS','ASSET_TLS'):
            trace=d.Trace(SHA,role='acquire');trace.start_assets();trace.asset_event(dict(event='asset_attempt',asset=0))
            trace.asset_event(dict(event='asset_exchange_intent',asset=0))
            connection=SimpleNamespace(settimeout=lambda _:None,connect=lambda _:None,close=lambda:None)
            def dns(*args,**kw):
                if stage=='ASSET_DNS':raise OSError(SECRET)
                return [(2,1,6,'',('8.8.8.8',443))]
            def tls():raise OSError(SECRET)
            with patch.object(a,'require_activation',lambda:None),patch.object(a.socket,'getaddrinfo',dns),\
                 patch.object(a.socket,'socket',lambda *args:connection),patch.object(a.ssl,'create_default_context',tls):
                try:a.native_get(0,h.ASSETS[0][0],h.Deadline(Clock(),600),trace)
                except OSError as exc:trace.fail(exc)
            self.assertEqual(trace.worker_snapshot()['first_failure']['stage'],stage)
            self.assertNotIn('CANARY',d.worker_line(trace).decode());self.assertEqual(trace.assets[0]['exchange_intents'],1)
    def fake_asset(self,mode):
        trace=d.Trace(SHA,role='acquire');clock=Clock();events=[];closed=[];written=[]
        data=(b'abcd',b'xy');assets=tuple((old[0],len(body),sha256(body).hexdigest()) for old,body in zip(h.ASSETS,data))
        def get(index,url,deadline,trace):
            trace.enter('ASSET_HEADERS')
            if mode=='framing':return Reader(response(data[index],[(b'Transfer-Encoding',b'chunked')]))
            if mode=='truncated':return Reader(b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nab')
            reader=Reader(response(data[index]))
            if mode=='close':reader.close=lambda:(_ for _ in ()).throw(OSError(SECRET))
            return reader
        def write(fd,body):
            if mode=='partial_write':written.append(1);raise OSError(28,SECRET)
            written.append(len(body));return len(body)
        with doubles(clock),patch.object(a,'require_activation',lambda:None),patch.object(h,'ASSETS',assets),\
             patch.object(a,'native_get',get),patch.object(a.os,'open',lambda *args:10),patch.object(a.os,'write',write),\
             patch.object(a.os,'fsync',lambda _:None),patch.object(a.os,'close',closed.append):
            try:a.acquire_assets('/fake',h.Deadline(clock,600),events.append,trace)
            except BaseException as exc:trace.fail(exc)
        return trace,events,closed,written
    def test_http_framing_failure_keeps_zero_body_count(self):
        t,events,closed,written=self.fake_asset('framing')
        self.assertEqual(t.worker_snapshot()['first_failure']['code'],'ASSET_FRAMING_REJECTED')
        self.assertEqual(t.assets[0]['received_bytes'],0);self.assertEqual(t.assets[1]['attempts'],0)
    def test_partial_transfer_bytes_survive_failure(self):
        t,events,closed,written=self.fake_asset('truncated')
        self.assertEqual(t.assets[0]['received_bytes'],2);self.assertEqual(t.assets[0]['written_bytes'],2)
        self.assertFalse(t.assets[0]['verified']);self.assertEqual(t.assets[1]['attempts'],0)
    def test_write_failure_separates_received_from_confirmed_written(self):
        t,events,closed,written=self.fake_asset('partial_write')
        self.assertEqual(t.assets[0]['received_bytes'],4);self.assertEqual(t.assets[0]['written_bytes'],0)
        self.assertEqual(t.worker_snapshot()['first_failure']['code'],'OS_STORAGE_FULL')
    def test_asset_cleanup_keeps_first_failure_and_marks_cleanup(self):
        t,events,closed,written=self.fake_asset('close')
        self.assertEqual(t.worker_snapshot()['first_failure']['stage'],'ASSET_CLOSE')
        self.assertIn('ASSET_CLOSE_FAILED',t.worker_snapshot()['cleanup_categories']);self.assertEqual(closed,[10])
    def test_exact_two_verified_assets_and_bounded_worker_frame(self):
        t,events,closed,written=self.fake_asset('success')
        self.assertEqual([a['written_bytes'] for a in t.assets],[4,2]);self.assertTrue(all(a['verified'] for a in t.assets))
        self.assertLessEqual(len(d.worker_line(t)),2048)

class HeaderDiagnosticTests(unittest.TestCase):
    def rejected_header(self,raw,*,expire=False,close_failure=False):
        trace=d.Trace(SHA,role='acquire');clock=Clock();reader=Reader(raw);events=[];closed=[]
        if expire:
            original=reader.read
            def late_read(n,remaining):
                data=original(n,remaining);clock.advance(601);return data
            reader.read=late_read
        if close_failure:reader.close=lambda:(_ for _ in ()).throw(OSError(9,SECRET))
        def no_body_write(*args):raise AssertionError('header failure must not write asset body')
        with doubles(clock),patch.object(a,'require_activation',lambda:None),\
             patch.object(a,'native_get',lambda *args:reader),patch.object(a.os,'open',lambda *args:10),\
             patch.object(a.os,'write',no_body_write),patch.object(a.os,'fsync',no_body_write),\
             patch.object(a.os,'close',closed.append):
            with self.assertRaises(BaseException):a.acquire_assets('/fake',h.Deadline(clock,600),events.append,trace)
        self.assertEqual(trace.assets[0],dict(attempts=1,exchange_intents=1,verified=False,received_bytes=0,written_bytes=0))
        self.assertEqual(trace.assets[1]['attempts'],0);self.assertEqual(closed,[10])
        self.assertEqual(trace.stage,'ASSET_CLOSE');self.assertNotIn(b'CANARY',d.worker_line(trace))
        return trace,reader
    def test_wire_limits_eof_crlf_and_deadline_have_finite_codes(self):
        raw_many=b'HTTP/1.1 200 OK\r\n'+b''.join(b'X-'+str(i).encode()+b': '+b'x'*1000+b'\r\n' for i in range(20))+b'\r\n'
        cases=[(b'HTTP/1.1 302 Found\r\nLocation: '+b'x'*2050+b'\r\n\r\n','HTTP_LINE_LIMIT',False),
            (raw_many,'HTTP_HEADER_BLOCK_LIMIT',False),
            (b'HTTP/1.1 200 OK\n\n','HTTP_CRLF_REJECTED',False),
            (b'HTTP/1.1 200 OK\r\nContent-Length:','HTTP_EOF_OR_INVALID_READ',False),
            (b'HTTP/1.1 200 OK\r\n\r\n','DEADLINE_EXPIRED',True)]
        for raw,code,expire in cases:
            with self.subTest(code=code):
                trace,reader=self.rejected_header(raw,expire=expire)
                self.assertEqual(trace.first['value'],dict(stage='ASSET_HEADERS',code=code))
                self.assertGreater(reader.position,0);self.assertEqual(trace.cleanup,[])
    def test_header_syntax_guards_remain_fail_closed_and_distinct(self):
        cases=[(b'not-http\r\n\r\n','ASSET_STATUS_LINE_REJECTED'),
            (b'HTTP/1.1 200 OK\r\nNoColon\r\n\r\n','ASSET_HEADER_FIELDS_REJECTED'),
            (b'HTTP/1.1 200 OK\r\nX: one\r\nX: two\r\n\r\n','ASSET_HEADER_SYNTAX_REJECTED'),
            (b'HTTP/1.1 200 OK\r\n'+b''.join(b'X-'+str(i).encode()+b': a\r\n' for i in range(65))+b'\r\n','ASSET_HEADER_FIELDS_REJECTED')]
        for raw,code in cases:
            with self.subTest(code=code):
                trace,_=self.rejected_header(raw);self.assertEqual(trace.first['value']['code'],code)
    def test_redirect_rejections_are_distinct_from_http_syntax(self):
        cases=[(None,'ASSET_REDIRECT_LIMIT_OR_LOCATION'),
            (b'https://invalid.example/object?CANARY=secret','ASSET_REDIRECT_HOST_REJECTED'),
            (b'https://cas-bridge.xethub.hf.co/../object','ASSET_PATH_REJECTED'),
            (b'https://cas-bridge.xethub.hf.co/object#CANARY','ASSET_LOCATION_REJECTED'),
            (b'https://user@cas-bridge.xethub.hf.co/object','ASSET_LOCATION_AUTHORITY_REJECTED'),
            (b'https://cas-bridge.xethub.hf.co:bad/object','ASSET_URL_PORT_REJECTED'),
            (b'https://cas-bridge.xethub.hf.co/','ASSET_REDIRECT_PATH_REJECTED')]
        for location,code in cases:
            with self.subTest(code=code):
                raw=b'HTTP/1.1 302 Found\r\n'+(b'Location: '+location+b'\r\n' if location else b'')+b'\r\n'
                trace,_=self.rejected_header(raw);self.assertEqual(trace.first['value'],dict(stage='ASSET_HEADERS',code=code))
    def test_zero_body_counter_does_not_claim_zero_network_traffic(self):
        raw=b'HTTP/1.1 302 Found\r\nLocation: https://invalid.example/object?CANARY=secret\r\n\r\n'
        trace,reader=self.rejected_header(raw)
        self.assertEqual(reader.position,len(raw));self.assertEqual(trace.assets[0]['received_bytes'],0)
    def test_original_header_failure_survives_close_failure(self):
        trace,_=self.rejected_header(b'HTTP/1.1 200 OK\n\n',close_failure=True)
        self.assertEqual(trace.first['value'],dict(stage='ASSET_HEADERS',code='HTTP_CRLF_REJECTED'))
        self.assertEqual(trace.cleanup,['ASSET_CLOSE_FAILED'])
    def test_all_closed_acquisition_header_and_redirect_guard_messages_are_mapped(self):
        source=ast.parse(Path(a.__file__).read_bytes());core=ast.parse(Path(h.__file__).read_bytes())
        selected=[node for node in source.body if isinstance(node,ast.FunctionDef) and node.name in
                  ('safe_path','validate_url','redirect','response_headers','stream_pinned','native_get','acquire_assets')]
        for node in core.body:
            if isinstance(node,ast.ClassDef) and node.name in ('Deadline','BoundedWire'):
                selected.extend(child for child in node.body if isinstance(child,ast.FunctionDef) and child.name in ('remaining','read','line'))
        messages=set()
        for function in selected:
            for node in ast.walk(function):
                if isinstance(node,ast.Call):
                    name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                    index=1 if name=='require' else 0 if name=='TerminalFailure' else None
                    if index is not None and len(node.args)>index and isinstance(node.args[index],ast.Constant) and isinstance(node.args[index].value,str):
                        messages.add(node.args[index].value)
        # response_headers always calls line with framing=False; this guard is
        # only for the separate chunk decoder and is not on this source path.
        messages.discard('chunk framing cap')
        self.assertTrue(messages);self.assertLessEqual(messages,set(d.EXACT_MESSAGES))
        for message in messages:self.assertIn(d.category(h.TerminalFailure(message)),d.CODES)
        self.assertNotIn('UNKNOWN_FAILURE',{d.category(h.TerminalFailure(message)) for message in messages})
    def test_arbitrary_errors_and_values_stay_unpublished(self):
        trace=d.Trace(SHA,role='acquire');trace.enter('ASSET_HEADERS');trace.fail(RuntimeError(SECRET))
        self.assertEqual(trace.first['value']['code'],'UNKNOWN_FAILURE');self.assertNotIn(b'CANARY',d.worker_line(trace))

class ControllerDiagnosticTests(unittest.TestCase):
    def control(self):
        clock=Clock();trace=d.Trace(SHA);trace.enter('acquire');trace.fail(code='CHILD_EXIT_FAILURE')
        control=AttemptControl(clock,trace)
        control.owner=SimpleNamespace(failure='synthetic child failure',failure_at=0.,outer_end=1475.,
            lifecycle_end=None,phase_end=600.,work_end=None,postready_end=None)
        control.worker=SimpleNamespace(join=lambda timeout:None,is_alive=lambda:False)
        control.result=dict(status='incomplete',cleanup_confirmed=True,protocol_complete=False)
        control.done.set();return control,trace
    def test_conservative_false_explains_result_rejection_without_child_leak_claim(self):
        control,trace=self.control();result=control.poll()
        self.assertFalse(result['cleanup_confirmed']);self.assertTrue(control.result['cleanup_confirmed'])
        self.assertEqual(trace.cleanup,['CONTROLLER_RESULT_REJECTED'])
        self.assertEqual(trace.first['value'],dict(stage='acquire',code='CHILD_EXIT_FAILURE'))
        self.assertNotIn(b'synthetic',d.encode(trace.snapshot()))
    def test_controller_reason_is_deduplicated_and_does_not_claim_deadline(self):
        control,trace=self.control();control.poll();control.poll()
        self.assertEqual(trace.cleanup,['CONTROLLER_RESULT_REJECTED']);self.assertNotIn('DEADLINE_EXPIRED',trace.cleanup)

class WorkerBoundaryTests(unittest.TestCase):
    def capture(self):return SimpleNamespace(buffer=io.BytesIO())
    def test_actual_bootstrap_admission_exception_emits_one_closed_frame(self):
        output=self.capture()
        def reject(*args):raise activation_scope.Denied(SECRET)
        with patch.object(bootstrap,'require_bootstrap_activation',lambda:None),patch.object(bootstrap,'load_verified',lambda *args:None),\
             patch.object(bootstrap.sys,'argv',['boot','manifest',SHA,'acquire','/fake']),\
             patch.object(activation_scope,'accept_worker',reject),patch.object(bootstrap.sys,'stdout',output):
            with self.assertRaises(SystemExit):bootstrap.main()
        lines=output.buffer.getvalue().splitlines();self.assertEqual(len(lines),1)
        self.assertTrue(lines[0].startswith(b'LUNA_WORKER_DIAGNOSTIC '));self.assertNotIn(b'CANARY',lines[0])
        value=json.loads(lines[0].split(b' ',1)[1]);self.assertEqual(value['first_failure']['stage'],'WORKER_ADMISSION')
        self.assertTrue(all(a['attempts'] is None for a in value['assets']))
    def worker_failure(self,open_error=False,close_error=False):
        p=kit_plan();raw=h.canonical(p);output=self.capture();events=[]
        def opening(journal):
            if open_error:raise OSError(13,SECRET)
            journal.fd=99
        def close(journal):
            if close_error:raise OSError(9,SECRET)
        def acquire(path,deadline,event,trace):
            trace.start_assets();trace.asset_event(dict(event='asset_attempt',asset=0));trace.asset_event(dict(event='asset_exchange_intent',asset=0))
            trace.enter('ASSET_BODY');trace.received(3);trace.written(2);raise OSError(5,SECRET)
        with doubles(Clock()),patch.object(runtime,'bounded_file',lambda *args:raw),patch.object(runtime,'bind_actions_roots',lambda roots:None),\
             patch.object(runtime,'CLAIM_ROOT',Path(p['paths']['claim_root'])),\
             patch.object(activation_scope,'require_role',lambda *roles:dict(claim_sha256=h.digest(raw))),\
             patch.object(kit_worker.WorkerJournal,'open',opening),patch.object(kit_worker.WorkerJournal,'event',lambda self,event:events.append(event)),\
             patch.object(kit_worker.WorkerJournal,'close',close),patch.object(a,'acquire_assets',acquire),\
             patch.object(kit_worker.sys,'stdout',output):
            with self.assertRaises(SystemExit):kit_worker.main('acquire',str(Path(p['paths']['claim_root'])/'ONE_SHOT_CPU_ATTEMPT.json'),SHA)
        lines=output.buffer.getvalue().splitlines();self.assertEqual(len(lines),1);self.assertNotIn(b'CANARY',lines[0])
        return json.loads(lines[0].split(b' ',1)[1])
    def test_worker_journal_open_failure_is_not_a_dns_guess(self):
        value=self.worker_failure(open_error=True)
        self.assertEqual(value['first_failure'],dict(stage='WORKER_JOURNAL',code='OS_ACCESS_DENIED'))
        self.assertIsNone(value['assets'][0]['exchange_intents'])
    def test_worker_partial_transfer_and_cleanup_preserve_first_failure(self):
        value=self.worker_failure(close_error=True)
        self.assertEqual(value['first_failure'],dict(stage='ASSET_BODY',code='OS_ERROR'))
        self.assertEqual(value['assets'][0]['received_bytes'],3);self.assertEqual(value['assets'][0]['written_bytes'],2)
        self.assertEqual(value['cleanup_categories'],['JOURNAL_CLOSE_FAILED'])
    def test_parent_merges_only_finite_manifest_bound_worker_receipt(self):
        child=d.Trace(SHA,role='acquire');child.start_assets();child.enter('ASSET_TLS');child.fail(OSError(SECRET))
        t=d.Trace(SHA);evidence=SimpleNamespace(file_bytes={'validation.log':20},output=Path('/fake'))
        with patch.object(runtime,'bounded_file',lambda *args:d.worker_line(child)):
            kit.collect_worker_diagnostics(None,evidence,t)
        self.assertEqual(t.children['acquire']['worker']['first_failure']['stage'],'ASSET_TLS')
        self.assertNotIn('CANARY',d.encode(t.snapshot()).decode())

class OpenSSLPolicyTests(unittest.TestCase):
    def test_exact_source_backed_sonames_have_baseline_cache_candidates(self):
        result=host.parse_loader_cache(cache())
        self.assertEqual(result['libssl.so.3'],'/lib/x86_64-linux-gnu/libssl.so.3')
        self.assertEqual(result['libcrypto.so.3'],'/lib/x86_64-linux-gnu/libcrypto.so.3')
    def test_old_abi_missing_and_ambiguous_openssl_stop(self):
        rows=[(name,'/lib/x86_64-linux-gnu/'+name,0) for name in host.HOST_POLICY['allowed_libraries']]
        variants=[row for row in rows if row[0]!='libssl.so.3']
        cases=[variants,variants+[('libssl.so.1.1','/lib/x86_64-linux-gnu/libssl.so.1.1',0)],
            rows+[('libcrypto.so.3','/usr/lib/x86_64-linux-gnu/libcrypto.so.3',0)],
            rows+[('libssl.so.3','/lib/x86_64-linux-gnu/libssl.so.3',1<<62)]]
        for entries in cases:
            with self.assertRaises(h.TerminalFailure):host.parse_loader_cache(cache(entries))
    def extracted_runtime(self,missing=False):
        resolved=dict(host_libraries={name:dict(path='/fake/'+name,sha256='1'*64) for name in host.HOST_POLICY['allowed_libraries']},
            interpreter=dict(path='/lib64/ld-linux-x86-64.so.2'),archive_library_dirs=['llama-b11349'])
        if missing:resolved['host_libraries'].pop('libcrypto.so.3')
        members=[dict(name='llama-b11349/llama-server',type='file',size=1,sha256=h.PINS['server'])]
        elf=dict(needed=['libssl.so.3','libcrypto.so.3'],interpreter='/lib64/ld-linux-x86-64.so.2',rpath='$ORIGIN',runpath=None)
        changed=[]
        with doubles(Clock()),patch.object(host,'recheck_host_bindings',lambda *args:None),\
             patch.object(host,'hash_file',lambda *args:h.PINS['server']),patch.object(a,'inspect_elf',lambda *args:elf),\
             patch.object(Path,'resolve',lambda self,**kw:self),patch.object(Path,'is_dir',lambda self:True),\
             patch.object(Path,'is_symlink',lambda self:False),patch.object(host.os,'chmod',lambda *args,**kw:changed.append(args[0])):
            if missing:
                with self.assertRaises(h.TerminalFailure):host.validate_extracted_runtime(resolved,'/fake/runtime',members,h.Deadline(Clock(),60))
            else:host.validate_extracted_runtime(resolved,'/fake/runtime',members,h.Deadline(Clock(),60))
        return changed
    def test_exact_needed_openssl_closure_passes_inert_elf_validation(self):self.assertEqual(len(self.extracted_runtime()),1)
    def test_unresolved_needed_crypto_stops_before_executable_mode(self):self.assertEqual(self.extracted_runtime(missing=True),[])

class BootstrapExitTests(unittest.TestCase):
    def run_tail(self,exception):
        source=ast.parse(Path(bootstrap.__file__).read_bytes());tail=source.body[-1];out=io.StringIO()
        def main():out.write('{"reason_code":"OPERATIONAL_FAILURE"}\n');raise exception
        with self.assertRaises(SystemExit):exec(compile(ast.Module(body=[tail],type_ignores=[]),'bootstrap-tail','exec'),{'__name__':'__main__','main':main,'sys':SimpleNamespace(stdout=out)})
        return out.getvalue()
    def test_intentional_exit_does_not_add_source_failure_label(self):
        self.assertEqual(self.run_tail(SystemExit(1)).splitlines(),['{"reason_code":"OPERATIONAL_FAILURE"}'])
    def test_unexpected_bootstrap_exception_is_sanitized(self):
        text=self.run_tail(ValueError(SECRET));self.assertIn('SOURCE_OR_EXECUTION_BLOCKED',text);self.assertNotIn('CANARY',text)
    def test_worker_admission_category_is_closed(self):
        t=d.Trace(SHA,role='acquire');t.enter('WORKER_ADMISSION')
        t.fail(h.TerminalFailure('actual parent argv differs from claim'))
        self.assertEqual(t.worker_snapshot()['first_failure']['code'],'WORKER_PARENT_ARGV')
    def test_helper_stays_free_of_native_stack(self):
        self.assertEqual(bootstrap.HELPER_MODULES,('actions_policy','diagnostics','activation_scope','cpu_harness','frozen_renderer','isolated_helper'))
        self.assertFalse(set(bootstrap.HELPER_MODULES)&{'ssl','guarded_runtime','acquisition_source','attempt_control'})

if __name__=='__main__':unittest.main()
