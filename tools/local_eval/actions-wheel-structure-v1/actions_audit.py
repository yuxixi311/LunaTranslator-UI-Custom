"""Separately reviewed thin activation wrapper around the unchanged exact49 audit.

No action on import. The operational entry requires the bound GitHub event/work
claim, reviewed source inventory and exact cached interpreter before any GET.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time

import audit_wheels as audit
import event_guard as guard

ROOT=Path(__file__).resolve().parent
INTERPRETER_PIN={'bytes':17752,'sha256':'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0'}
HELPER_SHA='a697eea878fa369863a38bfd3bd53821a48849a6de68df1b1e386c460ee06aed'
HELPER_BYTES=56588
PROBE_CODE='''import hashlib,os,stat,sys
assert sys.version_info[:3]==(3,12,14) and sys.flags.isolated and sys.flags.no_site
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as source:
 info=os.fstat(source.fileno())
 assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size==int(sys.argv[3])
 body=source.read(int(sys.argv[3])+1)
assert len(body)==int(sys.argv[3]) and hashlib.sha256(body).hexdigest()==sys.argv[2]
namespace={'__name__':'_luna_inert_source_probe','__file__':sys.argv[1],'__package__':None,'__cached__':None}
exec(compile(body,sys.argv[1],'exec'),namespace)
print('LUNA_FIXED49_IMPORTS_OK')
'''
PROTOCOL_SHA='75bf059dc779868d8b2ee41084cd765534688d270ff3bd7e834c3c163fcd9bf1'
FREEZE_SHA='179d6b9e4d41fbc0a3063580dffd400b5751470e69dee249f1f3caa0e234a97f'
JSON_CAP=audit.REPORT_CAP+32768
FRAME_CAP=3*1024*1024
CHUNK_SIZE=12000
PREFIX='LUNA_FIXED49_AUDIT'
_FRAME_STARTED=False
_FRAME_CONTEXT=None
_PUBLIC_DEADLINE=None
CLEAN_ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
CODES=frozenset({'source_binding_failed','event_binding_failed','attempt_already_exists',
    'runtime_unavailable','runtime_identity_failed','runtime_probe_failed','wrapper_deadline',
    'helper_report_missing','helper_report_invalid','helper_receipt_invalid','helper_failed',
    'source_changed','output_size_limit','output_exists','publication_failed','internal_error'})

class ActivationError(Exception):
    def __init__(self,code):
        self.code=code if code in CODES else 'internal_error'
        super().__init__(self.code)

def require(ok,code):
    if not ok:raise ActivationError(code)

def canonical(value):
    return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()

def exclusive_json(path,value,cap=JSON_CAP):
    data=canonical(value)
    require(len(data)<=cap,'output_size_limit')
    with Path(path).open('xb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def source_inputs(sha,allow_attempt=False):
    try:
        inventory=guard.verify_sources(sha,root=ROOT,allow_attempt=allow_attempt)
        require(inventory['files']['audit_wheels.py']['sha256']==HELPER_SHA,'source_binding_failed')
        require(inventory['files']['PROTOCOL.md']['sha256']==PROTOCOL_SHA,'source_binding_failed')
        require(inventory['files']['SOURCE_FREEZE.json']['sha256']==FREEZE_SHA,'source_binding_failed')
        require(inventory['files']['WHEELS49.frozen.json']['sha256']==audit.MANIFEST_SHA256,'source_binding_failed')
        records=audit.read_manifest(ROOT/'WHEELS49.frozen.json')
        return inventory,records
    except ActivationError:raise
    except BaseException:raise ActivationError('source_binding_failed') from None

def event_binding(env,sha):
    try:
        event=guard.validate_event(guard.read_json(Path(env['GITHUB_EVENT_PATH'])),env)
        require(event['source_inventory_sha256']==sha,'event_binding_failed')
        temporary=Path(env['RUNNER_TEMP'])
        require(temporary.is_absolute() and temporary.resolve(strict=True)==temporary,'event_binding_failed')
        work=temporary/guard.CLAIM_NAME
        require(work.resolve(strict=True)==work and work.is_dir(),'event_binding_failed')
        require(guard.read_json(work/'EVENT_BINDING.json')==event,'event_binding_failed')
        require({p.name for p in work.iterdir()}=={'EVENT_BINDING.json'},'attempt_already_exists')
        return event,work
    except ActivationError:raise
    except BaseException:raise ActivationError('event_binding_failed') from None

def runtime_identity(env):
    try:
        runtime=Path(env['RUNNER_TOOL_CACHE'])/'Python/3.12.14/x64'
        require(runtime.is_absolute() and runtime.resolve(strict=True)==runtime,'runtime_unavailable')
        require((runtime.parent/'x64.complete').is_file(),'runtime_unavailable')
        require(Path(sys.base_prefix).resolve(strict=True)==runtime,'runtime_identity_failed')
        executable=Path(sys.executable).resolve(strict=True)
        require(executable.parent==runtime/'bin' and guard.digest(executable)==INTERPRETER_PIN,'runtime_identity_failed')
        require(platform.python_implementation()=='CPython' and sys.version_info[:3]==(3,12,14)
            and platform.system()=='Linux' and platform.machine()=='x86_64'
            and sys.flags.isolated==1 and sys.flags.no_site==1,'runtime_identity_failed')
        return {'implementation':'CPython','python':'3.12.14','system':'Linux','machine':'x86_64',
            'interpreter':INTERPRETER_PIN},executable
    except ActivationError:raise
    except BaseException:raise ActivationError('runtime_identity_failed') from None

def clean_runtime_probe(executable,work,watchdog):
    process=None;okay=False
    try:
        process=subprocess.Popen.__new__(subprocess.Popen)
        subprocess.Popen.__init__(process,[str(executable),'-I','-S','-c',PROBE_CODE,
            str(ROOT/'audit_wheels.py'),HELPER_SHA,str(HELPER_BYTES)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env=dict(CLEAN_ENV),close_fds=True,start_new_session=True,cwd=work)
        data=process.stdout.read(513)
        code=process.wait(timeout=max(0.001,min(5,watchdog.deadline-time.monotonic()-10)))
        okay=code==0 and data==b'LUNA_FIXED49_IMPORTS_OK\n'
    except (BaseException,):okay=False
    finally:
        watchdog.reserve()
        try:
            okay=audit.stop_owned(process,min(watchdog.deadline,time.monotonic()+5)) and okay
            if process is not None and getattr(process,'stdout',None) is not None:process.stdout.close()
        except BaseException:okay=False
    require(okay,'runtime_probe_failed')

def helper_receipt(host):
    path=ROOT/'ATTEMPT.json'
    if not path.exists():return None,None
    try:
        receipt=audit.safe_json_read(path,4096)
        require(set(receipt)=={'schema','status','failure','manifest_sha256','protocol_sha256',
            'helper_sha256','interpreter_sha256','cleanup','owner_pid','directory_sha256'},'helper_receipt_invalid')
        require(receipt['schema']=='exact49-attempt-v1' and receipt['manifest_sha256']==audit.MANIFEST_SHA256
            and receipt['protocol_sha256']==PROTOCOL_SHA and receipt['helper_sha256']==HELPER_SHA
            and receipt['interpreter_sha256']==host['interpreter']['sha256'],'helper_receipt_invalid')
        require(type(receipt['owner_pid']) is int and receipt['owner_pid']==os.getpid(),'helper_receipt_invalid')
        require(receipt['status'] in ('claimed','acquisition','acquisition_verified','audit','incomplete',
            'structurally_complete','structurally_complete_with_findings'),'helper_receipt_invalid')
        require(receipt['cleanup'] in ('pending','verified','uncertain'),'helper_receipt_invalid')
        require(receipt['failure'] is None or (type(receipt['failure']) is str and receipt['failure'] in audit.HARD_CODES),'helper_receipt_invalid')
        require(receipt['directory_sha256'] is None or (type(receipt['directory_sha256']) is str
            and re.fullmatch('[0-9a-f]{64}',receipt['directory_sha256'])),'helper_receipt_invalid')
        return receipt,guard.digest(path)
    except ActivationError:raise
    except BaseException:raise ActivationError('helper_receipt_invalid') from None

def make_result(event,host,sha,claim_pin,records,work,helper_code,helper_error):
    receipt,receipt_pin=helper_receipt(host)
    source_inputs(sha,allow_attempt=receipt is not None)
    require(guard.read_json(work/'EVENT_BINDING.json')==event,'event_binding_failed')
    report=None;report_pin=None;failure=helper_error
    report_path=work/'ARCHIVE_REPORT.json'
    if report_path.exists():
        try:
            raw=audit.safe_bytes_read(report_path,audit.REPORT_CAP)
            parsed=json.loads(raw,object_pairs_hook=guard.no_duplicates)
            report=audit.validate_report(parsed,records)
            report_pin={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        except BaseException:failure={'origin':'activation','code':'helper_report_invalid'}
    elif failure is None:failure={'origin':'activation','code':'helper_report_missing'}
    complete=False
    if report is not None:
        if report['status'].startswith('structurally_complete'):
            complete=(helper_code==0 and failure is None and report['cleanup']=='verified' and receipt is not None
                and receipt['status']==report['status'] and receipt['cleanup']=='verified' and receipt['failure'] is None)
            if not complete and failure is None:failure={'origin':'activation','code':'helper_failed'}
        elif failure is None:
            failure={'origin':'audit','code':report['failure'] or 'internal_error'}
        if report['cleanup']=='verified':
            require({p.name for p in work.iterdir()}=={'EVENT_BINDING.json','RUN_CLAIM.json','ARCHIVE_REPORT.json'},'helper_report_invalid')
    value={'schema':'luna-fixed49-actions-evidence-v1','protocol':guard.PROTOCOL,
        'state':'complete' if complete else 'incomplete','event':event,'host':host,
        'bindings':{'source_inventory_sha256':sha,'audit_protocol_sha256':PROTOCOL_SHA,
            'audit_helper_sha256':HELPER_SHA,'audit_source_freeze_sha256':FREEZE_SHA,
            'dependency_manifest_sha256':audit.MANIFEST_SHA256,'run_claim':claim_pin,
            'helper_attempt':receipt_pin,'helper_report':report_pin},
        'limits_seconds':{'acquisition':240,'audit':600,'wrapper_preflight':30,'wrapper_postflight':30},
        'installation':'not_run','target_package_imports':0,'ner':'not_run','gpu':'not_run',
        'legal_clearance':'not_claimed','helper_exit_code':helper_code,'failure':failure,'report':report}
    require(helper_code in (None,0,1) and (type(helper_code) is int or helper_code is None),'helper_failed')
    if failure is not None:
        require(set(failure)=={'origin','code'} and ((failure['origin']=='activation' and failure['code'] in CODES)
            or (failure['origin']=='audit' and failure['code'] in audit.HARD_CODES)),'helper_report_invalid')
    return value

def frame_lines(value):
    data=canonical(value);require(len(data)<=JSON_CAP,'output_size_limit')
    payload=base64.b64encode(data).decode('ascii')
    chunks=[payload[i:i+CHUNK_SIZE] for i in range(0,len(payload),CHUNK_SIZE)]
    begin={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'chunks':len(chunks)}
    lines=[PREFIX+'_BEGIN '+canonical(begin).decode('ascii')]
    lines += [PREFIX+'_CHUNK '+str(i)+' '+chunk for i,chunk in enumerate(chunks)]
    lines += [PREFIX+'_END']
    require(sum(len(line)+1 for line in lines)<=FRAME_CAP,'output_size_limit')
    return data,lines

def decode_frame(lines):
    """Local evidence verifier used by fake tests and later result consumers."""
    require(type(lines) is list and 3<=len(lines)<=300,'helper_report_invalid')
    require(sum(len(line)+1 for line in lines)<=FRAME_CAP,'output_size_limit')
    require(lines[0].startswith(PREFIX+'_BEGIN ') and lines[-1]==PREFIX+'_END','helper_report_invalid')
    try:begin=json.loads(lines[0][len(PREFIX+'_BEGIN '):],object_pairs_hook=guard.no_duplicates)
    except BaseException:raise ActivationError('helper_report_invalid') from None
    require(set(begin)=={'bytes','sha256','chunks'} and type(begin['bytes']) is int and 0<=begin['bytes']<=JSON_CAP
        and type(begin['chunks']) is int and 1<=begin['chunks']<=298 and len(lines)==begin['chunks']+2
        and type(begin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',begin['sha256']),'helper_report_invalid')
    encoded=[]
    for index,line in enumerate(lines[1:-1]):
        prefix=PREFIX+'_CHUNK '+str(index)+' '
        require(line.startswith(prefix),'helper_report_invalid')
        text=line[len(prefix):]
        require(1<=len(text)<=CHUNK_SIZE and (index==begin['chunks']-1 or len(text)==CHUNK_SIZE),'helper_report_invalid')
        encoded.append(text)
    try:data=base64.b64decode(''.join(encoded),validate=True)
    except BaseException:raise ActivationError('helper_report_invalid') from None
    require(len(data)==begin['bytes'] and hashlib.sha256(data).hexdigest()==begin['sha256'],'helper_report_invalid')
    return data

def emit_frame(lines):
    global _FRAME_STARTED
    for line in lines:
        _FRAME_STARTED=True
        print(line,flush=True)


def fallback_frame(code):
    if _FRAME_STARTED:return
    value={'schema':'luna-fixed49-actions-failure-v1','protocol':guard.PROTOCOL,'state':'incomplete',
        'failure':code if code in CODES else 'internal_error','report':None,'context':_FRAME_CONTEXT}
    _,lines=frame_lines(value);emit_frame(lines)


def control(sha,env=os.environ):
    global _FRAME_STARTED,_FRAME_CONTEXT,_PUBLIC_DEADLINE
    _FRAME_STARTED=False;_FRAME_CONTEXT=None;_PUBLIC_DEADLINE=time.monotonic()+30
    with audit.PhaseWatchdog(30) as preflight:
        _PUBLIC_DEADLINE=preflight.deadline
        inventory,records=source_inputs(sha)
        event,work=event_binding(env,sha)
        host,executable=runtime_identity(env)
        clean_runtime_probe(executable,work,preflight)
        claim={'schema':'luna-fixed49-run-claim-v1','state':'claimed','protocol':guard.PROTOCOL,
            'event':event,'host':host,'source_inventory_sha256':sha,'owner_pid':os.getpid(),
            'manifest_sha256':audit.MANIFEST_SHA256,'helper_sha256':HELPER_SHA,'audit_protocol_sha256':PROTOCOL_SHA}
        claim_pin=exclusive_json(work/'RUN_CLAIM.json',claim,32768)
        _FRAME_CONTEXT={'event':event,'host':host,'source_inventory_sha256':sha,'run_claim':claim_pin}
    helper_code=None;helper_error=None
    try:helper_code=audit.run_approved(ROOT/'WHEELS49.frozen.json',work/'ARCHIVE_REPORT.json')
    except audit.Stop as error:helper_error={'origin':'audit','code':error.code}
    except BaseException:helper_error={'origin':'activation','code':'helper_failed'}
    with audit.PhaseWatchdog(30) as postflight:
        _PUBLIC_DEADLINE=postflight.deadline
        require(guard.digest(work/'RUN_CLAIM.json')==claim_pin,'attempt_already_exists')
        value=make_result(event,host,sha,claim_pin,records,work,helper_code,helper_error)
        data,lines=frame_lines(value)
        exclusive_json(work/'PUBLIC_RESULT.json',value)
        emit_frame(lines)
    return 0 if value['state']=='complete' else 1

def main(arguments=None):
    global _FRAME_STARTED,_FRAME_CONTEXT,_PUBLIC_DEADLINE
    _FRAME_STARTED=False;_FRAME_CONTEXT=None;_PUBLIC_DEADLINE=time.monotonic()+30
    parser=argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256',required=True)
    args=parser.parse_args(arguments)
    try:return control(args.inventory_sha256)
    except audit.PhaseTimeout:code='wrapper_deadline'
    except ActivationError as error:code=error.code
    except BaseException:code='internal_error'
    remaining=(_PUBLIC_DEADLINE or time.monotonic())-time.monotonic()
    if not _FRAME_STARTED and remaining>0:
        old=signal.getsignal(signal.SIGALRM)
        def alarm(signum,frame):raise audit.PhaseTimeout()
        signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,remaining)
        try:fallback_frame(code)
        except BaseException:pass
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    return 1

if __name__=='__main__':raise SystemExit(main())
