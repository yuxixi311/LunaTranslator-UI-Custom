"""Entirely fake model/runtime/socket/HTTP tests. No real child or model execution."""
import ast
import base64
import copy
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent / 'luna-threeway-repair-zip-verification'
TOOLS = ROOT / 'tools/local_eval'
sys.path.insert(0, str(TOOLS))
import run_hy_glossary as run
import validate_hy_glossary as validator
import threeway_model_preflight as gguf
import threeway_safety as safety


def gguf_bytes(values, tail=b'fake-tensors'):
    def string(value):
        raw = value.encode('utf-8')
        return struct.pack('<Q', len(raw)) + raw
    parts = [b'GGUF', struct.pack('<IQQ', 3, 1, len(values))]
    for key, value in values.items():
        kind, data = (8, string(value)) if isinstance(value, str) else (4, struct.pack('<I', value))
        parts += [string(key), struct.pack('<I', kind), data]
    return b''.join(parts) + tail


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.stopped = threading.Event()
    def poll(self): return self.returncode
    def terminate(self):
        self.returncode = -15
        self.stopped.set()
    def kill(self): self.terminate()
    def wait(self, timeout=None): return self.returncode


class ControlledClock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class ControlledTimers:
    """Keep callbacks pending until a test explicitly schedules one."""
    def __init__(self, clock):
        self.clock, self.instances = clock, []
        self.before_cancel = None

    def __call__(self, seconds, callback):
        scheduler = self
        class Timer:
            ident = None
            daemon = False
            cancelled = False
            fired = False
            def __init__(self):
                self.seconds = seconds
                self.callback = callback
            def start(self):
                self.ident = 1
                self.due = scheduler.clock() + seconds
            def cancel(self):
                if scheduler.before_cancel is not None:
                    scheduler.before_cancel(self)
                self.cancelled = True
            def join(self, timeout=None): pass
            def is_alive(self): return self.ident is not None and not (self.cancelled or self.fired)
            def fire(self):
                if self.cancelled:
                    raise AssertionError('Cannot fire a cancelled synthetic timer')
                scheduler.clock.now = max(scheduler.clock(), self.due)
                self.fired = True
                self.callback()
        timer = Timer()
        self.instances.append(timer)
        return timer


