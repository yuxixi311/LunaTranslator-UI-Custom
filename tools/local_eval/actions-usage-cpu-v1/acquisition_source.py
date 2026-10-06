"""Bounded native asset/extraction/ELF adapters behind conditional admission.

Only pure URL/tar/ELF helpers were used in synthetic preparation. No acquisition,
extraction, executable, live host probe or destination creation has run here.
"""
from hashlib import sha256
import ipaddress
import os
from pathlib import Path
import re
import socket
import ssl
import struct
import time
from urllib.parse import urljoin,urlsplit,unquote
import zlib
import cpu_harness as h
from guarded_runtime import require_activation


POLICY = {'initial_urls':[asset[0] for asset in h.ASSETS],
    'redirect_hosts':{'0':'cas-bridge.xethub.hf.co','1':'release-assets.githubusercontent.com'},
    'additional_model_redirect_host':'us.aws.cdn.hf.co',
    'runtime_header_field_line_bytes':16384,
    'https_port':443,'redirects_per_asset':3,'total_exchanges':8,'url_bytes':2048,
    'path':'nonempty_absolute_no_encoded_separator_or_dot_segments',
    'query':'opaque_provider_issued_unchanged_never_logged','credentials':False,'proxies':False}


def safe_path(path):
    for _ in range(4):
        h.require(not re.search(r'%2f|%5c',path,re.I) and '\\' not in path and
                  not any(p in ('.','..') for p in path.split('/')),'encoded path traversal/separator')
        decoded=unquote(path,errors='strict')
        if decoded==path:return
        path=decoded
    raise h.TerminalFailure('ambiguous repeated path encoding')


def validate_url(index,url,*,initial=False):
    h.require(type(index) is int and index in (0,1) and type(url) is str,'asset URL types')
    h.require(len(url.encode('utf-8'))<=2048 and url.isascii() and
              not re.search(r'[\x00-\x20\x7f\\]',url) and '#' not in url,'asset URL control/length/fragment')
    parsed=urlsplit(url)
    try:port=parsed.port
    except ValueError as exc:raise h.TerminalFailure('asset port') from exc
    h.require(parsed.scheme=='https' and port in (None,443) and parsed.username is None and
              parsed.password is None and not parsed.fragment,'asset URL scheme/authority')
    if initial:
        h.require(url==h.ASSETS[index][0],'initial pinned asset URL')
    else:
        h.require((parsed.hostname==POLICY['redirect_hosts'][str(index)] or
                   (index==0 and parsed.hostname==POLICY['additional_model_redirect_host'])) and
                  parsed.netloc in (parsed.hostname,parsed.hostname+':443'),'exact asset CDN host')
        path=parsed.path
        h.require(path.startswith('/') and len(path)>1,'absolute nonempty provider path')
        safe_path(path)
    return parsed


def redirect(index,previous,location):
    validate_url(index,previous,initial=previous==h.ASSETS[index][0])
    h.require(type(location) is str and location and location.isascii() and len(location)<=2048 and
              not re.search(r'[\x00-\x20\x7f\\]',location) and '#' not in location,'raw Location control/fragment')
    # urljoin strips controls and normalizes dot segments: reject them BEFORE it.
    raw=urlsplit(location);safe_path(raw.path)
    h.require(raw.username is None and raw.password is None and raw.scheme in ('','https'),'raw Location authority')
    url=urljoin(previous,location)
    if '?' in location:
        url=url.split('?',1)[0]+'?'+location.split('?',1)[1]
    validate_url(index,url)
    return url


def response_headers(reader,deadline,*,asset_index=0):
    h.require(type(asset_index) is int and asset_index in (0,1),'asset URL types')
    field_line_limit=POLICY['runtime_header_field_line_bytes'] if asset_index==1 else 2048
    wire=h.BoundedWire(reader,deadline)
    status=wire.line(2048)
    h.require(re.fullmatch(rb'HTTP/1\.[01] [0-9]{3}(?: [\x20-\x7e]*)?',status),'asset status line')
    headers={};fields=0
    while True:
        line=wire.line(field_line_limit)
        if not line:break
        fields+=1
        h.require(fields<=64 and b':' in line and not line.startswith((b' ',b'\t')),'asset header fields')
        key,value=line.split(b':',1);key=key.lower()
        h.require(re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+",key) and key not in headers and
                  not re.search(rb'[\x00-\x08\x0a-\x1f\x7f]',value),'asset header syntax/duplicates')
        headers[key]=value.strip(b' \t')
    return int(status.split()[1]),headers


