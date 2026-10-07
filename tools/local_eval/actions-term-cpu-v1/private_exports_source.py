"""Retained internal manifest helper only. No arm-key or blinding code runs here."""
from hashlib import sha256
import os
from pathlib import Path
import stat
import cpu_harness as h
import guarded_runtime as runtime


def manifest_private_files(plan,deadline,status):
    """Read only the fixed private allowlist; exclude the manifest's own digest."""
    runtime.require_activation()
    files=[];total=0
    roots=((Path(h.OUTPUT_POLICY['fixed_root']),h.OUTPUT_POLICY['fixed_files']),
           (Path(plan['paths']['output']),h.OUTPUT_POLICY['output_files']))
    for root,allowed in roots:
        for name,schema in allowed.items():
            if name=='manifest.json':continue
            deadline.remaining()
            path=root/name
            if not path.exists():continue  # Missing optional/unfinished files stay explicit below.
            deadline.remaining()
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                info=os.fstat(fd)
                h.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and
                          stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'private output ownership/mode')
                h.require(info.st_size<=schema['max_bytes'],'per-file manifest bound')
                total+=info.st_size;h.require(total<=64*h.MIB,'total retained output bound')
                hasher=sha256();remaining=info.st_size
                while remaining:
                    deadline.remaining();data=os.read(fd,min(65536,remaining));h.require(data,'short manifest read')
                    hasher.update(data);remaining-=len(data)
                files.append(dict(root='fixed_claim' if root==roots[0][0] else 'output',name=name,
                                  bytes=info.st_size,sha256=hasher.hexdigest(),schema=schema['schema']))
            finally:os.close(fd)
    deadline.remaining()
    return dict(schema=1,status=status,files=files,total_bytes_before_manifest=total,
                absent_outputs=sorted(set(h.OUTPUT_POLICY['output_files'])-{f['name'] for f in files}-{'manifest.json'}),
                excludes_own_digest=True,private_only=True)
