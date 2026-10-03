"""Create a paired review sheet only from complete, matched runs.

Keep key.json away from reviewers until scores are locked. This tool does not
judge translation quality or turn automated formatting checks into accuracy.
"""
import argparse
import json
from pathlib import Path
import random
from run import FIXTURE, FIXTURE_SHA, MODELS, TEMPLATES, digest, request_body


def load_run(folder):
    meta = json.loads((folder / 'metadata.json').read_text())
    rows = [json.loads(x) for x in (folder / 'results.jsonl').read_text().splitlines()]
    if meta['status'] != 'complete' or meta['fixture_sha256'] != FIXTURE_SHA:
        raise ValueError('Run is incomplete or fixture does not match')
    if meta['model'] not in MODELS:
        raise ValueError('Unknown model')
    _, sha, revision = MODELS[meta['model']]
    if meta['model_sha256'] != sha or meta['model_revision'] != revision:
        raise ValueError('Unrecognized model provenance')
    if meta['template_sha256'] != TEMPLATES[meta['model']][1]:
        raise ValueError('Unrecognized model-specific official template')
    cases = json.loads(FIXTURE.read_text())['cases']
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
    for field in ('context', 'threads', 'batch', 'ubatch', 'runtime_version', 'server_sha256', 'harness_sha256'):
        if lm[field] != rm[field]:
            raise ValueError('Different run configuration: ' + field)
    sheet, key = [], []
    rng = random.SystemRandom()
    for case, l, r in zip(json.loads(FIXTURE.read_text())['cases'], lr, rr):
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
