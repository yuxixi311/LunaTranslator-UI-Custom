"""Synthetic only: zero HTTP, socket, subprocess, model, acquisition, real claim.

Sources and lexical entries here are invented mechanical fixtures, never the
fresh study sources or parent-held criteria. Files exist only in private /tmp.
"""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import cpu_harness as h
import frozen_renderer as renderer


ATTEMPT = '0123456789ab4def8123456789abcdef'
ALIAS = h.alias_for(ATTEMPT)
LEXICON = h.canonical(dict(version='sense-candidate-prefix-v1', entries=[
    dict(headword=f'Z{i}', senses=['甲', '乙']) for i in range(6)]))
LEXICON_SHA = h.digest(LEXICON)


def source_for(row):
    if row not in h.ELIGIBLE_IDS:
        return 'synthetic ordinary source'
    return f'Z{((int(row[1:])-1)//6)%6} synthetic source'


def fake_count(body):
    content = json.loads(body)['messages'][0]['content']
    return 40 if content.startswith(renderer.PREFIX_TEMPLATE.split('{')[0]) else 20


def plans():
    return [h.preflight_pair(row, source_for(row), ALIAS, LEXICON, LEXICON_SHA, renderer, fake_count)
            for row in h.ROW_IDS]


class Clock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


class Reader:
    def __init__(self, raw, *, clock=None, delay=0):
        self.raw, self.position, self.closed = raw, 0, False
        self.clock, self.delay = clock, delay
        self.max_read = 0
    def read(self, n, remaining):
        self.max_read = max(n, self.max_read)
        if self.clock:
            self.clock.advance(self.delay)
        value = self.raw[self.position:self.position+n]
        self.position += len(value)
        return value
    def close(self):
        self.closed = True


def response(body=b'{}', headers=None, status='200 OK'):
    headers = headers if headers is not None else [(b'Content-Length', str(len(body)).encode())]
    return b'HTTP/1.1 ' + status.encode() + b'\r\n' + b''.join(k+b': '+v+b'\r\n' for k,v in headers) + b'\r\n'+body


def decode(raw, cap=65536, *, asset_size=None, clock=None, delay=0, evidence=None):
    clock = clock or Clock()
    reader = Reader(raw, clock=clock, delay=delay)
    wire = h.BoundedWire(reader, h.Deadline(clock, 5), evidence.retain if evidence else lambda _: None)
    return wire.response(cap, asset_size=asset_size), reader


def completion(text='synthetic output', reason='stop', count=20):
    return dict(model=ALIAS, choices=[dict(message=dict(content=text), finish_reason=reason)],
                usage=dict(prompt_tokens=count, completion_tokens=3, total_tokens=count+3,
                           prompt_tokens_details=dict(cached_tokens=0)), timings=dict(cache_n=0))


class IntegrityError(Exception):
    pass


def pass_integrity(source, output):
    return output


def checked(data, integrity=pass_integrity):
    return h.completion_response(h.canonical(data), ALIAS, h.CountReceipt(b'body', 20),
                                 'synthetic source', integrity, IntegrityError)


class FakeChild:
    def __init__(self, resist=False, unkillable=False, clock=None):
        self.resist, self.unkillable, self.clock = resist, unkillable, clock
        self.exit = None
        self.actions = []
    def poll(self):
        return self.exit
    def terminate(self):
        self.actions.append('terminate')
        if not self.resist:
            self.exit = -15
    def kill(self):
        self.actions.append('kill')
        if not self.unkillable:
            self.exit = -9
    def wait(self, timeout):
        self.actions.append(('wait', timeout))
        if self.exit is None:
            if self.clock:
                self.clock.advance(timeout)
            raise TimeoutError('fake still running')
        return self.exit


class FakeMonitor:
    def __init__(self, stuck=False):
        self.stuck, self.cancelled, self.joined = stuck, False, False
    def cancel(self):
        self.cancelled = True
    def join(self, timeout=None):
        self.joined = True
    def is_alive(self):
        return self.stuck


