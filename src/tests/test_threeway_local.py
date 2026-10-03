"""Synthetic-only tests: fake model/runtime/process/HTTP; no model execution."""
import ast
import base64
import copy
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/local_eval'
sys.path.insert(0, str(TOOLS))
import run_threeway_local as run
import validate_threeway_local as validator
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


class SyntheticRun:
    """Exercise the real production runner against entirely in-memory doubles."""
    def __init__(self, root, model='hy18', block=None, output=None):
        self.root, self.model, self.block, self.output = root, model, block, output
        self.stack = ExitStack()
        self.proc = FakeProcess()
        self.calls = []
        self.gguf, self.server, self.driver = root/'model.gguf', root/'llama-server', root/'nvidia-smi'
        self.server.write_bytes(b'synthetic runtime')
        self.driver.write_bytes(b'synthetic driver')
        self.design = root/'design.txt'
        self.design.write_text('synthetic design')
        self.historical, self.fresh = root/'historical.json', root/'fresh.json'
        historical = [{'id': f'old-{c}-{i}', 'category': f'category{c}', 'source': '合成の確認です。'} for c in range(8) for i in range(5)]
        fresh = [{'id': f'new-{c}-{i}', 'category': f'category{c}', 'source': '次の合成例です。'} for c in range(8) for i in range(3)]
        run.write_json(self.historical, {'schema_version': 1, 'cases': historical})
        run.write_json(self.fresh, {'schema_version': 1, 'cases': fresh})
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
        self.stack.enter_context(patch.object(run.platform, 'platform', return_value='synthetic test platform'))
        for name, value in {'MODELS': self.specs, 'DESIGN_SHA': run.digest(self.design),
                            'FRESH_SHA': run.digest(self.fresh), 'HISTORICAL_SHA': run.digest(self.historical),
                            'memory_available': lambda: 10*1024**3}.items():
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
                if self.endpoint == owner.block:
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
                case = {'source': body['messages'][0]['content'].split('\n\n', 1)[1]}
                payload = {'prompt': run.expected_prompt(case, self.alias, self.model)}
            elif endpoint == 'tokenize': payload = {'tokens': [1, 2, 3, 4, 5]}
            elif endpoint == 'v1/chat/completions':
                text = '这是一项翻译连接测试。' if self.output is None else self.output
                payload = {'model': self.alias, 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}],
                           'usage': {'prompt_tokens': 5, 'completion_tokens': 6, 'prompt_tokens_details': {'cached_tokens': 0}}}
            else: raise AssertionError(endpoint)
            return Response(endpoint, payload)
        self.stack.enter_context(patch.object(run.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=open_request)))
        return self

    def __exit__(self, *args): return self.stack.__exit__(*args)

    def execute(self, ownership=None):
        cases = run.experiment_cases(self.historical, self.fresh, self.design)
        record = gguf.read_metadata(self.gguf)
        info = gguf.validate_metadata(record, self.specs[self.model])
        run.run_owned(self.args, cases, self.specs[self.model], record, info, 10*1024**3, self.probe,
                      self.gpu, 'build 11349, commit fb4b2737a', {self.server.name: run.digest(self.server)}, ownership)

    def validate(self):
        return validator.load_evidence(self.args.out, self.historical, self.fresh, self.design)

    def rehash(self):
        run.write_json(self.args.out/'manifest.json', {p.name: run.digest(p) for p in self.args.out.iterdir() if p.is_file() and p.name != 'manifest.json'})