def stream_pinned(reader,headers,size,pin,deadline,write,trace=None):
    h.require(headers.get(b'content-encoding',b'identity').lower()==b'identity' and
              b'transfer-encoding' not in headers and headers.get(b'content-length')==str(size).encode(),
              'asset encoding/framing/exact size')
    if trace:trace.enter('ASSET_BODY')
    remaining=size;hasher=sha256()
    while remaining:
        chunk=reader.read(min(65536,remaining),deadline.remaining())
        if trace and type(chunk) is bytes:trace.received(len(chunk))
        deadline.remaining()
        h.require(type(chunk) is bytes and 0<len(chunk)<=min(65536,remaining),'asset stream length')
        hasher.update(chunk);write(chunk);remaining-=len(chunk)
    h.require(hasher.hexdigest()==pin,'asset hash mismatch')
    deadline.remaining()


class NativeReader:
    def __init__(self,connection):self.connection=connection
    def read(self,n,remaining):
        require_activation();self.connection.settimeout(remaining);return self.connection.recv(n)
    def close(self):
        require_activation();self.connection.close()


def native_get(index,url,deadline,trace=None):
    require_activation()
    parsed=validate_url(index,url,initial=url==h.ASSETS[index][0])
    # The owning parent worker watchdog independently bounds DNS and TLS stalls.
    if trace:trace.enter('ASSET_DNS')
    addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    deadline.remaining()
    h.require(addresses and all(ipaddress.ip_address(row[4][0]).is_global for row in addresses),
              'nonpublic/unknown asset address')
    family,kind,proto,_,address=addresses[0]  # No alternate-address retry.
    connection=socket.socket(family,kind,proto)
    try:
        if trace:trace.enter('ASSET_CONNECT')
        connection.settimeout(deadline.remaining());connection.connect(address)
        if trace:trace.enter('ASSET_TLS')
        context=ssl.create_default_context()
        connection=context.wrap_socket(connection,server_hostname=parsed.hostname)
        connection.settimeout(deadline.remaining())
        target=parsed.path+('?' + parsed.query if '?' in url else '')
        request=(f'GET {target} HTTP/1.1\r\nHost: {parsed.hostname}\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii')
        h.require(len(request)<=8192,'asset request-header cap')
        if trace:trace.enter('ASSET_SEND')
        view=memoryview(request)
        while view:
            connection.settimeout(deadline.remaining());n=connection.send(view[:8192])
            h.require(n>0,'asset send failure');view=view[n:]
        return NativeReader(connection)
    except BaseException as exc:
        if trace:trace.fail(exc)
        try:connection.close()
        except BaseException:
            if trace:trace.cleanup_issue('ASSET_CLOSE_FAILED')
            raise
        raise


def acquire_assets(staging,deadline,event,trace=None):
    """Exactly two source-pinned asset attempts; every failed partial is kept."""
    require_activation()
    staging=Path(staging);exchanges=0;receipts=[]
    if trace:trace.start_assets()
    def record(item):
        if trace:trace.asset_event(item)
        try:event(item)
        except BaseException as exc:
            if trace:trace.fail(exc,stage='WORKER_JOURNAL')
            raise
    for index,(initial,size,pin) in enumerate(h.ASSETS):
        record(dict(event='asset_attempt',asset=index,attempt=1))
        path=staging/('model.gguf' if index==0 else 'runtime.tar.gz')
        if trace:trace.enter('ASSET_OPEN')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        reader=None
        try:
            url=initial
            for hop in range(4):
                deadline.remaining();exchanges+=1;h.require(exchanges<=8,'asset exchange cap')
                record(dict(event='asset_exchange_intent',asset=index,exchange=exchanges,hop=hop))
                reader=native_get(index,url,deadline,trace) if trace else native_get(index,url,deadline)
                if trace:trace.enter('ASSET_HEADERS')
                status,headers=response_headers(reader,deadline,asset_index=index)
                if status in (301,302,303,307,308):
                    h.require(hop<3 and b'location' in headers,'asset redirect cap/location')
                    location=headers[b'location'].decode('ascii')
                    next_url=redirect(index,url,location)
                    reader.close();reader=None;url=next_url
                    continue  # Redirect/error bodies are never read.
                h.require(status==200,'asset response must be 200')
                def write(data):
                    view=memoryview(data)
                    while view:
                        deadline.remaining();n=os.write(fd,view);h.require(n>0,'asset file write')
                        if trace:trace.written(n)
                        view=view[n:]
                stream_pinned(reader,headers,size,pin,deadline,write,trace)
                if trace:trace.enter('ASSET_SYNC')
                os.fsync(fd)
                receipts.append(dict(asset=index,path=str(path),bytes=size,sha256=pin,verified=True))
                record(dict(event='asset_verified',asset=index,bytes=size,sha256=pin))
                break
            else:raise h.TerminalFailure('asset redirect exhaustion')
        except BaseException as exc:
            if trace:trace.fail(exc)
            raise
        finally:
            if trace:trace.enter('ASSET_CLOSE')
            try:
                if reader is not None:reader.close()
            except BaseException as exc:
                if trace:trace.fail(exc,stage='ASSET_CLOSE');trace.cleanup_issue('ASSET_CLOSE_FAILED')
                raise
            finally:
                try:os.close(fd)
                except BaseException as exc:
                    if trace:trace.fail(exc,stage='ASSET_CLOSE');trace.cleanup_issue('ASSET_CLOSE_FAILED')
                    raise
    h.require(len(receipts)==2,'asset attempt completeness')
    if trace:trace.enter('ASSET_COMPLETE')
    return dict(assets=receipts,exchanges=exchanges,payload_bytes=sum(x['bytes'] for x in receipts))