class FakeTransport:
    def __init__(self, raw, clock):
        self.raw, self.clock, self.sent, self.armed = raw, clock, [], False
        self.monitor = FakeMonitor()
    def arm_watchdog(self, deadline):
        self.armed = True
        return self.monitor
    def send(self, method, endpoint, body, remaining, **settings):
        assert self.armed
        self.sent.append((method, endpoint, body, settings))
        self.reader = Reader(self.raw)
        return self.reader


class RequestAndPlanTests(unittest.TestCase):
    def test_fixed_schedule(self):
        self.assertEqual(len(h.SCHEDULE), 176)
        self.assertEqual(len(h.ROW_IDS), 88)
        self.assertEqual(h.ROW_IDS[:4], ('N001','R001','N002','R002'))
        self.assertEqual(h.ROW_IDS[-8:], tuple(f'N{i:03d}' for i in range(41,49)))
        self.assertEqual(sum(arm=='baseline' for _,arm in h.SCHEDULE), 88)
        self.assertEqual(sum(h.SCHEDULE[i][1]=='baseline' for i in range(0,176,2)), 44)
    def test_alias_requires_uuid4(self):
        for bad in ('a'*32, ATTEMPT.upper(), '0'*32, '../fake'):
            with self.subTest(bad=bad), self.assertRaises(h.TerminalFailure):
                h.alias_for(bad)
    def test_request_exact_parameters_and_no_extra_template_fields(self):
        raw = h.serialize_request(renderer.baseline_messages('Z0\n{fake}'), ALIAS)
        data = json.loads(raw)
        self.assertEqual(set(data), {'model','messages',*h.SAMPLING})
        self.assertEqual(data['messages'], renderer.baseline_messages('Z0\n{fake}'))
        self.assertEqual({k:data[k] for k in h.SAMPLING}, h.SAMPLING)
    def test_request_size_cap_before_send(self):
        with self.assertRaises(h.TerminalFailure):
            h.serialize_request([dict(role='user',content='x'*32768)], ALIAS)
    def test_preflight_two_counts_per_row_and_coverage(self):
        calls=[]
        ps=[h.preflight_pair(row,source_for(row),ALIAS,LEXICON,LEXICON_SHA,renderer,
            lambda b: (calls.append(b),fake_count(b))[1]) for row in h.ROW_IDS]
        self.assertEqual(len(calls),176)
        self.assertEqual(sum(p.eligible for p in ps),44)
        h.validate_preflight(ps)
    def test_recurring_uncached_counts_include_budget_abstentions(self):
        counts=[]
        counter=lambda b: 390 if fake_count(b)==40 else 380
        p=h.preflight_pair('N001','Z0',ALIAS,LEXICON,LEXICON_SHA,renderer,counter)
        self.assertTrue(p.eligible)
        self.assertFalse(p.active)
        self.assertEqual(p.reason,'token_budget')
        raw=h.measured_candidate(p,'Z0',ALIAS,LEXICON,LEXICON_SHA,renderer,
            lambda b:(counts.append(b),counter(b))[1])
        self.assertEqual(len(counts),2)
        self.assertEqual(raw,p.baseline.body)
    def test_recurring_ineligible_makes_zero_counts(self):
        p=h.preflight_pair('R001','ordinary',ALIAS,LEXICON,LEXICON_SHA,renderer,fake_count)
        h.measured_candidate(p,'ordinary',ALIAS,LEXICON,LEXICON_SHA,renderer,
                             lambda _:self.fail('counter must not run'))
    def test_swallowed_renderer_failure_is_terminal(self):
        calls=[]
        def counter(body):
            calls.append(body)
            if len(calls)==2:
                raise OSError('synthetic count failure')
            return 20
        with self.assertRaises(h.TerminalFailure):
            h.preflight_pair('N001','Z0',ALIAS,LEXICON,LEXICON_SHA,renderer,counter)
        self.assertEqual(len(calls),2)
    def test_baseline_budget_stops_after_first_count(self):
        calls=[]
        with self.assertRaises(h.TerminalFailure):
            h.preflight_pair('N001','Z0',ALIAS,LEXICON,LEXICON_SHA,renderer,
                             lambda b:(calls.append(b),385)[1])
        self.assertEqual(len(calls),1)
    def test_inactive_second_count_must_agree(self):
        values=iter([20,21])
        with self.assertRaises(h.TerminalFailure):
            h.preflight_pair('R001','ordinary',ALIAS,LEXICON,LEXICON_SHA,renderer,lambda _:next(values))
    def test_measured_count_drift_terminal(self):
        p=plans()[0]
        with self.assertRaises(h.TerminalFailure):
            h.measured_candidate(p,source_for(p.row_id),ALIAS,LEXICON,LEXICON_SHA,renderer,lambda _:21)
    def test_coverage_no_pruning(self):
        ps=plans()
        for bad in (ps[:-1], list(reversed(ps))):
            with self.assertRaises(h.TerminalFailure):
                h.validate_preflight(bad)
        from dataclasses import replace
        ps=[replace(p,active=False) if p.row_id=='N041' else p for p in ps]
        with self.assertRaises(h.TerminalFailure):
            h.validate_preflight(ps)
    def test_token_response_exact_plain_integer_schema(self):
        self.assertEqual(h.token_response(b'{"object":"response.input_tokens","input_tokens":20}'),20)
        for value in (20,True,{},dict(object='wrong',input_tokens=2),dict(object='response.input_tokens',input_tokens=True),
                      dict(object='response.input_tokens',input_tokens=0),dict(object='response.input_tokens',input_tokens=2,extra=0)):
            with self.subTest(value=value), self.assertRaises(h.TerminalFailure):
                h.token_response(h.canonical(value))
    def test_duplicate_json_key_is_terminal(self):
        with self.assertRaises(h.TerminalFailure):
            h.token_response(b'{"object":"response.input_tokens","input_tokens":2,"input_tokens":3}')
    def test_readiness_unique_alias(self):
        h.readiness_response('health',b'{"status":"ok"}',ALIAS)
        h.readiness_response('models',h.canonical(dict(data=[dict(id=ALIAS)])),ALIAS)
        for items in ([],[dict(id='foreign')],[dict(id=ALIAS),dict(id=ALIAS)]):
            with self.assertRaises(h.TerminalFailure):
                h.readiness_response('models',h.canonical(dict(data=items)),ALIAS)


