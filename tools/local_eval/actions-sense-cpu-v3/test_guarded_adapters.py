"""Native adapter source tests with ALL native effects replaced by inert doubles.

No thread, child, socket, model, helper, file writer or live source reader runs.
The hard gate is replaced only within the isolated double context; the actual
entry points are separately tested as unconditionally disabled.
"""
from contextlib import ExitStack, contextmanager
import io
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys
import cpu_harness as h
import guarded_runtime as runtime
from isolated_helper import helper_benchmark, validate_helper_result
from test_cpu_harness import (Clock, FakeChild, FakeMonitor, ALIAS, LEXICON, LEXICON_SHA,
    source_for, plans)


def forbidden(*args,**kwargs):
    raise AssertionError('native operation forbidden in adapter test')


class FakeThread:
    def __init__(self,target=None,args=(),name='fake-thread',daemon=True):
        self.target,self.args,self.name=target,args,name
        self.alive=False;self.timeouts=[]
    def start(self):self.alive=True
    def is_alive(self):return self.alive
    def join(self,timeout=None):self.timeouts.append(timeout);self.alive=False


class FakePipe:
    def fileno(self):return 99
    def close(self):pass


class NativeChild(FakeChild):
    def __init__(self):
        super().__init__();self.pid=123456;self.stdout=FakePipe()


class FakeEvidence:
    def __init__(self):self.budget=h.EvidenceBudget();self.saved=[];self.closed=False
    def append(self,name,data):self.saved.append((name,data))
    def json(self,name,data):self.saved.append((name,data))
    def close(self):self.closed=True


@contextmanager
def doubles(clock):
    # Deny every native source operation before replacing the activation gate.
    with ExitStack() as stack:
        for name in ('open','read','write','fsync','close','walk'):
            stack.enter_context(patch.object(runtime.os,name,forbidden))
        stack.enter_context(patch.object(runtime.socket,'socket',forbidden))
        stack.enter_context(patch.object(runtime.subprocess,'Popen',forbidden))
        stack.enter_context(patch.object(runtime.shutil,'disk_usage',forbidden))
        stack.enter_context(patch.object(runtime,'bounded_file',forbidden))
        stack.enter_context(patch.object(runtime.threading,'Thread',FakeThread))
        stack.enter_context(patch.object(runtime.time,'monotonic',clock))
        stack.enter_context(patch.object(runtime,'PERSISTENCE_CHECKPOINT',None))
        stack.enter_context(patch.object(runtime,'COORDINATOR_CANCEL_EVENT',None))
        stack.enter_context(patch.object(runtime,'require_activation',lambda:None))
        yield


def supervisor(clock):
    evidence=FakeEvidence()
    owner=runtime.OwnedSupervisor(clock(),99,evidence,object(),'/fake/staging')
    owner.record=lambda event:evidence.saved.append(('journal',event))
    owner.monitor=FakeThread(name='resources');owner.monitor.start()
    owner.deadline_monitor=FakeThread(name='deadlines');owner.deadline_monitor.start()
    return owner


class DisabledEntryTests(unittest.TestCase):
    def test_native_entry_points_disabled_before_any_io(self):
        with patch.object(runtime.subprocess,'Popen',forbidden),patch.object(runtime.socket,'socket',forbidden),\
             patch.object(runtime.os,'open',forbidden):
            for operation in (lambda:runtime.main(),lambda:runtime.claim_once({}),
                              lambda:runtime.bounded_file('/fake',10),lambda:runtime.load_audited_components(),
                              lambda:runtime.load_source_only_rows(),lambda:runtime.cgroup_headroom(10)):
                with self.assertRaises(h.Disabled):operation()
    def test_supervisor_arming_disabled_without_creating_thread(self):
        owner=runtime.OwnedSupervisor(0,99,FakeEvidence(),object(),'/fake')
        with patch.object(runtime.threading,'Thread',forbidden),self.assertRaises(h.Disabled):owner.arm()
    def test_helper_entry_disabled_before_file_or_measurement(self):
        import isolated_helper
        with patch.object(runtime.os,'open',forbidden),self.assertRaises(h.Disabled):isolated_helper.main()


