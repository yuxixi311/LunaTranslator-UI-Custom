"""Validate sanitized installed-provider observations, not remote attestation."""
import json
import math
from pathlib import Path
import run_threeway_local as experiment
import run_threeway_google as collector


def load_evidence(folder,historical_fixture,fresh_fixture,design):
    folder=Path(folder);cases=experiment.experiment_cases(historical_fixture,fresh_fixture,design)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    names={'metadata.json','results.jsonl','calls.jsonl','smoke.json','host-probe.json'}|{'worker-%02d.json'%i for i in range(49)}
    if set(manifest)!=names:raise ValueError('Google manifest member mismatch')
    for name,sha in manifest.items():
        if experiment.digest(folder/name)!=sha:raise ValueError('Google manifest hash mismatch')
    proof=collector.validate_host_proof(folder/'host-probe.json',require_current_python=False)
    meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    fixed={'experiment':experiment.EXPERIMENT,'arm':'google','status':'complete','mode':collector.MODE,
           'design_sha256':experiment.DESIGN_SHA,'fresh_fixture_sha256':experiment.FRESH_SHA,
           'historical_fixture_sha256':experiment.HISTORICAL_SHA,'case_count':48,'maximum_calls':49,
           'provider_sha256':collector.PROVIDER_SHA256,'libcurl_sha256':collector.DLL_SHA256,
           'collector_hashes':collector.collector_hashes(),'host_probe_sha256':experiment.digest(folder/'host-probe.json'),'total_budget_seconds':240,
           'per_worker_budget_seconds':25,'minimum_start_interval_seconds':2.0,
           'app_ui_verified':False,'actual_calls':49,'successful_calls':49,'maximum_possible_calls':49}
    if any(meta.get(k)!=v for k,v in fixed.items()) or meta.get('failure_type'):
        raise ValueError('Unrecognized/incomplete Google collection')
    if not isinstance(meta.get('total_seconds'),(int,float)) or not math.isfinite(meta['total_seconds']) or not 0<meta['total_seconds']<=240:
        raise ValueError('Google total budget invalid')
    rows=[json.loads(l) for l in (folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    calls=[json.loads(l) for l in (folder/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows)!=48 or len(calls)!=49:raise ValueError('Google case/call count mismatch')
    last=None;last_finish=None
    for index,case in enumerate([experiment.SMOKE]+cases):
        result=json.loads((folder/('worker-%02d.json'%index)).read_text(encoding='utf-8'))
        collector.validate_worker_result(result,case,proof['python_executable_sha256'])
        call=calls[index]
        if set(call)!={'index','id','worker_started','worker_finished','exit_code','owned_worker_exit_confirmed'} or call['index']!=index or call['id']!=case['id'] or call['exit_code']!=0 or call['owned_worker_exit_confirmed'] is not True:
            raise ValueError('Google owned-call mismatch')
        start,end=call['worker_started'],call['worker_finished']
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (start,end)) or not start<=result['transport_started']<=end or not 0<end-start<=25 or result['seconds']>end-start:
            raise ValueError('Google call timing invalid')
        if last is not None and (result['transport_started']-last<2 or start<last_finish):
            raise ValueError('Google calls overlapped or pacing failed')
        last=result['transport_started'];last_finish=end
        if index==0:
            if json.loads((folder/'smoke.json').read_text(encoding='utf-8'))!=result:raise ValueError('Google smoke mismatch')
        else:
            row=rows[index-1]
            expected={'id':case['id'],'split':case['split'],'category':case['category'],'output':result['output'],
                      'seconds':result['seconds'],'worker_index':index,
                      'format':experiment.check_format(case['source'],result['output'])}
            if row!=expected:raise ValueError('Google scored observation mismatch')
    if calls[-1]['worker_finished']-calls[0]['worker_started']>meta['total_seconds']:
        raise ValueError('Google phase timing mismatch')
    return meta,cases,rows