class GzipChunks:
    """Bound gzip output before buffering; reject concatenated/extra streams."""
    def __init__(self,source,deadline):
        self.source,self.deadline=source,deadline
        self.decoder=zlib.decompressobj(31);self.pending=b'';self.buffer=b'';self.total=0;self.ended=False
    def read(self,n):
        h.require(0<n<=65536,'decompression read cap')
        while len(self.buffer)<n and not self.ended:
            self.deadline.remaining()
            if not self.pending:
                self.pending=self.source.read(65536)
                h.require(self.pending or self.decoder.eof,'truncated gzip')
            chunk=self.decoder.decompress(self.pending,65536)
            self.pending=self.decoder.unconsumed_tail
            self.total+=len(chunk);h.require(self.total<=512*h.MIB+2*h.MIB,'total tar expansion cap')
            self.buffer+=chunk
            if self.decoder.eof:
                h.require(not self.decoder.unused_data and not self.pending and not self.source.read(1),
                          'additional gzip/asset data')
                self.ended=True
        result=self.buffer[:n];self.buffer=self.buffer[n:];return result


def exact_tar(stream,n):
    parts=[]
    while n:
        part=stream.read(min(n,65536));h.require(part,'truncated tar');parts.append(part);n-=len(part)
    return b''.join(parts)


def tar_members(stream,consume):
    """Bounded ordinary ustar subset; unsupported extended metadata stops."""
    members=[];expanded=0;seen=set();framing=0
    def framing_bytes(n):
        nonlocal framing
        h.require(framing+n<=2*h.MIB,'separate tar framing cap')
        framing+=n;return exact_tar(stream,n)
    while True:
        header=framing_bytes(512)
        if header==b'\0'*512:
            h.require(framing_bytes(512)==b'\0'*512,'tar end marker')
            while True:
                trailing=stream.read(min(65536,max(1,2*h.MIB-framing)))
                if not trailing:break
                h.require(framing+len(trailing)<=2*h.MIB,'separate tar framing cap')
                framing+=len(trailing)
                h.require(not trailing.strip(b'\0'),'nonzero tar trailing data')
            return members
        h.require(len(members)<1024,'tar member count')
        checksum=int(header[148:156].strip(b'\0 ') or b'0',8)
        h.require(checksum==sum(header[:148])+8*32+sum(header[156:]),'tar checksum')
        field=lambda a,b:header[a:b].split(b'\0',1)[0].decode('utf-8','strict')
        magic=header[257:263]
        h.require(magic in (b'ustar\0',b'ustar '),'unsupported tar header dialect')
        name,prefix=field(0,100),field(345,500) if magic==b'ustar\0' else ''
        if prefix:name=prefix+'/'+name
        name=name.rstrip('/')
        h.require(name not in seen and name and not name.startswith('/') and '\\' not in name and
                  not re.search(r'[\x00-\x1f\x7f]',name) and
                  all(p not in ('','.','..') for p in name.split('/')),'tar path/duplicate')
        seen.add(name)
        size_raw=header[124:136].strip(b'\0 ')
        h.require(re.fullmatch(rb'[0-7]+',size_raw),'tar size form')
        size=int(size_raw,8);flag=header[156:157]
        h.require(flag in (b'0',b'\0',b'5',b'2'),'unsupported tar type/extended metadata')
        kind='file' if flag in (b'0',b'\0') else ('directory' if flag==b'5' else 'symlink')
        h.require(kind=='file' or size==0,'nonregular tar payload')
        if kind=='file':expanded+=size
        h.require(expanded<=512*h.MIB,'expanded regular-file cap')
        member=dict(name=name,type=kind,size=size)
        if kind=='symlink':member['target']=field(157,257)
        hasher=sha256();remaining=size
        def chunks():
            nonlocal remaining
            while remaining:
                block=exact_tar(stream,min(remaining,65536));hasher.update(block);remaining-=len(block);yield block
        consume(member,chunks())
        h.require(remaining==0,'extractor did not consume regular file')
        if kind=='file':member['sha256']=hasher.hexdigest()
        padding=(-size)%512
        if padding:h.require(framing_bytes(padding)==b'\0'*padding,'tar nonzero padding')
        members.append(member)


