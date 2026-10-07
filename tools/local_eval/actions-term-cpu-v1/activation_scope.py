"""Exact verified invocation grants, not an environment/CLI enable switch.

Trusted checkout/service provenance is the boundary. These checks do not
authenticate against malicious Python or a hostile process sharing the same UID.
No grant exists merely because this module was imported.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import actions_policy as policy

POLICY=policy.EXECUTION_POLICY
ROLES=('actions','acquire','validate')
_GRANT=None


class Denied(RuntimeError):pass

def require(value,code):
    if not value:raise Denied(code)


def bootstrap_context(role=None):
    value=globals().get('_BOOTSTRAP_INVOCATION')
    require(type(value) is dict and set(value)=={'mode','manifest_sha','source_root','argument','pid'} and
            value['mode'] in ROLES and value['pid']==os.getpid() and
            value['manifest_sha']==globals().get('_VERIFIED_BOOTSTRAP_SHA') and
            re.fullmatch('[0-9a-f]{64}',value['manifest_sha']),'verified bootstrap invocation required')
    if role is not None:require(value['mode']==role,'bootstrap role mismatch')
    return value


def require_actions_guard():
    require(_GRANT is None,'source guard cannot restart an armed process')
    return bootstrap_context('actions')


def read_guard_file(path,cap):
    """Read-only bootstrap/claim checks, distinct from permission for native work."""
    bootstrap_context()
    path=Path(path)
    require(path.is_absolute() and path.resolve(strict=True)==path,'canonical bootstrap-read path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=cap,'bounded bootstrap file')
        data=os.read(fd,cap+1)
        require(len(data)<=cap and (info.st_size==0 or len(data)==info.st_size),'bounded complete bootstrap read')
        return data
    finally:os.close(fd)


def structured_cmdline(raw):
    require(type(raw) is bytes and 0<len(raw)<=8192 and raw.endswith(b'\0'),'bounded process argv')
    args=raw[:-1].split(b'\0')
    require(all(args),'empty process argv entry')
    return [arg.decode('utf-8','strict') for arg in args]


def validate_owner_argv(argv,roots,manifest_sha):
    require(type(argv) is list and len(argv)==8 and all(type(v) is str for v in argv),'structured owner argv')
    require(argv[:3]==['/usr/bin/python3','-I','-B'] and argv[5:]==[manifest_sha,'actions','unused'],
            'exact reviewed Actions bootstrap command')
    workspace=Path(roots['workspace']);source=Path(roots['source'])
    def absolute(value):return Path(value) if Path(value).is_absolute() else workspace/value
    require(absolute(argv[3])==source/'verified_bootstrap.py' and absolute(argv[4])==source/'KIT_MANIFEST.json',
            'owner command source/manifest paths')
    return True


def accept_actions(binding,metadata,roots,manifest_sha):
    """Called only after actions_entry.inspect_source completes every check."""
    global _GRANT
    context=require_actions_guard();parsed=policy.validate_roots(roots)
    require(context['manifest_sha']==manifest_sha and context['source_root']==str(parsed['source']),
            'owner verified source binding')
    policy.validate_release_metadata(metadata)
    policy.validate_provider(binding,source_a=binding['before'],source_parent=metadata['source_parent'])
    argv=structured_cmdline(read_guard_file(Path('/proc')/str(os.getpid())/'cmdline',8192))
    validate_owner_argv(argv,roots,manifest_sha)
    _GRANT=dict(role='actions',pid=os.getpid(),owner_pid=os.getpid(),manifest_sha=manifest_sha,
                source_root=roots['source'],owner_argv=argv)


def require_role(*roles):
    require(type(_GRANT) is dict and _GRANT.get('pid')==os.getpid() and _GRANT.get('role') in roles,
            'verified process-bound role required')
    context=bootstrap_context()
    require(context['mode']==_GRANT['role'] and context['manifest_sha']==_GRANT['manifest_sha'] and
            context['source_root']==_GRANT['source_root'],'release/source binding drift')
    return _GRANT


def owner_identity():
    grant=require_role('actions')
    return dict(coordinator_pid=grant['owner_pid'],coordinator_argv=list(grant['owner_argv']))


def validate_worker_plan(plan,*,mode,argument,manifest_sha,source_root,parent_pid,parent_argv,parent_exe,self_exe,cwd,now):
    """Pure receipt predicate; native observations are collected by accept_worker."""
    import cpu_harness as h
    require(mode in ('acquire','validate'),'owned worker role')
    roots=policy.validate_roots(plan.get('roots'))
    require(str(roots['source'])==source_root and plan['component_manifest_sha256']==manifest_sha and
            plan['commitments']['harness_manifest']==manifest_sha,'worker manifest/source binding')
    base=dict(plan);base['redirect_policy']=[];h.validate_claim_plan(base)
    policy.validate_provider(plan['provider_binding'],source_a=plan['source_a'],source_parent=plan['source_parent'])
    require(type(plan['coordinator_pid']) is int and plan['coordinator_pid']>1 and parent_pid==plan['coordinator_pid'],
            'worker must be direct child of bound coordinator')
    validate_owner_argv(plan['coordinator_argv'],plan['roots'],manifest_sha)
    require(parent_argv==plan['coordinator_argv'],'actual parent argv differs from claim')
    require(parent_exe==self_exe==plan['absolute_python'] and cwd==str(roots['output']),'worker Python/cwd binding')
    require(type(now) in (float,int) and plan['claimed_monotonic']<=now<plan['outer_deadline_monotonic'],
            'worker attempt is not live')
    expected=roots['state']/'ONE_SHOT_CPU_ATTEMPT.json'
    require(argument==str(expected),'worker role/input path binding')
    return True


def accept_worker(mode,argument,manifest_sha):
    global _GRANT
    context=bootstrap_context(mode);require(_GRANT is None,'worker release already consumed')
    require(mode in ('acquire','validate') and context['argument']==argument and
            context['manifest_sha']==manifest_sha,'declared worker bootstrap')
    target=Path(argument)
    require(target.is_absolute() and '..' not in target.parts,'absolute worker input')
    claim_root=target.parent
    require(claim_root.name==policy.STATE_NAME and target.name=='ONE_SHOT_CPU_ATTEMPT.json',
            'fixed worker claim shape')
    claim=claim_root/'ONE_SHOT_CPU_ATTEMPT.json'
    for path,kind,permissions in ((claim_root,'directory',0o700),(claim,'file',0o600)):
        info=path.lstat()
        require(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==permissions and
                (stat.S_ISDIR(info.st_mode) if kind=='directory' else stat.S_ISREG(info.st_mode) and info.st_nlink==1),
                'owner-only fixed claim')
    raw=read_guard_file(claim,32768)
    import cpu_harness as h
    plan=h.strict_json(raw);require(raw==h.canonical(plan),'exact immutable canonical claim bytes')
    parent=os.getppid()
    argv=structured_cmdline(read_guard_file(Path('/proc')/str(parent)/'cmdline',8192))
    validate_worker_plan(plan,mode=mode,argument=argument,manifest_sha=manifest_sha,source_root=context['source_root'],
        parent_pid=parent,parent_argv=argv,parent_exe=os.readlink('/proc/'+str(parent)+'/exe'),
        self_exe=str(Path(sys.executable).resolve()),cwd=os.getcwd(),now=time.monotonic())
    _GRANT=dict(role=mode,pid=os.getpid(),owner_pid=parent,manifest_sha=manifest_sha,
                source_root=context['source_root'],claim_sha256=sha256(raw).hexdigest())
