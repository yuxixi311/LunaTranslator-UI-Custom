"""Verify the whole source-only kit before loading its isolated entry point."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import ModuleType


def read_source(path,cap):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>cap:
        raise ValueError('source shape')
    raw=path.read_bytes()
    if len(raw)!=info.st_size:raise ValueError('source size')
    return raw


def verified_sources(root,expected):
    if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('source binding')
    raw=read_source(root/'KIT_MANIFEST.json',65536)
    if sha256(raw).hexdigest()!=expected:raise ValueError('source binding')
    value=json.loads(raw);entries=value['files']
    if type(entries) is not list or not 1<=len(entries)<=32:raise ValueError('inventory')
    names=set();payloads={}
    for item in entries:
        name=item['path']
        if type(name) is not str or not re.fullmatch('[A-Za-z0-9_.-]{1,100}',name) or name in names:
            raise ValueError('inventory path')
        names.add(name);data=read_source(root/name,131072)
        if len(data)!=item['bytes'] or sha256(data).hexdigest()!=item['sha256']:raise ValueError('payload binding')
        payloads[name]=data
    if set(p.name for p in root.iterdir())!=names|{'KIT_MANIFEST.json'}:raise ValueError('source tree')
    return payloads


def main():
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode or len(sys.argv)!=4:
        raise ValueError('isolated invocation')
    mode,manifest_sha,argument=sys.argv[1:]
    if mode not in ('owner','worker'):raise ValueError('invocation role')
    root=Path(__file__).resolve().parent
    payloads=verified_sources(root,manifest_sha)
    for name in ('header_logic','probe_entry'):
        if name in sys.modules:raise ValueError('preloaded source')
        module=ModuleType(name);module.__file__=str(root/(name+'.py'));module.__package__=''
        module.__dict__.update(_SOURCE_ROOT=root,_MANIFEST_SHA=manifest_sha,_PAYLOADS=payloads,
            _BOOTSTRAP_MODE=mode,_BOOTSTRAP_PID=os.getpid(),_BOOTSTRAP_ARGUMENT=argument)
        sys.modules[name]=module
        exec(compile(payloads[name+'.py'],module.__file__,'exec'),module.__dict__)
    return sys.modules['probe_entry'].main(mode,argument)


if __name__=='__main__':
    try:raise SystemExit(main())
    except SystemExit:raise
    except BaseException:
        # A later output/validation exception may follow admission or a request;
        # this fallback makes no assertion about unobserved progress.
        sys.stdout.write('{"schema":1,"status":"incomplete","reason":"SOURCE_OR_EXECUTION_BLOCKED"}\n')
        raise SystemExit(1) from None
