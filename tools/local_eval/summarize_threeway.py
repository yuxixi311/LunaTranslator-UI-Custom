"""Validate complete three-way observations and export identity-masked text.

This file never scores semantic accuracy or naturalness. All anonymous pairwise
preferences must be frozen before the separate arm key is used.
"""
import argparse
import json
import math
from pathlib import Path
import random
import statistics

import run_threeway_local as experiment
import validate_threeway_local as local
import validate_threeway_google as google

ARMS=('google','hy18','qwen35_2b')


def metrics(rows):
    times=sorted(r['seconds'] for r in rows)
    return {'n':len(rows),'seconds_p50':statistics.median(times),
            'seconds_p95_nearest_rank':times[math.ceil(.95*len(times))-1],
            'protected_structure_failures':sum(not r['format']['protected_structure_exact'] for r in rows),
            'newline_failures':sum(not r['format']['newline_count_exact'] for r in rows)}


def summarize(google_folder,hy_folder,qwen_folder,historical_fixture,fresh_fixture,design,out):
    inputs={}
    inputs['google']=google.load_evidence(google_folder,historical_fixture,fresh_fixture,design)
    inputs['hy18']=local.load_evidence(hy_folder,historical_fixture,fresh_fixture,design)
    inputs['qwen35_2b']=local.load_evidence(qwen_folder,historical_fixture,fresh_fixture,design)
    cases=inputs['google'][1]
    for arm in ('hy18','qwen35_2b'):
        meta,other,_=inputs[arm]
        if meta['model']!=arm or other!=cases:
            raise ValueError('Model/source mismatch across arms')
    hy_meta,qwen_meta=inputs['hy18'][0],inputs['qwen35_2b'][0]
    for field in ('runtime_files_sha256','server_sha256','nvidia_smi_sha256'):
        if hy_meta.get(field)!=qwen_meta.get(field) or not hy_meta.get(field):
            raise ValueError('Local runtime/driver changed across arms')
    if hy_meta.get('gpu',{}).get('uuid')!=qwen_meta.get('gpu',{}).get('uuid') or not hy_meta.get('gpu',{}).get('uuid'):
        raise ValueError('Local GPU changed across arms')
    if len(cases)!=48:raise ValueError('Expected48 frozen cases')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    report={'experiment':experiment.EXPERIMENT,'status':'complete-mechanical-evidence',
            'semantic_review':'not performed','scope':'synthetic pilot; no production or general superiority claim',
            'timing_scope':{'google':'fresh owned host/session per request; provider transport+parse timing excludes host startup',
                            'locals':'CUDA request timing after separate smoke; different declared model policies'},'metrics':{}}
    for split in ('all','historical','fresh'):
        report['metrics'][split]={arm:metrics([r for r in inputs[arm][2] if split=='all' or r['split']==split]) for arm in ARMS}
    report['local_cost_ratios_descriptive_only']={k:report['metrics']['all']['qwen35_2b'][k]/report['metrics']['all']['hy18'][k] for k in ('seconds_p50','seconds_p95_nearest_rank')}
    report['input_evidence_manifests']={arm:experiment.digest(Path(folder)/'manifest.json') for arm,folder in zip(ARMS,(google_folder,hy_folder,qwen_folder))}
    sheets=[];key=[];rng=random.SystemRandom()
    for index,case in enumerate(cases):
        order=list(ARMS);rng.shuffle(order)
        row={'id':case['id'],'split':case['split'],'category':case['category'],'source':case['source'],
             'scores':{'A':None,'B':None,'C':None},'pair_preferences':{'A/B':None,'A/C':None,'B/C':None},'notes':''}
        mapping={'id':case['id']}
        for label,arm in zip(('A','B','C'),order):
            record=inputs[arm][2][index]
            if record['id']!=case['id']:raise ValueError('Case ordering changed')
            row[label]=record['output'] if arm=='google' else record['response']['choices'][0]['message']['content']
            mapping[label]=arm
        sheets.append(row);key.append(mapping)
    (out/'threeway-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'threeway-masked.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sheets),encoding='utf-8')
    (out/'threeway-arm-key.json').write_text(json.dumps(key,indent=2),encoding='utf-8')
    instructions=('Review exact source and each anonymous output independently for critical fidelity, protected structure and uncertainty. '
                  'Then score all eligible anonymous pairs A/B, A/C and B/C for naturalness only when BOTH outputs are definite fidelity and structure passes. '
                  'Record the preferred anonymous label, tie or uncertainty; never infer provider identity. Preserve valid source ambiguity as correct, and never repair output. '
                  'Use the separate frozen fresh criteria. Freeze all ratings before any arm mapping. '
                  'This synthetic model-assisted review is not human bilingual validation.\n')
    (out/'REVIEW_INSTRUCTIONS.txt').write_text(instructions,encoding='utf-8')
    names=('threeway-summary.json','threeway-masked.jsonl','threeway-arm-key.json','REVIEW_INSTRUCTIONS.txt')
    (out/'summary-manifest.json').write_text(json.dumps({n:experiment.digest(out/n) for n in names},indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('google','hy','qwen','historical-fixture','fresh-fixture','design','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=summarize(a.google,a.hy,a.qwen,a.historical_fixture,a.fresh_fixture,a.design,a.out)
    print(json.dumps({'status':r['status'],'semantic_review':r['semantic_review'],'metrics':r['metrics']},indent=2))