class CompletionTests(unittest.TestCase):
    def test_valid_completion(self):
        self.assertFalse(checked(completion())['scoreable_generation_failure'])
    def test_empty_whitespace_and_length_are_scoreable(self):
        for output,reason,flag in (('', 'stop','empty_output'),(' \n','stop','empty_output'),('x','length','length_finish')):
            result=checked(completion(output,reason))
            self.assertEqual(result['output'],output)
            self.assertIn(flag,result['flags'])
            self.assertFalse(result['definite_faithful_pass_eligible'])
            self.assertEqual(result['raw_response'],h.canonical(completion(output,reason)))
    def test_expected_integrity_rejection_scoreable(self):
        def reject(*_):
            raise IntegrityError('synthetic rejection')
        self.assertEqual(checked(completion(),reject)['flags'],['integrity_rejection'])
    def test_unexpected_checker_exception_terminal(self):
        def reject(*_):
            raise RuntimeError('checker bug')
        with self.assertRaises(h.TerminalFailure):
            checked(completion(),reject)
    def test_boolean_usage_fields_rejected(self):
        for field in ('prompt_tokens','completion_tokens','total_tokens'):
            data=completion(); data['usage'][field]=True
            with self.subTest(field=field),self.assertRaises(h.TerminalFailure): checked(data)
        data=completion();data['usage']['prompt_tokens_details']['cached_tokens']=False
        with self.assertRaises(h.TerminalFailure): checked(data)
    def test_missing_cache_evidence_rejected(self):
        data=completion();del data['usage']['prompt_tokens_details']
        with self.assertRaises(h.TerminalFailure): checked(data)
    def test_cache_contradictions_rejected(self):
        for location in ('usage','timings'):
            data=completion()
            if location=='usage':data['usage']['prompt_tokens_details']['cached_tokens']=1
            else:data['timings']['cache_n']=1
            with self.assertRaises(h.TerminalFailure):checked(data)
    def test_prompt_alias_finish_choice_and_total_failures(self):
        mutations=[lambda d:d.update(model='foreign'),lambda d:d['usage'].update(prompt_tokens=21),
                   lambda d:d['usage'].update(total_tokens=24),lambda d:d['choices'].append(d['choices'][0]),
                   lambda d:d['choices'][0].update(finish_reason='tool_calls')]
        for mutate in mutations:
            data=completion(); mutate(data)
            with self.assertRaises(h.TerminalFailure):checked(data)
    def test_zero_completion_tokens_allowed(self):
        data=completion('');data['usage'].update(completion_tokens=0,total_tokens=20)
        self.assertTrue(checked(data)['scoreable_generation_failure'])