def extract_archive(archive,root,deadline):
    require_activation()
    root=Path(root);os.mkdir(root,0o700)
    def consume(member,chunks):
        deadline.remaining();path=root/member['name']
        if member['type']=='symlink':return  # All symlink creation deferred.
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        h.require(not any(p.is_symlink() for p in path.parents if p!=root.parent),'symlink extraction parent')
        if member['type']=='directory':path.mkdir(mode=0o700,exist_ok=True);return
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            for data in chunks:
                view=memoryview(data)
                while view:
                    deadline.remaining();n=os.write(fd,view);h.require(n>0,'extraction write');view=view[n:]
            os.fsync(fd)
        finally:os.close(fd)
    with open(archive,'rb') as source:
        members=tar_members(GzipChunks(source,deadline),consume)
    h.validate_archive_members(members)
    for member in members:
        if member['type']=='symlink':os.symlink(member['target'],root/member['name'])
    deadline.remaining()
    return members


def elf_dependencies(read_at,size):
    """Pure bounded ELF64/x86-64 dynamic-name inspection, never ldd/execution."""
    header=read_at(0,64)
    h.require(len(header)==64 and header[:7]==b'\x7fELF\x02\x01\x01','ELF64 little-endian required')
    fields=struct.unpack('<HHIQQQIHHHHHH',header[16:64])
    typ,machine,_,_,phoff,_,_,_,phsize,phnum,*_=fields
    h.require(typ in (2,3) and machine==62 and phsize==56 and 0<phnum<=1024 and phoff+phnum*56<=size,'ELF program table')
    programs=[struct.unpack('<IIQQQQQQ',read_at(phoff+i*56,56)) for i in range(phnum)]
    loads=[p for p in programs if p[0]==1];dynamic=[p for p in programs if p[0]==2]
    h.require(len(dynamic)<=1,'ELF dynamic sections')
    interpreter=None
    for p in programs:
        h.require(p[2]+p[5]<=size,'ELF segment bound')
        if p[0]==3:
            h.require(interpreter is None and 0<p[5]<=4096,'ELF interpreter cap')
            interpreter=read_at(p[2],p[5]).rstrip(b'\0').decode('ascii')
    if not dynamic:return dict(needed=[],interpreter=interpreter,rpath=None,runpath=None)
    segment=dynamic[0];h.require(segment[5]<=65536 and segment[5]%16==0,'ELF dynamic cap')
    entries=[]
    for offset in range(segment[2],segment[2]+segment[5],16):
        tag,value=struct.unpack('<qQ',read_at(offset,16))
        if tag==0:break
        entries.append((tag,value))
    else:raise h.TerminalFailure('unterminated ELF dynamic table')
    pointers=[v for t,v in entries if t==5];sizes=[v for t,v in entries if t==10]
    h.require(len(pointers)==len(sizes)==1 and 0<sizes[0]<=h.MIB,'ELF string table')
    address,length=pointers[0],sizes[0]
    matching=[p for p in loads if p[3]<=address and address+length<=p[3]+p[5]]
    h.require(len(matching)==1,'ELF string mapping')
    p=matching[0];strings=read_at(p[2]+address-p[3],length)
    def value(offset):
        h.require(offset<len(strings),'ELF string offset');tail=strings[offset:offset+4096]
        h.require(b'\0' in tail,'ELF unterminated string');return tail.split(b'\0',1)[0].decode('ascii')
    needed=[value(v) for t,v in entries if t==1]
    h.require(len(needed)<=128 and all('/' not in name and name for name in needed),'ELF needed names')
    result=dict(needed=needed,interpreter=interpreter,rpath=None,runpath=None)
    for tag,key in ((15,'rpath'),(29,'runpath')):
        values=[value(v) for t,v in entries if t==tag];h.require(len(values)<=1,'duplicate ELF search field')
        if values:result[key]=values[0]
    return result


def inspect_elf(path,deadline):
    require_activation()
    with open(path,'rb') as source:
        size=os.fstat(source.fileno()).st_size
        def read_at(offset,n):
            deadline.remaining();h.require(0<=offset and 0<n<=h.MIB and offset+n<=size,'ELF bounded read')
            source.seek(offset);data=source.read(n);h.require(len(data)==n,'ELF short read');return data
        return elf_dependencies(read_at,size)
