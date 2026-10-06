"""Non-mutating host checks after verified Actions/owned-worker admission."""
from hashlib import sha256
import locale
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import time
import actions_policy
import acquisition_source as acquisition
import cpu_harness as h
import guarded_runtime as runtime


HOST_POLICY=dict(schema=1,cpu_flags=['sse2'],archive_library_dirs=['llama-b11349'],
    interpreter='/lib64/ld-linux-x86-64.so.2',cache_format='glibc-1.1-le64-baseline-only',
    allowed_libraries=['ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libstdc++.so.6',
                       'libgcc_s.so.1','libgomp.so.1','libpthread.so.0','libdl.so.2','librt.so.1',
                       'libssl.so.3','libcrypto.so.3'],
    canonical_library_root='/usr/lib/x86_64-linux-gnu',optional_cpu_backends='upstream-dynamic-selection')


def validate_host_plan(plan):
    h.require(plan==HOST_POLICY,'exact source-backed baseline/loader policy')


def parse_loader_cache(raw):
    """Bounded glibc new-format reader; unsupported relevant hwcaps stop.

    Layout: glibc-2.39 sysdeps/generic/dl-cache.h, file_entry_new/cache_file_new.
    The cache is used only for approved library names, never as arbitrary paths.
    """
    h.require(type(raw) is bytes and 48<=len(raw)<=h.MIB and raw[:20]==b'glibc-ld.so.cache1.1',
              'unsupported loader cache header')
    count,strings=struct.unpack_from('<II',raw,20)
    h.require(raw[28]&3==2 and 0<count<=32768,'unknown cache endianness/count')
    first=48+24*count;last=first+strings
    h.require(first<=last<=len(raw),'cache string table bounds')
    def string(offset):
        h.require(first<=offset<last,'cache string offset')
        end=raw.find(b'\0',offset,min(last,offset+4097));h.require(end>=0,'cache string cap')
        return raw[offset:end].decode('ascii','strict')
    result={}
    for i in range(count):
        flags,key,value,unused,hwcap=struct.unpack_from('<iIIIQ',raw,48+24*i)
        name=string(key)
        if name not in HOST_POLICY['allowed_libraries'] or flags!=0x303:continue
        h.require(hwcap==0,'ambiguous relevant glibc-hwcaps resolution')
        path=string(value)
        h.require(path.startswith(('/lib/x86_64-linux-gnu/','/usr/lib/x86_64-linux-gnu/')) and
                  Path(path).name==name and '..' not in Path(path).parts,'unexpected cached library path')
        h.require(name not in result,'duplicate or ambiguous baseline cache entry')
        result[name]=path
    h.require(set(result)==set(HOST_POLICY['allowed_libraries']),'required host dependency cache missing')
    return result


def resolve_host_libraries(cache,deadline):
    runtime.require_activation()
    resolved={};elf={}
    for name,path in parse_loader_cache(cache).items():
        canonical=Path(path).resolve(strict=True)
        h.require(canonical.parent==Path(HOST_POLICY['canonical_library_root']),'unreviewed host-library directory')
        identity=hash_file(canonical,deadline,max_bytes=64*h.MIB)
        view=acquisition.inspect_elf(canonical,deadline)
        h.require(view['rpath'] is None and view['runpath'] is None,'host library search overrides unknown')
        resolved[name]=dict(path=str(canonical),cache_path=path,sha256=identity);elf[name]=view
    for view in elf.values():
        h.require(set(view['needed'])<=set(resolved),'host dependency closure unknown')
    interp=Path(HOST_POLICY['interpreter']).resolve(strict=True)
    h.require(str(interp)==resolved['ld-linux-x86-64.so.2']['path'],'ELF interpreter/cache mismatch')
    return dict(cpu_flags=HOST_POLICY['cpu_flags'],archive_library_dirs=HOST_POLICY['archive_library_dirs'],
        host_libraries=resolved,interpreter=dict(path=HOST_POLICY['interpreter'],
        canonical_path=str(interp),sha256=resolved['ld-linux-x86-64.so.2']['sha256']),
        loader_cache_sha256=h.digest(cache)),elf


