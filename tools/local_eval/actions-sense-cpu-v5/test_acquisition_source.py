"""Pure synthetic URL/framing/gzip/tar/ELF tests; no files or live transport."""
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import tarfile
import unittest
from unittest.mock import patch
import acquisition_source as a
import cpu_harness as h
import diagnostics as d
from test_cpu_harness import Clock,Reader,response
from test_guarded_adapters import doubles


class ExactModelCdnCompatibilityTests(unittest.TestCase):
    NEW='us.aws.cdn.hf.co'
    OLD='cas-bridge.xethub.hf.co'
    def test_only_named_addition_and_commitment_changed(self):
        prior=dict(a.POLICY);self.assertEqual(prior.pop('additional_model_redirect_host'),self.NEW)
        self.assertEqual(prior.pop('runtime_header_field_line_bytes'),16384)
        self.assertEqual(h.digest(h.canonical(prior)),'e25f05b118991409636e9a7f769abbded2a4546224b713e1dc3c99a311c31ed2')
        metadata=json.loads((Path(__file__).parent/'INPUT_COMMITMENTS.json').read_bytes())
        self.assertEqual(metadata['commitments']['redirect_policy'],h.digest(h.canonical(a.POLICY)))
        self.assertEqual(a.POLICY['redirect_hosts']['1'],'release-assets.githubusercontent.com')
    def test_exact_new_model_host_with_canonical443_is_accepted(self):
        for authority in (self.NEW,self.NEW+':443'):
            url='https://'+authority+'/object?sig=opaque%2Fvalue%3D&x=1'
            self.assertEqual(a.redirect(0,h.ASSETS[0][0],url),url)
    def test_other_hosts_subdomains_case_userinfo_ports_and_fragments_rejected(self):
        urls=['https://us.gcp.cdn.hf.co/object','https://cdn-lfs-us-1.hf.co/object',
            'https://prefix.'+self.NEW+'/object','https://'+self.NEW+'.invalid/object',
            'https://'+self.NEW.upper()+'/object','https://'+self.NEW+'./object',
            'https://user@'+self.NEW+'/object','https://user:secret@'+self.NEW+'/object',
            'https://'+self.NEW+':80/object','https://'+self.NEW+':0443/object',
            'http://'+self.NEW+'/object','https://'+self.NEW+'/object#secret',
            'https://'+self.NEW+'/object?sig=bad\tvalue']
        for url in urls:
            with self.subTest(url=url),self.assertRaises(h.TerminalFailure):a.redirect(0,h.ASSETS[0][0],url)
    def test_path_rules_match_existing_model_host(self):
        for suffix in ('/object','/a/b','/object?sig=a%2Fb+%2Bc','/object?'):
            values=[a.redirect(0,h.ASSETS[0][0],'https://'+host+suffix) for host in (self.OLD,self.NEW)]
            self.assertEqual(values[1],values[0].replace(self.OLD,self.NEW))
        for suffix in ('/','', '/../object','/a/../object','/a/%2e%2e/object','/a%2fb',
                       '/a%5cb','/a\\b','/object#','/object?sig=a\r\nb'):
            for host in (self.OLD,self.NEW):
                with self.subTest(host=host,suffix=suffix),self.assertRaises(h.TerminalFailure):
                    a.redirect(0,h.ASSETS[0][0],'https://'+host+suffix)
    def test_runtime_asset_never_accepts_either_model_host(self):
        for host in (self.OLD,self.NEW):
            with self.assertRaises(h.TerminalFailure):a.redirect(1,h.ASSETS[1][0],'https://'+host+'/object')
        runtime='https://release-assets.githubusercontent.com/object?sig=opaque'
        self.assertEqual(a.redirect(1,h.ASSETS[1][0],runtime),runtime)
        with self.assertRaises(h.TerminalFailure):a.redirect(0,h.ASSETS[0][0],runtime)
    def test_opaque_query_is_preserved_without_repair_or_signature_claim(self):
        previous='https://'+self.NEW+'/base/object?old=opaque'
        for location in ('next?sig=a%2Fb+%2Bc&x=%23&x=2','next?','next?sig=changed-unverified'):
            self.assertEqual(a.redirect(0,previous,location),'https://'+self.NEW+'/base/'+location)
        with self.assertRaises(h.TerminalFailure):a.redirect(0,previous,'next?sig=value#fragment')
    def test_mutated_policy_plan_rejected(self):
        from copy import deepcopy
        from test_final_kit import kit_plan
        import final_coordinator as coordinator
        plan=kit_plan()
        for mutated in ('us.gcp.cdn.hf.co','*.hf.co','us.aws.cdn.hf.co.invalid'):
            bad=deepcopy(plan);bad['redirect_policy']['additional_model_redirect_host']=mutated
            with self.assertRaises(h.TerminalFailure):coordinator.validate_kit_plan(bad,'1'*64)
    def fake_new_host(self,mode):
        clock=Clock();events=[];calls=[];files={};fd_iter=iter(range(10,20));closed=[]
        assets=tuple((old[0],len(body),sha256(body).hexdigest()) for old,body in zip(h.ASSETS,(b'ab',b'xyz')))
        def opened(path,*args):
            fd=next(fd_iter);files[fd]=bytearray();return fd
        def written(fd,data):files[fd].extend(data);return len(data)
        def get(index,url,deadline):
            calls.append((index,url));hop=sum(i==index for i,_ in calls)-1
            if index==0 and (hop==0 or mode=='redirect_exhaustion'):
                raw=response(b'never-read',[(b'Location',('https://'+self.NEW+'/object?sig=opaque-secret').encode())],'302 Found')
            else:raw=response(b'zz' if mode=='tampered' and index==0 else b'ab' if index==0 else b'xyz')
            return Reader(raw)
        with doubles(clock),patch.object(a,'require_activation',lambda:None),patch.object(h,'ASSETS',assets),\
             patch.object(a,'native_get',get),patch.object(a.os,'open',opened),patch.object(a.os,'write',written),\
             patch.object(a.os,'fsync',lambda _:None),patch.object(a.os,'close',closed.append):
            if mode=='valid':result=a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
            else:
                with self.assertRaises(h.TerminalFailure):a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
                result=None
        self.assertNotIn('opaque-secret',h.canonical(events).decode())
        return result,events,calls,files,closed
    def test_new_host_verified_body_keeps_fixed_acquisition_accounting(self):
        result,events,calls,files,closed=self.fake_new_host('valid')
        self.assertEqual(result['exchanges'],3);self.assertEqual(result['payload_bytes'],5)
        self.assertEqual([i for i,_ in calls],[0,0,1]);self.assertEqual(closed,[10,11])
    def test_new_host_tampered_body_still_stops_before_second_asset(self):
        result,events,calls,files,closed=self.fake_new_host('tampered')
        self.assertEqual([i for i,_ in calls],[0,0]);self.assertEqual(list(files.values()),[bytearray(b'zz')]);self.assertEqual(closed,[10])
        self.assertFalse(any(e['event']=='asset_verified' for e in events))
    def test_new_host_does_not_expand_redirect_budget_or_retry(self):
        result,events,calls,files,closed=self.fake_new_host('redirect_exhaustion')
        self.assertEqual(len(calls),4);self.assertEqual({i for i,_ in calls},{0});self.assertEqual(closed,[10])