class SyntheticRun:
    """Exercise the real production runner against entirely in-memory doubles."""
    def __init__(self, root, model='hy18', block=None, output=None):
        self.root, self.model, self.block, self.output = root, model, block, output
        self.stack = ExitStack()
        self.proc = FakeProcess()
        self.calls = []
        self.block_entered = threading.Event()
        self.on_block = None
        self.on_read = None
        self.gguf, self.server, self.driver = root/'model.gguf', root/'llama-server', root/'nvidia-smi'
        self.server.write_bytes(b'synthetic runtime')
        self.driver.write_bytes(b'synthetic driver')
        self.design = root/'design.txt'
        self.design.write_text('synthetic design')
        self.historical, self.fresh = root/'historical.json', root/'fresh.json'
        historical = [{'id': ident, 'category': 'old', 'source': f'確認番号{i}です。'} for i, ident in enumerate(run.FIXED_OLD_IDS)]
        historical += [{'id': f'extra-{i}', 'category': 'old', 'source': f'過去番号{i}です。'} for i in range(32)]
        fresh = []
        for category, count in run.STRATA.items():
            for i in range(count):
                target = category in ('name-word-person', 'explicit-named-participant')
                active = target or category == 'matched-commonword-subword'
                fresh.append({'id': f'{category}-{i}', 'stratum': category, 'source': ('光' if active else '猫') + f'合成{category}{i}。',
                              'target_entity_src': '光' if target else None, 'scenario_id': f'scenario-{category}-{i}' if target else None})
        run.write_json(self.historical, {'schema_version': 1, 'cases': historical})
        run.write_json(self.fresh, fresh)
        self.pins = root/'pins.json'
        run.write_json(self.pins, {'runtime_files_sha256': {self.server.name: run.digest(self.server)},
            'server_sha256': run.digest(self.server), 'nvidia_smi_sha256': run.digest(self.driver), 'runtime_version': 'build 11349, commit fb4b2737a'})
        self.specs = copy.deepcopy(run.MODELS)
        spec = self.specs[model]
        arch = spec['architecture']
        values = {'general.architecture': arch, 'general.file_type': 15, arch+'.block_count': 32,
                  'tokenizer.chat_template': (TOOLS/spec['template_file']).read_text()}
        if model == 'qwen35_2b':
            values[arch+'.nextn_predict_layers'] = 1
        self.gguf.write_bytes(gguf_bytes(values))
        spec.update(bytes=self.gguf.stat().st_size, sha256=run.digest(self.gguf))
        self.gpu = {'uuid': 'GPU-synthetic', 'index': 0, 'name': 'synthetic', 'driver_version': 'test',
                    'free_bytes': 8*1024**3, 'total_bytes': 12*1024**3}
        self.probe = types.SimpleNamespace(gpu=lambda: dict(self.gpu))
        self.args = types.SimpleNamespace(model=model, gguf=self.gguf, server=self.server,
                                         nvidia_smi=self.driver, out=root/'out')

    def __enter__(self):
        fake_socket = types.SimpleNamespace(__enter__=lambda self: self, __exit__=lambda *args: None)
        class Socket:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def bind(self, address): pass
            def getsockname(self): return ('127.0.0.1', 43210)
        self.stack.enter_context(patch.object(run.socket, 'socket', Socket))
        self.stack.enter_context(patch.object(run.platform, 'platform', return_value='synthetic test platform'))
        for name, value in {'MODELS': self.specs, 'DESIGN_SHA': run.digest(self.design),
                            'FRESH_SHA': run.digest(self.fresh), 'HISTORICAL_SHA': run.digest(self.historical),
                            'RUNTIME_PINS': self.pins, 'RUNTIME_PIN_SHA': run.digest(self.pins), 'memory_available': lambda: 10*1024**3}.items():
            self.stack.enter_context(patch.object(run, name, value))
        def monitor(kind):
            samples = {'resource_guard_stopped_process': False, 'resource_guard_reason': None,
                       'minimum_available_ram_bytes': 4*1024**3, 'peak_process_rss_bytes': 2048,
                       'rss_sample_count': 1} if kind == 'ram' else {
                       'peak_process_vram_bytes': None, 'vram_sample_count': 0, 'vram_probe_errors': 0,
                       'vram_scope': 'owned server PID on selected GPU only'}
            return types.SimpleNamespace(samples=samples, stop=threading.Event(),
                   thread=types.SimpleNamespace(start=lambda: None, ident=None, is_alive=lambda: False))
        self.stack.enter_context(patch.object(run, 'RamMonitor', side_effect=lambda *args: monitor('ram')))
        self.stack.enter_context(patch.object(run, 'GpuMonitor', side_effect=lambda *args: monitor('gpu')))
        def popen(command, **kwargs):
            self.command = command
            self.alias = command[command.index('--alias')+1]
            kwargs['stdout'].write('using device CUDA0\noffloaded 33/33 layers to GPU\nCUDA0 model buffer size = 10.0 MiB\n')
            kwargs['stdout'].flush()
            return self.proc
        self.stack.enter_context(patch.object(run.subprocess, 'Popen', side_effect=popen))
        owner = self
        class Response:
            status = 200
            def __init__(self, endpoint, payload): self.endpoint, self.payload = endpoint, payload
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                if owner.on_read is not None:
                    owner.on_read(self.endpoint)
                if self.endpoint == owner.block:
                    owner.block_entered.set()
                    if owner.on_block is not None:
                        owner.on_block()
                    if not owner.proc.stopped.wait(2):
                        raise AssertionError('Watchdog did not stop blocked fake read')
                    raise TimeoutError('fake owned process stopped')
                return json.dumps(self.payload, ensure_ascii=False).encode()
        def open_request(request, **kwargs):
            endpoint = request.full_url.split('/', 3)[-1]
            body = json.loads(request.data) if request.data else None
            self.calls.append(endpoint)
            if endpoint == 'health': payload = {'status': 'ok'}
            elif endpoint == 'v1/models': payload = {'data': [{'id': self.alias}]}
            elif endpoint == 'apply-template':
                payload = {'prompt': '<｜hy_begin▁of▁sentence｜><｜hy_User｜>' + body['messages'][0]['content'] + '<｜hy_Assistant｜>'}
            elif endpoint == 'tokenize': payload = {'tokens': [1, 2, 3, 4, 5]}
            elif endpoint == 'v1/chat/completions':
                text = '这是一项翻译连接测试。' if self.output is None else (self.output(len(self.calls)) if callable(self.output) else self.output)
                payload = {'model': self.alias, 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}],
                           'usage': {'prompt_tokens': 5, 'completion_tokens': 6, 'prompt_tokens_details': {'cached_tokens': 0}}}
            else: raise AssertionError(endpoint)
            return Response(endpoint, payload)
        self.stack.enter_context(patch.object(run.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=open_request)))
        return self

    def __exit__(self, *args): return self.stack.__exit__(*args)

    def execute(self, ownership=None):
        self.args.claim_path = self.root/'persistent-claim.json'
        run.write_json(self.args.claim_path, run.claim_record(self.args.out))
        cases = run.experiment_cases(self.historical, self.fresh, self.design)
        record = gguf.read_metadata(self.gguf)
        info = gguf.validate_metadata(record, self.specs[self.model])
        run.run_owned(self.args, cases, self.specs[self.model], record, info, 10*1024**3, self.probe,
                      self.gpu, 'build 11349, commit fb4b2737a', {self.server.name: run.digest(self.server)}, ownership)

    def validate(self):
        return validator.load_evidence(self.args.out, self.historical, self.fresh, self.design)

    def rehash(self):
        run.write_json(self.args.out/'manifest.json', {p.name: run.digest(p) for p in self.args.out.iterdir() if p.is_file() and p.name != 'manifest.json'})


