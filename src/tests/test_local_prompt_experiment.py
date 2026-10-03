"""Test-only prompt experiment checks; no model execution or semantic grading."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/local_eval'
sys.path.insert(0, str(TOOLS))
import run
import run_prompt_experiment as experiment
import summarize_prompt_experiment as summary


class PromptExperimentTests(unittest.TestCase):
    def test_baseline_exact_and_candidate_one_addition_only(self):
        source = 'これは合成例です。\n次の行。'
        baseline = experiment.request_body(source, 'owned', 'baseline')
        candidate = experiment.request_body(source, 'owned', 'candidate')
        self.assertEqual(baseline, run.request_body(source, 'owned'))
        self.assertEqual(candidate['messages'][0]['content'].replace('\n' + experiment.CANDIDATE_ADDITION, '', 1), baseline['messages'][0]['content'])
        baseline.pop('messages'); candidate.pop('messages')
        self.assertEqual(candidate, baseline)
        with self.assertRaises(ValueError):
            experiment.request_body(source, 'owned', 'unregistered')

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
        path = Path(directory) / 'fresh.json'
        path.write_text(json.dumps({'cases': [{'id': 'new-%02d' % i, 'category': 'synthetic', 'source': '合成例', 'context': '', 'glossary': []} for i in range(24)]}), encoding='utf-8')
        return path

    def test_pair_count_order_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = self.fixture(tmp)
            with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)):
                cases = experiment.experiment_cases(fresh)
                self.assertEqual(len(cases), 128)
                self.assertEqual(sum(c['split'] == 'regression' for c in cases), 80)
                self.assertEqual(sum(c['split'] == 'fresh' for c in cases), 48)
                self.assertEqual(sum(cases[i]['variant'] == 'baseline' for i in range(0, 128, 2)), 32)
                for i in range(0, 128, 2):
                    self.assertEqual(cases[i]['id'], cases[i+1]['id'])
                    self.assertEqual({cases[i]['variant'], cases[i+1]['variant']}, {'baseline', 'candidate'})
            with self.assertRaises(ValueError):
                experiment.experiment_cases(fresh)

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

    def synthetic_evidence(self, folder, fresh):
        cases = experiment.experiment_cases(fresh)
        metadata = {
            'status': 'complete', 'experiment': experiment.EXPERIMENT,
            'model': '1.8b', 'model_sha256': experiment.MODELS['1.8b'][1],
            'fixture_sha256': experiment.FIXTURE_SHA, 'fresh_fixture_sha256': experiment.FRESH_SHA,
            'template_sha256': experiment.TEMPLATES['1.8b'][1],
            'harness_sha256': experiment.digest(Path(experiment.__file__)),
            'resource_probe_sha256': experiment.digest(TOOLS/'resources.py'),
            'integrity_checker_sha256': experiment.digest(ROOT/'src/LunaTranslator/myutils/local_translation_integrity.py'),
            'candidate_addition': experiment.CANDIDATE_ADDITION,
            'candidate_sha256': hashlib.sha256(experiment.CANDIDATE_ADDITION.encode()).hexdigest(),
            'resource_guard_stopped_process': False, 'inference_budget_exceeded': False, 'backend': 'cpu',
            'startup_checks': {'security_warning_gate': 'passed', 'cuda_proof': None},
            'peak_process_rss_bytes': 100, 'rss_sample_count': 1,
            'case_count': 64, 'request_count': 128,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
            'inference_budget_seconds': 600, 'runtime_warmup': False,
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
            with patch.object(experiment, 'FRESH_SHA', experiment.digest(fresh)):
                self.synthetic_evidence(folder, fresh)
                report = summary.summarize(folder, fresh)
                self.assertEqual(report['semantic_grade'], 'not performed')
                self.assertEqual(report['metrics']['fresh']['baseline']['n'], 24)
                blind = [json.loads(line) for line in (folder/'prompt-blind.jsonl').read_text().splitlines()]
                self.assertEqual(len(blind), 64)
                self.assertNotIn('variant', blind[0]); self.assertNotIn('request', blind[0])
                with self.assertRaises(ValueError):
                    summary.summarize(folder, fresh)

    def test_tamper_or_incomplete_evidence_rejected(self):
        mutations = [lambda m: m.update(status='incomplete'), lambda m: m.update(resource_guard_stopped_process=True),
                     lambda m: m.update(harness_sha256='0'*64), lambda m: m.update(rss_sample_count=0),
                     lambda m: m.update(runtime_version='wrong runtime'), lambda m: m.update(context=9999),
                     lambda m: m.update(threads=200), lambda m: m.update(inference_budget_seconds=999999),
                     lambda m: m.update(cors_policy='wildcard'), lambda m: m.update(server_sha256='b'*64),
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


if __name__ == '__main__':
    unittest.main()
