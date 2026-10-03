"""Offline evidence validation and timing/structure reporting; no semantic grades."""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import statistics

import run_hy_glossary as experiment


def require_equal(actual, expected, label):
    # JSON booleans must not masquerade as 0/1 or sampling numbers.
    if json.dumps(actual, sort_keys=True, separators=(',', ':')) != json.dumps(expected, sort_keys=True, separators=(',', ':')):
        raise ValueError('Evidence mismatch: ' + label)


def number(value, label, lower=0, upper=float('inf')):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Invalid numeric evidence: ' + label)
    return value


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def decode_wire(wire, allow_error=False):
    result = {}
    for side in ('request', 'response'):
        if side + '_base64' not in wire:
            if allow_error and side == 'response' and wire.get('error'):
                result[side] = None
                continue
            raise ValueError('Missing raw wire evidence')
        raw = base64.b64decode(wire[side + '_base64'], validate=True)
        require_equal(hashlib.sha256(raw).hexdigest(), wire[side + '_sha256'], 'wire ' + side + ' hash')
        result[side] = json.loads(raw) if raw else None
    if wire.get('error') and not allow_error:
        raise ValueError('Failed wire request in successful inference evidence')
    if not wire.get('error'):
        require_equal(wire.get('status'), 200, 'HTTP status')
    return result


def validate_execution(meta, folder, model):
    command = meta.get('command')
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
        raise ValueError('Malformed runtime command')
    def argument(flag):
        if command.count(flag) != 1 or command.index(flag) + 1 >= len(command):
            raise ValueError('Missing/duplicate runtime argument: ' + flag)
        return command[command.index(flag) + 1]
    port = argument('--port')
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Invalid loopback port')
    alias = argument('--alias')
    if not alias:
        raise ValueError('Empty runtime alias')
    require_equal(alias, meta.get('alias'), 'runtime alias')
    expected = experiment.build_command(command[0], argument('-m'), port, alias, argument('--chat-template-file'), model)
    # Exact list equality excludes metadata override flags and all hidden extras.
    require_equal(command, expected, 'fixed command / prohibited overrides')
    if 'build 11349, commit fb4b2737a' not in meta.get('runtime_version', ''):
        raise ValueError('Wrong pinned runtime')
    files = meta.get('runtime_files_sha256')
    if not isinstance(files, dict) or not files or not all(experiment.valid_hash(v) for v in files.values()):
        raise ValueError('Missing runtime hashes')
    server_name = command[0].replace('\\', '/').rsplit('/', 1)[-1]
    require_equal(files.get(server_name), meta.get('server_sha256'), 'server hash consistency')
    if not experiment.valid_hash(meta.get('server_sha256')) or not experiment.valid_hash(meta.get('nvidia_smi_sha256')):
        raise ValueError('Missing server/driver hashes')
    if experiment.digest(experiment.RUNTIME_PINS) != experiment.RUNTIME_PIN_SHA:
        raise ValueError('Runtime pin manifest changed')
    pins = json.loads(experiment.RUNTIME_PINS.read_text(encoding='utf-8'))
    require_equal(files, pins['runtime_files_sha256'], 'entire pinned runtime inventory')
    require_equal(meta.get('nvidia_smi_sha256'), pins['nvidia_smi_sha256'], 'pinned driver hash')
    require_equal(meta.get('server_sha256'), pins['server_sha256'], 'pinned server hash')
    require_equal(meta.get('runtime_version'), pins['runtime_version'], 'pinned runtime version')
    spec = experiment.MODELS[model]
    require_equal(meta.get('model_bytes_observed'), spec['bytes'], 'model size')
    require_equal(meta.get('model_sha256_observed'), spec['sha256'], 'model hash')
    require_equal(meta.get('template_sha256_observed'), spec['template_sha256'], 'explicit template hash')
    require_equal(experiment.digest(experiment.SUPPORT / spec['template_file']), spec['template_sha256'], 'validator template bytes')
    record = json.loads((folder / 'model-metadata.json').read_text(encoding='utf-8'))
    model_info = experiment.validate_metadata(record, spec)
    if not experiment.valid_hash(record.get('metadata_sha256')):
        raise ValueError('Missing raw GGUF metadata digest')
    require_equal(model_info, meta.get('model_metadata'), 'GGUF metadata summary')
    proof = experiment.full_offload_proof(folder / 'server.log', model_info)
    require_equal(meta.get('startup_checks'), {'security_warning_gate': 'passed', 'cuda_proof': proof}, 'startup security/full CUDA proof')
    number(meta.get('memory_available_before'), 'RAM before', spec['bytes'] + 2300 * experiment.MIB)
    number(meta.get('minimum_available_ram_bytes'), 'minimum available RAM', 768 * experiment.MIB)
    number(meta.get('peak_process_rss_bytes'), 'RSS peak', 1)
    if type(meta.get('rss_sample_count')) is not int or meta['rss_sample_count'] < 1:
        raise ValueError('Missing RSS samples')
    gpu = meta.get('gpu')
    if not isinstance(gpu, dict) or not gpu.get('uuid') or not gpu.get('name') or not gpu.get('driver_version'):
        raise ValueError('Missing CUDA device identity')
    number(gpu.get('free_bytes'), 'VRAM before', spec['bytes'] + 1024 * experiment.MIB)
    number(gpu.get('total_bytes'), 'VRAM total', gpu['free_bytes'])
    number(meta.get('vram_sample_count'), 'VRAM sample count')
    if type(meta['vram_sample_count']) is not int:
        raise ValueError('Invalid VRAM sample count')
    if meta['vram_sample_count']:
        number(meta.get('peak_process_vram_bytes'), 'VRAM peak', 1)
    elif meta.get('peak_process_vram_bytes') is not None:
        raise ValueError('Unobserved per-process VRAM must remain unknown')
    require_equal(meta.get('vram_scope'), 'owned server PID on selected GPU only', 'VRAM scope')
    return alias


