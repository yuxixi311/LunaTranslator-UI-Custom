"""Verified-source reads followed by separate Actions/owned-worker admission."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from types import ModuleType

MODULE_ORDER=('actions_policy','diagnostics','activation_scope','cpu_harness','frozen_renderer','evidence_validation','guarded_runtime',
              'isolated_helper','acquisition_source','host_validation_source','private_exports_source',
              'public_exports','kit_worker','attempt_control','final_coordinator','actions_entry')
HELPER_MODULES=('actions_policy','diagnostics','activation_scope','cpu_harness','frozen_renderer','isolated_helper')


def require_bootstrap_activation():
    # This permits only verified source reads, never native runtime operations.
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode or len(sys.argv)!=5:
        raise RuntimeError('exact isolated bootstrap invocation required')
    manifest_path,expected_sha,mode,argument=sys.argv[1:]
    if mode not in ('actions','acquire','validate','helper') or not re.fullmatch('[0-9a-f]{64}',expected_sha):
        raise RuntimeError('unrecognized bootstrap role/hash')
    root=Path(__file__).resolve().parent
    if Path(manifest_path).resolve()!=root/'KIT_MANIFEST.json':raise RuntimeError('fixed source manifest required')
    if mode=='actions':
        if argument!='unused' or os.environ.get('GITHUB_ACTIONS')!='true' or \
                os.environ.get('GITHUB_RUN_ATTEMPT')!='1' or os.environ.get('LUNA_MANIFEST_SHA')!=expected_sha:
            raise RuntimeError('Actions service/source context absent')
    return dict(mode=mode,manifest_sha=expected_sha,source_root=str(root),argument=argument,pid=os.getpid())


def verify_payloads(raw,expected_sha,payloads,module_names=MODULE_ORDER):
    if not re.fullmatch('[0-9a-f]{64}',expected_sha) or sha256(raw).hexdigest()!=expected_sha:
        raise ValueError('kit manifest hash')
    manifest=json.loads(raw)
    entries=manifest.get('files')
    if type(entries) is not list or len(entries)>128:raise ValueError('kit manifest schema')
    pinned={item['path']:item for item in entries}
    if len(pinned)!=len(entries):raise ValueError('duplicate manifest path')
    verified={}
    for name in module_names:
        filename=name+'.py'
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
    with open(manifest_path,'rb') as source:raw=source.read(65537)
    if len(raw)>65536:raise ValueError('manifest cap')
    payloads={}
    modules=HELPER_MODULES if mode=='helper' else MODULE_ORDER
    for name in modules:
        path=root/(name+'.py')
        with open(path,'rb') as source:data=source.read(262145)
        payloads[path.name]=data
    verified=verify_payloads(raw,expected_sha,payloads,modules)
    for name in modules:
        if name in sys.modules:raise ValueError('ambiguous preloaded kit module')
        module=ModuleType(name);module.__file__=str(root/(name+'.py'));module.__package__=''
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
    if mode in ('acquire','validate','helper'):
        try:sys.modules['activation_scope'].accept_worker(mode,plan_path,expected_sha)
        except BaseException as exc:
            trace=sys.modules['diagnostics'].Trace(expected_sha,role=mode);trace.enter('WORKER_ADMISSION');trace.fail(exc)
            sys.stdout.buffer.write(sys.modules['diagnostics'].worker_line(trace));sys.stdout.buffer.flush()
            raise SystemExit(1) from None
    if mode in ('acquire','validate','helper'):
        try:
            if mode=='helper':
                sys.argv=[str(Path(__file__).parent/'isolated_helper.py'),'--input',plan_path]
                sys.modules['isolated_helper'].main()
            else:sys.modules['kit_worker'].main(mode,plan_path,expected_sha)
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
