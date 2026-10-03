"""Create a paired review sheet only from complete, matched runs.

Keep key.json away from reviewers until scores are locked. This tool does not
judge translation quality or turn automated formatting checks into accuracy.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import random
from run import FIXTURE, FIXTURE_SHA, MODELS, TEMPLATES, digest, request_body


def load_run(folder):
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    rows = [json.loads(x) for x in (folder / 'results.jsonl').read_text(encoding='utf-8').splitlines()]
    if meta.get('schema_version', 1) == 2:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'results.jsonl', 'wire.jsonl', 'server.log'):
            if manifest.get(name) != digest(folder / name):
                raise ValueError('Run file hash mismatch: ' + name)
        wires = [json.loads(x) for x in (folder / 'wire.jsonl').read_text(encoding='utf-8').splitlines()]
        if len(wires) != len(rows):
            raise ValueError('Raw exchange count differs from results')
        for wire, row in zip(wires, rows):
            for kind in ('request', 'response'):
                raw = base64.b64decode(wire[kind + '_base64'], validate=True)
                if hashlib.sha256(raw).hexdigest() != wire[kind + '_sha256'] or json.loads(raw) != row[kind]:
                    raise ValueError('Raw exchange hash/content mismatch')
        if meta.get('resource_guard_stopped_process'):
            raise ValueError('Resource guard stopped this run')
    elif meta.get('schema_version', 1) != 1:
        raise ValueError('Unknown evaluation schema')
    if meta['status'] != 'complete' or meta['fixture_sha256'] != FIXTURE_SHA:
        raise ValueError('Run is incomplete or fixture does not match')
    if meta['model'] not in MODELS:
        raise ValueError('Unknown model')
    _, sha, revision = MODELS[meta['model']]
    if meta['model_sha256'] != sha or meta['model_revision'] != revision:
        raise ValueError('Unrecognized model provenance')
    if meta['template_sha256'] != TEMPLATES[meta['model']][1]:
        raise ValueError('Unrecognized model-specific official template')
    cases = json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']
    expected = [x['id'] for x in cases]
    if [x['id'] for x in rows] != expected:
        raise ValueError('Missing, reordered or duplicated cases')
    for case, row in zip(cases, rows):
        if row['split'] != case['split'] or row['request'] != request_body(case['source'], row['request']['model']):
            raise ValueError('Request does not match canonical frozen case')
        if row['response']['model'] != row['request']['model']:
            raise ValueError('Response model alias does not match request')
        if row['response']['choices'][0]['finish_reason'] != 'stop':
            raise ValueError('Truncated/non-stop output requires a separately documented rerun')
    return meta, rows


def make_sheet(left, right):
    if digest(FIXTURE) != FIXTURE_SHA:
        raise ValueError('Frozen fixture was changed')
    lm, lr = load_run(left); rm, rr = load_run(right)
    if lm['model_sha256'] == rm['model_sha256']:
        raise ValueError('Two distinct models are required for this comparison')
    if lm.get('schema_version', 1) != rm.get('schema_version', 1):
        raise ValueError('Different evaluation schema')
    if lm.get('schema_version') == 2:
        for field in ('backend', 'gpu_layers', 'runtime_files_sha256', 'resource_probe_sha256', 'platform'):
            if lm[field] != rm[field]:
                raise ValueError('Different run configuration: ' + field)
        for field in ('uuid', 'name', 'total_bytes', 'driver_version'):
            if (lm['gpu'] or {}).get(field) != (rm['gpu'] or {}).get(field):
                raise ValueError('Different GPU configuration: ' + field)
    for field in ('context', 'threads', 'batch', 'ubatch', 'runtime_version', 'server_sha256', 'harness_sha256'):
        if lm[field] != rm[field]:
            raise ValueError('Different run configuration: ' + field)
    sheet, key = [], []
    rng = random.SystemRandom()
    for case, l, r in zip(json.loads(FIXTURE.read_text(encoding='utf-8'))['cases'], lr, rr):
        lb = {k:v for k,v in l['request'].items() if k != 'model'}
        rb = {k:v for k,v in r['request'].items() if k != 'model'}
        if lb != rb:
            raise ValueError('Different input or sampling for ' + case['id'])
        pair = [(lm['model'], l), (rm['model'], r)]
        rng.shuffle(pair)
        sheet.append({'id': case['id'], 'split': case['split'], 'source': case['source'],
            'expected_facts_for_review': case['expected_facts'],
            'A': pair[0][1]['response']['choices'][0]['message']['content'],
            'B': pair[1][1]['response']['choices'][0]['message']['content'],
            'A_semantics_0_to_3': None, 'B_semantics_0_to_3': None,
            'A_naturalness_0_to_2': None, 'B_naturalness_0_to_2': None,
            'preference_A_B_tie': None, 'notes': ''})
        key.append({'id': case['id'], 'A': pair[0][0], 'B': pair[1][0]})
    return sheet, key


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('left', type=Path); p.add_argument('right', type=Path)
    p.add_argument('out', type=Path)
    a = p.parse_args(); sheet, key = make_sheet(a.left, a.right)
    a.out.mkdir(parents=True, exist_ok=False)
    for name, data in [('review.json', sheet), ('key.json', key)]:
        (a.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