class RuntimeHeaderFieldCompatibilityTests(unittest.TestCase):
    STATUS=b'HTTP/1.1 200 OK\r\n'
    def field(self,length,key=b'X-Fictional'):
        prefix=key+b': ';self.assertGreaterEqual(length,len(prefix)+2)
        return prefix+b'x'*(length-len(prefix)-2)+b'\r\n'
    def parse(self,raw,index=1):
        reader=Reader(raw);value=a.response_headers(reader,h.Deadline(Clock(),600),asset_index=index)
        return value,reader
    def test_policy_is_only_runtime_field_line_exception(self):
        prior=dict(a.POLICY);self.assertEqual(prior.pop('runtime_header_field_line_bytes'),16384)
        self.assertEqual(h.digest(h.canonical(prior)),'62c151b131858875a577551dc12b7a97be275451335e128a38425d38b483cf0d')
        self.assertEqual(h.LIMITS['header_line'],2048);self.assertEqual(h.LIMITS['response_headers'],16384)
        self.assertEqual(h.LIMITS['header_fields'],64);self.assertEqual(a.POLICY['url_bytes'],2048)
    def test_model_field_line_boundary_is_unchanged(self):
        (status,_),reader=self.parse(self.STATUS+self.field(2048)+b'\r\n',0);self.assertEqual(status,200)
        for index in (0,):
            with self.assertRaisesRegex(h.TerminalFailure,'HTTP line cap'):self.parse(self.STATUS+self.field(2049)+b'\r\n',index)
        with self.assertRaisesRegex(h.TerminalFailure,'HTTP line cap'):
            a.response_headers(Reader(self.STATUS+self.field(2049)+b'\r\n'),h.Deadline(Clock(),600))
    def test_runtime_long_field_is_accepted_without_reading_body(self):
        head=self.STATUS+self.field(4096)+b'\r\n';(status,headers),reader=self.parse(head+b'CANARY-BODY')
        self.assertEqual(status,200);self.assertIn(b'x-fictional',headers);self.assertEqual(reader.position,len(head))
        self.assertEqual(reader.raw[reader.position:],b'CANARY-BODY')
    def test_status_line_stays2048_for_both_assets(self):
        prefix=b'HTTP/1.1 200 '
        for index in (0,1):
            raw=prefix+b'x'*(2048-len(prefix)-2)+b'\r\n\r\n'
            self.assertEqual(self.parse(raw,index)[0][0],200)
            with self.assertRaisesRegex(h.TerminalFailure,'HTTP line cap'):
                self.parse(prefix+b'x'*(2049-len(prefix)-2)+b'\r\n\r\n',index)
    def test_total_header_boundary_exact16384_and_one_over(self):
        length=16384-len(self.STATUS)-2;head=self.STATUS+self.field(length)+b'\r\n'
        self.assertEqual(len(head),16384);self.assertEqual(self.parse(head)[1].position,16384)
        with self.assertRaisesRegex(h.TerminalFailure,'header block cap'):
            self.parse(self.STATUS+self.field(length+1)+b'\r\n')
    def test_two_long_fields_still_share_total_block_cap(self):
        head=self.STATUS+self.field(8000,b'X-A')+self.field(8000,b'X-B')+b'\r\n'
        self.assertEqual(len(self.parse(head)[0][1]),2)
        with self.assertRaisesRegex(h.TerminalFailure,'header block cap'):
            self.parse(head[:-2]+self.field(500,b'X-C')+b'\r\n')
    def test_64field_limit_is_not_relaxed(self):
        fields=b''.join(('X-%d: a\r\n'%i).encode() for i in range(64))
        self.assertEqual(len(self.parse(self.STATUS+fields+b'\r\n')[0][1]),64)
        with self.assertRaisesRegex(h.TerminalFailure,'asset header fields'):
            self.parse(self.STATUS+fields+b'X-64: a\r\n\r\n')
    def test_malformed_crlf_duplicates_controls_and_folded_fields_still_reject(self):
        prefix=self.STATUS+self.field(3000)
        cases=[b'Bad: value\n\n',b'X-A: a\r\nx-a: b\r\n\r\n',b'Bad Name: a\r\n\r\n',
            b'Bad: a\0b\r\n\r\n',b'Bad: a\rb\r\n\r\n',b' folded\r\n\r\n',b'\tfolded\r\n\r\n']
        for tail in cases:
            with self.subTest(tail=tail),self.assertRaises(h.TerminalFailure):self.parse(prefix+tail)
    def test_url_location_bound_remains2048_despite_field_framing_room(self):
        prefix='https://release-assets.githubusercontent.com/object?signature='
        for length,accepted in ((2048,True),(2049,False)):
            location=prefix+'a'*(length-len(prefix));raw=b'HTTP/1.1 302 Found\r\nLocation: '+location.encode()+b'\r\n\r\n'
            (status,headers),reader=self.parse(raw);self.assertEqual(status,302)
            if accepted:self.assertEqual(a.redirect(1,h.ASSETS[1][0],headers[b'location'].decode()),location)
            else:
                with self.assertRaises(h.TerminalFailure):a.redirect(1,h.ASSETS[1][0],headers[b'location'].decode())
    def test_invalid_asset_selector_rejects_before_any_read(self):
        for index in (True,-1,2,'1',None):
            reader=Reader(self.STATUS+b'\r\n')
            with self.assertRaises(h.TerminalFailure):a.response_headers(reader,h.Deadline(Clock(),600),asset_index=index)
            self.assertEqual(reader.position,0)
    def test_finite_failure_diagnostic_never_exports_long_header_or_signature(self):
        raw=self.STATUS+b'X-Fictional: CANARY signature=private'+b'x'*17000+b'\r\n\r\n'
        trace=d.Trace('1'*64,role='acquire');trace.enter('ASSET_HEADERS')
        try:self.parse(raw)
        except h.TerminalFailure as exc:trace.fail(exc)
        self.assertEqual(trace.worker_snapshot()['first_failure']['code'],'HTTP_HEADER_BLOCK_LIMIT')
        public=d.worker_line(trace);self.assertNotIn(b'CANARY',public);self.assertNotIn(b'signature',public)
    def test_deadline_after_long_field_progress_is_still_terminal(self):
        clock=Clock();reader=Reader(self.STATUS+self.field(4096)+b'\r\n');original=reader.read
        def delayed(n,remaining):
            value=original(n,remaining)
            if reader.position==2050:clock.advance(601)
            return value
        reader.read=delayed
        with self.assertRaisesRegex(h.TerminalFailure,'absolute deadline expired'):
            a.response_headers(reader,h.Deadline(clock,600),asset_index=1)
        self.assertEqual(reader.position,2050)
    def fake_acquisition(self,long_asset):
        clock=Clock();calls=[];events=[];files={};fds=iter((10,11))
        assets=tuple((old[0],len(body),sha256(body).hexdigest()) for old,body in zip(h.ASSETS,(b'ab',b'xyz')))
        def opened(*args):
            fd=next(fds);files[fd]=bytearray();return fd
        def written(fd,data):files[fd].extend(data);return len(data)
        def get(index,url,deadline):
            calls.append(index);body=(b'ab',b'xyz')[index]
            headers=[(b'Content-Length',str(len(body)).encode())]
            if index==long_asset:headers.append((b'X-Fictional',b'x'*3000))
            return Reader(response(body,headers))
        with doubles(clock),patch.object(a,'require_activation',lambda:None),patch.object(h,'ASSETS',assets),\
             patch.object(a,'native_get',get),patch.object(a.os,'open',opened),patch.object(a.os,'write',written),\
             patch.object(a.os,'fsync',lambda _:None),patch.object(a.os,'close',lambda _:None):
            if long_asset==1:result=a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
            else:
                with self.assertRaisesRegex(h.TerminalFailure,'HTTP line cap'):
                    a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
                result=None
        return result,calls,files
    def test_only_fixed_runtime_asset_selects_the_larger_field_bound(self):
        result,calls,files=self.fake_acquisition(1);self.assertEqual(calls,[0,1]);self.assertEqual(result['exchanges'],2)
        self.assertEqual(result['payload_bytes'],5);self.assertEqual(list(files.values()),[bytearray(b'ab'),bytearray(b'xyz')])
        result,calls,files=self.fake_acquisition(0);self.assertEqual(calls,[0]);self.assertEqual(list(files.values()),[bytearray()])