class TransportTests(unittest.TestCase):
    def test_bounded_identity_response(self):
        body=b'x'*65536
        decoded,reader=decode(response(body))
        self.assertEqual(decoded,body);self.assertLessEqual(reader.max_read,8192)
    def test_header_field_count_line_and_total_caps(self):
        cases=[response(headers=[(f'X{i}'.encode(),b'1') for i in range(65)]),
               response(headers=[(b'Long',b'x'*2048)]),
               response(headers=[(f'X{i}'.encode(),b'x'*1000) for i in range(17)])]
        for raw in cases:
            with self.assertRaises(h.TerminalFailure):decode(raw)
    def test_length_encoding_and_framing_errors(self):
        cases=[[(b'Content-Length',b'3'),(b'Transfer-Encoding',b'chunked')],
               [(b'Content-Length',b'-1')],[(b'Content-Length',b'02')],
               [(b'Content-Length',b'2'),(b'Content-Length',b'2')],
               [(b'Content-Length',b'2'),(b'Content-Encoding',b'gzip')],
               [(b'Transfer-Encoding',b'gzip, chunked')],[]]
        for headers in cases:
            with self.subTest(headers=headers),self.assertRaises(h.TerminalFailure):decode(response(headers=headers))
    def test_asset_requires_exact_length(self):
        self.assertEqual(decode(response(b'123'),asset_size=3)[0],b'123')
        for raw in (response(b'123'),response(b'0\r\n\r\n',[(b'Transfer-Encoding',b'chunked')])):
            with self.assertRaises(h.TerminalFailure):decode(raw,asset_size=2)
    def test_error_body_is_never_read(self):
        reader=Reader(response(b'private error body',status='302 Found'))
        wire=h.BoundedWire(reader,h.Deadline(Clock(),5))
        with self.assertRaises(h.TerminalFailure):wire.response(65536)
        self.assertTrue(reader.closed)
        self.assertTrue(reader.raw[reader.position:].startswith(b'private'))
    def test_content_length_cap_stops_before_body(self):
        reader=Reader(response(b'x'*10))
        wire=h.BoundedWire(reader,h.Deadline(Clock(),5))
        with self.assertRaises(h.TerminalFailure):wire.response(9)
        self.assertEqual(reader.raw[reader.position:],b'x'*10)
    def test_chunked_success(self):
        raw=response(b'3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n',[(b'Transfer-Encoding',b'chunked')])
        self.assertEqual(decode(raw)[0],b'abcde')
    def test_chunk_count_cap(self):
        raw=response(b'1\r\na\r\n'*1025+b'0\r\n\r\n',[(b'Transfer-Encoding',b'chunked')])
        with self.assertRaises(h.TerminalFailure):decode(raw)
    def test_chunk_size_extensions_trailers_and_body_caps(self):
        for body in (b'ff\r\n',b'1;extension=yes\r\na\r\n0\r\n\r\n',b'0\r\nX: y\r\n\r\n',b'a'*129+b'\r\n'):
            with self.assertRaises(h.TerminalFailure):
                decode(response(body,[(b'Transfer-Encoding',b'chunked')]),cap=10)
    def test_truncated_body_and_absolute_read_deadline(self):
        with self.assertRaises(h.TerminalFailure):decode(response(b'12',[(b'Content-Length',b'3')]))
        with self.assertRaises(h.TerminalFailure):decode(response(),clock=Clock(),delay=.2)
    def test_global_evidence_budget(self):
        budget=h.EvidenceBudget(20)
        with self.assertRaises(h.TerminalFailure):decode(response(),evidence=budget)
        self.assertLessEqual(budget.retained,20)
    def test_empty_redirect_policy_always_blocks(self):
        for target in ('https://official.example/asset','/asset','http://example.com',
                       'https://user@example.com/','https://127.0.0.1/','https://example.com/#fragment'):
            with self.assertRaises(h.TerminalFailure):h.redirect_target(h.ASSETS[0][0],target)


