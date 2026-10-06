"""Independent-review regressions, using only deterministic inert doubles."""
from copy import deepcopy
from dataclasses import replace
import unittest
import cpu_harness as h
import evidence_validation as ev
import frozen_renderer as renderer
from test_cpu_harness import (Clock, FakeChild, FakeMonitor, FakeTransport, Reader, ALIAS,
    LEXICON, LEXICON_SHA, source_for, plans, fake_count, completion, response,
    pass_integrity, IntegrityError)


class CleanupReviewTests(unittest.TestCase):
    def exchange(self, transport, clock, ledger=None, validator=lambda raw:raw):
        ledger=ledger or h.RequestLedger()
        return h.checked_exchange(ledger,'health',None,None,lambda:None,transport,clock,[180],
                                  validator,h.EvidenceBudget())
    def test_watchdog_creation_failure_terminal_before_send(self):
        clock=Clock();transport=FakeTransport(response(),clock);ledger=h.RequestLedger()
        def broken(deadline):raise OSError('fake watchdog creation')
        transport.arm_watchdog=broken
        with self.assertRaises(OSError):self.exchange(transport,clock,ledger)
        self.assertIsNotNone(ledger.terminal);self.assertEqual(transport.sent,[])
    def test_reader_close_failure_does_not_skip_watchdog_cleanup(self):
        clock=Clock();transport=FakeTransport(response(),clock);ledger=h.RequestLedger()
        original=transport.send
        def send(*args,**kwargs):
            reader=original(*args,**kwargs)
            def broken():raise OSError('fake close')
            reader.close=broken
            return reader
        transport.send=send
        with self.assertRaises(h.TerminalFailure):self.exchange(transport,clock,ledger)
        self.assertIsNotNone(ledger.terminal)
        self.assertTrue(transport.monitor.cancelled and transport.monitor.joined)
        with self.assertRaises(h.TerminalFailure):ledger.consume('models')
    def test_monitor_join_receives_timeout_and_late_cleanup_is_terminal(self):
        clock=Clock();transport=FakeTransport(response(),clock);ledger=h.RequestLedger();timeouts=[]
        def delayed(timeout=None):timeouts.append(timeout);clock.advance(100)
        transport.monitor.join=delayed
        with self.assertRaises(h.TerminalFailure):self.exchange(transport,clock,ledger)
        self.assertEqual(timeouts,[7]);self.assertIsNotNone(ledger.terminal)
    def test_monitor_cancel_and_join_exception_isolated(self):
        clock=Clock();transport=FakeTransport(response(),clock);ledger=h.RequestLedger();calls=[]
        def cancel():calls.append('cancel');raise OSError('fake cancel')
        def join(timeout):calls.append('join');raise OSError('fake join')
        transport.monitor.cancel=cancel;transport.monitor.join=join
        with self.assertRaises(h.TerminalFailure):self.exchange(transport,clock,ledger)
        self.assertEqual(calls,['cancel','join']);self.assertIsNotNone(ledger.terminal)
    def test_failure_journal_does_not_skip_children(self):
        clock=Clock()
        def journal(event):raise OSError('fake journal')
        supervisor=h.SyntheticSupervisor(clock,journal)
        first,second=FakeChild(),FakeChild()
        supervisor.handles={'first':first,'second':second}
        supervisor.fail('original failure')
        self.assertIsNotNone(first.poll());self.assertIsNotNone(second.poll())
        self.assertEqual(supervisor.failure,'original failure')
        self.assertTrue(supervisor.cleanup_errors)
    def test_first_child_stop_failure_does_not_skip_second(self):
        supervisor=h.SyntheticSupervisor(Clock());first,second=FakeChild(),FakeChild()
        def broken():raise OSError('fake terminate')
        first.terminate=broken;supervisor.handles={'first':first,'second':second}
        supervisor.fail('failed')
        self.assertIsNotNone(second.poll());self.assertTrue(supervisor.cleanup_errors)
    def test_socket_close_failure_does_not_skip_children_or_finalize(self):
        supervisor=h.SyntheticSupervisor(Clock());child=FakeChild();reader=Reader(b'')
        def broken():raise OSError('fake close')
        reader.close=broken;supervisor.sockets=[reader];supervisor.handles={'owned':child}
        supervisor.fail('failed')
        self.assertIsNotNone(child.poll())
        self.assertFalse(supervisor.finalize()['cleanup_confirmed'])
    def test_intent_journal_failure_never_launches_and_blocks_later_phase(self):
        calls=[]
        def journal(event):raise OSError('fake intent persistence')
        supervisor=h.SyntheticSupervisor(Clock(),journal)
        with self.assertRaises(OSError):supervisor.launch('server',{},180,lambda *_:calls.append('spawn'))
        self.assertEqual(calls,[]);self.assertIsNotNone(supervisor.failure)
        with self.assertRaises(h.TerminalFailure):supervisor.launch('helper',{},15,lambda *_:FakeChild())
    def test_first_failure_starts_cleanup_clock_not_finalize(self):
        clock=Clock();supervisor=h.SyntheticSupervisor(clock)
        supervisor.fail('failed');clock.advance(21)
        self.assertFalse(supervisor.finalize()['cleanup_confirmed'])
    def test_source_drift_rejected_before_off_plan_counter_call(self):
        plan=plans()[0];calls=[]
        with self.assertRaises(h.TerminalFailure):
            h.measured_candidate(plan,'Z0 changed source',ALIAS,LEXICON,LEXICON_SHA,renderer,
                                 lambda body:(calls.append(body),fake_count(body))[1])
        self.assertEqual(calls,[])


