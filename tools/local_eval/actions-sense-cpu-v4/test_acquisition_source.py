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
from test_cpu_harness import Clock,Reader,response
from test_guarded_adapters import doubles


class ExactModelCdnCompatibilityTests(unittest.TestCase):
    NEW='us.aws.cdn.hf.co'
    OLD='cas-bridge.xethub.hf.co'
    def test_only_named_addition_and_commitment_changed(self):
        prior=dict(a.POLICY);self.assertEqual(prior.pop('additional_model_redirect_host'),self.NEW)
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