def recheck_host_bindings(resolved,deadline):
    runtime.require_activation()
    h.require(h.digest(runtime.bounded_file('/etc/ld.so.cache',h.MIB))==resolved['loader_cache_sha256'],
              'loader cache changed after preflight')
    h.require(str(Path(resolved['interpreter']['path']).resolve(strict=True))==resolved['interpreter']['canonical_path'],
              'interpreter resolution drift')
    for binding in resolved['host_libraries'].values():
        h.require(str(Path(binding['cache_path']).resolve(strict=True))==binding['path'],'cached symlink resolution drift')
        h.require(hash_file(binding['path'],deadline,max_bytes=64*h.MIB)==binding['sha256'],'host library drift')


def namespace_observation(read,readlink):
    """Pure when callbacks are inert. Provider provenance is checked separately."""
    status=read('/proc/self/status',65536).decode('ascii')
    depths=[line.split(':',1)[1].split() for line in status.splitlines() if line.startswith('NSpid:')]
    h.require(len(depths)==1 and len(depths[0])==1 and depths[0][0].isdigit() and int(depths[0][0])>1,
              'nested or unknown PID namespace')
    h.require(read('/proc/1/comm',128).strip()==b'systemd','non-standard VM init')
    init_status=read('/proc/1/status',65536).decode('ascii')
    init_fields={line.split(':',1)[0]:line.split(':',1)[1].split() for line in init_status.splitlines() if ':' in line}
    h.require(init_fields.get('Name')==['systemd'] and init_fields.get('Pid')==['1'] and
              init_fields.get('NSpid')==['1'],'PID1 status/topology unknown or contradictory')
    links={}
    for name in ('pid','cgroup','mnt'):
        own=readlink('/proc/self/ns/'+name)
        h.require(re.fullmatch(name+r':\[[0-9]+\]',own),'self namespace fingerprint unknown')
        links[name]=own
    # Initial namespace identity is not proven by these unprivileged observations.
    # The exact non-container standard-provider policy is the declared trust basis.
    mounts=read('/proc/self/mountinfo',h.MIB).decode('ascii').splitlines()
    groups=[line.split() for line in mounts if ' - cgroup2 ' in line]
    h.require(len(groups)==1 and groups[0][3]=='/','absent, ambiguous or hidden cgroup mount')
    h.require(read('/proc/self/cgroup',65536).decode('ascii').startswith('0::/'),'unified cgroup identity required')
    return links


def hash_file(path,deadline,expected_size=None,max_bytes=2*h.GIB):
    runtime.require_activation()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd);h.require(0<=info.st_size<=max_bytes,'bounded file identity')
        if expected_size is not None:h.require(info.st_size==expected_size,'pinned file length')
        hasher=sha256();remaining=info.st_size
        while remaining:
            deadline.remaining();block=os.read(fd,min(65536,remaining));h.require(block,'short local hash read')
            hasher.update(block);remaining-=len(block)
        deadline.remaining();return hasher.hexdigest()
    finally:os.close(fd)