class AcquisitionSourceTests(unittest.TestCase):
    def fake_acquire(self,mode):
        clock=Clock();events=[];calls=[];files={};next_fd=iter(range(10,20));readers=[]
        assets=tuple((item[0],len(data),sha256(data).hexdigest()) for item,data in zip(h.ASSETS,(b'ab',b'xyz')))
        def opened(path,flags,permissions):
            fd=next(next_fd);files[fd]=bytearray();return fd
        def written(fd,data):files[fd].extend(data);return len(data)
        def get(index,url,deadline):
            self.assertEqual(events[-1]['event'],'asset_exchange_intent')
            calls.append((index,url));hop=sum(i==index for i,_ in calls)-1
            if mode=='redirect_overflow' or (mode=='maximum' and hop<3):
                location=('https://'+a.POLICY['redirect_hosts'][str(index)]+'/object?sig=opaque-secret').encode()
                raw=response(b'never-read',[(b'Location',location)],'302 Found')
            else:
                raw=response(b'ab' if index==0 else b'xyz')
                if mode=='bad_hash' and index==0:raw=response(b'zz')
            reader=Reader(raw);readers.append(reader);return reader
        with doubles(clock),patch.object(a,'require_activation',lambda:None),patch.object(h,'ASSETS',assets),\
             patch.object(a,'native_get',get),patch.object(a.os,'open',opened),patch.object(a.os,'write',written),\
             patch.object(a.os,'fsync',lambda _:None),patch.object(a.os,'close',lambda _:None):
            if mode=='maximum':result=a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
            else:
                with self.assertRaises(h.TerminalFailure):a.acquire_assets('/fake',h.Deadline(clock,600),events.append)
                result=None
        return result,events,calls,files,readers
    def test_exact_two_attempts_and_eight_exchange_maximum(self):
        result,events,calls,files,readers=self.fake_acquire('maximum')
        self.assertEqual(len(calls),8);self.assertEqual(result['payload_bytes'],5)
        self.assertEqual(sum(e['event']=='asset_attempt' for e in events),2)
        self.assertNotIn('opaque-secret',h.canonical(events).decode())
        self.assertTrue(all(r.closed for r in readers))
    def test_fourth_redirect_stops_without_second_asset_or_retry(self):
        result,events,calls,files,readers=self.fake_acquire('redirect_overflow')
        self.assertEqual(len(calls),4);self.assertEqual({i for i,_ in calls},{0})
        self.assertTrue(all(r.closed for r in readers))
    def test_bad_hash_keeps_partial_bytes_and_stops_route(self):
        result,events,calls,files,readers=self.fake_acquire('bad_hash')
        self.assertEqual(len(calls),1);self.assertEqual(list(files.values()),[bytearray(b'zz')])
    def test_only_exact_asset_hosts_and_opaque_query(self):
        url='https://cas-bridge.xethub.hf.co/cas/object?signature=a%2Fb%2Bc'
        self.assertEqual(a.redirect(0,h.ASSETS[0][0],url),url)
        for invalid in ('https://evil.example/object','https://release-assets.githubusercontent.com/object',
                        'http://cas-bridge.xethub.hf.co/object','https://cas-bridge.xethub.hf.co/a/%2e%2e/b',
                        'https://cas-bridge.xethub.hf.co/a%2fb','https://user@cas-bridge.xethub.hf.co/a',
                        'https://cas-bridge.xethub.hf.co/a#x','https://cas-bridge.xethub.hf.co/a\\b'):
            with self.subTest(invalid=invalid),self.assertRaises(h.TerminalFailure):a.validate_url(0,invalid)
    def test_initial_urls_exact_and_no_invented_cdn(self):
        for index,asset in enumerate(h.ASSETS):a.validate_url(index,asset[0],initial=True)
        with self.assertRaises(h.TerminalFailure):a.validate_url(0,h.ASSETS[0][0]+'?probe=1',initial=True)
    def test_raw_location_rejected_before_lossy_join(self):
        previous='https://cas-bridge.xethub.hf.co/base/object?old=token'
        for location in ('next?sig=a\tb','a/../next?sig=x','../next','./next','next#',
                         'https://cas-bridge.xethub.hf.co/a/../next?sig=x',
                         'https://cas-bridge.xethub.hf.co/next#'):
            with self.subTest(location=location),self.assertRaises(h.TerminalFailure):a.redirect(0,previous,location)
    def test_relative_signed_query_is_byte_preserved(self):
        previous='https://cas-bridge.xethub.hf.co/base/object?old=token'
        self.assertEqual(a.redirect(0,previous,'next?sig=a%2Fb+%2Bc'),
                         'https://cas-bridge.xethub.hf.co/base/next?sig=a%2Fb+%2Bc')
        self.assertEqual(a.redirect(0,previous,'next?'),'https://cas-bridge.xethub.hf.co/base/next?')
    def test_tar_framing_has_independent_two_mib_cap(self):
        for size,valid in ((2*h.MIB,True),(3*h.MIB,False)):
            stream=a.GzipChunks(io.BytesIO(gzip.compress(b'\0'*size)),h.Deadline(Clock(),60))
            if valid:self.assertEqual(a.tar_members(stream,lambda m,c:list(c)),[])
            else:
                with self.assertRaises(h.TerminalFailure):a.tar_members(stream,lambda m,c:list(c))
    def test_redirect_headers_leave_body_unread(self):
        reader=Reader(response(b'not read',[(b'Location',b'https://cas-bridge.xethub.hf.co/object')],'302 Found'))
        code,headers=a.response_headers(reader,h.Deadline(Clock(),600))
        self.assertEqual(code,302);self.assertEqual(reader.raw[reader.position:],b'not read')
    def test_header_controls_cannot_disappear_during_strip(self):
        for suffix in (b'\x0b',b'\x0c'):
            raw=response(b'',[(b'Location',b'https://cas-bridge.xethub.hf.co/object'+suffix)],'302 Found')
            with self.assertRaises(h.TerminalFailure):a.response_headers(Reader(raw),h.Deadline(Clock(),600))
        raw=response(b'',[(b'Location',b'\thttps://cas-bridge.xethub.hf.co/object\t')],'302 Found')
        _,headers=a.response_headers(Reader(raw),h.Deadline(Clock(),600))
        self.assertEqual(headers[b'location'],b'https://cas-bridge.xethub.hf.co/object')
    def test_asset_stream_exact_hash_length_and_chunk_cap(self):
        data=b'x'*70000;reader=Reader(data);written=[]
        a.stream_pinned(reader,{b'content-length':b'70000'},len(data),sha256(data).hexdigest(),h.Deadline(Clock(),600),written.append)
        self.assertEqual(b''.join(written),data);self.assertLessEqual(reader.max_read,65536)
        for headers in ({b'content-length':b'69999'}, {b'content-length':b'70000',b'transfer-encoding':b'chunked'},
                        {b'content-length':b'70000',b'content-encoding':b'gzip'}):
            with self.assertRaises(h.TerminalFailure):a.stream_pinned(Reader(data),headers,len(data),sha256(data).hexdigest(),h.Deadline(Clock(),600),written.append)
    def test_native_acquisition_disabled(self):
        with self.assertRaises(h.Disabled):a.acquire_assets('/fake',h.Deadline(Clock(),600),lambda _:None)
        with self.assertRaises(h.Disabled):a.native_get(0,h.ASSETS[0][0],h.Deadline(Clock(),600))
    def tar(self,name='lib/test.so',kind=None):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            item=tarfile.TarInfo(name);item.size=3
            if kind:item.type=kind;item.size=0
            archive.addfile(item,io.BytesIO(b'abc') if not kind else None)
        return buffer.getvalue()
    def test_bounded_tar_gzip_preserves_hash_and_file_bytes(self):
        raw=gzip.compress(self.tar());output=[]
        members=a.tar_members(a.GzipChunks(io.BytesIO(raw),h.Deadline(Clock(),60)),
                              lambda member,chunks:output.append((member['name'],b''.join(chunks))))
        self.assertEqual(output,[('lib/test.so',b'abc')]);self.assertEqual(members[0]['sha256'],sha256(b'abc').hexdigest())
    def test_tar_unsafe_paths_and_unsupported_members(self):
        for raw in (self.tar('../escape'),self.tar('/absolute'),self.tar('link',tarfile.LNKTYPE),self.tar('device',tarfile.CHRTYPE)):
            with self.assertRaises(h.TerminalFailure):a.tar_members(io.BytesIO(raw),lambda m,c:list(c))
    def test_truncated_or_concatenated_gzip_rejected(self):
        raw=gzip.compress(self.tar())
        for bad in (raw[:-8],raw+gzip.compress(b'extra')):
            with self.assertRaises((h.TerminalFailure,EOFError)):
                a.tar_members(a.GzipChunks(io.BytesIO(bad),h.Deadline(Clock(),60)),lambda m,c:list(c))
    def test_elf_static_x64_only_and_bounds(self):
        header=b'\x7fELF\x02\x01\x01'+b'\0'*9+struct.pack('<HHIQQQIHHHHHH',2,62,1,0,64,0,0,64,56,1,0,0,0)
        program=struct.pack('<IIQQQQQQ',1,5,0,0,0,120,120,4096);blob=header+program
        self.assertEqual(a.elf_dependencies(lambda off,n:blob[off:off+n],len(blob))['needed'],[])
        for bad in (b'not ELF',blob[:64],blob[:18]+struct.pack('<H',183)+blob[20:]):
            with self.assertRaises(h.TerminalFailure):a.elf_dependencies(lambda off,n:bad[off:off+n],len(bad))


if __name__=='__main__':unittest.main()