class NativeLifecycleDoubleTests(unittest.TestCase):
    def test_two_independent_monitors_are_source_wired(self):
        clock=Clock()
        with doubles(clock):
            owner=runtime.OwnedSupervisor(0,99,FakeEvidence(),object(),'/fake')
            owner.arm()
            self.assertTrue(owner.monitor.is_alive() and owner.deadline_monitor.is_alive())
            self.assertIsNot(owner.monitor,owner.deadline_monitor)
    def test_native_launch_intent_precedes_fake_popen(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);child=NativeChild();calls=[]
            def popen(*args,**kwargs):
                calls.append((args,kwargs))
                self.assertTrue(owner.intents['server'].pending)
                self.assertEqual(owner.intents['server'].deadline,180)
                self.assertEqual(owner.lifecycle_end,800)
                self.assertEqual(owner.work_end,780)
                return child
            with patch.object(runtime.subprocess,'Popen',popen):
                owner.launch('server',h.server_spec('/fake/server','/fake/model','/fake/template',
                             '/fake/cwd',18080,ALIAS),180,'server.log')
            self.assertFalse(owner.intents['server'].pending)
            self.assertEqual(calls[0][1]['env'],{'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'})
            self.assertFalse(calls[0][1]['shell']);self.assertTrue(calls[0][1]['close_fds'])
    def test_native_late_popen_adopts_and_stops_fake_child(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);child=NativeChild()
            def popen(*args,**kwargs):clock.advance(181);return child
            with patch.object(runtime.subprocess,'Popen',popen),self.assertRaises(h.TerminalFailure):
                owner.launch('server',h.child_spec('/fake/server',[],'/fake'),180,'server.log')
            self.assertIs(owner.intents['server'].process,child);self.assertIsNotNone(child.poll())
    def test_native_intent_failure_never_calls_popen(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock)
            def broken(event):raise OSError('fake journal')
            owner.record=broken
            with self.assertRaises(OSError):owner.launch('server',h.child_spec('/fake/server',[],'/fake'),180,'server.log')
            self.assertIsNotNone(owner.failure)
    def test_native_cleanup_isolates_socket_and_child_failure(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);first,second=NativeChild(),NativeChild()
            def broken():raise OSError('fake terminate')
            first.terminate=broken
            owner.intents={'a':runtime.Intent('a',{},180,False,first),'b':runtime.Intent('b',{},180,False,second)}
            class BadSocket:
                def shutdown(self,how):raise OSError('fake shutdown')
                def close(self):raise OSError('fake close')
            owner.connections.add(BadSocket());owner.fail('failure')
            self.assertIsNotNone(second.poll());self.assertTrue(owner.cleanup_errors)
            result=owner.finalize();self.assertFalse(result['cleanup_confirmed'])
    def test_native_version_output_cap_stops_without_retaining_excess(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);child=NativeChild();intent=runtime.Intent('version',{},15,False,child)
            owner.intents['version']=intent
            chunks=iter([b'x'*8192]*9)
            with patch.object(runtime.os,'read',lambda *args:next(chunks)):
                owner._read_log(intent,'version.log')
            retained=sum(len(v) for name,v in owner.evidence.saved if name=='version.log')
            self.assertEqual(retained,65536);self.assertIsNotNone(owner.failure)
    def test_native_security_warning_stops_and_model_marker_sets_ready(self):
        for data,failed in ((b'model loaded\n',False),(b'security: unsafe configuration\n',True)):
            clock=Clock()
            with doubles(clock):
                owner=supervisor(clock);child=NativeChild();intent=runtime.Intent('server',{},180,False,child)
                owner.intents['server']=intent;chunks=iter([data,b''])
                with patch.object(runtime.os,'read',lambda *args:next(chunks)):
                    owner._read_log(intent,'server.log')
                self.assertEqual(owner.failure is not None,failed)
                self.assertEqual(owner.loaded.is_set(),not failed)