class LedgerAndDeadlineTests(unittest.TestCase):
    def test_exact_442_success_accounting(self):
        events=[]; ledger=h.RequestLedger(events.append)
        for item in ledger.queue:
            if ledger.total==178:ledger.seal_preflight(plans())
            ledger.consume(*item)
        ledger.assert_complete()
        self.assertEqual(len([e for e in events if e['event']=='request_intent']),442)
        self.assertEqual(ledger.counts['completion'],176)
        self.assertEqual(ledger.counts['preflight']+ledger.counts['recurring'],264)
        with self.assertRaises(h.TerminalFailure):ledger.consume('completion','N048','baseline')
    def test_generation_blocked_before_coverage_seal(self):
        ledger=h.RequestLedger()
        for item in ledger.queue[:178]:ledger.consume(*item)
        with self.assertRaises(h.TerminalFailure):ledger.consume(*ledger.queue[178])
        self.assertEqual(ledger.total,178)
    def test_wrong_order_and_failed_request_consumed(self):
        ledger=h.RequestLedger()
        with self.assertRaises(h.TerminalFailure):ledger.consume('models')
        self.assertIsNotNone(ledger.terminal)
        ledger=h.RequestLedger()
        ledger.consume('health');ledger.fail('connection failed')
        self.assertEqual(ledger.total,1)
        with self.assertRaises(h.TerminalFailure):ledger.consume('health')
    def test_journal_failure_consumes_intent(self):
        def fail(event):raise OSError('synthetic disk failure')
        ledger=h.RequestLedger(fail)
        with self.assertRaises(OSError):ledger.consume('health')
        self.assertEqual(ledger.total,1)
        self.assertEqual(ledger.terminal,'journal_failure')
    def test_deadline_intersection(self):
        clock=Clock();deadline=h.Deadline(clock,60,12,18)
        self.assertEqual(deadline.end,12)
        clock.advance(12)
        with self.assertRaises(h.TerminalFailure):deadline.remaining()
    def test_late_parsing_is_terminal_and_connection_closed(self):
        clock=Clock();transport=FakeTransport(response(b'{"status":"ok"}'),clock);ledger=h.RequestLedger()
        def parse(raw):clock.advance(6);return {'status':'ok'}
        with self.assertRaises(h.TerminalFailure):
            h.checked_exchange(ledger,'health',None,None,lambda:None,transport,clock,[180],parse,h.EvidenceBudget())
        self.assertEqual(ledger.total,1);self.assertTrue(transport.reader.closed)
        self.assertTrue(transport.monitor.cancelled and transport.monitor.joined)
    def test_serialization_is_inside_deadline_before_send(self):
        clock=Clock();transport=FakeTransport(response(),clock);ledger=h.RequestLedger()
        def prepare():clock.advance(6)
        with self.assertRaises(h.TerminalFailure):
            h.checked_exchange(ledger,'health',None,None,prepare,transport,clock,[180],lambda x:x,h.EvidenceBudget())
        self.assertEqual(ledger.total,0);self.assertEqual(transport.sent,[])
    def test_checked_exchange_no_proxy_redirect_and_armed_before_send(self):
        clock=Clock();transport=FakeTransport(response(b'{"status":"ok"}'),clock);ledger=h.RequestLedger()
        h.checked_exchange(ledger,'health',None,None,lambda:None,transport,clock,[180],
            lambda raw:h.readiness_response('health',raw,ALIAS),h.EvidenceBudget())
        self.assertEqual(transport.sent[0][3],dict(proxy=False,redirects=False,request_header_cap=8192))
    def test_unobserved_rows_are_explicit(self):
        rows=h.all_row_accounting({('N001','baseline'):{'status':'observed'}})
        self.assertEqual(len(rows),88)
        self.assertEqual(rows[0]['arms']['candidate'],{'status':'unobserved'})