def check_host_before_claim(plan,resources,disk_root,provider,source_a,source_parent):
    """No downloads or claims until reviewed host bindings pass. Re-run at launch."""
    runtime.require_activation();validate_host_plan(plan)
    deadline=h.Deadline(time.monotonic,60)
    h.require(platform.system()=='Linux' and platform.machine()=='x86_64','CPU executor architecture')
    actions_policy.validate_provider(provider,source_a=source_a,source_parent=source_parent)
    namespaces=namespace_observation(runtime.bounded_file,os.readlink)
    cache=runtime.bounded_file('/etc/ld.so.cache',h.MIB)
    resolved,elf=resolve_host_libraries(cache,deadline)
    if Path('/etc/ld.so.preload').exists():
        h.require(not runtime.bounded_file('/etc/ld.so.preload',4096).strip(),'system preload is not approved')
    cpu=runtime.bounded_file('/proc/cpuinfo',h.MIB).decode('ascii')
    flags=[set(line.split(':',1)[1].split()) for line in cpu.splitlines() if line.startswith('flags\t')]
    h.require(flags and all(set(plan['cpu_flags'])<=row for row in flags),'CPU flags unknown/unsupported')
    previous=locale.setlocale(locale.LC_ALL)
    try:locale.setlocale(locale.LC_ALL,'C.UTF-8')
    finally:locale.setlocale(locale.LC_ALL,previous)
    available=resources.memory_available()
    headroom=runtime.cgroup_headroom(available,hierarchy_root_verified=True)
    h.resource_gate(available,headroom,startup=True,free_disk=shutil.disk_usage(disk_root).free)
    deadline.remaining()
    return dict(host_policy_sha256=h.digest(h.canonical(plan)),namespaces=namespaces,provider_binding_sha256=h.digest(h.canonical(provider)),
                provenance='trusted GitHub service context plus local observations; not cryptographic attestation',
                available_ram=available,effective_headroom=headroom,host_dependencies=elf,resolved_host=resolved,locale='C.UTF-8')


def check_library_basenames(members):
    names=set()
    for member in members:
        name=Path(member['name']).name
        if member['type']=='symlink' or (member['type']=='file' and '.so' in name):
            h.require(name not in names,'ambiguous file/alias library basename')
            names.add(name)


def validate_extracted_runtime(plan,archive_root,members,deadline):
    runtime.require_activation()
    recheck_host_bindings(plan,deadline)
    check_library_basenames(members)
    root=Path(archive_root).resolve();files={m['name']:m for m in members if m['type']=='file'}
    servers=[name for name in files if Path(name).name=='llama-server']
    h.require(len(servers)==1 and files[servers[0]]['sha256']==h.PINS['server'],'unique pinned extracted server')
    directories=[(root/relative).resolve() for relative in plan['archive_library_dirs']]
    h.require(all(d.is_relative_to(root) and d.is_dir() and not d.is_symlink() for d in directories),'verified archive library dirs')
    archive_libraries={}
    for name,member in files.items():
        path=root/name
        h.require(hash_file(path,deadline,member['size'],512*h.MIB)==member['sha256'],'extracted member drift')
        if '.so' in path.name:
            h.require(path.name not in archive_libraries,'ambiguous extracted library basename')
            archive_libraries[path.name]=path
    for member in members:
        if member['type']=='symlink':
            path=root/member['name'];target=path.resolve()
            h.require(target.is_relative_to(root) and target.is_file(),'library symlink resolution')
            h.require(path.name not in archive_libraries,'ambiguous extracted library alias')
            archive_libraries[path.name]=path
    h.require(not set(archive_libraries).intersection(plan['host_libraries']),'archive/host library collision')
    inspected={}
    for path in [root/servers[0],*archive_libraries.values()]:
        elf=acquisition.inspect_elf(path,deadline);inspected[str(path.relative_to(root))]=elf
        h.require(elf['interpreter'] is None or elf['interpreter']==plan['interpreter']['path'],'unreviewed ELF interpreter')
        for field in ('rpath','runpath'):
            if elf[field] is not None:
                h.require(all(entry in ('$ORIGIN','${ORIGIN}') for entry in elf[field].split(':')),'unreviewed ELF search path')
        for dependency in elf['needed']:
            h.require(dependency in archive_libraries or dependency in plan['host_libraries'],'runtime dependency unknown')
            if dependency in archive_libraries and dependency not in plan['host_libraries']:
                search=list(directories)
                if any(elf[field] is not None for field in ('rpath','runpath')):search.append(path.parent.resolve())
                h.require(archive_libraries[dependency].parent.resolve() in search,'archive dependency is not loader-reachable')
    server=root/servers[0]
    os.chmod(server,0o700,follow_symlinks=False)
    deadline.remaining()
    return dict(server=str(server),library_dirs=[str(d) for d in directories],elf=inspected,
                host_policy_sha256=h.digest(h.canonical(plan)))
