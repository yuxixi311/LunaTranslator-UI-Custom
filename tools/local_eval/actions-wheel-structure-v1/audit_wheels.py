#!/usr/bin/env python3
"""Source-only proposed exact49 audit. No action occurs on import.

Use only after separate approval of this source and protocol. No target package is
imported, installed or extracted. Tests inject synthetic archives and transport.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
import csv
from email import policy
from email.parser import BytesParser
import hashlib
import http.client
import io
import json
import keyword
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

MIB = 1024 * 1024
MANIFEST_SHA256 = 'c04f4e31641594e90b9a6436625ad20d0de550b5f8543d70d5d70f46458d3401'
EXPECTED_COUNT = 49
EXPECTED_BYTES = 207406351
ACQUIRE_SECONDS, AUDIT_SECONDS = 240, 600
ACQUIRE_CAP, REPORT_CAP = 250 * MIB, 2 * MIB
SCHEMES = ('purelib', 'platlib', 'scripts', 'headers', 'data', 'unknown')
VERSIONS = ('1.0', '1.1', '1.2', '2.1', '2.2', '2.3', '2.4', '2.5', '2.6', 'other', 'unobserved')
SETUPTOOLS_PTH = '2638ce9e2500e572a5e0de7faed6661eb569d1b696fcba07b0dd223da5f5d224'
SETUPTOOLS_SHIM = 'ced72e54431ecf2d8d7dbd8a1e27724f1b171af3ca1503c304bf11c59a7fe861'
HARD_CODES = frozenset(('manifest_pin','manifest_shape','access_denied','http_status',
    'redirect_denied','response_encoding','response_size','acquisition_size_limit',
    'archive_size','archive_hash','archive_type','archive_changed','archive_missing',
    'zip_envelope','zip_bounds','zip_encoding','zip_path','zip_duplicate','zip_type',
    'zip_permissions','zip_overlap','zip_local_header','zip_read','record_missing',
    'record_ambiguous','record_parse','record_shape','record_member','record_self',
    'record_coverage','record_size','record_digest','metadata_hash','metadata_bounds',
    'fact_limit','deadline','resource_limit','worker_failed','report_invalid',
    'disk_limit','cleanup_failed','attempt_exists','source_pin','internal_error'))
FINDINGS = frozenset(('relocation_scheme_unsupported','relocation_scheme_unknown',
    'foreign_data_root','data_root_not_directory','scheme_root_not_directory',
    'foreign_dist_info','required_metadata_missing','metadata_parse_unsupported',
    'metadata_identity_mismatch','metadata_version_unsupported','wheel_parse_unsupported',
    'wheel_version_unsupported','wheel_root_is_purelib_invalid','wheel_tag_mismatch',
    'destination_collision','destination_file_directory_collision','mapping_incomplete',
    'startup_pth_forbidden','startup_customization_forbidden','startup_bytecode_forbidden',
    'setuptools_pth_mismatch','setuptools_shim_mismatch','notice_declared_missing',
    'notice_declaration_unsafe','notice_modern_placement_absent','import_syntax_unsupported',
    'import_ownership_ambiguous','import_ownership_collision','import_prefix_overlap'))

class Stop(Exception):
    def __init__(self, code):
        self.code = code if code in HARD_CODES else 'internal_error'
        super().__init__(self.code)

def fail(code):
    raise Stop(code)

def digest(value):
    return hashlib.sha256(value).hexdigest()

def commitment(value):
    return digest(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode())

def bounded(items, limit):
    if len(items) > limit:
        fail('fact_limit')
    return items

def check_deadline(deadline):
    if time.monotonic() >= deadline:
        fail('deadline')

def safe_path(name, directory=False):
    if not isinstance(name, str) or not name or len(name.encode('utf-8')) > 4096:
        fail('zip_path')
    if '\\' in name or ':' in name or name.startswith('/') or '\x00' in name:
        fail('zip_path')
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in name) or unicodedata.normalize('NFC', name) != name:
        fail('zip_path')
    clean = name[:-1] if directory and name.endswith('/') else name
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or len(p.encode('utf-8')) > 255 for p in clean.split('/')):
        fail('zip_path')
    return clean

def read_manifest(path):
    try:data=safe_bytes_read(path,30148,expected_size=30148)
    except (Stop,OSError):fail('manifest_pin')
    if digest(data) != MANIFEST_SHA256:
        fail('manifest_pin')
    obj = json.loads(data)
    rows = obj['files']
    if len(rows) != EXPECTED_COUNT or sum(r['wheel']['bytes'] for r in rows) != EXPECTED_BYTES:
        fail('manifest_shape')
    seen = set()
    for r in rows:
        w = r['wheel']; u = urllib.parse.urlsplit(w['url'])
        if (u.scheme != 'https' or u.netloc != 'files.pythonhosted.org' or u.query or u.fragment
                or not u.path.startswith('/packages/') or u.path.rsplit('/', 1)[-1] != w['filename']
                or '/' in w['filename'] or w['filename'] in seen):
            fail('manifest_shape')
        seen.add(w['filename'])
    return rows

def status_rows(records):
    return [{'index':i, 'name':r['name'], 'version':r['version'],
        'archive_sha256':r['wheel']['sha256'], 'acquisition':'not_attempted',
        'audit':'not_attempted', 'failure':None, 'facts':None} for i,r in enumerate(records)]

def initial_report(records):
    return {'schema':'exact49-structural-audit-v1', 'manifest_sha256':MANIFEST_SHA256,
        'status':'incomplete', 'phase':'not_started', 'failure':None,
        'installation':'not_run', 'runtime':'unverified', 'ner':'not_run',
        'legal_clearance':'not_claimed', 'rows':status_rows(records),
        'acquired_bytes':0, 'audited_uncompressed_bytes':0,
        'audited_member_count':0, 'compatibility_findings':[], 'cleanup':'pending'}

def write_json(path, obj):
    data = json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    if len(data) > REPORT_CAP:
        fail('fact_limit')
    # Destination belongs to this invocation; never overwrite arbitrary input.
    tmp = Path(str(path) + '.new')
    with tmp.open('xb') as stream:
        stream.write(data)
    os.replace(tmp, path)


def safe_bytes_read(path,cap=REPORT_CAP,expected_size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>cap or (expected_size is not None and before.st_size!=expected_size): fail('report_invalid')
        data=stream.read(cap+1)
        after=os.fstat(stream.fileno())
        if len(data)>cap or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns): fail('report_invalid')
    return data


def safe_json_read(path,cap=REPORT_CAP):
    data=safe_bytes_read(path,cap)
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: fail('report_invalid')
            result[key]=value
        return result
    try: return json.loads(data,object_pairs_hook=pairs)
    except (ValueError,UnicodeError): fail('report_invalid')


def validate_report(obj,records):
    """Closed publication projection. Untrusted state never supplies field names."""
    def require(ok):
        if not ok: fail('report_invalid')
    def keys(value,allowed): require(type(value) is dict and set(value)==set(allowed))
    def integer(value,maximum=2*1024*MIB): require(type(value) is int and 0<=value<=maximum)
    def enum(value,values): require(type(value) is str and value in values)
    def sha(value,optional=False): require((optional and value is None) or (type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None))
    def code(value): require(value is None or (type(value) is str and value in HARD_CODES))
    def findings(value):
        require(type(value) is list and len(value)<=len(FINDINGS) and all(type(v) is str and v in FINDINGS for v in value) and len(value)==len(set(value)))
    def fact(value,extras=()):
        keys(value,('path_sha256','content_sha256','bytes')+tuple(extras))
        sha(value['path_sha256']);sha(value['content_sha256']);integer(value['bytes'],512*MIB)
    def fact_list(value,maximum,extras=()):
        require(type(value) is list and len(value)<=maximum)
        for item in value: fact(item,extras)
    def counter(value,allowed):
        require(type(value) is dict and set(value)<=set(allowed))
        for number in value.values(): integer(number)
    template=initial_report(records); keys(obj,template)
    for field in ('schema','manifest_sha256','installation','runtime','ner','legal_clearance'):
        require(obj[field]==template[field])
    enum(obj['status'],('incomplete','structurally_complete','structurally_complete_with_findings'))
    enum(obj['phase'],('not_started','acquisition','audit','finished'))
    enum(obj['cleanup'],('pending','verified','uncertain','failed'))
    code(obj['failure']); findings(obj['compatibility_findings'])
    integer(obj['acquired_bytes'],ACQUIRE_CAP); integer(obj['audited_uncompressed_bytes']); integer(obj['audited_member_count'],100000)
    require(type(obj['rows']) is list and len(obj['rows'])==len(records))
    acquired_all=True; audit_started=False
    for index,(row,record) in enumerate(zip(obj['rows'],records)):
        keys(row,template['rows'][index]);integer(row['index'],len(records)-1)
        for field in ('index','name','version','archive_sha256'): require(row[field]==template['rows'][index][field])
        for field in ('acquisition','audit'): enum(row[field],('not_attempted','in_progress','verified','failed','unobserved_after_termination','facts_omitted_due_to_report_limit'))
        code(row['failure'])
        acquired_all=acquired_all and row['acquisition']=='verified'
        audit_started=audit_started or row['audit']!='not_attempted'
        if row['audit']!='verified': require(row['facts'] is None); continue
        require(row['acquisition']=='verified' and row['failure'] is None)
        f=row['facts']
        keys(f,('integrity','member_count','record_rows','record_signature_exemptions','inventory_sha256','root_inventory_sha256','dist_info_root_count','data_root_count','layout','relocation','unknown_scheme_sha256','member_kinds','scripts','startup','entry_metadata','notice_candidates','native_libraries','notice_inventory','metadata_version','core_metadata_sha256','metadata_field_commitment','dynamic_count','dependency_count','imports','declared_notices','wheel_version','root_is_purelib','findings'))
        require(f['integrity']=='verified' and f['notice_inventory']=='heuristic_nonexhaustive')
        for field in ('member_count','record_rows','dist_info_root_count','data_root_count'): integer(f[field],50000)
        integer(f['record_signature_exemptions'],2)
        sha(f['inventory_sha256']);sha(f['root_inventory_sha256']);sha(f['core_metadata_sha256'],True);sha(f['metadata_field_commitment'],True)
        if f['core_metadata_sha256'] is not None: require(f['core_metadata_sha256']==record['wheel']['core_metadata_sha256'])
        counter(f['layout'],(x+y for x in ('root','data','dist_info') for y in ('_members','_bytes')))
        counter(f['relocation'],(x+y for x in SCHEMES for y in ('_members','_bytes')))
        counter(f['member_kinds'],('directories','native','bytecode','python_source','other_files'))
        require(type(f['unknown_scheme_sha256']) is list and len(f['unknown_scheme_sha256'])<=32)
        for h in f['unknown_scheme_sha256']: sha(h)
        fact_list(f['scripts'],4096,('executable','shebang'))
        for item in f['scripts']:
            require(type(item['executable']) is bool);enum(item['shebang'],('wheel_python','wheel_pythonw','other','none'))
        fact_list(f['startup'],128,('kind',))
        for item in f['startup']: enum(item['kind'],('pth','customization','bytecode'))
        fact_list(f['entry_metadata'],128,('kind',))
        for item in f['entry_metadata']: enum(item['kind'],('entry_points','top_level'))
        fact_list(f['notice_candidates'],4096);fact_list(f['native_libraries'],4096)
        enum(f['metadata_version'],VERSIONS);enum(f['wheel_version'],('1.0','other','unobserved'));enum(f['root_is_purelib'],('true','false','other','unobserved'))
        for field in ('dynamic_count','dependency_count'):
            if f[field] is not None: integer(f[field],2048)
        if f['imports'] is not None:
            im=f['imports'];keys(im,(x+y for x in ('names','namespaces') for y in ('_state','_count','_sha256')))
            for x in ('names','namespaces'):
                enum(im[x+'_state'],('absent_unknown','declared','explicit_empty'));integer(im[x+'_count'],256);sha(im[x+'_sha256'])
        require(type(f['declared_notices']) is list and len(f['declared_notices'])<=1024)
        for item in f['declared_notices']:
            keys(item,('declaration_sha256','matches','modern_placement','safe'));sha(item['declaration_sha256'])
            require(type(item['safe']) is bool and type(item['modern_placement']) is bool);fact_list(item['matches'],1024)
        findings(f['findings'])
    require(not audit_started or acquired_all)
    for field in ('acquisition','audit'):
        unattempted=False; terminal=False
        for row in obj['rows']:
            value=row[field]
            if value=='not_attempted': unattempted=True
            else:
                require(not unattempted and (not terminal or value=='unobserved_after_termination'))
                if value not in ('verified','facts_omitted_due_to_report_limit'): terminal=True
    if acquired_all:require(obj['acquired_bytes']==sum(r['wheel']['bytes'] for r in records))
    if obj['status'].startswith('structurally_complete'):
        require(obj['audited_member_count']==sum(row['facts']['member_count'] for row in obj['rows'] if row['facts'] is not None))
        require(obj['audited_uncompressed_bytes']==sum(sum(row['facts']['layout'].get(place+'_bytes',0) for place in ('root','data','dist_info')) for row in obj['rows'] if row['facts'] is not None))
        require(obj['failure'] is None and acquired_all and all(r['audit']=='verified' for r in obj['rows']) and obj['phase']=='finished')
    return obj


def compact_failure(report,records,code):
    result=initial_report(records);result['failure']=code;result['status']='incomplete'
    result['phase']=report['phase'];result['cleanup']=report['cleanup']
    result['acquired_bytes']=report['acquired_bytes']
    for old,new in zip(report['rows'],result['rows']):
        new['acquisition']=old['acquisition']
        new['audit']='facts_omitted_due_to_report_limit' if old['audit']=='verified' else old['audit']
        for key in ('acquisition','audit'):
            if new[key]=='in_progress': new[key]='unobserved_after_termination'
        new['failure']=code if new['audit']=='facts_omitted_due_to_report_limit' else old['failure']
    return result

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None: fp.close()
        fail('redirect_denied')

def live_transport(url, timeout):
    # ProxyHandler({}) deliberately ignores ambient proxy variables.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers={'Accept-Encoding':'identity','User-Agent':'Luna-exact49-structural-audit/1'})
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        code='redirect_denied' if 300 <= error.code < 400 else 'http_status'
        error.close();fail(code)
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        fail('access_denied')

def acquire(records, directory, report, deadline, transport=live_transport, checkpoint=lambda:None):
    report['phase'] = 'acquisition'
    total = 0
    for index, record in enumerate(records):
        row = report['rows'][index]; w = record['wheel']
        row['acquisition'] = 'in_progress'
        checkpoint()
        try:
            check_deadline(deadline)
            with transport(w['url'], min(15, max(0.1, deadline-time.monotonic()))) as response:
                if response.status != 200:
                    fail('http_status')
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    fail('response_encoding')
                length = response.headers.get('Content-Length')
                if length is not None and (not re.fullmatch(r'[0-9]{1,12}', length) or int(length) != w['bytes']):
                    fail('response_size')
                size = 0; sha = hashlib.sha256()
                with (Path(directory) / w['filename']).open('xb') as stream:
                    while True:
                        check_deadline(deadline)
                        block = response.read(min(MIB, w['bytes']-size+1))
                        if not block:
                            break
                        size += len(block); total += len(block)
                        if total > ACQUIRE_CAP:
                            fail('acquisition_size_limit')
                        if size > w['bytes']:
                            fail('response_size')
                        stream.write(block); sha.update(block)
                if size != w['bytes']:
                    fail('archive_size')
                if sha.hexdigest() != w['sha256']:
                    fail('archive_hash')
                check_deadline(deadline)
                row['acquisition'] = 'verified'
                report['acquired_bytes'] = total
                checkpoint()
        except Stop as error:
            row['acquisition'] = 'failed'; row['failure'] = error.code
            report['failure'] = error.code
            raise
        except (OSError, http.client.HTTPException, urllib.error.URLError):
            row['acquisition'] = 'failed'; row['failure'] = 'access_denied'
            report['failure'] = 'access_denied'; fail('access_denied')


def check_source_collisions(entries):
    seen = {}
    for name, directory in entries:
        key = name.casefold()
        if key in seen:
            fail('zip_duplicate')
        seen[key] = directory
    for key in seen:
        parts = key.split('/')
        if any(seen.get('/'.join(parts[:i])) is False for i in range(1,len(parts))):
            fail('zip_duplicate')


def zip_envelope(stream, size):
    if not 22 <= size <= 256*MIB:
        fail('zip_bounds')
    stream.seek(0)
    if stream.read(4) != b'PK\x03\x04':
        fail('zip_envelope')
    stream.seek(size-22); end = stream.read(22)
    if end[:4] != b'PK\x05\x06':
        fail('zip_envelope')
    _, disk, cd_disk, n_disk, count, cd_size, cd_offset, comment = struct.unpack('<4s4H2IH',end)
    if disk or cd_disk or n_disk != count or comment or count == 0xffff or cd_size == 0xffffffff or cd_offset == 0xffffffff:
        fail('zip_encoding')
    if not 1 <= count <= 50000 or cd_size > 16*MIB or cd_offset+cd_size != size-22:
        fail('zip_bounds')
    return cd_offset, count


def check_extra(data):
    offset=0
    while offset<len(data):
        if offset+4>len(data): fail('zip_encoding')
        field,size=struct.unpack('<HH',data[offset:offset+4]); offset+=4
        if field==1 or offset+size>len(data): fail('zip_encoding')
        offset+=size


def local_regions(stream, infos, cd_offset):
    regions = [];data_offsets={}
    for info in infos:
        stream.seek(info.header_offset)
        head = stream.read(30)
        if len(head) != 30:
            fail('zip_local_header')
        sig, version, flags, method, _, _, crc, compressed, size, nlen, xlen = struct.unpack('<4s5H3I2H', head)
        if sig != b'PK\x03\x04' or version!=info.extract_version or flags != info.flag_bits or method != info.compress_type:
            fail('zip_local_header')
        raw_name = stream.read(nlen); extra = stream.read(xlen)
        check_extra(extra); check_extra(info.extra)
        try:
            name = raw_name.decode('utf-8' if flags & 0x800 else 'cp437')
        except UnicodeError:
            fail('zip_local_header')
        if name != info.orig_filename or len(extra) != xlen:
            fail('zip_local_header')
        if not flags & 8 and (crc,compressed,size) != (info.CRC,info.compress_size,info.file_size):
            fail('zip_local_header')
        if flags & 8 and (crc not in (0,info.CRC) or compressed not in (0,info.compress_size) or size not in (0,info.file_size)):
            fail('zip_local_header')
        data_offsets[info.filename]=info.header_offset+30+nlen+xlen
        end = data_offsets[info.filename]+info.compress_size
        if flags & 8:
            stream.seek(end); descriptor = stream.read(16)
            if descriptor[:4] == b'PK\x07\x08':
                values = struct.unpack('<3I',descriptor[4:16]); end += 16
            elif len(descriptor) >= 12:
                values = struct.unpack('<3I',descriptor[:12]); end += 12
            else:
                fail('zip_local_header')
            if values != (info.CRC,info.compress_size,info.file_size):
                fail('zip_local_header')
        if info.header_offset < 0 or end > cd_offset:
            fail('zip_overlap')
        regions.append((info.header_offset,end))
    regions.sort()
    # No unaudited prefix, gap payload, overlapping data or trailing local payload.
    cursor = 0
    for start,end in regions:
        if start != cursor:
            fail('zip_overlap')
        cursor = end
    if cursor != cd_offset:
        fail('zip_overlap')
    return data_offsets



def central_directory(stream,offset,count,size):
    stream.seek(offset);data=stream.read(size-22-offset)
    cursor=0
    for _ in range(count):
        if cursor+46>len(data):fail('zip_envelope')
        fields=struct.unpack('<4s6H3I5H2I',data[cursor:cursor+46])
        sig,made,needed,flags,method,mtime,mdate,crc,csize,usize,nlen,xlen,clen,disk,iattr,eattr,local=fields
        if sig!=b'PK\x01\x02' or disk or needed not in (10,20) or method not in (0,8) or flags & ~0x80e or csize==0xffffffff or usize==0xffffffff or local==0xffffffff:fail('zip_encoding')
        end=cursor+46+nlen+xlen+clen
        if end>len(data):fail('zip_envelope')
        if clen:fail('zip_encoding')
        check_extra(data[cursor+46+nlen:cursor+46+nlen+xlen])
        cursor=end
    if cursor!=len(data):fail('zip_envelope')


def member_chunks(stream,info,offset,deadline):
    stream.seek(offset);remaining=info.compress_size;crc=0;size=0
    if info.compress_type==zipfile.ZIP_STORED and info.compress_size!=info.file_size:fail('zip_read')
    inflater=zlib.decompressobj(-zlib.MAX_WBITS) if info.compress_type==zipfile.ZIP_DEFLATED else None
    while remaining:
        check_deadline(deadline);compressed=stream.read(min(MIB,remaining))
        if not compressed:fail('zip_read')
        remaining-=len(compressed)
        pending=compressed
        while pending:
            if inflater:
                try: chunk=inflater.decompress(pending,min(MIB,info.file_size-size+1))
                except zlib.error:fail('zip_read')
                if inflater.unused_data:fail('zip_read')
                pending=inflater.unconsumed_tail
                if inflater.eof and (remaining or pending):fail('zip_read')
            else:chunk=pending;pending=b''
            size+=len(chunk);crc=zlib.crc32(chunk,crc)
            if size>info.file_size or size>512*MIB:fail('zip_bounds')
            if chunk:yield chunk
    if inflater and (not inflater.eof or inflater.unused_data or inflater.unconsumed_tail):fail('zip_read')
    if size!=info.file_size or (crc&0xffffffff)!=info.CRC:fail('zip_read')

def check_record(data, record_path, hashes):
    try:
        rows = list(csv.reader(io.StringIO(data.decode('utf-8'), newline=''), strict=True))
    except (UnicodeError,csv.Error):
        fail('record_parse')
    if len(rows) > len(hashes) or any(len(row)!=3 for row in rows):
        fail('record_shape')
    seen=set()
    for name,field,size in rows:
        safe_path(name)
        if name in seen or name not in hashes:
            fail('record_member')
        seen.add(name)
        if name == record_path:
            if field or size:
                fail('record_self')
            continue
        if not re.fullmatch(r'0|[1-9][0-9]{0,11}',size) or int(size)!=hashes[name]['bytes']:
            fail('record_size')
        alg,sep,encoded=field.partition('=')
        if sep!='=' or alg not in ('sha256','sha384','sha512'):
            fail('record_digest')
        expected=base64.urlsafe_b64encode(bytes.fromhex(hashes[name][alg])).rstrip(b'=').decode()
        if encoded!=expected:
            fail('record_digest')
    exempt={record_path+'.jws',record_path+'.p7s'}
    if record_path not in seen or (set(hashes)-seen)-exempt:
        fail('record_coverage')
    return len(rows), len(set(hashes)-seen)


def headers(data):
    try:
        text=data.decode('utf-8','strict')
        obj=BytesParser(policy=policy.default).parsebytes(data)
        if obj.defects or len(list(obj.raw_items()))>2048:
            return None
        # Check header defects without serializing attacker-controlled values.
        if any(getattr(v,'defects',()) for _,v in obj.items()):
            return None
        return obj
    except (UnicodeError,ValueError,TypeError):
        return None


def shebang(prefix):
    if prefix.startswith(b'#!pythonw') and prefix[9:10] in (b'',b'\r',b'\n',b' '):
        return 'wheel_pythonw'
    if prefix.startswith(b'#!python') and prefix[8:9] in (b'',b'\r',b'\n',b' '):
        return 'wheel_python'
    if prefix.startswith(b'#!'):
        return 'other'
    return 'none'


def abstract_destination(name, directory, base, findings):
    parts=name.split('/')
    if not parts[0].endswith('.data'):
        return ('library',name,directory)
    if parts[0]!=base+'.data':
        findings.add('foreign_data_root')
    if len(parts)==1:
        if not directory: findings.add('data_root_not_directory')
        return None
    scheme=parts[1]
    if scheme not in SCHEMES[:-1]:
        findings.update(('relocation_scheme_unknown','mapping_incomplete'))
        return None
    if scheme not in ('purelib','platlib'):
        findings.add('relocation_scheme_unsupported')
    if len(parts)==2:
        if not directory: findings.add('scheme_root_not_directory')
        return None
    return ('library' if scheme in ('purelib','platlib') else scheme, '/'.join(parts[2:]),directory)


def destination_findings(entries):
    findings=set(); seen={}
    for scheme,name,directory in entries:
        key=(scheme,name.casefold())
        if key in seen and not (directory and seen[key]):
            findings.add('destination_collision')
        seen[key]=seen.get(key,True) and directory
    for (scheme,name) in seen:
        parts=name.split('/')
        if any(seen.get((scheme,'/'.join(parts[:i]))) is False for i in range(1,len(parts))):
            findings.add('destination_file_directory_collision')
    return findings


def import_facts(meta, findings):
    result={}; declarations=[]
    for field,key in (('Import-Name','names'),('Import-Namespace','namespaces')):
        values=[str(v) for v in meta.get_all(field,[])]
        bounded(values,256)
        result[key+'_state']='absent_unknown' if not values else 'declared'
        result[key+'_count']=len(values)
        result[key+'_sha256']=commitment(values)
        if field=='Import-Name' and values==['']:
            result[key+'_state']='explicit_empty'; continue
        for value in values:
            ident,sep,qualifier=value.partition(';')
            ident=ident.strip()
            if (not ident or (sep and qualifier.strip()!='private') or
                    any(not p.isidentifier() or keyword.iskeyword(p) for p in ident.split('.')) or
                    unicodedata.normalize('NFKC',ident)!=ident or len(value)>512):
                findings.add('import_syntax_unsupported'); continue
            declarations.append((ident,field=='Import-Name'))
    exclusive={name for name,ex in declarations if ex}
    namespaces={name for name,ex in declarations if not ex}
    if exclusive & namespaces:
        findings.add('import_ownership_ambiguous')
    return result,declarations


def observe(record, infos, hashes, captures, record_path, row_count, exemptions):
    base='-'.join(record['wheel']['filename'].split('-')[:2]); expected=base+'.dist-info'
    findings=set(); paths={i.filename.rstrip('/') for i in infos}; files=set(hashes)
    inventory=[]; schemes=Counter(); layout=Counter(); kinds=Counter(); destinations=[]
    unknown=set(); scripts=[]; startup=[]; notices=[]; native=[]; entry=[]; roots=set()
    for info in infos:
        name=info.filename.rstrip('/'); parts=name.split('/'); directory=info.is_dir()
        if parts[0].endswith(('.dist-info','.data')): roots.add(parts[0])
        dest=abstract_destination(name,directory,base,findings)
        if dest: destinations.append(dest)
        if parts[0].endswith('.dist-info'):
            placement='dist_info'
            if parts[0]!=expected: findings.add('foreign_dist_info')
        elif parts[0].endswith('.data'):
            placement='data'
        else: placement='root'
        layout[placement+'_members']+=1; layout[placement+'_bytes']+=info.file_size
        if placement=='data' and len(parts)>=2:
            scheme=parts[1] if parts[1] in SCHEMES[:-1] else 'unknown'
            schemes[scheme+'_members']+=1; schemes[scheme+'_bytes']+=info.file_size
            if scheme=='unknown': unknown.add(digest(parts[1].encode()))
        if directory:
            inventory.append({'path_sha256':digest(name.encode()),'content_sha256':digest(b''),'bytes':0,'directory':True})
            kinds['directories']+=1; continue
        h=hashes[info.filename]
        fact={'path_sha256':digest(name.encode()),'content_sha256':h['sha256'],'bytes':h['bytes']}
        inventory.append(dict(fact,directory=False))
        lower=parts[-1].lower()
        if lower.endswith(('.so','.pyd','.dll','.dylib')) or re.search(r'\.so\.[0-9]',lower):
            kinds['native']+=1; native.append(fact)
        elif lower.endswith(('.pyc','.pyo')):
            kinds['bytecode']+=1
        elif lower.endswith('.py'): kinds['python_source']+=1
        else: kinds['other_files']+=1
        if placement=='data' and len(parts)>=3 and parts[1]=='scripts':
            scripts.append(dict(fact,executable=bool((info.external_attr>>16)&0o111),shebang=h['shebang']))
        dest_name=dest[1] if dest else name
        first=dest_name.split('/')[0].casefold(); last=dest_name.rsplit('/',1)[-1].casefold()
        start_kind=None
        if last.endswith('.pth'):
            start_kind='pth'
            if (record['name'],record['version'],name,dest_name)==('setuptools','84.0.0','distutils-precedence.pth','distutils-precedence.pth'):
                if h['sha256']!=SETUPTOOLS_PTH: findings.add('setuptools_pth_mismatch')
            else: findings.add('startup_pth_forbidden')
        if first in ('sitecustomize','usercustomize') or re.match(r'^(sitecustomize|usercustomize)\.',first):
            start_kind='customization'; findings.add('startup_customization_forbidden')
        if last.endswith(('.pyc','.pyo')):
            start_kind='bytecode'; findings.add('startup_bytecode_forbidden')
        if start_kind: startup.append(dict(fact,kind=start_kind))
        if lower in ('entry_points.txt','top_level.txt'):
            entry.append(dict(fact,kind='entry_points' if lower=='entry_points.txt' else 'top_level'))
        if any(token in lower for token in ('license','licence','notice','copying','copyright','authors')):
            notices.append(fact)
    if record['name']=='setuptools' and 'distutils-precedence.pth' in hashes:
        if hashes.get('_distutils_hack/__init__.py',{}).get('sha256')!=SETUPTOOLS_SHIM:
            findings.add('setuptools_shim_mismatch')
    findings.update(destination_findings(destinations))
    metadata_path=expected+'/METADATA'; wheel_path=expected+'/WHEEL'
    facts={'integrity':'verified','member_count':len(infos),'record_rows':row_count,
        'record_signature_exemptions':exemptions,'inventory_sha256':commitment(inventory),
        'root_inventory_sha256':commitment(sorted(roots)),
        'dist_info_root_count':sum(r.endswith('.dist-info') for r in roots),
        'data_root_count':sum(r.endswith('.data') for r in roots),
        'layout':dict(sorted(layout.items())),'relocation':dict(sorted(schemes.items())),
        'unknown_scheme_sha256':sorted(bounded(unknown,32)),'member_kinds':dict(sorted(kinds.items())),
        'scripts':bounded(scripts,4096),'startup':bounded(startup,128),
        'entry_metadata':bounded(entry,128),'notice_candidates':bounded(notices,4096),
        'native_libraries':bounded(native,4096),'notice_inventory':'heuristic_nonexhaustive',
        'metadata_version':'unobserved','core_metadata_sha256':None,
        'metadata_field_commitment':None,'dynamic_count':None,'dependency_count':None,
        'imports':None,'declared_notices':[],'wheel_version':'unobserved','root_is_purelib':'unobserved'}
    declarations=[]
    if not {metadata_path,wheel_path,expected+'/RECORD'} <= files:
        findings.add('required_metadata_missing')
    observed_metadata_path=metadata_path if metadata_path in captures else record_path.rsplit('/',1)[0]+'/METADATA'
    observed_wheel_path=wheel_path if wheel_path in captures else record_path.rsplit('/',1)[0]+'/WHEEL'
    if observed_metadata_path in captures:
        raw=captures[observed_metadata_path]
        if digest(raw)!=record['wheel']['core_metadata_sha256']: fail('metadata_hash')
        facts['core_metadata_sha256']=digest(raw)
        meta=headers(raw)
        if meta is None: findings.add('metadata_parse_unsupported')
        else:
            version=str(meta.get('Metadata-Version',''))
            facts['metadata_version']=version if version in VERSIONS else 'other'
            if version not in VERSIONS[:8]: findings.add('metadata_version_unsupported')
            canonical=lambda s:re.sub(r'[-_.]+','-',s).lower()
            if canonical(str(meta.get('Name','')))!=record['name'] or str(meta.get('Version',''))!=record['version']:
                findings.add('metadata_identity_mismatch')
            facts['metadata_field_commitment']=commitment(list(meta.raw_items()))
            facts['dynamic_count']=len(meta.get_all('Dynamic',[])); facts['dependency_count']=len(meta.get_all('Requires-Dist',[]))
            facts['imports'],declarations=import_facts(meta,findings)
            license_files=[str(v) for v in meta.get_all('License-File',[])]
            bounded(license_files,1024)
            for declared in license_files:
                item={'declaration_sha256':digest(declared.encode()),'matches':[], 'modern_placement':False,'safe':True}
                try: safe_path(declared)
                except Stop:
                    item['safe']=False; findings.add('notice_declaration_unsafe')
                else:
                    matches=sorted(n for n in files if n not in (record_path,record_path+'.jws',record_path+'.p7s') and (n==declared or n.endswith('/'+declared)))
                    item['matches']=bounded([{'path_sha256':digest(n.encode()),'content_sha256':hashes[n]['sha256'],'bytes':hashes[n]['bytes']} for n in matches],1024)
                    item['modern_placement']=expected+'/licenses/'+declared in matches
                    if not matches: findings.add('notice_declared_missing')
                    if version in ('2.4','2.5','2.6') and not item['modern_placement']: findings.add('notice_modern_placement_absent')
                facts['declared_notices'].append(item)
    if observed_wheel_path in captures:
        wheel=headers(captures[observed_wheel_path])
        if wheel is None: findings.add('wheel_parse_unsupported')
        else:
            v=str(wheel.get('Wheel-Version','')); facts['wheel_version']='1.0' if v=='1.0' else 'other'
            if v!='1.0': findings.add('wheel_version_unsupported')
            root=str(wheel.get('Root-Is-Purelib','')).lower()
            facts['root_is_purelib']=root if root in ('true','false') else 'other'
            if root not in ('true','false'): findings.add('wheel_root_is_purelib_invalid')
            filename=record['wheel']['filename'][:-4].split('-')
            expected_tags={a+'-'+b+'-'+c for a in filename[-3].split('.') for b in filename[-2].split('.') for c in filename[-1].split('.')}
            if set(str(v) for v in wheel.get_all('Tag',[]))!=expected_tags: findings.add('wheel_tag_mismatch')
    facts['findings']=sorted(findings)
    assert findings <= FINDINGS
    return facts,destinations,declarations


def audit_one(path, record, deadline, remaining_bytes=2*1024*MIB, remaining_members=100000):
    check_deadline(deadline)
    initial=path.lstat(); w=record['wheel']
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink!=1 or path.name!=w['filename']:
        fail('archive_type')
    if initial.st_size!=w['bytes']: fail('archive_size')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if (before.st_ino,before.st_dev,before.st_size)!=(initial.st_ino,initial.st_dev,initial.st_size): fail('archive_changed')
        sha=hashlib.sha256()
        while block:=stream.read(MIB):
            check_deadline(deadline); sha.update(block)
        if sha.hexdigest()!=w['sha256']: fail('archive_hash')
        cd_offset,expected_count=zip_envelope(stream,before.st_size)
        central_directory(stream,cd_offset,expected_count,before.st_size)
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            infos=archive.infolist()
            if len(infos)!=expected_count or len(infos)>remaining_members: fail('zip_bounds')
            total=0; entries=[]
            for info in infos:
                check_deadline(deadline)
                if info.orig_filename!=info.filename: fail('zip_path')
                entries.append((safe_path(info.filename,info.is_dir()),info.is_dir()))
                mode=info.external_attr>>16
                if stat.S_IFMT(mode) not in (0,stat.S_IFDIR if info.is_dir() else stat.S_IFREG): fail('zip_type')
                if mode & (stat.S_ISUID|stat.S_ISGID|stat.S_ISVTX): fail('zip_permissions')
                if info.flag_bits & (1|64) or info.compress_type not in (0,8): fail('zip_encoding')
                if info.file_size>512*MIB or (info.is_dir() and info.file_size) or info.file_size>max(MIB,1000*info.compress_size): fail('zip_bounds')
                total+=info.file_size
                if total>1024*MIB or total>remaining_bytes: fail('zip_bounds')
            check_source_collisions(entries); data_offsets=local_regions(stream,infos,cd_offset)
            candidates=[i.filename for i in infos if not i.is_dir() and len(i.filename.split('/'))==2 and i.filename.split('/')[0].endswith('.dist-info') and i.filename.endswith('/RECORD')]
            if not candidates: fail('record_missing')
            if len(candidates)!=1: fail('record_ambiguous')
            record_path=candidates[0]; hashes={}; captures={}; captured_bytes=0
            for info in infos:
                check_deadline(deadline)
                capture=(info.filename==record_path or info.filename.rsplit('/',1)[-1] in ('METADATA','WHEEL','entry_points.txt','top_level.txt'))
                limit=16*MIB if info.filename==record_path else 2*MIB
                if capture and info.file_size>limit: fail('metadata_bounds')
                if capture:
                    captured_bytes+=info.file_size
                    if captured_bytes>32*MIB or len(captures)>=128: fail('metadata_bounds')
                hs={alg:hashlib.new(alg) for alg in ('sha256','sha384','sha512')}
                blocks=[]; count=0; prefix=b''
                if True:
                    for block in member_chunks(stream,info,data_offsets[info.filename],deadline):
                        check_deadline(deadline); count+=len(block)
                        if count>info.file_size or count>512*MIB: fail('zip_bounds')
                        for h in hs.values(): h.update(block)
                        if not prefix: prefix=block[:32]
                        if capture: blocks.append(block)
                if count!=info.file_size: fail('zip_bounds')
                if not info.is_dir(): hashes[info.filename]=dict({a:h.hexdigest() for a,h in hs.items()},bytes=count,shebang=shebang(prefix))
                if capture: captures[info.filename]=b''.join(blocks)
            row_count,exemptions=check_record(captures[record_path],record_path,hashes)
            for metadata_name,metadata_bytes in captures.items():
                pieces=metadata_name.split('/')
                if len(pieces)==2 and pieces[0].endswith('.dist-info') and pieces[1]=='METADATA':
                    if digest(metadata_bytes)!=w['core_metadata_sha256']: fail('metadata_hash')
            after=os.fstat(stream.fileno())
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns): fail('archive_changed')
            facts,destinations,imports=observe(record,infos,hashes,captures,record_path,row_count,exemptions)
    return facts,total,destinations,imports


def audit(records,directory,report,deadline,checkpoint=lambda:None):
    report['phase']='audit'; destinations=[]; imports=[]; findings=set()
    for index,record in enumerate(records):
        row=report['rows'][index]; row['audit']='in_progress'
        checkpoint()
        try:
            facts,total,dests,declarations=audit_one(Path(directory)/record['wheel']['filename'],record,deadline,2*1024*MIB-report['audited_uncompressed_bytes'],100000-report['audited_member_count'])
            report['audited_uncompressed_bytes']+=total
            report['audited_member_count']+=facts['member_count']
            if report['audited_uncompressed_bytes']>2*1024*MIB or report['audited_member_count']>100000: fail('zip_bounds')
            destinations.extend(dests); imports.extend((index,name,ex) for name,ex in declarations)
            bounded(imports,4096)
            findings.update(facts['findings']); report['compatibility_findings']=sorted(findings)
            row['audit']='verified'; row['facts']=facts
            checkpoint()
        except Stop as error:
            row['audit']='failed'; row['failure']=error.code; report['failure']=error.code; raise
        except FileNotFoundError:
            row['audit']='failed'; row['failure']='archive_missing'; report['failure']='archive_missing'; fail('archive_missing')
        except (OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError,EOFError,UnicodeError):
            row['audit']='failed'; row['failure']='zip_read'; report['failure']='zip_read'; fail('zip_read')
    findings.update(destination_findings(destinations))
    for i,(owner,name,exclusive) in enumerate(imports):
        for other_owner,other_name,other_exclusive in imports[i+1:]:
            if owner==other_owner: continue
            if name==other_name and (exclusive or other_exclusive): findings.add('import_ownership_collision')
            elif name.startswith(other_name+'.') or other_name.startswith(name+'.'): findings.add('import_prefix_overlap')
    report['compatibility_findings']=sorted(findings)
    report['status']='structurally_complete_with_findings' if findings else 'structurally_complete'
    report['phase']='finished'


def enforce_limits(phase):
    cpu,memory,seconds=(120,512*MIB,ACQUIRE_SECONDS) if phase=='acquisition' else (480,1024*MIB,AUDIT_SECONDS)
    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
    resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
    resource.setrlimit(resource.RLIMIT_FSIZE,(256*MIB,256*MIB))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def alarm(signum,frame): fail('deadline')
    signal.signal(signal.SIGALRM,alarm); signal.alarm(seconds-10)


def worker(phase,manifest,directory,state):
    enforce_limits(phase)
    receipt=safe_json_read(Path(__file__).resolve().with_name('ATTEMPT.json'),4096)
    with open(sys.executable,'rb') as interpreter_stream:
        if hashlib.file_digest(interpreter_stream,'sha256').hexdigest()!=receipt.get('interpreter_sha256'):fail('source_pin')
    if (receipt.get('status')!=phase or receipt.get('owner_pid')!=os.getppid() or
            receipt.get('directory_sha256')!=digest(str(Path(directory).resolve()).encode()) or
            receipt.get('helper_sha256')!=digest(safe_bytes_read(Path(__file__),2*MIB)) or
            os.getsid(0)!=os.getpid() or Path(state).resolve()!=Path(directory).resolve()/'state.json'):
        fail('access_denied')
    records=read_manifest(manifest)
    report=validate_report(safe_json_read(Path(state)),records)
    try:
        if phase=='acquisition': acquire(records,directory,report,time.monotonic()+ACQUIRE_SECONDS-10,checkpoint=lambda:write_json(state,report))
        else: audit(records,directory,report,time.monotonic()+AUDIT_SECONDS-10,checkpoint=lambda:write_json(state,report))
    except Stop as error: report['failure']=error.code; report['status']='incomplete'
    except MemoryError: report['failure']='resource_limit'; report['status']='incomplete'
    except BaseException: report['failure']='internal_error'; report['status']='incomplete'
    finally:
        signal.alarm(0)
        try: write_json(state,report)
        except Stop as error:
            report=compact_failure(report,records,error.code);write_json(state,report)
    return 0 if not report['failure'] else 1


class PhaseTimeout(Exception):
    pass


class PhaseWatchdog:
    def __init__(self,seconds):self.seconds=seconds;self.deadline=0;self.old=None
    def __enter__(self):
        if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):fail('internal_error')
        self.deadline=time.monotonic()+self.seconds;self.old=signal.getsignal(signal.SIGALRM)
        def alarm(signum,frame):raise PhaseTimeout()
        signal.signal(signal.SIGALRM,alarm)
        signal.setitimer(signal.ITIMER_REAL,self.seconds-10)
        return self
    def reserve(self):signal.setitimer(signal.ITIMER_REAL,max(0.001,self.deadline-time.monotonic()))
    def __exit__(self,*args):
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,self.old)


def process_group_exists(pid):
    try:os.killpg(pid,0);return True
    except ProcessLookupError:return False


def signal_owned(process,signum):
    try:os.killpg(process.pid,signum)
    except ProcessLookupError:
        if getattr(process,'returncode',None) is None:
            try:os.kill(process.pid,signum)
            except ProcessLookupError:pass


def stop_owned(process,deadline):
    if process is None or getattr(process,'pid',None) is None:return True
    if process.returncode is None or process_group_exists(process.pid):
        signal_owned(process,signal.SIGTERM)
        try:process.wait(timeout=max(0,min(2,deadline-time.monotonic())))
        except subprocess.TimeoutExpired:pass
    if process.returncode is None or process_group_exists(process.pid):signal_owned(process,signal.SIGKILL)
    try:process.wait(timeout=max(0,min(3,deadline-time.monotonic())))
    except subprocess.TimeoutExpired:pass
    return process.returncode is not None and not process_group_exists(process.pid)


def run_child(phase,manifest,directory,state,phase_deadline):
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
    process=None;failure=None;code=None
    try:
        # Allocate ownership before Popen can block after fork/pid assignment.
        process=subprocess.Popen.__new__(subprocess.Popen)
        subprocess.Popen.__init__(process,[sys.executable,'-I','-S',str(Path(__file__).resolve()),
            '--worker',phase,'--manifest',str(manifest),'--directory',str(directory),'--state',str(state)],
            env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            close_fds=True,start_new_session=True,cwd=directory)
        code=process.wait(timeout=max(0.001,phase_deadline-time.monotonic()-10))
    except (subprocess.TimeoutExpired,PhaseTimeout):failure='deadline'
    except BaseException:failure='worker_failed'
    finally:
        # The enclosing PhaseWatchdog owns this final absolute deadline.
        if failure:signal.setitimer(signal.ITIMER_REAL,max(0.001,phase_deadline-time.monotonic()))
        try:
            if not stop_owned(process,min(phase_deadline-5,time.monotonic()+5)):failure='resource_limit'
        except PhaseTimeout:failure='deadline'
    return code,failure


def claim_attempt():
    root=Path(__file__).resolve().parent
    path=root/'ATTEMPT.json'
    frozen=safe_json_read(root/'SOURCE_FREEZE.json',4096)
    if digest(safe_bytes_read(root/'PROTOCOL.md',64*1024))!=frozen['protocol_sha256'] or digest(safe_bytes_read(Path(__file__),2*MIB))!=frozen['helper_sha256']:
        fail('source_pin')
    with open(sys.executable,'rb') as stream:
        interpreter=hashlib.file_digest(stream,'sha256').hexdigest()
    receipt={'schema':'exact49-attempt-v1','status':'claimed','failure':None,
        'manifest_sha256':MANIFEST_SHA256,'protocol_sha256':frozen['protocol_sha256'],
        'helper_sha256':frozen['helper_sha256'],'interpreter_sha256':interpreter,
        'cleanup':'pending','owner_pid':os.getpid(),'directory_sha256':None}
    try:
        with path.open('x') as stream: json.dump(receipt,stream,sort_keys=True)
    except FileExistsError: fail('attempt_exists')
    return path,receipt


def bounded_cleanup(directory):
    # Caller keeps its parent phase watchdog armed through deletion. The directory
    # was created by this invocation and contains only its archives/state files.
    try:shutil.rmtree(directory);return not directory.exists()
    except (OSError,PhaseTimeout):return False


def prepare_final(report,records):
    report=validate_report(report,records)
    data=json.dumps(report,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()+b'\n'
    if len(data)>REPORT_CAP:
        report=validate_report(compact_failure(report,records,'fact_limit'),records)
        data=json.dumps(report,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()+b'\n'
    return report,data


def write_final(path,report,records):
    report,data=prepare_final(report,records)
    with Path(path).open('xb') as stream:stream.write(data)
    return report



def uncertain_phase_report(records,prior,phase,code):
    result=initial_report(records);result['phase']=phase;result['failure']=code
    if phase=='audit' and all(row['acquisition']=='verified' for row in prior['rows']):
        result['acquired_bytes']=sum(r['wheel']['bytes'] for r in records)
        for row in result['rows']:row['acquisition']='verified';row['audit']='unobserved_after_termination';row['failure']=code
    else:
        for row in result['rows']:row['acquisition']='unobserved_after_termination';row['failure']=code
    return result

def run_approved(manifest,output):
    records=read_manifest(manifest);report=initial_report(records)
    output=Path(output).absolute()
    if output.exists() or not output.parent.is_dir() or output.resolve()==Path(__file__).resolve().with_name('ATTEMPT.json'):fail('access_denied')
    if shutil.disk_usage(output.parent).free<300*MIB:fail('disk_limit')
    attempt_path,receipt=claim_attempt();directory=None;finished=False;creation_started=False
    try:
        for phase in ('acquisition','audit'):
            with PhaseWatchdog(ACQUIRE_SECONDS if phase=='acquisition' else AUDIT_SECONDS) as watchdog:
                try:
                    if phase=='acquisition':
                        creation_started=True
                        directory=Path(tempfile.mkdtemp(prefix='luna-exact49-owned-',dir=output.parent))
                        os.chmod(directory,0o700);state=directory/'state.json'
                        receipt['directory_sha256']=digest(str(directory.resolve()).encode());write_json(state,report)
                    receipt['status']=phase;write_json(attempt_path,receipt)
                    code,failure=run_child(phase,Path(manifest).resolve(),directory,state,watchdog.deadline)
                    report=validate_report(safe_json_read(state),records)
                    if failure or code!=0 or report['failure']:
                        report['failure']=failure or report['failure'] or ('resource_limit' if code and code<0 else 'worker_failed')
                        report['status']='incomplete';report['phase']=phase
                        for row in report['rows']:
                            key='acquisition' if phase=='acquisition' else 'audit'
                            if row[key]=='in_progress':row[key]='unobserved_after_termination';row['failure']=report['failure']
                    if phase=='acquisition' and report['failure'] is None:
                        if not all(row['acquisition']=='verified' and row['audit']=='not_attempted' for row in report['rows']):fail('report_invalid')
                        receipt['status']='acquisition_verified';write_json(attempt_path,receipt)
                        continue
                except (Stop,PhaseTimeout) as error:
                    code=error.code if isinstance(error,Stop) else 'deadline'
                    report=uncertain_phase_report(records,report,phase,code)
                except BaseException:
                    report=uncertain_phase_report(records,report,phase,'internal_error')
                finally:
                    watchdog.reserve()
                try:
                    clean=(not creation_started) if directory is None else bounded_cleanup(directory)
                    report['cleanup']='verified' if clean else 'uncertain'
                    if report['cleanup']!='verified':report['failure']='cleanup_failed';report['status']='incomplete'
                    report,data=prepare_final(report,records)
                    receipt['status']=report['status'];receipt['failure']=report['failure'];receipt['cleanup']=report['cleanup']
                    write_json(attempt_path,receipt)
                    with output.open('xb') as final_stream:final_stream.write(data)
                    finished=True
                except (PhaseTimeout,OSError,Stop):
                    # Deadline/OS failure can prevent final persistence. Existing
                    # attempt record still blocks repeat; no success is returned.
                    fail('cleanup_failed')
                break
    finally:
        if directory is not None and not finished and directory.exists():
            # Do not start an unbounded retry after a deadline. Receipt remains
            # claimed/incomplete; report cleanup uncertainty to the caller.
            pass
    return 0 if report['status'].startswith('structurally_complete') and finished else 1


def main():
    parser=argparse.ArgumentParser(description='Proposed exact49 audit; separate approval required before live execution.')
    parser.add_argument('--manifest',default=str(Path(__file__).with_name('WHEELS49.frozen.json')))
    parser.add_argument('--approved-acquire-and-audit',action='store_true',help='Execution intent only; never substitutes for user authorization')
    parser.add_argument('--output')
    parser.add_argument('--worker',choices=('acquisition','audit'),help=argparse.SUPPRESS)
    parser.add_argument('--directory',help=argparse.SUPPRESS)
    parser.add_argument('--state',help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:
        if args.worker:
            if not args.directory or not args.state: fail('access_denied')
            return worker(args.worker,args.manifest,args.directory,args.state)
        if not args.approved_acquire_and_audit or not args.output:
            print('{"status":"source_only","failure":null}'); return 0
        return run_approved(args.manifest,args.output)
    except Stop as error:
        print(json.dumps({'status':'incomplete','failure':error.code})); return 1
    except BaseException:
        print('{"status":"incomplete","failure":"internal_error"}'); return 1

if __name__=='__main__':
    sys.exit(main())