class LifecycleResourceTests(unittest.TestCase):
    def test_environment_is_fresh_cpu_fixed(self):
        spec=h.server_spec('/fake/llama-server','/fake/model','/fake/template','/fake/private',18080,ALIAS)
        self.assertEqual(spec['env'],dict(LANG='C.UTF-8',LC_ALL='C.UTF-8',TZ='UTC'))
        self.assertFalse(spec['shell']);self.assertTrue(spec['close_fds'])
        self.assertIn('--no-warmup',spec['argv']);self.assertIn('--cors-origins',spec['argv'])
        self.assertEqual(spec['argv'][spec['argv'].index('-ngl')+1],'0')
        with self.assertRaises(h.TerminalFailure):h.child_spec('/a',[],'/b',library_dirs=('/unsafe',))
    def test_resource_independent_host_and_cgroup(self):
        h.resource_gate(3544805248,3544805248,startup=True)
        for host,cgroup in ((None,10*h.GIB),(10*h.GIB,None),(3544805247,10*h.GIB),(10*h.GIB,3544805247)):
            with self.assertRaises(h.TerminalFailure):h.resource_gate(host,cgroup,startup=True)
    def test_runtime_floor_disk_growth_rss(self):
        h.resource_gate(768*h.MIB,768*h.MIB,rss=4*h.GIB,free_disk=h.GIB,growth=2*h.GIB)
        for kwargs in (dict(rss=4*h.GIB+1),dict(free_disk=h.GIB-1),dict(growth=2*h.GIB+1)):
            with self.assertRaises(h.TerminalFailure):h.resource_gate(h.GIB,h.GIB,**kwargs)
    def test_intent_and_deadline_before_launch(self):
        clock=Clock();supervisor=h.SyntheticSupervisor(clock);child=FakeChild()
        def launch(owner,deadline):
            self.assertTrue(owner.intents['server']['pending_handle'])
            self.assertTrue(owner.intents['server']['monitor_armed'])
            self.assertEqual(deadline.end,180)
            return child
        supervisor.launch('server',{},180,launch)
        supervisor.ready()
        self.assertEqual(supervisor.postready.end,600)
        self.assertEqual(supervisor.finalize()['status'],'synthetic_complete')
        self.assertIsNotNone(child.poll())
    def test_late_handle_adopted_and_stopped_no_later_phase(self):
        clock=Clock();supervisor=h.SyntheticSupervisor(clock);child=FakeChild()
        def launch(owner,deadline):
            clock.advance(181);owner.tick(deadline);return child
        with self.assertRaises(h.TerminalFailure):supervisor.launch('server',{},180,launch)
        self.assertIs(supervisor.handles['server'],child)
        self.assertIsNotNone(child.poll())
        with self.assertRaises(h.TerminalFailure):supervisor.launch('helper',{},15,lambda *_:FakeChild())
        self.assertEqual(supervisor.finalize()['status'],'incomplete')
    def test_failed_launch_retains_unknown_state(self):
        supervisor=h.SyntheticSupervisor(Clock())
        def launch(*_):raise OSError('synthetic ambiguous Popen failure')
        with self.assertRaises(OSError):supervisor.launch('version',{},15,launch)
        result=supervisor.finalize()
        self.assertIn('version:unknown launch state',result['unresolved'])
        self.assertFalse(result['cleanup_confirmed'])
    def test_terminate_kill_only_owned_handle(self):
        child=FakeChild(resist=True);other=FakeChild()
        h.SyntheticSupervisor.stop(child)
        self.assertEqual(child.actions,['terminate',('wait',3),'kill',('wait',3)])
        self.assertEqual(other.actions,[])
    def test_cleanup_unconfirmed_never_complete(self):
        supervisor=h.SyntheticSupervisor(Clock());child=FakeChild(resist=True,unkillable=True)
        supervisor.launch('server',{},180,lambda *_:child)
        supervisor.monitors.append(FakeMonitor(stuck=True))
        result=supervisor.finalize()
        self.assertFalse(result['cleanup_confirmed']);self.assertEqual(result['status'],'incomplete')
    def test_cleanup_deadline_and_failed_finalization(self):
        clock=Clock();supervisor=h.SyntheticSupervisor(clock)
        result=supervisor.finalize(lambda:clock.advance(21))
        self.assertIn('evidence finalization incomplete',result['unresolved'])
    def test_postready_clock_never_reset_or_borrow_cleanup(self):
        clock=Clock();supervisor=h.SyntheticSupervisor(clock)
        supervisor.launch('server',{},180,lambda *_:FakeChild())
        clock.advance(179);supervisor.ready()
        self.assertEqual(supervisor.postready.end,779)
        with self.assertRaises(h.TerminalFailure):supervisor.ready()
        clock.advance(600);supervisor.tick(supervisor.postready)
        self.assertEqual(supervisor.failure,'watchdog_expired')