class HelperDoubleTests(unittest.TestCase):
    def test_fixed_helper_passes_with_receipt_only_fake_clock(self):
        ps=plans();receipts={h.digest(r.body):r.count for p in ps for r in (p.baseline,p.provisional)}
        rows=[dict(id=p.row_id,source=source_for(p.row_id),reason=p.reason,active=p.active) for p in ps]
        ticks=iter(range(1000,2_000_000,1000))
        result=helper_benchmark(rows,ALIAS,LEXICON,LEXICON_SHA,receipts,lambda:next(ticks))
        self.assertEqual((result['priming_renders'],result['measured_renders'],result['total_renders']),(88,880,968))
        self.assertEqual(result['render_ns']['p95'],1000)
        result['peak_rss_bytes']=10*h.MIB
        validate_helper_result(result,1e-9)
        result['peak_rss_bytes']=32*h.MIB+1
        with self.assertRaises(h.TerminalFailure):validate_helper_result(result,1e-9)
    def test_helper_missing_receipt_does_not_silently_abstain(self):
        ps=plans();rows=[dict(id=p.row_id,source=source_for(p.row_id),reason=p.reason,active=p.active) for p in ps]
        with self.assertRaises(h.TerminalFailure):helper_benchmark(rows,ALIAS,LEXICON,LEXICON_SHA,{},lambda:1000)


class NativeTransportResourceDoubleTests(unittest.TestCase):
    def test_direct_owned_socket_with_bounded_reads_and_no_proxy(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);sent=[];timeouts=[];connections=[]
            raw=b'HTTP/1.1 200 OK\r\nContent-Length: 15\r\n\r\n{"status":"ok"}'
            class FakeSocket:
                def __init__(self,*args):self.raw=raw;self.closed=False;self.max_read=0
                def settimeout(self,value):timeouts.append(value)
                def connect(self,address):connections.append(address)
                def send(self,data):sent.append(bytes(data));return len(data)
                def recv(self,n):
                    self.max_read=max(n,self.max_read);result=self.raw[:n];self.raw=self.raw[n:];return result
                def close(self):self.closed=True
                def shutdown(self,how):pass
            socket_double=FakeSocket()
            transport=runtime.LoopbackTransport(owner,18080)
            with patch.object(runtime.socket,'socket',lambda *args:socket_double):
                result=h.checked_exchange(h.RequestLedger(),'health',None,None,lambda:None,transport,clock,[180],
                    lambda raw:h.readiness_response('health',raw,ALIAS),runtime.WireCapture())
            self.assertEqual(connections,[('127.0.0.1',18080)])
            self.assertTrue(socket_double.closed);self.assertLessEqual(socket_double.max_read,8192)
            self.assertTrue(all(0<t<=5 for t in timeouts))
            self.assertIn(b'Connection: close',b''.join(sent));self.assertNotIn(b'Authorization',b''.join(sent))
    def test_connect_failure_closes_and_removes_owned_socket(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);closed=[]
            class BadSocket:
                def settimeout(self,value):pass
                def connect(self,address):raise OSError('fake connect')
                def close(self):closed.append(True)
            transport=runtime.LoopbackTransport(owner,18080)
            with patch.object(runtime.socket,'socket',lambda *args:BadSocket()),self.assertRaises(OSError):
                h.checked_exchange(h.RequestLedger(),'health',None,None,lambda:None,transport,clock,[180],
                                   lambda raw:raw,runtime.WireCapture())
            self.assertEqual(closed,[True]);self.assertEqual(owner.connections,set())
    def test_effective_cgroup_headroom_uses_stricter_ancestor(self):
        clock=Clock()
        files={'/proc/self/cgroup':b'0::/tenant/job\n',
               '/proc/self/mountinfo':b'1 0 0:1 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n',
               '/sys/fs/cgroup/tenant/job/memory.max':str(1024*h.MIB).encode(),
               '/sys/fs/cgroup/tenant/job/memory.current':str(128*h.MIB).encode(),
               '/sys/fs/cgroup/tenant/memory.max':str(512*h.MIB).encode(),
               '/sys/fs/cgroup/tenant/memory.current':str(64*h.MIB).encode()}
        with doubles(clock),patch.object(runtime,'bounded_file',lambda path,cap:files[str(path)]):
            self.assertEqual(runtime.cgroup_headroom(10*h.GIB,hierarchy_root_verified=True),448*h.MIB)
    def test_unsupported_or_unknown_cgroup_is_terminal(self):
        for raw in (b'1:memory:/legacy\n',b'0::/../../escape\n',b'0::/first\n0::/second\n'):
            with doubles(Clock()),patch.object(runtime,'bounded_file',lambda path,cap:raw),self.assertRaises(h.TerminalFailure):
                runtime.cgroup_headroom(10*h.GIB)