class ThreewayTests(unittest.TestCase):
    def test_unfrozen_design_blocks_before_read_or_execution(self):
        with patch.object(run, 'DESIGN_SHA', 'PENDING'), patch.object(run, 'digest') as digest:
            with self.assertRaisesRegex(ValueError, 'PENDING'):
                run.experiment_cases(Path('absent'), Path('absent'), Path('absent'))
            digest.assert_not_called()

    def test_preserved_safety_sources(self):
        reviewed = ROOT.parent/'luna-prompt-experiment'
        if not reviewed.exists(): self.skipTest('Integration comparison source is not included in consumer kit')
        def definitions(path):
            return {n.name: ast.dump(n) for n in ast.parse(path.read_text()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        old, new = definitions(reviewed/'tools/local_eval/run_context_experiment.py'), definitions(Path(safety.__file__))
        for name in ('digest', 'check_format', 'NoRedirect', 'InferenceDeadline', 'check_startup_log'):
            self.assertEqual(old[name], new[name])
        for relative in ('tools/local_eval/resources.py', 'src/LunaTranslator/myutils/local_translation.py', 'src/LunaTranslator/myutils/local_translation_integrity.py'):
            self.assertEqual((ROOT/relative).read_bytes(), (reviewed/relative).read_bytes())

    def test_both_models_share_only_plain_prompt_and_declared_sampling(self):
        case = {'source': '合成文です。'}
        hy = run.request_body(case, 'owned', 'hy18')
        qwen = run.request_body(case, 'owned', 'qwen35_2b')
        self.assertEqual(hy['messages'], qwen['messages'])
        self.assertEqual(qwen['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(hy['seed'], qwen['seed'])
        self.assertEqual(qwen['max_tokens'], 512)
        self.assertEqual(qwen['temperature'], 1.0)
        self.assertEqual(qwen['presence_penalty'], 2.0)
        self.assertEqual(hy['top_p'], .6)
        for bad in ('x\ny', 'x\ry', 'x\u2028y', 'x\u2028', 'x\u2029', 'x\t', 'x'*201, '<|im_start|>user', '<think>secret'):
            with self.assertRaises(ValueError): run.validate_source(bad)
        for bad in ({'tokens': [True]}, {'tokens': []}, {'tokens': [-1]}, {'tokens': [0]*385}):
            with self.assertRaises(ValueError): run.checked_tokens(bad)

    def test_historical_selection_and_source_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp)) as fixture:
            cases = run.experiment_cases(fixture.historical, fixture.fresh, fixture.design)
            self.assertEqual(len(cases), 48)
            self.assertEqual([row['id'] for row in cases[:3]], ['old-0-0', 'old-0-1', 'old-0-4'])
            self.assertEqual(cases[0]['source'], '合成の確認です。')
            public = json.loads(fixture.fresh.read_text())
            public['cases'][0]['context'] = 'not allowed'
            run.write_json(fixture.fresh, public)
            with patch.object(run, 'FRESH_SHA', run.digest(fixture.fresh)), self.assertRaises(ValueError):
                run.experiment_cases(fixture.historical, fixture.fresh, fixture.design)

    def test_bounded_metadata_and_nextn_not_added_twice(self):
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), 'qwen35_2b') as fixture:
            record = gguf.read_metadata(fixture.gguf)
            self.assertEqual(gguf.validate_metadata(record, run.MODELS['qwen35_2b'])['expected_offloaded_layers'], 33)
            for key, value in (('general.architecture', 'wrong'), ('general.file_type', 7), ('qwen35.block_count', True), ('tokenizer.chat_template', 'unknown')):
                changed = copy.deepcopy(record)
                changed['values'][key] = value
                with self.assertRaises(ValueError): gguf.validate_metadata(changed, run.MODELS['qwen35_2b'])
            raw = fixture.gguf.read_bytes()
            for changed in (raw[:10], b'BAD!'+raw[4:], b'GGUF'+struct.pack('<IQQQ', 3, 1, 1, gguf.MAX_STRING_BYTES+1)):
                fixture.gguf.write_bytes(changed)
                with self.assertRaises(ValueError): gguf.read_metadata(fixture.gguf)
            fixture.gguf.write_bytes(raw)
            with patch.object(gguf, 'MAX_METADATA_BYTES', 32), self.assertRaises(ValueError): gguf.read_metadata(fixture.gguf)

    def test_strict_cuda_proof_and_security_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'
            good = 'using device CUDA0\noffloaded 33/33 layers to GPU\nCUDA0 model buffer size = 100 MiB\n'
            path.write_text(good)
            self.assertEqual(run.full_offload_proof(path, {'expected_offloaded_layers': 33})['offloaded_layers'], 33)
            for text in (good.replace('33/33', '32/33'), good.replace('33/33', '34/34'), good.replace('CUDA0', 'CPU'), good+'security: warning\n'):
                path.write_text(text)
                with self.assertRaises(RuntimeError): run.full_offload_proof(path, {'expected_offloaded_layers': 33})

    def test_complete_evidence_for_both_arms_and_order(self):
        for model in run.MODELS:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), model) as fixture:
                fixture.execute()
                meta, cases, rows = fixture.validate()
                self.assertEqual(len(rows), 48)
                self.assertEqual(fixture.calls, ['health', 'v1/models'] + ['apply-template', 'tokenize']*49 + ['v1/chat/completions']*49)
                self.assertTrue(meta['owned_process_stopped'])
                report = validator.report(fixture.args.out, fixture.historical, fixture.fresh, fixture.design)
                self.assertEqual(report['semantic_grade'], 'not performed')
                self.assertEqual(report['metrics']['fresh']['n'], 24)
                self.assertIsNone(report['resources']['peak_process_vram_bytes'])

    def test_smoke_failure_stops_before_batch_and_preserves_raw_output(self):
        for output in ('', 'これは接続確認です。', '<think>secret</think>译文', 'OK', 'This is a translation connection check.'):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), output=output) as fixture:
                with self.assertRaises(ValueError): fixture.execute()
                self.assertEqual(fixture.calls.count('v1/chat/completions'), 1)
                smoke = json.loads((fixture.args.out/'smoke.json').read_text())
                self.assertEqual(smoke['response']['choices'][0]['message']['content'], output)
                self.assertEqual((fixture.args.out/'results.jsonl').read_text(), '')
                with self.assertRaises(ValueError): fixture.validate()

    def test_hidden_reasoning_and_tokens_rejected(self):
        response = {'model': 'owned', 'choices': [{'finish_reason': 'stop', 'message': {'content': '中文'}}],
                    'usage': {'prompt_tokens': 5, 'completion_tokens': 2, 'prompt_tokens_details': {'cached_tokens': 0}}}
        for mutate in (lambda r: r['choices'][0]['message'].update(reasoning_content='hidden'),
                       lambda r: r['usage'].update(completion_tokens_details={'reasoning_tokens': 1}),
                       lambda r: r['usage'].update(prompt_tokens=6),
                       lambda r: r['usage'].update(completion_tokens=513),
                       lambda r: r['usage']['prompt_tokens_details'].update(cached_tokens=True)):
            bad = copy.deepcopy(response); mutate(bad)
            with self.assertRaises(ValueError): run.check_response(bad, 'owned', 5)

    def test_owned_watchdogs_stop_blocked_reads_and_preserve_evidence(self):
        for endpoint, budget in (('health', 'STARTUP_BUDGET_SECONDS'), ('apply-template', 'INFERENCE_BUDGET_SECONDS'), ('v1/chat/completions', 'INFERENCE_BUDGET_SECONDS')):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), block=endpoint) as fixture, patch.object(run, budget, .02):
                with self.assertRaises((TimeoutError, RuntimeError)): fixture.execute()
                self.assertTrue(fixture.proc.stopped.is_set())
                meta = json.loads((fixture.args.out/'metadata.json').read_text())
                self.assertEqual(meta['status'], 'incomplete')
                field = 'startup_budget_exceeded' if endpoint == 'health' else 'inference_budget_exceeded'
                self.assertTrue(meta[field])
                wires = validator.read_jsonl(fixture.args.out/'wire.jsonl')
                self.assertTrue(any(w.get('error') for w in wires))
                self.assertTrue((fixture.args.out/'manifest.json').is_file())

    def test_evidence_tampering_and_incomplete_rows_rejected(self):
        mutations = [lambda m: m.update(status='incomplete'), lambda m: m.update(owned_process_stopped=False),
                     lambda m: m.update(schema_version=True),
                     lambda m: m.update(post_ready_seconds=181), lambda m: m.update(probe_count=96),
                     lambda m: m.update(model_sha256_observed='0'*64), lambda m: m.update(smoke_status='pending'),
                     lambda m: m['model_spec']['sampling'].update(temperature=.1),
                     lambda m: m['command'].extend(['--override-kv', 'qwen35.block_count=int:1']),
                     lambda m: m.update(batch_started_at_seconds=0),
                     lambda m: m['startup_checks']['cuda_proof'].update(offloaded_layers=1)]
        with tempfile.TemporaryDirectory() as tmp, SyntheticRun(Path(tmp), 'qwen35_2b') as fixture:
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


if __name__ == '__main__':
    unittest.main()