class ArchiveAndClaimTests(unittest.TestCase):
    def test_safe_members_and_relative_library_chain(self):
        members=[dict(name='lib',type='directory',size=0),dict(name='lib/a.so.1',type='file',size=10),
                 dict(name='lib/a.so',type='symlink',target='a.so.1',size=0)]
        self.assertEqual(h.validate_archive_members(members),dict(member_count=3,expanded_bytes=10))
    def test_unsafe_archive_members(self):
        bad=[dict(name='/absolute',type='file',size=1),dict(name='../parent',type='file',size=1),
             dict(name='device',type='device',size=0),dict(name='hard',type='hardlink',size=0),
             dict(name='huge',type='file',size=512*h.MIB+1),
             dict(name='a.so',type='symlink',target='../escape',size=0)]
        for member in bad:
            with self.assertRaises(h.TerminalFailure):h.validate_archive_members([member])
    def test_archive_cycle_and_symlink_parent(self):
        for members in ([dict(name='a.so',type='symlink',target='b.so',size=0),dict(name='b.so',type='symlink',target='a.so',size=0)],
                        [dict(name='a.so',type='symlink',target='b',size=0),dict(name='a.so/x',type='file',size=0),dict(name='b',type='file',size=1)]):
            with self.assertRaises(h.TerminalFailure):h.validate_archive_members(members)
    def test_fake_exclusive_claim_persists_across_instances(self):
        with tempfile.TemporaryDirectory(prefix='luna-sense-fake-') as directory:
            store=h.SyntheticClaimStore(directory)
            store.claim(dict(synthetic_only=True,attempt_id=ATTEMPT))
            store.append(dict(event='terminal',status='incomplete',consumed=1));store.close()
            saved=(Path(directory)/'ONE_SHOT_CPU_ATTEMPT.json').read_bytes()
            retry=h.SyntheticClaimStore(directory)
            try:
                with self.assertRaises(FileExistsError):retry.claim(dict(synthetic_only=True,attempt_id=ATTEMPT))
            finally:retry.close()
            self.assertEqual((Path(directory)/'ONE_SHOT_CPU_ATTEMPT.json').read_bytes(),saved)
            self.assertEqual((Path(directory)/'ONE_SHOT_CPU_ATTEMPT.json').stat().st_mode&0o777,0o600)
            self.assertEqual(len((Path(directory)/'ONE_SHOT_CPU_EVENTS.jsonl').read_text().splitlines()),2)
    def test_journal_creation_failure_consumes_claim(self):
        with tempfile.TemporaryDirectory(prefix='luna-sense-fake-') as directory:
            store=h.SyntheticClaimStore(directory)
            try:
                with self.assertRaises(h.TerminalFailure):store.claim(dict(synthetic_only=True),fail_after_claim=True)
                with self.assertRaises(FileExistsError):store.claim(dict(synthetic_only=True))
            finally:store.close()
    def test_symlink_and_partial_claim_block(self):
        for symlink in (False,True):
            with tempfile.TemporaryDirectory(prefix='luna-sense-fake-') as directory:
                path=Path(directory)/'ONE_SHOT_CPU_ATTEMPT.json'
                if symlink:path.symlink_to('missing-target')
                else:path.write_bytes(b'{')
                store=h.SyntheticClaimStore(directory)
                try:
                    with self.assertRaises(FileExistsError):store.claim(dict(synthetic_only=True))
                finally:store.close()
    def test_production_claim_root_rejected(self):
        with self.assertRaises(h.TerminalFailure):
            h.SyntheticClaimStore('/forbidden-production-root')
    def test_real_execution_hard_disabled(self):
        with self.assertRaises(h.Disabled):h.run_real(approved=True,redirect_policy=['anything'])