def load_evidence(folder, historical_fixture, fresh_fixture, design):
    """Return validated metadata, frozen cases, and 48 raw-output rows.

    Missing/incomplete evidence raises; callers must report comparison blocked,
    never count a technical failure as a semantic loss or fourth-arm trigger.
    """
    cases = experiment.experiment_cases(historical_fixture, fresh_fixture, design)
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    required = ('metadata.json', 'model-metadata.json', 'server.log', 'wire.jsonl',
                'token-preflight.jsonl', 'smoke.json', 'results.jsonl', 'run-claim.json')
    for name in required:
        require_equal(manifest.get(name), experiment.digest(folder / name), 'manifest ' + name)
    if set(manifest) != set(required) or {f.name for f in folder.iterdir() if f.is_file()} != set(required) | {'manifest.json'}:
        raise ValueError('Unexpected or missing evidence artifacts')
    claim = experiment.check_claim(json.loads((folder / 'run-claim.json').read_text(encoding='utf-8')))
    require_equal(meta.get('claim_sha256'), experiment.digest(folder / 'run-claim.json'), 'archived persistent claim hash')
    require_equal(meta.get('run_id'), claim['run_id'], 'persistent run identity')
    require_equal(meta.get('claimed_output'), claim['requested_output'], 'claimed original destination')
    model = meta.get('model')
    if model != 'hy18':
        raise ValueError('Unrecognized model arm')
    expected = experiment.base_metadata(model, cases)
    expected.update(status='complete', smoke_status='passed', owned_process_stopped=True)
    expected.pop('startup_checks')
    for key, value in expected.items():
        require_equal(meta.get(key), value, key)
    for key in ('resource_guard_stopped_process', 'startup_budget_exceeded', 'inference_budget_exceeded'):
        if meta.get(key) is not False:
            raise ValueError('Missing/failed resource, cleanup or budget evidence: ' + key)
    for key in ('failure', 'resource_guard_reason', 'cleanup_error', 'startup_stop_error', 'inference_stop_error'):
        if meta.get(key):
            raise ValueError('Incomplete execution: ' + key)
    alias = validate_execution(meta, folder, model)
    startup = number(meta.get('startup_seconds'), 'startup', 0, experiment.STARTUP_BUDGET_SECONDS)
    require_equal(meta.get('ready_at_seconds'), startup, 'ready time')
    post_ready = number(meta.get('post_ready_seconds'), 'post-readiness', 0, experiment.INFERENCE_BUDGET_SECONDS)
    probe_seconds = number(meta.get('token_probe_seconds'), 'token probes', 0, post_ready)
    smoke_seconds = number(meta.get('smoke_seconds'), 'smoke', 0, post_ready)
    wires = read_jsonl(folder / 'wire.jsonl')
    decoded, last_end = [], 0
    for index, wire in enumerate(wires, 1):
        require_equal(wire.get('sequence'), index, 'wire sequence')
        start = number(wire.get('started_seconds'), 'wire start', last_end)
        last_end = number(wire.get('finished_seconds'), 'wire finish', start)
        decoded.append(decode_wire(wire, allow_error=wire.get('endpoint') in ('health', 'v1/models')))
    # Only health/model discovery may precede the fixed probes and completions.
    readiness = len(wires) - 130 - 65
    if readiness < 2:
        raise ValueError('Missing readiness evidence or probe/completion count mismatch')
    for wire in wires[:readiness]:
        if wire['endpoint'] not in ('health', 'v1/models') or decode_wire(wire, True)['request'] is not None:
            raise ValueError('Unexpected pre-probe request')
    require_equal([w['endpoint'] for w in wires[readiness - 2:readiness]], ['health', 'v1/models'], 'last readiness order')
    final_health, final_models = decoded[readiness - 2:readiness]
    if wires[readiness - 2].get('error') or wires[readiness - 1].get('error'):
        raise ValueError('Failed final readiness request')
    require_equal(final_health['response'].get('status'), 'ok', 'readiness status')
    if alias not in [item['id'] for item in final_models['response']['data']]:
        raise ValueError('Owned alias missing from readiness')
    if wires[readiness - 1]['finished_seconds'] > startup:
        raise ValueError('Readiness evidence occurs after ready timestamp')
    tail_wires, tail_data = wires[readiness:], decoded[readiness:]
    require_equal([w['endpoint'] for w in tail_wires], ['apply-template', 'tokenize'] * 65 + ['v1/chat/completions'] * 65, 'all probes before all completions')
    if startup >= 180 or post_ready >= 180:
        raise ValueError('Deadline equality is a terminal timeout')
    if tail_wires[0]['started_seconds'] < startup or tail_wires[-1]['finished_seconds'] > startup + post_ready:
        raise ValueError('Probe/smoke/batch lies outside shared post-readiness budget')
    probes = read_jsonl(folder / 'token-preflight.jsonl')
    if len(probes) != 65:
        raise ValueError('Missing/duplicate token preflight')
    for index, (case, row) in enumerate(zip([experiment.SMOKE] + cases, probes)):
        request = experiment.template_body(case, alias, model)
        prompt = experiment.expected_prompt(case, alias, model)
        token_request = {'content': prompt, 'add_special': False, 'parse_special': True}
        require_equal(row.get('arm'), case.get('arm', 'A'), 'probe arm')
        require_equal(row.get('id'), case['id'], 'probe case ID')
        require_equal(row.get('split'), case['split'], 'probe split')
        require_equal(row.get('template_request'), request, 'probe request')
        require_equal(row['template_response'].get('prompt'), prompt, 'exact rendered template')
        require_equal(row.get('prompt_request'), token_request, 'full-prompt tokenizer request')
        require_equal(row.get('prompt_tokens'), experiment.checked_tokens(row['prompt_response']), 'prompt token count')
        for offset, prefix in enumerate(('template', 'prompt')):
            require_equal(tail_data[2 * index + offset], {side: row[prefix + '_' + side] for side in ('request', 'response')}, 'probe wire')
    for i in range(1, 65, 2):
        pair = {probes[j]['arm']: probes[j]['prompt_tokens'] for j in (i, i + 1)}
        experiment.policy().check_applied_token_counts(pair['A'], pair['B'])
    rows = read_jsonl(folder / 'results.jsonl')
    smoke = json.loads((folder / 'smoke.json').read_text(encoding='utf-8'))
    if len(rows) != 64:
        raise ValueError('Expected exactly 64 scored rows')
    completion_wires, completion_data = tail_wires[130:], tail_data[130:]
    durations = []
    for index, (case, row, wire, decoded_row, probe) in enumerate(zip([experiment.SMOKE] + cases, [smoke] + rows, completion_wires, completion_data, probes)):
        for key in ('id', 'split', 'category'):
            require_equal(row.get(key), case[key], 'output ' + key)
        require_equal(row.get('arm'), case.get('arm', 'A'), 'output arm')
        require_equal(row.get('request'), experiment.request_body(case, alias, model), 'fixed model sampling/prompt')
        require_equal(row.get('validation'), 'passed', 'output validation')
        require_equal(row.get('wire_sequence'), wire['sequence'], 'output wire sequence')
        require_equal(decoded_row, {side: row[side] for side in ('request', 'response')}, 'raw output wire')
        text = experiment.check_response(row['response'], alias, probe['prompt_tokens'], smoke=index == 0)
        require_equal(row.get('format'), experiment.check_format(case['source'], text), 'protected structure')
        elapsed = number(row.get('seconds'), 'completion latency', 0.000000001, post_ready)
        if elapsed + 1e-9 < wire['finished_seconds'] - wire['started_seconds']:
            raise ValueError('Completion duration shorter than raw wire duration')
        durations.append(elapsed)
    require_equal(smoke_seconds, smoke['seconds'], 'smoke timing')
    batch_start = number(meta.get('batch_started_at_seconds'), 'batch start', completion_wires[0]['finished_seconds'], completion_wires[1]['started_seconds'])
    if probe_seconds + sum(durations) > post_ready + 1e-6:
        raise ValueError('Separate timing components exceed shared post-readiness budget')
    if tail_wires[129]['finished_seconds'] - tail_wires[0]['started_seconds'] > probe_seconds + 1e-6:
        raise ValueError('Probe duration does not cover probe wire')
    return meta, cases, rows


