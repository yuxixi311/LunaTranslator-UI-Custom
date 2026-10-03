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
import run_prompt_experiment_v2 as experiment
import summarize_prompt_experiment_v2 as summary


class PromptExperimentV2Tests(unittest.TestCase):
    def test_baseline_exact_and_candidate_one_addition_only(self):
        source = 'これは合成例です。\n次の行。'
        baseline = experiment.request_body(source, 'owned', 'baseline')
        candidate = experiment.request_body(source, 'owned', 'candidate')
        self.assertEqual(baseline, run.request_body(source, 'owned'))
        self.assertEqual(candidate['messages'][0]['content'].removeprefix(experiment.CANDIDATE_ADDITION + '\n'), baseline['messages'][0]['content'])
        baseline.pop('messages'); candidate.pop('messages')
        self.assertEqual(candidate, baseline)
        with self.assertRaises(ValueError):
            experiment.request_body(source, 'owned', 'unregistered')

    def test_v2_only_repositions_same_v1_instruction(self):
        source = '合成文です。'
        before = v1.request_body(source, 'owned', 'candidate')
        after = experiment.request_body(source, 'owned', 'candidate')
        baseline = run.request_body(source, 'owned')
        self.assertEqual(experiment.CANDIDATE_ADDITION, v1.CANDIDATE_ADDITION)
        self.assertEqual(after['messages'][0]['content'], experiment.CANDIDATE_ADDITION + '\n' + baseline['messages'][0]['content'])
        self.assertTrue(after['messages'][0]['content'].split('\n\n', 1)[0].endswith('：'))
        for body in (before, after):
            body.pop('messages')
        self.assertEqual(before, after)

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

    def fixture(self, directory, prefix="new"):
        path = Path(directory) / (prefix + '.json')
        path.write_text(json.dumps({'cases': [{'id': prefix + '-%02d' % i, 'category': 'synthetic', 'source': '合成例', 'context': '', 'glossary': []} for i in range(24)]}), encoding='utf-8')
        return path

    def test_pair_count_order_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = self.fixture(tmp)
            previous = self.fixture(tmp, "previous")
            with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)), patch.object(experiment, 'PREVIOUS_FRESH_SHA', experiment.digest(previous)):
                cases = experiment.experiment_cases(fresh, previous)
                self.assertEqual(len(cases), 176)
                self.assertEqual(sum(c['split'] == 'regression' for c in cases), 128)
                self.assertEqual(sum(c['split'] == 'fresh' for c in cases), 48)
                self.assertEqual(sum(cases[i]['variant'] == 'baseline' for i in range(0, 176, 2)), 44)
                for i in range(0, 176, 2):
                    self.assertEqual(cases[i]['id'], cases[i+1]['id'])
                    self.assertEqual({cases[i]['variant'], cases[i+1]['variant']}, {'baseline', 'candidate'})
            with self.assertRaises(ValueError):
                experiment.experiment_cases(fresh, previous)

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
            fresh, previous = self.fixture(tmp), self.fixture(tmp, 'previous')
            model, server = root/'model.gguf', root/'llama-server.exe'
            model.write_bytes(b'x'); server.write_bytes(b'test runtime')
            values = {
                'FRESH_SHA': experiment.digest(fresh), 'PREVIOUS_FRESH_SHA': experiment.digest(previous),
                'STARTUP_BUDGET_SECONDS': .02,
                'MODELS': {'1.8b': (1, experiment.digest(model), experiment.MODELS['1.8b'][2])},
                'memory_available': lambda: 10 * 1024**3, 'RamMonitor': Monitor,
            }
            for name, value in values.items():
                stack.enter_context(patch.object(experiment, name, value))
            stack.enter_context(patch.object(experiment.subprocess, 'check_output', return_value='build 11349, commit fb4b2737a'))
            stack.enter_context(patch.object(experiment.subprocess, 'Popen', return_value=proc))
            stack.enter_context(patch.object(experiment.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=lambda *args, **kwargs: Response())))
            stack.enter_context(patch.object(sys, 'argv', ['run_prompt_experiment_v2.py', '--gguf', str(model), '--server', str(server), '--out', str(root/'out'), '--fresh-fixture', str(fresh), '--previous-fixture', str(previous), '--restrict-cors-to-loopback']))
            with self.assertRaises(TimeoutError):
                experiment.main()
            self.assertTrue(stopped.is_set())
            metadata = json.loads((root/'out/metadata.json').read_text())
            self.assertTrue(metadata['startup_budget_exceeded'])
            self.assertEqual(metadata['status'], 'incomplete')
            self.assertIsNotNone(proc.poll())

    def synthetic_evidence(self, folder, fresh, previous):
        cases = experiment.experiment_cases(fresh, previous)
        metadata = {
            'status': 'complete', 'experiment': experiment.EXPERIMENT,
            'model': '1.8b', 'model_sha256': experiment.MODELS['1.8b'][1],
            'fixture_sha256': experiment.FIXTURE_SHA, 'fresh_fixture_sha256': experiment.FRESH_SHA,
            'previous_fixture_sha256': experiment.PREVIOUS_FRESH_SHA,
            'template_sha256': experiment.TEMPLATES['1.8b'][1],
            'harness_sha256': experiment.digest(Path(experiment.__file__)),
            'resource_probe_sha256': experiment.digest(TOOLS/'resources.py'),
            'integrity_checker_sha256': experiment.digest(ROOT/'src/LunaTranslator/myutils/local_translation_integrity.py'),
            'candidate_addition': experiment.CANDIDATE_ADDITION,
            'candidate_sha256': hashlib.sha256(experiment.CANDIDATE_ADDITION.encode()).hexdigest(),
            'resource_guard_stopped_process': False, 'inference_budget_exceeded': False, 'startup_budget_exceeded': False, 'backend': 'cpu',
            'startup_checks': {'security_warning_gate': 'passed', 'cuda_proof': None},
            'peak_process_rss_bytes': 100, 'rss_sample_count': 1,
            'case_count': 88, 'request_count': 176,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
            'inference_budget_seconds': 600, 'startup_budget_seconds': 180, 'runtime_warmup': False,
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
            request = experiment.request_body(case['source'], 'owned', case['variant'])
            response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '合成输出'}}],
                        'usage': {'prompt_tokens': 20, 'completion_tokens': 4, 'prompt_tokens_details': {'cached_tokens': 0}}}
            row = {'id': case['id'], 'split': case['split'], 'variant': case['variant'],
                   'request': request, 'response': response, 'seconds': .1,
                   'format': experiment.check_format(case['source'], '合成输出')}
            wire = {}
            for side in ('request', 'response'):
                raw = json.dumps(row[side]).encode()
                wire[side+'_base64'] = base64.b64encode(raw).decode()
                wire[side+'_sha256'] = hashlib.sha256(raw).hexdigest()
            rows.append(row); wires.append(wire)
        (folder/'metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
        (folder/'results.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
        (folder/'wire.jsonl').write_text('\n'.join(map(json.dumps, wires)), encoding='utf-8')
        (folder/'server.log').write_text('synthetic test only', encoding='utf-8')
        self.manifest(folder)

    def manifest(self, folder):
        names = ('metadata.json', 'results.jsonl', 'wire.jsonl', 'server.log')
        (folder/'manifest.json').write_text(json.dumps({name: experiment.digest(folder/name) for name in names}), encoding='utf-8')

    def test_summary_is_nonsemantic_and_mapping_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); fresh = self.fixture(tmp)
            previous = self.fixture(tmp, "previous")
            with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)), patch.object(experiment, 'PREVIOUS_FRESH_SHA', experiment.digest(previous)):
                self.synthetic_evidence(folder, fresh, previous)
                report = summary.summarize(folder, fresh, previous)
                self.assertEqual(report['semantic_grade'], 'not performed')
                self.assertEqual(report['metrics']['fresh']['baseline']['n'], 24)
                blind = [json.loads(line) for line in (folder/'prompt-blind.jsonl').read_text().splitlines()]
                self.assertEqual(len(blind), 88)
                self.assertNotIn('variant', blind[0]); self.assertNotIn('request', blind[0])
                with self.assertRaises(ValueError):
                    summary.summarize(folder, fresh, previous)

    def test_tamper_or_incomplete_evidence_rejected(self):
        mutations = [lambda m: m.update(status='incomplete'), lambda m: m.update(resource_guard_stopped_process=True),
                     lambda m: m.update(harness_sha256='0'*64), lambda m: m.update(rss_sample_count=0),
                     lambda m: m.update(runtime_version='wrong runtime'), lambda m: m.update(context=9999),
                     lambda m: m.update(threads=200), lambda m: m.update(inference_budget_seconds=999999),
                     lambda m: m.update(startup_budget_exceeded=True), lambda m: m.update(startup_budget_seconds=999999),
                     lambda m: m.update(cors_policy='wildcard'), lambda m: m.update(server_sha256='b'*64),
                     lambda m: m['command'].__setitem__(m['command'].index('--host') + 1, '0.0.0.0')]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp); fresh = self.fixture(tmp)
                previous = self.fixture(tmp, "previous")
                with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)), patch.object(experiment, 'PREVIOUS_FRESH_SHA', experiment.digest(previous)):
                    self.synthetic_evidence(folder, fresh, previous)
                    metadata = json.loads((folder/'metadata.json').read_text())
                    mutate(metadata)
                    (folder/'metadata.json').write_text(json.dumps(metadata))
                    self.manifest(folder)
                    with self.assertRaises(ValueError):
                        summary.load_evidence(folder, fresh, previous)


if __name__ == '__main__':
    unittest.main()