class AdapterReviewCorrectionTests(unittest.TestCase):
    def test_native_timeout_expired_uses_terminate_then_kill(self):
        for unkillable in (False,True):
            with doubles(Clock()):
                owner=supervisor(Clock())
                class TimeoutChild(NativeChild):
                    def terminate(self):self.actions.append('terminate')
                    def kill(self):
                        self.actions.append('kill')
                        if not unkillable:self.exit=-9
                    def wait(self,timeout):
                        self.actions.append(('wait',timeout))
                        if self.exit is None:raise runtime.subprocess.TimeoutExpired('fake-owned',timeout)
                        return self.exit
                child=TimeoutChild();intent=runtime.Intent('server',{},180,False,child)
                if unkillable:
                    with self.assertRaises(runtime.subprocess.TimeoutExpired):owner._stop(intent)
                    self.assertFalse(intent.exit_confirmed)
                else:
                    owner._stop(intent);self.assertTrue(intent.exit_confirmed)
                self.assertEqual(child.actions,['terminate',('wait',3),'kill',('wait',3)])
    def test_journal_stall_does_not_hold_ownership_lock(self):
        class Lock:
            def __init__(self):self.held=False
            def __enter__(self):
                if self.held:raise AssertionError('watchdog blocked behind ownership lock')
                self.held=True
            def __exit__(self,*args):self.held=False
        with doubles(Clock()):
            owner=supervisor(Clock());owner.lock=Lock();owner.evidence.lock=Lock();child=NativeChild()
            owner.intents['server']=runtime.Intent('server',{},180,False,child)
            def blocked_write(*args):
                self.assertFalse(owner.lock.held)
                owner.fail('watchdog while journal is blocked')
                self.assertIsNotNone(child.poll())
            with patch.object(runtime,'persistent_write',blocked_write):
                runtime.OwnedSupervisor.record(owner,dict(event='fake'))
    def test_verified_bytes_bypass_stale_import_loader_and_empty_package(self):
        raw={'resources.py':b'marker="verified source"\n',
             'myutils/local_translation.py':b'class LocalTranslationError(Exception): pass\n',
             'myutils/local_translation_integrity.py':b'from myutils.local_translation import LocalTranslationError\ndef validate_integrity(a,b): return b\n'}
        names=['resources','myutils','myutils.local_translation','myutils.local_translation_integrity']
        saved={name:sys.modules.get(name) for name in names}
        for name in names:sys.modules.pop(name,None)
        try:
            with doubles(Clock()),patch.object(runtime,'pinned_file',lambda path,pin,cap:raw[str(path.relative_to(runtime.AUDITED))]),\
                 patch.object(runtime,'bounded_file',lambda path,cap:b''),patch.object(runtime.importlib,'import_module',forbidden):
                resource,error,checker=runtime.load_audited_components()
                self.assertEqual(resource.marker,'verified source');self.assertEqual(checker('a','b'),'b')
                self.assertEqual(sys.modules['myutils'].__path__,[])
        finally:
            for name in names:
                sys.modules.pop(name,None)
                if saved[name] is not None:sys.modules[name]=saved[name]
    def test_hidden_cgroup_ancestors_and_unverified_namespace_rejected(self):
        files={'/proc/self/cgroup':b'0::/tenant/job\n',
               '/proc/self/mountinfo':b'1 0 0:1 /tenant/job /sys/fs/cgroup rw - cgroup2 cgroup rw\n'}
        with doubles(Clock()),patch.object(runtime,'bounded_file',lambda path,cap:files[str(path)]):
            with self.assertRaises(h.TerminalFailure):runtime.cgroup_headroom(10*h.GIB,hierarchy_root_verified=True)
            with self.assertRaises(h.TerminalFailure):runtime.cgroup_headroom(10*h.GIB)
    def test_growth_scan_permission_error_terminal(self):
        def walk(*args,**kwargs):kwargs['onerror'](PermissionError('fake EACCES'))
        with doubles(Clock()),patch.object(runtime.os,'walk',walk),self.assertRaises(PermissionError):
            runtime.owned_growth('/fake')
    def test_log_thread_start_failure_stops_adopted_child(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock);child=NativeChild()
            class BadThread(FakeThread):
                def start(self):raise RuntimeError('fake thread start')
            with patch.object(runtime.subprocess,'Popen',lambda *args,**kwargs:child),\
                 patch.object(runtime.threading,'Thread',BadThread),self.assertRaises(RuntimeError):
                owner.launch('server',h.child_spec('/fake/server',[],'/fake'),180,'server.log')
            self.assertIsNotNone(owner.failure);self.assertIsNotNone(child.poll())
    def test_failed_join_does_not_skip_other_cleanup(self):
        clock=Clock()
        with doubles(clock):
            owner=supervisor(clock)
            class BadThread(FakeThread):
                def join(self,timeout=None):raise RuntimeError('fake join')
            owner.readers=[BadThread(name='bad')]
            result=owner.finalize()
            self.assertTrue(owner.evidence.closed);self.assertFalse(result['cleanup_confirmed'])
    def test_mid_candidate_failure_preserves_prior_count_and_partial_wire(self):
        from test_cpu_harness import completion,response,Reader,FakeMonitor,pass_integrity,IntegrityError
        clock=Clock();ps=plans();by_id={p.row_id:p for p in ps};ledger=h.RequestLedger()
        for item in ledger.queue[:178]:ledger.consume(*item)
        ledger.seal_preflight(ps)
        class Transport:
            def __init__(self):self.calls=0
            def arm_watchdog(self,deadline):self.deadline=deadline;self.request_started=clock();return FakeMonitor()
            def send(self,method,endpoint,body,remaining,**kwargs):
                self.calls+=1
                if self.calls==1:return Reader(response(h.canonical(completion(count=20))))
                if self.calls==2:return Reader(response(h.canonical(dict(object='response.input_tokens',input_tokens=20))))
                return Reader(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{"object":')
        with doubles(clock),patch.dict(h.PINS,{'lexicon':LEXICON_SHA}):
            owner=supervisor(clock);owner.work_end=780;owner.postready_end=600
            with self.assertRaises(h.TerminalFailure):
                runtime.measured_schedule_source(owner,Transport(),ALIAS,LEXICON,
                    {row:source_for(row) for row in h.ROW_IDS},by_id,pass_integrity,IntegrityError,owner.evidence,ledger)
            wires=[r for name,r in owner.evidence.saved if name=='wire.jsonl']
            self.assertEqual(len(wires),3);self.assertEqual(wires[1]['status'],'validated')
            self.assertEqual(wires[2]['status'],'failed');self.assertTrue(bytes.fromhex(wires[2]['response_wire_hex']).endswith(b'{"object":'))
            rows=[r for name,r in owner.evidence.saved if name=='all_rows.json'][0]
            self.assertEqual(rows[0]['arms']['candidate']['status'],'operational_failure')
            self.assertEqual(rows[1]['arms']['baseline']['status'],'unobserved')
            self.assertEqual(ledger.total,181)


if __name__=='__main__':unittest.main()
