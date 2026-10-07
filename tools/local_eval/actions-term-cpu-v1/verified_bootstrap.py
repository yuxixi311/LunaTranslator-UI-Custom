"""Verified-source reads followed by separate Actions/owned-worker admission."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import ModuleType

# Dependencies are executed only after every module byte below is verified.
# The legacy lexicon/public-export/helper entry modules are not loaded.
MODULE_ORDER=('actions_policy', 'diagnostics', 'activation_scope', 'cpu_harness', 'frozen_renderer', 'evidence_validation', 'guarded_runtime', 'acquisition_source', 'host_validation_source', 'private_exports_source', 'term_lock_policy', 'term_runner_core', 'term_worker', 'term_runner_source', 'term_evidence_validation', 'usage_helper_bridge', 'term_worker_entry', 'term_worker_packets', 'term_runtime_inventory', 'term_public_exports', 'term_native_adapter', 'kit_worker', 'attempt_control', 'final_coordinator', 'actions_entry')
MODULE_PATHS={n:("policy/term_lock_policy.py" if n=="term_lock_policy" else n+".py") for n in MODULE_ORDER}


def require_bootstrap_activation():
    # This permits only verified source reads, never native runtime operations.
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode or len(sys.argv)!=5:
        raise RuntimeError('exact isolated bootstrap invocation required')
    manifest_path,expected_sha,mode,argument=sys.argv[1:]
    if mode not in ('actions','acquire','validate') or not re.fullmatch('[0-9a-f]{64}',expected_sha):
        raise RuntimeError('unrecognized bootstrap role/hash')
    root=Path(__file__).resolve().parent
    if Path(manifest_path).resolve()!=root/'KIT_MANIFEST.json':raise RuntimeError('fixed source manifest required')
    if mode=='actions':
        if argument!='unused' or os.environ.get('GITHUB_ACTIONS')!='true' or \
                os.environ.get('GITHUB_RUN_ATTEMPT')!='1' or os.environ.get('LUNA_MANIFEST_SHA')!=expected_sha:
            raise RuntimeError('Actions service/source context absent')
    return dict(mode=mode,manifest_sha=expected_sha,source_root=str(root),argument=argument,pid=os.getpid())



def _bounded_source_read(path,cap):
    """No ambient imports, symlinks, devices or unbounded source reads."""
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:
        raise ValueError('canonical source path required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<=info.st_size<=cap:
            raise ValueError('bounded regular source file required')
        raw=os.read(fd,cap+1)
        if len(raw)!=info.st_size:raise ValueError('complete bounded source read required')
        return raw
    finally:os.close(fd)


def _unique_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate source manifest key')
        result[key]=value
    return result


def verify_payloads(raw,expected_sha,payloads,module_names=MODULE_ORDER):
    if not re.fullmatch('[0-9a-f]{64}',expected_sha) or sha256(raw).hexdigest()!=expected_sha:
        raise ValueError('kit manifest hash')
    manifest=json.loads(raw,object_pairs_hook=_unique_keys,
                        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('invalid manifest scalar')))
    if type(manifest) is not dict:raise ValueError('kit manifest object')
    entries=manifest.get('files')
    if type(entries) is not list or len(entries)>128:raise ValueError('kit manifest schema')
    for item in entries:
        if type(item) is not dict or set(item)!={'path','bytes','sha256'} or type(item['path']) is not str or \
                Path(item['path']).is_absolute() or '..' in Path(item['path']).parts or \
                str(Path(item['path']))!=item['path'] or type(item['bytes']) is not int or not 0<=item['bytes']<=2*1024*1024 or \
                type(item['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',item['sha256']):
            raise ValueError('kit manifest member schema')
    pinned={item['path']:item for item in entries}
    if len(pinned)!=len(entries):raise ValueError('duplicate manifest path')
    verified={}
    for name in module_names:
        filename=MODULE_PATHS.get(name,name+'.py')
        if filename not in pinned or filename not in payloads:raise ValueError('required module missing')
        data=payloads[filename]
        if type(data) is not bytes or len(data)>262144 or len(data)!=pinned[filename]['bytes'] or \
                sha256(data).hexdigest()!=pinned[filename]['sha256']:raise ValueError('verified source mismatch')
        verified[name]=data
    return verified


def load_verified(root,manifest_path,expected_sha,mode):
    invocation=require_bootstrap_activation()
    root=Path(root)
    if str(root)!=invocation['source_root'] or mode!=invocation['mode']:raise ValueError('bootstrap loader role/root')
    raw=_bounded_source_read(manifest_path,65536)
    payloads={}
    modules=MODULE_ORDER
    for name in modules:
        path=root/MODULE_PATHS.get(name,name+'.py')
        data=_bounded_source_read(path,262144)
        payloads[MODULE_PATHS.get(name,name+'.py')]=data
    verified=verify_payloads(raw,expected_sha,payloads,modules)
    for name in modules:
        if name in sys.modules:raise ValueError('ambiguous preloaded kit module')
        module=ModuleType(name);module.__file__=str(root/MODULE_PATHS.get(name,name+'.py'));module.__package__=''
        module.__dict__['_VERIFIED_BOOTSTRAP_SHA']=expected_sha
        if name=='activation_scope':module.__dict__['_BOOTSTRAP_INVOCATION']=dict(invocation)
        sys.modules[name]=module
        exec(compile(verified[name],module.__file__,'exec'),module.__dict__)


def main():
    require_bootstrap_activation()
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:raise ValueError('Python isolation flags')
    if len(sys.argv)<5:raise ValueError('bootstrap requires manifest, hash, mode, plan')
    manifest_path,expected_sha,mode,plan_path=sys.argv[1:5]
    load_verified(Path(__file__).resolve().parent,manifest_path,expected_sha,mode)
    if mode in ('acquire','validate'):
        try:sys.modules['activation_scope'].accept_worker(mode,plan_path,expected_sha)
        except BaseException as exc:
            trace=sys.modules['diagnostics'].Trace(expected_sha,role=mode);trace.enter('WORKER_ADMISSION');trace.fail(exc)
            sys.stdout.buffer.write(sys.modules['diagnostics'].worker_line(trace));sys.stdout.buffer.flush()
            raise SystemExit(1) from None
    if mode in ('acquire','validate'):
        try:
            sys.modules['kit_worker'].main(mode,plan_path,expected_sha)
        except SystemExit:raise
        except BaseException as exc:
            trace=sys.modules['diagnostics'].Trace(expected_sha,role=mode);trace.enter(mode);trace.fail(exc)
            sys.stdout.buffer.write(sys.modules['diagnostics'].worker_line(trace));sys.stdout.buffer.flush()
            raise SystemExit(1) from None
    elif mode=='actions':
        result=sys.modules['actions_entry'].main(expected_sha)
        sys.stdout.write(json.dumps(result,separators=(',',':'))+'\n');sys.stdout.flush()
        if result.get('status')!='complete':raise SystemExit(1)
    else:raise ValueError('unsupported owned worker mode')


if __name__=='__main__':
    try:main()
    except SystemExit:
        raise
    except BaseException:
        sys.stdout.write('{"schema":1,"status":"incomplete","reason_code":"SOURCE_OR_EXECUTION_BLOCKED"}\n')
        raise SystemExit(1) from None