class CostTests(unittest.TestCase):
    def rows(self):
        return [dict(id=row,baseline=1.,candidate=1.2,active=row in h.ELIGIBLE_IDS,complete=True,
                     baseline_tokens=20,candidate_tokens=40,quality_failure=False) for row in h.ROW_IDS]
    def test_cost_uses_rowwise_ratios_not_quantile_ratio(self):
        rows=self.rows()
        for index,row in enumerate(rows):
            row['baseline']=1. if index%2 else 100.
            row['candidate']=2. if index%2 else 100.
        result=h.paired_cost(rows,1e-9)
        self.assertEqual(result['groups']['all_rows']['ratios']['median'],1.5)
        self.assertEqual(result['groups']['all_rows']['ratios']['p95'],2.)
        self.assertEqual(result['status'],'fail')
        self.assertNotEqual(1.5,51/50.5)
    def test_nearest_rank(self):
        self.assertEqual(h.quantiles(list(range(1,21))),dict(n=20,median=10.5,p95=19))
    def test_scoreable_quality_failures_keep_valid_cost(self):
        rows=self.rows();rows[0]['quality_failure']=True
        result=h.paired_cost(rows,1e-9)
        self.assertEqual(result['groups']['all_rows']['ratios']['n'],88)
        self.assertEqual(result['status'],'pass')
    def test_missing_nonfinite_zero_partial_and_resolution_failures(self):
        for value in (None,float('nan'),float('inf'),0.,1e-9):
            rows=self.rows();rows[0]['baseline']=value
            with self.assertRaises(h.TerminalFailure):h.paired_cost(rows,1e-9)
        rows=self.rows();rows[0]['complete']=False
        with self.assertRaises(h.TerminalFailure):h.paired_cost(rows,1e-9)
    def test_empty_active_and_missing_row_invalid(self):
        rows=self.rows()
        for row in rows:row['active']=False
        with self.assertRaises(h.TerminalFailure):h.paired_cost(rows,1e-9)
        with self.assertRaises(h.TerminalFailure):h.paired_cost(self.rows()[:-1],1e-9)
    def test_noise_is_inconclusive_and_abba_balanced(self):
        result=h.paired_cost(self.rows(),1e-9,material_noise=True)
        self.assertEqual(result['status'],'inconclusive')
        self.assertEqual(result['order_strata']['AB']['n'],44)
        self.assertEqual(result['order_strata']['BA']['n'],44)


if __name__=='__main__':
    unittest.main()
