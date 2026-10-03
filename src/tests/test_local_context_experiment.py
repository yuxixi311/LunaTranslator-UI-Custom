"""Test-only prompt experiment checks; no model execution or semantic grading."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
from contextlib import ExitStack
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/local_eval'
sys.path.insert(0, str(TOOLS))
import run
import run_prompt_experiment as v1
import run_context_experiment as experiment
import summarize_context_experiment as summary


class ContextExperimentTests(unittest.TestCase):
    def test_only_context_field_changes(self):
        case = {'source': '合成例です。', 'context_sentences': ['前の合成文です。']}
        empty = experiment.request_body(case, 'owned', 'baseline')
        populated = experiment.request_body(case, 'owned', 'candidate')
        self.assertEqual(empty['messages'][0]['content'], '〖背景信息〗\n\n请结合背景信息将以下文本翻译为简体中文。\n〖待翻译文本〗\n合成例です。')
        self.assertEqual(populated['messages'][0]['content'].replace('前の合成文です。', ''), empty['messages'][0]['content'])
        empty.pop('messages'); populated.pop('messages')
        self.assertEqual(empty, populated)
        with self.assertRaises(ValueError): experiment.request_body(case, 'owned', 'wrong')

    def test_original_safety_functions_are_identical(self):
        def definitions(path):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            return {node.name: ast.dump(node) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        old, new = definitions(TOOLS / 'run.py'), definitions(Path(experiment.__file__))
        for name in ('digest', 'NoRedirect', 'check_startup_log'):
            self.assertEqual(old[name], new[name])
        source = Path(experiment.__file__).read_text(encoding='utf-8')
        self.assertIn("choices=('1.8b',)", source)
        self.assertIn('reserve = 2300 * 1024**2', source)
        self.assertIn("size + 1024 * MIB", source)
        self.assertIn("if not a.restrict_cors_to_loopback:", source)
        self.assertIn("check_startup_log(log_path, cuda=bool(gpu), require_gpu=True)", source)

    def fixture(self, directory):
        cases = []
        for i in range(12):
            for alt in ('a', 'b'):
                cases.append({'id': str(i)+alt, 'family_id': str(i), 'kind': 'family', 'alternative': alt,
                              'source': '合成例です。', 'context_sentences': ['合成背景'+alt+'。']})
        cases += [{'id':'control'+str(i), 'family_id':'control'+str(i), 'kind':'control', 'alternative':'control',
                   'source':'合成対照例です。', 'context_sentences':['前の合成文です。']} for i in range(8)]
        path = Path(directory)/'fixture.json'
        path.write_text(json.dumps({'schema_version':1,'cases':cases}),encoding='utf-8')
        return path

    def test_fixture_bounds_hash_and_pair_balance(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = self.fixture(tmp)
            with patch.object(experiment,'FRESH_SHA',experiment.digest(fresh)):
                cases=experiment.experiment_cases(fresh)
                self.assertEqual(len(cases),64)
                self.assertEqual(sum(cases[i]['variant']=='baseline' for i in range(0,64,2)),16)
            with self.assertRaises(ValueError):experiment.experiment_cases(fresh)
            data=json.loads(fresh.read_text()); data['cases'][0]['context_sentences']=['あ'*129]
            fresh.write_text(json.dumps(data))
            with patch.object(experiment,'FRESH_SHA',experiment.digest(fresh)),self.assertRaises(ValueError):experiment.experiment_cases(fresh)

    def fake_probe(self, endpoint, body, wire=None):
        if endpoint=='apply-template':
            return {'prompt':'<｜hy_begin▁of▁sentence｜><｜hy_User｜>'+body['messages'][0]['content']+'<｜hy_Assistant｜>'}
        return {'tokens': list(range(20)) if body['parse_special'] else list(range(3 if body['content'] else 0))}

    def test_token_probes_fail_closed_before_completions(self):
        case={'id':'x','variant':'candidate','source':'合成例。','context_sentences':['前文。']}
        calls=[]
        def call(endpoint,body,wire):
            calls.append(endpoint)
            return self.fake_probe(endpoint,body,wire)
        records=experiment.preflight_tokens([case],'owned',call,None)
        self.assertEqual(calls,['tokenize','apply-template','tokenize'])
        self.assertEqual(records[0]['prompt_tokens'],20)
        for bad in ({'tokens':[0]*129},{'tokens':[True]},{'tokens':[-1]}):
            with self.assertRaises(ValueError):experiment.checked_tokens(bad,128)
        with self.assertRaises(ValueError):experiment.preflight_tokens([case],'owned',lambda *args:{'tokens':[1]*129},None)
        with self.assertRaises(ValueError):experiment.preflight_tokens([case],'owned',lambda *args:{'tokens':[]},None)
        self.assertEqual(experiment.checked_tokens({'tokens':[]},128,0),0)
        with self.assertRaises(ValueError):experiment.checked_tokens({'tokens':[]},384,1)

    def test_general_structure_and_deadline_guard(self):
        self.assertFalse(experiment.check_format('<em data-id="x">%1$s</em>', '%1$s')['protected_structure_exact'])
        self.assertFalse(experiment.check_format('名前 %1$s 点 %2$d', '名字')['protected_structure_exact'])
        self.assertFalse(experiment.check_format('%s: %d', '%d: %s')['protected_structure_exact'])
        self.assertTrue(experiment.check_format('%1$s: %2$d', '%2$d: %1$s')['protected_structure_exact'])
        proc = object()
        with patch.object(experiment, 'stop_owned') as stop:
            guard = experiment.InferenceDeadline(proc, seconds=.01)
            guard.start()
            self.assertTrue(guard.expired.wait(1))
            guard.close()
            stop.assert_called_once_with(proc)
            self.assertIsNone(guard.error)

    def test_legacy_false_positive_is_not_counted_as_general_failure(self):
        row = {'seconds': .1, 'response': {'usage': {'prompt_tokens': 4, 'completion_tokens': 2}},
               'format': experiment.check_format('%score', '积分')}
        result = summary.metrics([row])
        self.assertEqual(result['legacy_basic_token_failures'], 1)
        self.assertEqual(result['legacy_only_flags'], 1)
        self.assertEqual(result['protected_structure_failures'], 0)

    def test_startup_watchdog_interrupts_blocked_read_and_cleans_up(self):
        # Exercise production main without a runtime/model/network request. The
        # fake read blocks until the owned-child watchdog terminates fake Popen.
        stopped = threading.Event()
        class FakeProcess:
            returncode = None
            def poll(self): return self.returncode
            def terminate(self):
                self.returncode = -15
                stopped.set()
            def kill(self): self.terminate()
            def wait(self, timeout=None): return self.returncode
        proc = FakeProcess()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                if not stopped.wait(2):
                    raise AssertionError('Startup watchdog failed to stop blocked readiness')
                raise TimeoutError('Owned server stopped while readiness read was blocked')
        class Monitor:
            def __init__(self, *args):
                self.stop = threading.Event()
                self.samples = {'resource_guard_stopped_process': False}
                self.thread = types.SimpleNamespace(start=lambda: None, ident=None, is_alive=lambda: False)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            fresh = self.fixture(tmp)
            model, server = root/'model.gguf', root/'llama-server.exe'
            model.write_bytes(b'x'); server.write_bytes(b'test runtime')
            values = {
                'FRESH_SHA': experiment.digest(fresh),
                'STARTUP_BUDGET_SECONDS': .02,
                'MODELS': {'1.8b': (1, experiment.digest(model), experiment.MODELS['1.8b'][2])},
                'memory_available': lambda: 10 * 1024**3, 'RamMonitor': Monitor,
            }
            for name, value in values.items():
                stack.enter_context(patch.object(experiment, name, value))
            stack.enter_context(patch.object(experiment.subprocess, 'check_output', return_value='build 11349, commit fb4b2737a'))
            stack.enter_context(patch.object(experiment.subprocess, 'Popen', return_value=proc))
            stack.enter_context(patch.object(experiment.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=lambda *args, **kwargs: Response())))
            stack.enter_context(patch.object(sys, 'argv', ['run_prompt_experiment_v2.py', '--gguf', str(model), '--server', str(server), '--out', str(root/'out'), '--fresh-fixture', str(fresh), '--restrict-cors-to-loopback']))
            with self.assertRaises(TimeoutError):
                experiment.main()
            self.assertTrue(stopped.is_set())
            metadata = json.loads((root/'out/metadata.json').read_text())
            self.assertTrue(metadata['startup_budget_exceeded'])
            self.assertEqual(metadata['status'], 'incomplete')
            self.assertIsNotNone(proc.poll())

    def test_post_readiness_watchdog_covers_blocked_token_probe(self):
        # Exercise production main without a runtime/model/network request. The
        # fake read blocks until the owned-child watchdog terminates fake Popen.
        stopped = threading.Event()
        class FakeProcess:
            returncode = None
            def poll(self): return self.returncode
            def terminate(self):
                self.returncode = -15
                stopped.set()
            def kill(self): self.terminate()
            def wait(self, timeout=None): return self.returncode
        proc = FakeProcess()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                if not stopped.wait(2):
                    raise AssertionError('Startup watchdog failed to stop blocked readiness')
                raise TimeoutError('Owned server stopped while readiness read was blocked')
        class Monitor:
            def __init__(self, *args):
                self.stop = threading.Event()
                self.samples = {'resource_guard_stopped_process': False}
                self.thread = types.SimpleNamespace(start=lambda: None, ident=None, is_alive=lambda: False)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            fresh = self.fixture(tmp)
            model, server = root/'model.gguf', root/'llama-server.exe'
            model.write_bytes(b'x'); server.write_bytes(b'test runtime')
            values = {
                'FRESH_SHA': experiment.digest(fresh),
                'STARTUP_BUDGET_SECONDS': 2, 'INFERENCE_BUDGET_SECONDS': .02,
                'MODELS': {'1.8b': (1, experiment.digest(model), experiment.MODELS['1.8b'][2])},
                'memory_available': lambda: 10 * 1024**3, 'RamMonitor': Monitor,
            }
            for name, value in values.items():
                stack.enter_context(patch.object(experiment, name, value))
            stack.enter_context(patch.object(experiment.subprocess, 'check_output', return_value='build 11349, commit fb4b2737a'))
            stack.enter_context(patch.object(experiment.subprocess, 'Popen', return_value=proc))
            class ReadyResponse:
                def __init__(self, payload): self.payload=payload
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self):return json.dumps(self.payload).encode()
            def open_request(request, **kwargs):
                if request.full_url.endswith('/health'):return ReadyResponse({'status':'ok'})
                if request.full_url.endswith('/v1/models'):
                    port=request.full_url.split(':')[2].split('/')[0]
                    return ReadyResponse({'data':[{'id':'luna-eval-1.8b-'+port}]})
                self.assertTrue(request.full_url.endswith('/tokenize'))
                return Response()
            stack.enter_context(patch.object(experiment.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=open_request)))
            stack.enter_context(patch.object(sys, 'argv', ['run_prompt_experiment_v2.py', '--gguf', str(model), '--server', str(server), '--out', str(root/'out'), '--fresh-fixture', str(fresh), '--restrict-cors-to-loopback']))
            with self.assertRaises(TimeoutError):
                experiment.main()
            self.assertTrue(stopped.is_set())
            metadata = json.loads((root/'out/metadata.json').read_text())
            self.assertFalse(metadata['startup_budget_exceeded'])
            self.assertTrue(metadata['inference_budget_exceeded'])
            self.assertEqual(metadata['status'], 'incomplete')
            self.assertIsNotNone(proc.poll())

    def synthetic_evidence(self, folder, fresh):
        cases = experiment.experiment_cases(fresh)
        metadata = {
            'status': 'complete', 'experiment': experiment.EXPERIMENT, 'design_sha256': experiment.DESIGN_SHA,
            'model': '1.8b', 'model_sha256': experiment.MODELS['1.8b'][1],
            'fresh_fixture_sha256': experiment.FRESH_SHA,
            'template_sha256': experiment.TEMPLATES['1.8b'][1],
            'harness_sha256': experiment.digest(Path(experiment.__file__)),
            'resource_probe_sha256': experiment.digest(TOOLS/'resources.py'),
            'integrity_checker_sha256': experiment.digest(ROOT/'src/LunaTranslator/myutils/local_translation_integrity.py'),
            'prompt_template': experiment.PROMPT_TEMPLATE,
            'prompt_template_sha256': hashlib.sha256(experiment.PROMPT_TEMPLATE.encode()).hexdigest(),
            'context_char_limit':128,'context_token_limit':128,'prompt_token_limit':384,
            'token_probe_count':192,'token_probe_seconds':.2,
            'resource_guard_stopped_process': False, 'inference_budget_exceeded': False, 'startup_budget_exceeded': False, 'backend': 'cpu',
            'startup_checks': {'security_warning_gate': 'passed', 'cuda_proof': None},
            'peak_process_rss_bytes': 100, 'rss_sample_count': 1,
            'case_count': 32, 'request_count': 64,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
            'inference_budget_seconds': 180, 'startup_budget_seconds': 180, 'runtime_warmup': False,
            'cors_policy': 'owned loopback origin only',
            'model_revision': experiment.MODELS['1.8b'][2],
            'runtime_version': 'build 11349, commit fb4b2737a',
            'server_sha256': 'a'*64, 'runtime_files_sha256': {'llama-server': 'a'*64},
            'gpu_layers': 0, 'gpu': None, 'nvidia_smi_sha256': None,
            'command': ['llama-server', '-lv', '4', '--log-colors', 'off', '--no-log-jsonl',
                        '--no-warmup', '-m', 'model.gguf', '--host', '127.0.0.1', '--port', '23456',
                        '--alias', 'owned', '-c', '2048', '-t', '2', '-tb', '2', '-np', '1', '-ngl', '0',
                        '-b', '128', '-ub', '128', '--chat-template-file', 'hymt_chat_template.jinja',
                        '--cors-origins', 'http://127.0.0.1:23456'],
        }
        rows, wires = [], []
        for case in cases:
            request = experiment.request_body(case, 'owned', case['variant'])
            response = {'model':'owned','choices': [{'finish_reason': 'stop', 'message': {'content': '合成输出'}}],
                        'usage': {'prompt_tokens': 20, 'completion_tokens': 4, 'prompt_tokens_details': {'cached_tokens': 0}}}
            row = {'id': case['id'], 'split': case['split'], 'variant': case['variant'],
                   'request': request, 'response': response, 'seconds': .1,
                   'format': experiment.check_format(case['source'], '合成输出')}
            wire = {'endpoint':'v1/chat/completions'}
            for side in ('request', 'response'):
                raw = json.dumps(row[side]).encode()
                wire[side+'_base64'] = base64.b64encode(raw).decode()
                wire[side+'_sha256'] = hashlib.sha256(raw).hexdigest()
            rows.append(row); wires.append(wire)
        (folder/'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
        (folder/'results.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
        (folder/'wire.jsonl').write_text('\n'.join(map(json.dumps, wires)), encoding='utf-8')
        (folder/'server.log').write_text('synthetic test only', encoding='utf-8')
        probes = experiment.preflight_tokens(cases,'owned',self.fake_probe,None)
        probe_wire=[]
        for record in probes:
            for prefix,endpoint in [('context','tokenize'),('template','apply-template'),('prompt','tokenize')]:
                wire={'endpoint':endpoint}
                for side in ['request','response']:
                    raw=json.dumps(record[prefix+'_'+side]).encode()
                    wire[side+'_base64']=base64.b64encode(raw).decode()
                    wire[side+'_sha256']=hashlib.sha256(raw).hexdigest()
                probe_wire.append(wire)
        (folder/'token-preflight.json').write_text(json.dumps(probes))
        (folder/'token-wire.jsonl').write_text('\n'.join(map(json.dumps,probe_wire)))
        self.manifest(folder)

    def manifest(self, folder):
        names = ('metadata.json', 'results.jsonl', 'wire.jsonl', 'server.log','token-preflight.json','token-wire.jsonl')
        (folder/'manifest.json').write_text(json.dumps({name: experiment.digest(folder/name) for name in names}), encoding='utf-8')

    def test_summary_is_nonsemantic_and_mapping_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); fresh = self.fixture(tmp)
            with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)):
                self.synthetic_evidence(folder, fresh)
                report = summary.summarize(folder, fresh)
                self.assertEqual(report['semantic_grade'], 'not performed')
                self.assertEqual(report['metrics']['family']['baseline']['n'], 24)
                blind = [json.loads(line) for line in (folder/'prompt-blind.jsonl').read_text().splitlines()]
                self.assertEqual(len(blind), 32)
                self.assertEqual(sorted([len(blind[0]['A_context']),len(blind[0]['B_context'])]),[0,1])
                self.assertIn('context availability',blind[0]['review_limit'])
                self.assertNotIn('variant', blind[0]); self.assertNotIn('request', blind[0])
                with self.assertRaises(ValueError):
                    summary.summarize(folder, fresh)

    def test_tamper_or_incomplete_evidence_rejected(self):
        mutations = [lambda m: m.update(status='incomplete'), lambda m: m.update(resource_guard_stopped_process=True),
                     lambda m: m.update(harness_sha256='0'*64), lambda m: m.update(rss_sample_count=0),
                     lambda m: m.update(runtime_version='wrong runtime'), lambda m: m.update(context=9999),
                     lambda m: m.update(threads=200), lambda m: m.update(inference_budget_seconds=999999),
                     lambda m: m.update(startup_budget_exceeded=True), lambda m: m.update(startup_budget_seconds=999999),
                     lambda m: m.update(token_probe_count=1),lambda m: m.update(context_token_limit=999),lambda m: m.update(cors_policy='wildcard'), lambda m: m.update(server_sha256='b'*64),
                     lambda m: m['command'].__setitem__(m['command'].index('--host') + 1, '0.0.0.0')]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp); fresh = self.fixture(tmp)
                with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)):
                    self.synthetic_evidence(folder, fresh)
                    metadata = json.loads((folder/'metadata.json').read_text())
                    mutate(metadata)
                    (folder/'metadata.json').write_text(json.dumps(metadata))
                    self.manifest(folder)
                    with self.assertRaises(ValueError):
                        summary.load_evidence(folder, fresh)

    def test_probe_and_prompt_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);fresh=self.fixture(tmp)
            with patch.object(experiment,'FRESH_SHA',experiment.digest(fresh)):
                self.synthetic_evidence(folder,fresh)
                originals={name:(folder/name).read_text() for name in ['token-preflight.json','token-wire.jsonl','results.jsonl']}
                changes=[('token-preflight.json',lambda x:x[0].update(prompt_tokens=19)),
                         ('token-preflight.json',lambda x:x[0]['template_response'].update(prompt='different template')),
                         ('token-wire.jsonl',lambda x:x[0].update(endpoint='completion')),
                         ('results.jsonl',lambda x:x[0]['response']['usage'].update(prompt_tokens=21))]
                for name,mutate in changes:
                    for key,value in originals.items():(folder/key).write_text(value)
                    records=json.loads(originals[name]) if name.endswith('.json') else [json.loads(l) for l in originals[name].splitlines()]
                    mutate(records)
                    (folder/name).write_text(json.dumps(records) if name.endswith('.json') else '\n'.join(map(json.dumps,records)))
                    self.manifest(folder)
                    with self.assertRaises(ValueError):summary.load_evidence(folder,fresh)


if __name__ == '__main__':
    unittest.main()
