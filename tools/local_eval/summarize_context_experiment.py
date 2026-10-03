"""Validate paired prompt evidence and export input-aware masked-label text plus a separate key; context availability reveals treatment.

This computes structure/timing only. It never grades semantic correctness.
Private semantic criteria are intentionally not inputs to this tool.
"""
import argparse
import base64
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

import run_context_experiment as experiment


def validate_execution(meta, log_path):
    fixed = {'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
             'inference_budget_seconds': experiment.INFERENCE_BUDGET_SECONDS,
             'startup_budget_seconds': experiment.STARTUP_BUDGET_SECONDS,
             'runtime_warmup': False, 'cors_policy': 'owned loopback origin only',
             'model_revision': experiment.MODELS['1.8b'][2]}
    for field, expected in fixed.items():
        if meta.get(field) != expected:
            raise ValueError('Execution configuration mismatch: ' + field)
    if 'build 11349, commit fb4b2737a' not in meta.get('runtime_version', ''):
        raise ValueError('Wrong pinned runtime')
    command = meta['command']
    if not isinstance(command, list) or not all(isinstance(value, str) for value in command):
        raise ValueError('Malformed runtime command')
    def argument(flag):
        if command.count(flag) != 1:
            raise ValueError('Missing/duplicate runtime argument: ' + flag)
        return command[command.index(flag) + 1]
    model, port, alias = argument('-m'), argument('--port'), argument('--alias')
    if not port.isdigit() or not 1 <= int(port) <= 65535 or not alias:
        raise ValueError('Invalid loopback port/alias')
    cuda = meta['backend'] == 'cuda'
    expected_command = [command[0], '-lv', '4', '--log-colors', 'off', '--no-log-jsonl',
                        '--no-warmup', '-m', model, '--host', '127.0.0.1', '--port', port,
                        '--alias', alias, '-c', '2048', '-t', '2', '-tb', '2', '-np', '1',
                        '-ngl', '99' if cuda else '0', '-b', '128', '-ub', '128',
                        '--chat-template-file', argument('--chat-template-file'),
                        '--cors-origins', 'http://127.0.0.1:' + port]
    if cuda:
        expected_command += ['--device', 'CUDA0']
    if command != expected_command or meta.get('gpu_layers') != (99 if cuda else 0):
        raise ValueError('Runtime command differs from the preregistration')
    def valid_hash(value):
        return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None
    files = meta.get('runtime_files_sha256')
    server_name = command[0].replace('\\', '/').rsplit('/', 1)[-1]
    if not isinstance(files, dict) or not files or not all(valid_hash(value) for value in files.values()):
        raise ValueError('Runtime file hashes missing/invalid')
    if not valid_hash(meta.get('server_sha256')) or files.get(server_name) != meta['server_sha256']:
        raise ValueError('Runtime hash evidence inconsistent')
    if cuda:
        if not valid_hash(meta.get('nvidia_smi_sha256')) or not isinstance(meta.get('gpu'), dict) or not meta['gpu'].get('uuid'):
            raise ValueError('Missing CUDA driver/device evidence')
    elif meta.get('gpu') is not None or meta.get('nvidia_smi_sha256') is not None:
        raise ValueError('CPU run has inconsistent CUDA metadata')
    proof = experiment.check_startup_log(log_path, cuda=cuda, require_gpu=True)
    if meta.get('startup_checks', {}).get('cuda_proof') != proof:
        raise ValueError('CUDA trace proof differs from metadata')
    return alias