def metrics(rows):
    times = sorted(row['seconds'] for row in rows)
    return {'n': len(rows), 'model_request_seconds_median': statistics.median(times),
            'model_request_seconds_p95_nearest_rank': times[math.ceil(.95 * len(times)) - 1],
            'prompt_tokens_median': statistics.median(row['response']['usage']['prompt_tokens'] for row in rows),
            'completion_tokens_median': statistics.median(row['response']['usage']['completion_tokens'] for row in rows),
            'protected_structure_failures': sum(not row['format']['protected_structure_exact'] for row in rows),
            'newline_failures': sum(not row['format']['newline_count_exact'] for row in rows)}


def paired_cost(cases, rows):
    by_id = {}
    for case, row in zip(cases, rows):
        by_id.setdefault(case['id'], {'active': bool(case['matched']), 'category': case['category']})[case['arm']] = row['seconds']
    result = {}
    for subset in ('all', 'matcher_active', *sorted({c['category'] for c in cases})):
        selected = [r for r in by_id.values() if subset == 'all' or (subset == 'matcher_active' and r['active']) or r['category'] == subset]
        ratios = sorted(r['B'] / r['A'] for r in selected)
        arm_a = sorted(r['A'] for r in selected)
        arm_b = sorted(r['B'] for r in selected)
        p95_index = math.ceil(.95 * len(selected)) - 1
        result[subset] = {'count': len(ratios), 'paired_ratios_descriptive': ratios,
                          'median_ratio': statistics.median(arm_b) / statistics.median(arm_a) if selected else None,
                          'p95_nearest_rank_ratio': arm_b[p95_index] / arm_a[p95_index] if selected else None,
                          'arm_a_median': statistics.median(arm_a) if selected else None,
                          'arm_b_median': statistics.median(arm_b) if selected else None,
                          'arm_a_p95': arm_a[p95_index] if selected else None,
                          'arm_b_p95': arm_b[p95_index] if selected else None}
    result['cost_eligible'] = all(result[k]['count'] and result[k]['median_ratio'] <= 1.25 and result[k]['p95_nearest_rank_ratio'] <= 1.25 for k in ('all', 'matcher_active'))
    return result