def final_fixture(active_subset=None, ratios=None):
    sources={row:source_for(row) for row in h.ROW_IDS}
    ps=[]
    for row in h.ROW_IDS:
        def count(body,row=row):
            n=fake_count(body)
            return 100 if n==40 and active_subset is not None and row not in active_subset else n
        ps.append(h.preflight_pair(row,sources[row],ALIAS,LEXICON,LEXICON_SHA,renderer,count))
    by_id={p.row_id:p for p in ps}
    ledger=h.RequestLedger();transcripts=[];intervals=[]
    now=.1
    interval_by_key={}
    for row,arm in h.SCHEDULE:
        duration=(ratios or {}).get(row,1.2) if arm=='candidate' else 1.
        interval_by_key[(row,arm)]=dict(row=row,arm=arm,start=10+sum(i['end']-i['start']+.1 for i in intervals),end=0)
        interval=interval_by_key[(row,arm)];interval['end']=interval['start']+duration
        interval.update(perf_start_ns=round(interval['start']*1e9),total_ns=round(duration*1e9))
        interval['perf_end_ns']=interval['perf_start_ns']+interval['total_ns'];intervals.append(interval)
    arm_positions={}
    for kind,row,arm in ledger.queue:
        if kind in ('health','models'):
            body=None
            raw=h.canonical({'status':'ok'} if kind=='health' else {'data':[{'id':ALIAS}]})
        else:
            p=by_id[row]
            receipt=(p.baseline if arm=='baseline' else p.provisional) if kind!='completion' else (
                     p.baseline if arm=='baseline' else p.candidate)
            body=receipt.body
            raw=h.canonical(completion(count=receipt.count) if kind=='completion' else
                            dict(object='response.input_tokens',input_tokens=receipt.count))
        if kind in ('recurring','completion'):
            key=(row,'candidate' if kind=='recurring' else arm)
            index=arm_positions.get(key,0);arm_positions[key]=index+1
            now=interval_by_key[key]['start']+.01+index*.02
        wire=response(raw)
        transcripts.append(dict(kind=kind,row=row,arm=arm,request_body=body,response_wire=wire,
            request_sha256=h.digest(body) if body is not None else None,response_sha256=h.digest(wire),
            start=now,validated_end=now+.001,deadline=now+h.ENDPOINTS[kind][3]-.1))
        now+=.01
    return ps,sources,transcripts,intervals


def validate_fixture(fixture):
    ps,sources,transcripts,intervals=fixture
    return ev.validate_final_evidence(ps,sources,ALIAS,LEXICON,LEXICON_SHA,renderer,
        transcripts,intervals,1e-9,pass_integrity,IntegrityError)


