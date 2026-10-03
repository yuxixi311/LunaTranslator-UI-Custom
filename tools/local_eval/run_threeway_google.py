"""Bounded synthetic collection through the unchanged installed Google provider.

No headers, user history, credential values, proxy values or exception text are
recorded. Each HTTP call runs in its own disposable original-libcurl host.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_threeway_local as experiment
from google_existing_provider import load_existing_provider, PROVIDER_SHA256
from google_installed_host import load_host, SOURCE_HASHES, DLL_SHA256, STRUCTURES_LF_SHA
from google_guard import GuardedExistingSession, CollectionStopped

TOTAL_BUDGET = 240
PER_WORKER_BUDGET = 25
CLEANUP_RESERVE = 7
START_INTERVAL = 2.0
MAX_CALLS = 49
MODE = 'isolated-installed-provider-original-libcurl-system-proxy'


def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def collector_hashes():
    root=Path(__file__).parent
    names=('run_threeway_google.py','google_existing_provider.py','google_installed_host.py','google_guard.py','google_curl_observer.py')
    hashes={n:experiment.digest(root/n) for n in names}
    hashes['shared_runner_dependencies']=experiment.code_hashes()
    return hashes


def validate_worker_result(result, case, python_sha=None):
    fields={'status','id','output','seconds','transport_started','status_code','response_bytes',
            'request_count','provider_sha256','source_hashes','libcurl_sha256','mode','python_executable_sha256','curl_completion'}
    if not isinstance(result,dict) or set(result)!=fields or result['status']!='complete':
        raise ValueError('Invalid or incomplete installed-provider result')
    if result['curl_completion'] is not True or not re.fullmatch('[0-9a-f]{64}',str(result['python_executable_sha256'])) or (python_sha is not None and result['python_executable_sha256']!=python_sha):
        raise ValueError('Worker completion/executable evidence mismatch')
    if result['id']!=case['id'] or result['provider_sha256']!=PROVIDER_SHA256 or result['libcurl_sha256']!=DLL_SHA256 or result['mode']!=MODE:
        raise ValueError('Installed-provider identity mismatch')
    hashes=result['source_hashes']
    expected_keys=set(SOURCE_HASHES)|{'network/structures.py','network/structures.py.normalized-lf'}
    if not isinstance(hashes,dict) or set(hashes)!=expected_keys or hashes.get('network/structures.py.normalized-lf')!=STRUCTURES_LF_SHA or not re.fullmatch('[0-9a-f]{64}',str(hashes.get('network/structures.py',''))):
        raise ValueError('Installed structures identity mismatch')
    if any(hashes.get(k)!=v for k,v in SOURCE_HASHES.items()):
        raise ValueError('Installed dependency mismatch')
    if result['request_count']!=1 or result['status_code']!=200 or type(result['response_bytes']) is not int or not 0<result['response_bytes']<=65536:
        raise ValueError('Transport count/status/size mismatch')
    for key in ('seconds','transport_started'):
        if not isinstance(result[key],(int,float)) or not math.isfinite(result[key]) or result[key]<=0:
            raise ValueError('Invalid provider clock')
    if not isinstance(result['output'],str) or not result['output'].strip():
        raise ValueError('Empty provider output')
    if case['split']=='smoke' and (not re.search('[\u4e00-\u9fff]',result['output']) or re.search('[\u3040-\u30ff]',result['output']) or re.search(r'captcha|unusual traffic|verify.{0,20}human|人机验证|异常流量|验证码|配额',result['output'],re.I)):
        raise ValueError('Provider smoke sanity failed')


def probe_result(a):
    session,response_factory,hashes,completion=load_host(a.installed_source_root,a.libcurl)
    if type(session.requester).__module__!='network.client.libcurl.requester':
        raise ValueError('Wrong installed network backend')
    class FakeSession:
        calls=0
        def post(self,url,**kwargs):
            from google_existing_provider import ENDPOINT
            expected=[[[experiment.SMOKE['source']],'ja','zh-CN'],'wt_lib']
            if url!=ENDPOINT or json.loads(kwargs['data'])!=expected:
                raise ValueError('Existing provider request semantics differ')
            self.calls+=1
            response=response_factory(False)
            response.headers={'Content-Type':'application/json; charset=utf-8'}
            response.content=b'[["sanity &amp; check"]]'
            return response
    fake=FakeSession()
    provider=load_existing_provider(a.installed_source_root/'translator/google.py',fake)
    if provider.translate(experiment.SMOKE['source'])!='sanity & check' or fake.calls!=1:
        raise ValueError('Existing provider parsing differs')
    return {'status':'complete','mode':MODE,'provider_sha256':PROVIDER_SHA256,
            'source_hashes':hashes,'libcurl_sha256':DLL_SHA256,
            'real_network_calls':0,'fake_requests':1,'backend':'installed-libcurl',
            'request_and_html_parsing_match':True,'app_ui_verified':False,
            'python_version':list(sys.version_info[:3]),'python_executable_sha256':experiment.digest(sys.executable),
            'collector_hashes':collector_hashes()}


def validate_host_proof(path, require_current_python=True):
    proof=json.loads(Path(path).read_text(encoding='utf-8'))
    fixed={'status':'complete','mode':MODE,'provider_sha256':PROVIDER_SHA256,
           'libcurl_sha256':DLL_SHA256,'real_network_calls':0,'fake_requests':1,
           'backend':'installed-libcurl','request_and_html_parsing_match':True,
           'app_ui_verified':False,
           'collector_hashes':collector_hashes()}
    version=proof.get('python_version')
    if not isinstance(version,list) or len(version)!=3 or version[:2]!=[3,12] or not all(type(n) is int and n>=0 for n in version):
        raise ValueError('Unsupported probe Python version')
    if require_current_python and version!=list(sys.version_info[:3]):
        raise ValueError('Probe and collector Python differ')
    executable_sha=proof.get('python_executable_sha256')
    if not re.fullmatch('[0-9a-f]{64}',str(executable_sha)) or (require_current_python and executable_sha!=experiment.digest(sys.executable)):
        raise ValueError('Probe and collector Python executable differ')
    if set(proof)!=set(fixed)|{'source_hashes','python_version','python_executable_sha256'} or any(proof.get(k)!=v for k,v in fixed.items()):
        raise ValueError('Host probe identity/configuration mismatch')
    if any(proof['source_hashes'].get(k)!=v for k,v in SOURCE_HASHES.items()) or proof['source_hashes'].get('network/structures.py.normalized-lf')!=STRUCTURES_LF_SHA:
        raise ValueError('Host probe installed-source mismatch')
    return proof


def probe_child(a):
    try:
        result=probe_result(a)
        write_json(a.worker_result,result)
        os._exit(0)
    except BaseException:
        write_json(a.worker_result,{'status':'incomplete','reason':'host_probe_failed','real_network_calls':0})
        os._exit(2)


def probe_parent(a):
    if a.out.exists():raise ValueError('New probe output path required')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-I',str(Path(__file__).resolve()),'--probe-child','--worker-result',str(a.out.resolve()),
             '--installed-source-root',str(a.installed_source_root.resolve()),'--libcurl',str(a.libcurl.resolve())]
    lock=Path(tempfile.gettempdir())/'luna-threeway-google.lock'
    with experiment.owned_model_lock(lock) as ownership:
        code=invoke_owned(command,PER_WORKER_BUDGET-CLEANUP_RESERVE,ownership)
    if code!=0 or not a.out.is_file():raise RuntimeError('Installed host probe incomplete')
    result=json.loads(a.out.read_text(encoding='utf-8'))
    if result.get('status')!='complete' or result.get('real_network_calls')!=0:
        raise ValueError('Invalid host probe evidence')


def worker(a):
    # This function exits without native-object finalization. The owned process
    # is the cleanup boundary for libcurl's potentially live callback thread.
    guard=None
    try:
        validate_host_proof(a.host_proof)
        cases=[experiment.SMOKE]+experiment.experiment_cases(a.historical_fixture,a.fresh_fixture,a.design)
        if not 0<=a.worker_index<len(cases):raise ValueError('Invalid fixed case index')
        case=cases[a.worker_index]
        session,response_factory,hashes,completion=load_host(a.installed_source_root,a.libcurl)
        retained=[]
        guard=GuardedExistingSession(session,response_factory,retained.append,completion.require_success,time.monotonic()+20)
        guard.expected_source=case['source']
        provider=load_existing_provider(a.installed_source_root/'translator/google.py',guard)
        output=provider.translate(case['source'])
        result={'status':'complete','id':case['id'],'output':output,
                'seconds':time.monotonic()-guard.last_start,'transport_started':guard.last_start,
                'status_code':guard.status_code,'response_bytes':guard.response_bytes,
                'request_count':guard.starts,'provider_sha256':PROVIDER_SHA256,
                'source_hashes':hashes,'libcurl_sha256':DLL_SHA256,'mode':MODE,
                'python_executable_sha256':experiment.digest(sys.executable),'curl_completion':True}
        validate_worker_result(result,case)
        write_json(a.worker_result,result)
        os._exit(0)
    except BaseException as exc:
        code=exc.code if isinstance(exc,CollectionStopped) else 'provider_or_host_failed'
        write_json(a.worker_result,{'status':'incomplete','reason':code,'request_count':guard.starts if guard else 0})
        os._exit(2)


def invoke_owned(command, timeout, ownership):
    ownership.starting_child()
    work_deadline=time.monotonic()+timeout
    proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        return proc.wait(timeout=max(0,work_deadline-time.monotonic()))
    finally:
        if proc.poll() is None:
            proc.kill()
            try:proc.wait(timeout=CLEANUP_RESERVE)
            except BaseException:
                raise experiment.OwnedProcessCleanupError('Owned Google worker termination unconfirmed') from None
        ownership.confirm_stopped(proc)


def collect(a, cases):
    proof=validate_host_proof(a.host_proof)
    a.out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(a.host_proof,a.out/'host-probe.json')
    started=time.monotonic();deadline=started+TOTAL_BUDGET
    metadata={'experiment':experiment.EXPERIMENT,'arm':'google','status':'incomplete','mode':MODE,
              'design_sha256':experiment.DESIGN_SHA,'fresh_fixture_sha256':experiment.FRESH_SHA,
              'historical_fixture_sha256':experiment.HISTORICAL_SHA,'case_count':48,'maximum_calls':49,
              'provider_sha256':PROVIDER_SHA256,'libcurl_sha256':DLL_SHA256,
              'collector_hashes':collector_hashes(),'host_probe_sha256':experiment.digest(a.host_proof),'total_budget_seconds':TOTAL_BUDGET,
              'per_worker_budget_seconds':PER_WORKER_BUDGET,'minimum_start_interval_seconds':START_INTERVAL,
              'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
              'timing_scope':'provider transport and parsing; fresh host/session overhead separate',
              'configuration_scope':'known installed backend and system-proxy policy; no full app configuration/history imported',
              'app_ui_verified':False,'actual_calls':None,'successful_calls':0,'maximum_possible_calls':0}
    write_json(a.out/'metadata.json',metadata)
    last_start=None
    lock=Path(tempfile.gettempdir())/'luna-threeway-google.lock'
    try:
        with experiment.owned_model_lock(lock) as ownership, (a.out/'results.jsonl').open('w',encoding='utf-8') as rows, (a.out/'calls.jsonl').open('w',encoding='utf-8') as calls:
            for index,case in enumerate([experiment.SMOKE]+cases):
                if last_start is not None:
                    delay=last_start+START_INTERVAL-time.monotonic()
                    if delay>0:time.sleep(delay)
                timeout=min(PER_WORKER_BUDGET,deadline-time.monotonic())-CLEANUP_RESERVE
                if timeout<=0:raise TimeoutError('Collection budget exhausted')
                result_path=a.out/('worker-%02d.json'%index)
                command=[sys.executable,'-I',str(Path(__file__).resolve()),'--worker-index',str(index),
                         '--worker-result',str(result_path.resolve()),'--historical-fixture',str(a.historical_fixture.resolve()),
                         '--fresh-fixture',str(a.fresh_fixture.resolve()),'--design',str(a.design.resolve()),
                         '--host-proof',str(a.host_proof.resolve()),
                         '--installed-source-root',str(a.installed_source_root.resolve()),'--libcurl',str(a.libcurl.resolve())]
                metadata['maximum_possible_calls']=index+1
                launch=time.monotonic()
                exitcode=invoke_owned(command,timeout,ownership)
                ended=time.monotonic()
                event={'index':index,'id':case['id'],'worker_started':launch,'worker_finished':ended,
                       'exit_code':exitcode,'owned_worker_exit_confirmed':True}
                experiment.append_json(calls,event)
                if exitcode!=0 or not result_path.is_file() or result_path.stat().st_size>1024*1024:
                    raise ValueError('Owned provider worker incomplete')
                result=json.loads(result_path.read_text(encoding='utf-8'))
                validate_worker_result(result,case,proof['python_executable_sha256'])
                if not launch<=result['transport_started']<=ended or result['seconds']>ended-launch or ended>deadline:
                    raise ValueError('Provider clock/budget mismatch')
                if last_start is not None and result['transport_started']-last_start<START_INTERVAL:
                    raise ValueError('Provider pacing violated')
                last_start=result['transport_started'];metadata['successful_calls']+=result['request_count']
                if index==0:write_json(a.out/'smoke.json',result)
                else:
                    row={'id':case['id'],'split':case['split'],'category':case['category'],'output':result['output'],
                         'seconds':result['seconds'],'worker_index':index,
                         'format':experiment.check_format(case['source'],result['output'])}
                    experiment.append_json(rows,row)
            metadata['actual_calls']=metadata['successful_calls']
            metadata['status']='complete'
    except BaseException as exc:
        # Never persist external exception text, headers, paths or proxy values.
        metadata['failure_type']='owned_cleanup_unconfirmed' if isinstance(exc,experiment.OwnedProcessCleanupError) else 'collection_incomplete'
        raise RuntimeError(metadata['failure_type']) from None
    finally:
        metadata['total_seconds']=time.monotonic()-started
        write_json(a.out/'metadata.json',metadata)
        manifest={p.name:experiment.digest(p) for p in a.out.iterdir() if p.is_file() and p.name!='manifest.json'}
        write_json(a.out/'manifest.json',manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installed-source-root',type=Path,required=True)
    p.add_argument('--libcurl',type=Path,required=True)
    p.add_argument('--historical-fixture',type=Path)
    p.add_argument('--fresh-fixture',type=Path)
    p.add_argument('--design',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--host-proof',type=Path)
    p.add_argument('--probe-host',action='store_true')
    p.add_argument('--probe-child',action='store_true')
    p.add_argument('--worker-index',type=int)
    p.add_argument('--worker-result',type=Path)
    a=p.parse_args()
    if a.probe_child:
        if a.worker_result is None:p.error('Probe result path required')
        probe_child(a)
    if a.probe_host:
        if a.out is None:p.error('New probe output path required')
        probe_parent(a);return
    if None in (a.historical_fixture,a.fresh_fixture,a.design,a.host_proof):p.error('Frozen input and design paths required')
    if a.worker_index is not None:
        if a.worker_result is None:p.error('Worker result path required')
        worker(a)
    if a.out is None:p.error('New output directory required')
    cases=experiment.experiment_cases(a.historical_fixture,a.fresh_fixture,a.design)
    collect(a,cases)

if __name__=='__main__':main()