def load_evidence(folder, fresh_fixture):
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for filename in ('metadata.json', 'results.jsonl', 'wire.jsonl', 'server.log', 'token-preflight.json', 'token-wire.jsonl'):
        if manifest.get(filename) != experiment.digest(folder / filename):
            raise ValueError('Run manifest mismatch: ' + filename)
    expected = {
        'status': 'complete', 'experiment': experiment.EXPERIMENT, 'design_sha256': experiment.DESIGN_SHA,
        'model': '1.8b', 'model_sha256': experiment.MODELS['1.8b'][1],
        'fresh_fixture_sha256': experiment.FRESH_SHA,
        'template_sha256': experiment.TEMPLATES['1.8b'][1],
        'harness_sha256': experiment.digest(Path(experiment.__file__)),
        'resource_probe_sha256': experiment.digest(Path(experiment.__file__).with_name('resources.py')),
        'integrity_checker_sha256': experiment.digest(experiment.ROOT / 'src/LunaTranslator/myutils/local_translation_integrity.py'),
        'prompt_template': experiment.PROMPT_TEMPLATE,
        'prompt_template_sha256': hashlib.sha256(experiment.PROMPT_TEMPLATE.encode('utf-8')).hexdigest(),
        'context_char_limit': experiment.CONTEXT_CHAR_LIMIT,
        'context_token_limit': experiment.CONTEXT_TOKEN_LIMIT, 'prompt_token_limit': experiment.PROMPT_TOKEN_LIMIT,
    }
    for field, value in expected.items():
        if meta.get(field) != value:
            raise ValueError('Unrecognized/incomplete experiment: ' + field)
    if meta.get('resource_guard_stopped_process') is not False or meta.get('cleanup_error') or meta.get('inference_budget_exceeded') is not False or meta.get('budget_stop_error') or meta.get('startup_budget_exceeded') is not False or meta.get('startup_stop_error'):
        raise ValueError('Resource stop or failed cleanup')
    if meta.get('startup_checks', {}).get('security_warning_gate') != 'passed':
        raise ValueError('Missing startup security evidence')
    if meta.get('backend') not in ('cpu', 'cuda') or meta.get('rss_sample_count', 0) <= 0 or not meta.get('peak_process_rss_bytes'):
        raise ValueError('Missing backend/RAM measurement')
    alias = validate_execution(meta, folder / 'server.log')
    cases = experiment.experiment_cases(fresh_fixture)
    if meta.get('case_count') != len(cases) // 2 or meta.get('request_count') != len(cases):
        raise ValueError('Metadata count mismatch')
    rows = [json.loads(line) for line in (folder / 'results.jsonl').read_text(encoding='utf-8').splitlines()]
    wires = [json.loads(line) for line in (folder / 'wire.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows) != len(cases) or len(wires) != len(cases):
        raise ValueError('Missing or duplicate paired records')
    probes = validate_token_probes(folder, cases, alias, meta)
    for index, (case, row, wire) in enumerate(zip(cases, rows, wires)):
        if (row['id'], row['split'], row['variant']) != (case['id'], case['split'], case['variant']):
            raise ValueError('Unexpected case, split, or arm order')
        if row['request'] != experiment.request_body(case, alias, case['variant']):
            raise ValueError('Request does not match the preregistration')
        for side in ('request', 'response'):
            raw = base64.b64decode(wire[side + '_base64'], validate=True)
            if hashlib.sha256(raw).hexdigest() != wire[side + '_sha256'] or json.loads(raw) != row[side]:
                raise ValueError('Raw wire record mismatch')
        if wire.get('endpoint') != 'v1/chat/completions':
            raise ValueError('Wrong inference endpoint')
        response = row['response']
        if response.get('model') != alias:
            raise ValueError('Response alias mismatch')
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop' or not isinstance(choice['message']['content'], str) or not choice['message']['content'].strip():
            raise ValueError('Incomplete output')
        usage = response['usage']
        if usage['prompt_tokens'] != probes[index]['prompt_tokens']:
            raise ValueError('Actual prompt-token count differs from token probe')
        if usage['prompt_tokens_details']['cached_tokens'] != 0:
            raise ValueError('Prompt cache was used')
        for field in ('prompt_tokens', 'completion_tokens'):
            if type(usage[field]) is not int or usage[field] <= 0:
                raise ValueError('Missing token count')
        if not isinstance(row['seconds'], (int, float)) or not math.isfinite(row['seconds']) or row['seconds'] <= 0:
            raise ValueError('Invalid latency')
        if row['format'] != experiment.check_format(case['source'], choice['message']['content']):
            raise ValueError('Format check mismatch')
    return meta, cases, rows


def validate_token_probes(folder, cases, alias, meta):
    probes = json.loads((folder / 'token-preflight.json').read_text(encoding='utf-8'))
    wires = [json.loads(line) for line in (folder / 'token-wire.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(probes) != len(cases) or len(wires) != 3 * len(cases) or meta.get('token_probe_count') != len(wires):
        raise ValueError('Token-probe count mismatch')
    duration = meta.get('token_probe_seconds')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration < experiment.INFERENCE_BUDGET_SECONDS:
        raise ValueError('Invalid token-probe duration')
    for index, (case, probe) in enumerate(zip(cases, probes)):
        if (probe['id'], probe['variant']) != (case['id'], case['variant']):
            raise ValueError('Token-probe order mismatch')
        context_body, template_body = experiment.token_probe_bodies(case, alias)
        expected_rendered = '<｜hy_begin▁of▁sentence｜><｜hy_User｜>' + template_body['messages'][0]['content'] + '<｜hy_Assistant｜>'
        expected_prompt = {'content': expected_rendered, 'add_special': False, 'parse_special': True}
        if probe['context_request'] != context_body or probe['template_request'] != template_body or probe['prompt_request'] != expected_prompt or probe['template_response'].get('prompt') != expected_rendered:
            raise ValueError('Token-probe request/template mismatch')
        if probe['context_tokens'] != experiment.checked_tokens(probe['context_response'], experiment.CONTEXT_TOKEN_LIMIT, int(bool(context_body['content']))) or probe['prompt_tokens'] != experiment.checked_tokens(probe['prompt_response'], experiment.PROMPT_TOKEN_LIMIT, 1):
            raise ValueError('Token count mismatch')
        for offset, (prefix, endpoint) in enumerate((('context', 'tokenize'), ('template', 'apply-template'), ('prompt', 'tokenize'))):
            wire = wires[3 * index + offset]
            if wire.get('endpoint') != endpoint:
                raise ValueError('Token-probe endpoint mismatch')
            for side in ('request', 'response'):
                raw = base64.b64decode(wire[side + '_base64'], validate=True)
                if hashlib.sha256(raw).hexdigest() != wire[side + '_sha256'] or json.loads(raw) != probe[prefix + '_' + side]:
                    raise ValueError('Token-probe wire mismatch')
    return probes


def metrics(rows):
    seconds = sorted(row['seconds'] for row in rows)
    return {
        'n': len(rows), 'seconds_p50': statistics.median(seconds),
        'seconds_p95_nearest_rank': seconds[math.ceil(.95 * len(seconds)) - 1],
        'prompt_tokens_median': statistics.median(row['response']['usage']['prompt_tokens'] for row in rows),
        'completion_tokens_median': statistics.median(row['response']['usage']['completion_tokens'] for row in rows),
        'protected_structure_failures': sum(not row['format']['protected_structure_exact'] for row in rows),
        'newline_failures': sum(not row['format']['newline_count_exact'] for row in rows),
        'legacy_basic_token_failures': sum(not row['format']['legacy_basic_tokens_exact'] for row in rows),
        'legacy_only_flags': sum(not row['format']['legacy_basic_tokens_exact'] and row['format']['protected_structure_exact'] for row in rows),
    }


def summarize(folder, fresh_fixture):
    names = ('prompt-summary.json', 'prompt-blind.jsonl', 'prompt-arm-key.json', 'prompt-summary-manifest.json')
    if any((folder / name).exists() for name in names):
        raise ValueError('Summary output already exists; preserve the original arm mapping')
    meta, cases, rows = load_evidence(folder, fresh_fixture)
    report = {'experiment': experiment.EXPERIMENT, 'semantic_grade': 'not performed',
              'scope': 'one matched synthetic run; no quality or deployment recommendation', 'metrics': {}}
    for split in ('all', 'family', 'control'):
        selected = [row for row in rows if split == 'all' or row['split'] == split]
        arms = {arm: metrics([row for row in selected if row['variant'] == arm]) for arm in ('baseline', 'candidate')}
        arms['candidate_cost_ratios'] = {
            key: arms['candidate'][key] / arms['baseline'][key]
            for key in ('seconds_p50', 'seconds_p95_nearest_rank')}
        report['metrics'][split] = arms
    report['resources_whole_process_not_per_arm'] = {
        key: value for key, value in meta.items()
        if key in ('peak_process_rss_bytes', 'minimum_available_ram_bytes', 'peak_process_vram_bytes',
                   'rss_sample_count', 'vram_sample_count', 'resource_guard_stopped_process')}
    pairs = []
    blind, key = [], []
    rng = random.SystemRandom()
    for index in range(0, len(rows), 2):
        pair = rows[index:index + 2]
        by_arm = {row['variant']: row for row in pair}
        arms = ['baseline', 'candidate']
        rng.shuffle(arms)
        case = cases[index]
        blind.append({'id': case['id'], 'split': case['split'], 'family_id': case['family_id'], 'alternative': case['alternative'],
                      'source': case['source'],
                      'A': by_arm[arms[0]]['response']['choices'][0]['message']['content'],
                      'B': by_arm[arms[1]]['response']['choices'][0]['message']['content'],
                      'A_context': case['context_sentences'] if arms[0] == 'candidate' else [],
                      'B_context': case['context_sentences'] if arms[1] == 'candidate' else [],
                      'review_limit': 'Input-aware masked labels; context availability can reveal treatment',
                      'A_score': None, 'B_score': None, 'notes': ''})
        key.append({'id': case['id'], 'A': arms[0], 'B': arms[1]})
        pairs.append({'id': case['id'], 'split': case['split'],
                      'candidate_minus_baseline_seconds': by_arm['candidate']['seconds'] - by_arm['baseline']['seconds'],
                      'candidate_minus_baseline_prompt_tokens': by_arm['candidate']['response']['usage']['prompt_tokens'] - by_arm['baseline']['response']['usage']['prompt_tokens']})
    report['paired_differences'] = pairs
    (folder / names[0]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / names[1]).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in blind), encoding='utf-8')
    (folder / names[2]).write_text(json.dumps(key, indent=2), encoding='utf-8')
    (folder / names[3]).write_text(json.dumps({name: experiment.digest(folder / name) for name in names[:3]}, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--fresh-fixture', type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.folder, args.fresh_fixture)
    print(json.dumps({'experiment': report['experiment'], 'semantic_grade': report['semantic_grade'], 'metrics': report['metrics']}, indent=2))