class FinalEvidenceReviewTests(unittest.TestCase):
    def test_full_442_protocol_reconciliation_and_176_cost_observations(self):
        result=validate_fixture(final_fixture())
        self.assertEqual(result['tokens']['count_only_requests'],264)
        self.assertEqual(result['cost']['groups']['all_rows']['ratios']['n'],88)
        self.assertEqual(len(result['all_rows']),88)
        self.assertIsNone(result['semantic_quality_claim'])
    def test_changed_active_membership_rejected(self):
        fixture=final_fixture();fixture[0][0]=replace(fixture[0][0],active=False)
        with self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_absent_and_duplicate_completions_rejected(self):
        for duplicate in (False,True):
            fixture=final_fixture()
            if duplicate:fixture[2][-1]=deepcopy(fixture[2][-2])
            else:fixture[2].pop()
            with self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_request_source_arm_and_pin_mismatches_rejected(self):
        for kind in ('request','source','arm','pin'):
            fixture=final_fixture()
            if kind=='request':fixture[2][-1]['request_body']=b'changed'
            elif kind=='source':fixture[1]['N001']='Z0 changed'
            elif kind=='arm':fixture[2][-1]['arm']='candidate'
            else:fixture[0][0]=replace(fixture[0][0],baseline=replace(fixture[0][0].baseline,template='0'*64))
            with self.subTest(kind=kind),self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_response_usage_mismatch_and_scoreable_empty_output(self):
        fixture=final_fixture();record=next(r for r in fixture[2] if r['kind']=='completion')
        raw=completion('',count=20);wire=response(h.canonical(raw));record.update(response_wire=wire,response_sha256=h.digest(wire))
        result=validate_fixture(fixture)
        self.assertTrue(result['all_rows'][0]['arms']['baseline']['scoreable_generation_failure'])
        raw['usage']['prompt_tokens']=21;wire=response(h.canonical(raw));record.update(response_wire=wire,response_sha256=h.digest(wire))
        with self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_recurring_count_outside_candidate_timing_rejected(self):
        fixture=final_fixture();record=next(r for r in fixture[2] if r['kind']=='recurring')
        record.update(start=9,validated_end=9.001,deadline=13.9)
        with self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_request_deadline_and_framing_evidence_rejected(self):
        for violation in ('late','frame'):
            fixture=final_fixture();record=fixture[2][-1]
            if violation=='late':record['validated_end']=record['deadline']
            else:
                wire=record['response_wire'].replace(b'Content-Length',b'Content-Encoding',1)
                record.update(response_wire=wire,response_sha256=h.digest(wire))
            with self.assertRaises(h.TerminalFailure):validate_fixture(fixture)
    def test_active_subgroup_failure_cannot_hide_in_pool(self):
        pairs=(0,1,2,3,4,6,8,10)
        active={f'N{3*f+d:03d}' for f in pairs for d in (1,2)}
        active|={f'N{3*f+1:03d}' for f in (5,7)}
        active|={f'N{3*f+3:03d}' for f in (0,2,4,6,8,10)}
        active|={f'N{i:03d}' for i in range(41,49)}
        self.assertEqual(len(active),32)
        result=validate_fixture(final_fixture(active,{'N001':1.3,'N002':1.3}))
        self.assertLessEqual(result['cost']['groups']['all_new']['ratios']['p95'],1.25)
        self.assertGreater(result['cost']['groups']['active_new']['ratios']['p95'],1.25)
        self.assertEqual(result['cost']['status'],'fail')
    def test_exact_125_ratio_boundary_passes(self):
        result=validate_fixture(final_fixture(ratios={row:1.25 for row in h.ROW_IDS}))
        self.assertEqual(result['cost']['status'],'pass')
    def test_perf_counter_ns_is_authoritative_not_monotonic_span(self):
        fixture=final_fixture()
        current=0
        for interval in fixture[3]:
            interval['perf_start_ns']=current
            interval['total_ns']=1_300_000_000 if interval['arm']=='candidate' else 1_000_000_000
            interval['perf_end_ns']=current+interval['total_ns'];current=interval['perf_end_ns']+100_000_000
        result=validate_fixture(fixture)
        self.assertEqual(result['cost']['status'],'fail')
        self.assertEqual(result['cost']['groups']['all_rows']['ratios']['median'],1.3)


if __name__=='__main__':unittest.main()