def report(folder, historical_fixture, fresh_fixture, design):
    meta, cases, rows = load_evidence(folder, historical_fixture, fresh_fixture, design)
    no_match = []
    by_id = {}
    for case, row in zip(cases, rows):
        by_id.setdefault(case['id'], {})[case['arm']] = (case, row)
    for ident, arms in by_id.items():
        if not arms['A'][0]['matched']:
            require_equal(arms['A'][1]['request'], arms['B'][1]['request'], 'no-match identical request')
            no_match.append({'id': ident, 'outputs_identical': arms['A'][1]['response']['choices'][0]['message']['content'] == arms['B'][1]['response']['choices'][0]['message']['content']})
    return {'technical_status': 'complete', 'semantic_eligibility': 'unknown; requires frozen independent source-only review',
            'promotion': 'blocked pending semantic review', 'paired_latency_ratios': paired_cost(cases, rows),
            'no_match_variability': no_match, 'no_match_interpretation': 'Identical prompts; differences are sampling/execution variability, never glossary benefit',
            'timings_seconds': {key: meta[key] for key in ('startup_seconds', 'token_probe_seconds', 'smoke_seconds', 'post_ready_seconds')},
            'metrics': {split: metrics([row for row in rows if split == 'all' or row['split'] == split]) for split in ('all', 'historical', 'fresh')},
            'resources': {key: meta[key] for key in ('memory_available_before', 'minimum_available_ram_bytes', 'peak_process_rss_bytes', 'rss_sample_count', 'gpu', 'peak_process_vram_bytes', 'vram_sample_count', 'vram_scope')}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    for flag in ('historical-fixture', 'fresh-fixture', 'design'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.folder, args.historical_fixture, args.fresh_fixture, args.design), ensure_ascii=False, indent=2))