class GlossaryTests(unittest.TestCase):
    def test_owned_watchdogs_stop_blocked_reads_and_preserve_evidence(self):
        # Select the failure stage explicitly. No 20 ms assumption is imposed on
        # the 98 preceding probe/flush operations on any operating system.
        for endpoint in ('health', 'apply-template', 'v1/chat/completions'):
            clock = ControlledClock()
            timers = ControlledTimers(clock)
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), block=endpoint) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
                fixture.on_block = lambda: timers.instances[-1].fire()
                with self.assertRaises((TimeoutError, RuntimeError)): fixture.execute()
                self.assertTrue(fixture.block_entered.is_set(), 'The requested read must actually be reached')
                self.assertTrue(fixture.proc.stopped.is_set())
                meta = json.loads((fixture.args.out/'metadata.json').read_text())
                self.assertEqual(meta['status'], 'incomplete')
                field = 'startup_budget_exceeded' if endpoint == 'health' else 'inference_budget_exceeded'
                self.assertTrue(meta[field])
                self.assertTrue(meta[field.replace('budget_exceeded', 'watchdog_fired')])
                if endpoint == 'v1/chat/completions':
                    self.assertEqual(fixture.calls, ['health', 'v1/models'] + ['apply-template', 'tokenize']*65 + ['v1/chat/completions'])
                wires = validator.read_jsonl(fixture.args.out/'wire.jsonl')
                self.assertTrue(any(w['endpoint'] == endpoint and w.get('error') for w in wires))
                self.assertTrue((fixture.args.out/'manifest.json').is_file())


    def test_synchronous_inference_deadline_records_expiry_with_callback_pending(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        original = run.preflight_tokens
        def finish_probes_then_exhaust_budget(*args):
            result = original(*args)
            clock.advance(run.INFERENCE_BUDGET_SECONDS)
            return result
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers), patch.object(run, 'preflight_tokens', side_effect=finish_probes_then_exhaust_budget):
            with self.assertRaisesRegex(TimeoutError, 'request budget exhausted'):
                fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertTrue(meta['inference_budget_exceeded'])
            self.assertFalse(meta['inference_watchdog_fired'])
            self.assertFalse(meta['startup_budget_exceeded'])
            self.assertEqual(meta['post_ready_seconds'], run.INFERENCE_BUDGET_SECONDS)
            self.assertEqual(meta['status'], 'incomplete')
            self.assertTrue(meta['owned_process_stopped'])
            self.assertEqual(fixture.calls.count('tokenize'), 65)
            self.assertEqual(fixture.calls.count('v1/chat/completions'), 0)
            self.assertFalse(any(timer.fired for timer in timers.instances))
            self.assertTrue(all(timer.cancelled for timer in timers.instances))


    def test_startup_uses_same_absolute_deadline_despite_late_timer_setup(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        def resource_probe():
            clock.advance(run.STARTUP_BUDGET_SECONDS)
            return 10*1024**3
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers), patch.object(run, 'memory_available', side_effect=resource_probe):
            with self.assertRaises(TimeoutError): fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertTrue(meta['startup_budget_exceeded'])
            self.assertFalse(meta['startup_watchdog_fired'])
            self.assertEqual(timers.instances[0].seconds, 0)
            self.assertEqual(fixture.calls, [])
            self.assertTrue(meta['owned_process_stopped'])


    def test_final_successful_response_cannot_return_success_after_deadline(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
            def on_read(endpoint):
                if endpoint == 'v1/chat/completions' and fixture.calls.count(endpoint) == 65:
                    clock.advance(run.INFERENCE_BUDGET_SECONDS)
            fixture.on_read = on_read
            with self.assertRaisesRegex(TimeoutError, 'Post-readiness watchdog expired'):
                fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertEqual(fixture.calls.count('v1/chat/completions'), 65)
            self.assertTrue(meta['inference_budget_exceeded'])
            self.assertFalse(meta['inference_watchdog_fired'])
            self.assertEqual(meta['status'], 'incomplete')


    def test_cleanup_duration_cannot_overrun_completed_operation(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        original_stop = run.stop_owned
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
            def slow_cleanup(proc):
                clock.advance(500)
                original_stop(proc)
            with patch.object(run, 'stop_owned', side_effect=slow_cleanup):
                fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertEqual(meta['status'], 'complete')
            self.assertEqual(meta['post_ready_seconds'], 0)
            self.assertFalse(meta['startup_budget_exceeded'])
            self.assertFalse(meta['inference_budget_exceeded'])


    def test_budget_crossing_after_final_check_is_terminal(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        original = run.budget_exceeded
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
            final_checks = 0
            def cross_after_final_check(guard, deadline, observed_at):
                nonlocal final_checks
                result = original(guard, deadline, observed_at)
                if fixture.calls.count('v1/chat/completions') == 65:
                    final_checks += 1
                    if final_checks == 2:
                        clock.advance(run.INFERENCE_BUDGET_SECONDS)
                return result
            with patch.object(run, 'budget_exceeded', side_effect=cross_after_final_check), self.assertRaisesRegex(TimeoutError, 'inference budget expired before cleanup'):
                fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertEqual(final_checks, 2)
            self.assertEqual(meta['status'], 'incomplete')
            self.assertTrue(meta['inference_budget_exceeded'])
            self.assertFalse(meta['inference_watchdog_fired'])
            self.assertTrue(meta['failure'].startswith('TimeoutError:'))


    def test_callback_firing_during_cleanup_cannot_retroactively_overrun_run(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture, patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
            def callback_during_cleanup(timer):
                if len(timers.instances) == 2 and timer is timers.instances[1] and not timer.cancelled:
                    timer.fire()
            timers.before_cancel = callback_during_cleanup
            fixture.execute()
            meta = json.loads((fixture.args.out/'metadata.json').read_text())
            self.assertEqual(meta['status'], 'complete')
            self.assertEqual(meta['post_ready_seconds'], 0)
            self.assertTrue(meta['inference_watchdog_fired'])
            self.assertFalse(meta['inference_budget_exceeded'])


    def test_absolute_watchdog_adapter_deducts_preparation_time(self):
        clock = ControlledClock()
        timers = ControlledTimers(clock)
        with patch.object(run.time, 'perf_counter', clock), patch.object(safety.threading, 'Timer', timers):
            deadline = clock() + 180
            clock.advance(17)
            guard = run.start_owned_watchdog(FakeProcess(), deadline)
            self.assertEqual(timers.instances[0].seconds, 163)
            self.assertEqual(timers.instances[0].due, deadline)
            guard.close()


    def test_evidence_tampering_and_incomplete_rows_rejected(self):
        mutations = [lambda m: m.update(status='incomplete'), lambda m: m.update(owned_process_stopped=False),
                     lambda m: m.update(schema_version=True),
                     lambda m: m.update(post_ready_seconds=181), lambda m: m.update(probe_count=96),
                     lambda m: m.update(model_sha256_observed='0'*64), lambda m: m.update(smoke_status='pending'),
                     lambda m: m['model_spec']['sampling'].update(temperature=.1),
                     lambda m: m['command'].extend(['--override-kv', 'qwen35.block_count=int:1']),
                     lambda m: m.update(batch_started_at_seconds=0),
                     lambda m: m['startup_checks']['cuda_proof'].update(offloaded_layers=1)]
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture:
            fixture.execute()
            originals = {p.name: p.read_bytes() for p in fixture.args.out.iterdir() if p.is_file()}
            for mutate in mutations:
                for name, data in originals.items(): (fixture.args.out/name).write_bytes(data)
                meta = json.loads(originals['metadata.json']); mutate(meta)
                run.write_json(fixture.args.out/'metadata.json', meta)
                fixture.rehash()
                with self.assertRaises((ValueError, RuntimeError)): fixture.validate()
            for filename in ('results.jsonl', 'token-preflight.jsonl', 'wire.jsonl'):
                for name, data in originals.items(): (fixture.args.out/name).write_bytes(data)
                path = fixture.args.out/filename
                path.write_text('\n'.join(path.read_text().splitlines()[1:]))
                fixture.rehash()
                with self.assertRaises(ValueError): fixture.validate()


    def test_exclusive_lock_never_removes_an_existing_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'lock'
            with run.owned_model_lock(path):
                with self.assertRaises(FileExistsError):
                    with run.owned_model_lock(path): pass
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())


    def test_cleanup_failure_is_terminal_and_retains_lock_for_live_child(self):
        for cleanup in ('raises', 'returns_without_stopping'):
            with self.subTest(cleanup=cleanup), tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture:
                path = Path(tmp)/'model.lock'
                replacement = {'side_effect': OSError('synthetic termination failure')} if cleanup == 'raises' else {'return_value': None}
                with patch.object(run, 'stop_owned', **replacement), self.assertRaises(run.OwnedProcessCleanupError):
                    with run.owned_model_lock(path) as ownership:
                        fixture.execute(ownership)
                self.assertIsNone(fixture.proc.poll())
                self.assertTrue(path.exists())
                with self.assertRaises(FileExistsError):
                    with run.owned_model_lock(path): pass
                meta = json.loads((fixture.args.out/'metadata.json').read_text())
                self.assertEqual(meta['status'], 'incomplete')
                self.assertFalse(meta['owned_process_stopped'])
                self.assertTrue((fixture.args.out/'manifest.json').exists())
                with self.assertRaises(ValueError): fixture.validate()
                fixture.proc.terminate()  # End only the fake process after assertions.


    def test_successful_cleanup_releases_lock_after_owned_child_stops(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture:
            path = Path(tmp)/'model.lock'
            with run.owned_model_lock(path) as ownership:
                fixture.execute(ownership)
                self.assertIsNotNone(fixture.proc.poll())
                self.assertTrue(ownership.termination_confirmed)
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())
            fixture.validate()


    def test_inflight_child_exception_does_not_release_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'model.lock'
            with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'):
                with run.owned_model_lock(path) as ownership:
                    ownership.starting_child()
                    raise RuntimeError('synthetic interruption before confirmed cleanup')
            self.assertTrue(path.exists())


    def test_inflight_child_cannot_leave_lock_context_successfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'model.lock'
            with self.assertRaises(run.OwnedProcessCleanupError):
                with run.owned_model_lock(path) as ownership:
                    ownership.starting_child()
            self.assertTrue(path.exists())


    def test_full_success_order_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as f:
            f.execute()
            meta, cases, rows = f.validate()
            self.assertEqual(f.calls, ['health', 'v1/models'] + ['apply-template', 'tokenize'] * 65 + ['v1/chat/completions'] * 65)
            self.assertEqual(len(rows), 64)
            self.assertEqual(sum(cases[i]['arm'] == 'A' for i in range(0, 64, 2)), 16)
            report = validator.report(f.args.out, f.historical, f.fresh, f.design)
            self.assertEqual(report['paired_latency_ratios']['all']['count'], 32)
            self.assertEqual(report['paired_latency_ratios']['matcher_active']['count'], 16)
            self.assertEqual(len(report['no_match_variability']), 16)
            self.assertEqual(report['semantic_eligibility'], 'unknown; requires frozen independent source-only review')

    def test_prompt_limits_stop_before_completion(self):
        for bad in (385, True):
            with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as f:
                real = run.checked_tokens
                with patch.object(run, 'checked_tokens', side_effect=lambda r: real({'tokens': [1] * bad}) if type(bad) is int else real({'tokens': [True]})):
                    with self.assertRaises(ValueError): f.execute()
                self.assertNotIn('v1/chat/completions', f.calls)
        with self.assertRaises(ValueError): run.policy().check_applied_token_counts(100, 165)
        with self.assertRaises(ValueError): run.policy().prepare_pair('光翼蓮桜泉', run.CANON)

    def test_no_match_variability_is_descriptive(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), output=lambda i: '翻译内容' + str(i)) as f:
            f.execute()
            result = validator.report(f.args.out, f.historical, f.fresh, f.design)
            self.assertTrue(all(not r['outputs_identical'] for r in result['no_match_variability']))
            self.assertIn('never glossary benefit', result['no_match_interpretation'])

    def test_rehashed_prompt_and_arm_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as f:
            f.execute()
            originals = {p.name: p.read_bytes() for p in f.args.out.iterdir() if p.is_file()}
            for change in ('prompt', 'arm', 'tokens', 'wire'):
                for name, data in originals.items(): (f.args.out/name).write_bytes(data)
                rows = validator.read_jsonl(f.args.out/'results.jsonl')
                if change == 'prompt': rows[0]['request']['messages'][0]['content'] += 'changed'
                elif change == 'arm': rows[0]['arm'] = 'B' if rows[0]['arm'] == 'A' else 'A'
                elif change == 'tokens': rows[0]['response']['usage']['prompt_tokens'] += 1
                else: rows.reverse()
                (f.args.out/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
                f.rehash()
                with self.assertRaises(ValueError): f.validate()

    def test_quantile_ratios_use_same_subset_not_quantiles_of_ratios(self):
        cases, rows = [], []
        for i, (a, b) in enumerate([(1, 2), (2, 1), (100, 100), (101, 101)]):
            for arm, seconds in [('A', a), ('B', b)]:
                cases.append({'id': str(i), 'arm': arm, 'matched': [{'src': '光'}], 'category': 'target'})
                rows.append({'seconds': seconds})
        result = validator.paired_cost(cases, rows)
        self.assertEqual(result['all']['median_ratio'], 1)
        self.assertEqual(result['all']['p95_nearest_rank_ratio'], 1)
        self.assertTrue(result['cost_eligible'])
        self.assertEqual(max(result['all']['paired_ratios_descriptive']), 2)

    def test_archived_claim_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as f:
            f.execute()
            claim = json.loads((f.args.out/'run-claim.json').read_text())
            claim['run_id'] = '0' * 32
            run.write_json(f.args.out/'run-claim.json', claim)
            f.rehash()
            with self.assertRaises(ValueError): f.validate()

    def test_archived_claim_validates_after_evidence_relocation(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as f:
            f.execute()
            moved = f.root/'relocated-evidence'
            f.args.out.rename(moved)
            f.args.out = moved
            f.args.claim_path.unlink()
            meta, cases, rows = f.validate()
            self.assertEqual(meta['status'], 'complete')

    def test_pending_source_or_runtime_blocks(self):
        with patch.object(run, 'FRESH_SHA', 'PENDING'):
            with self.assertRaisesRegex(ValueError, 'PENDING'): run.experiment_cases(Path('absent'), Path('absent'), Path('absent'))
        with patch.object(run, 'RUNTIME_PIN_SHA', 'PENDING'):
            with self.assertRaisesRegex(ValueError, 'PENDING'): run.verify_runtime_pins(Path('absent'), Path('absent'), Path('absent'))

if __name__ == '__main__':
    unittest.main()
