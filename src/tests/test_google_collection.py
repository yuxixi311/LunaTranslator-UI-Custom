import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import run_threeway_google as collector
import validate_threeway_google as validator

class CollectionTests(unittest.TestCase):
    def cases(self):return [{'id':'case%02d'%i,'split':'historical' if i<24 else 'fresh','category':'synthetic','source':'合成例。'} for i in range(48)]
    def fake_result(self,case,start):
        return {'status':'complete','id':case['id'],'output':'这是翻译连接确认。','seconds':.02,
                'transport_started':start+.05,'status_code':200,'response_bytes':40,'request_count':1,
                'provider_sha256':collector.PROVIDER_SHA256,'source_hashes':dict(collector.SOURCE_HASHES,**{'network/structures.py':'a'*64,'network/structures.py.normalized-lf':collector.STRUCTURES_LF_SHA}),
                'libcurl_sha256':collector.DLL_SHA256,'mode':collector.MODE,'python_executable_sha256':collector.experiment.digest(sys.executable),'curl_completion':True}
    def host_proof(self,path):
        value={'status':'complete','mode':collector.MODE,'provider_sha256':collector.PROVIDER_SHA256,
               'source_hashes':dict(collector.SOURCE_HASHES,**{'network/structures.py':'a'*64,'network/structures.py.normalized-lf':collector.STRUCTURES_LF_SHA}),
               'libcurl_sha256':collector.DLL_SHA256,'real_network_calls':0,'fake_requests':1,
               'backend':'installed-libcurl','request_and_html_parsing_match':True,'app_ui_verified':False,
               'python_version':[3,12,0],'python_executable_sha256':collector.experiment.digest(sys.executable),'collector_hashes':collector.collector_hashes()}
        collector.write_json(path,value);return path
    def test_complete_fake_collection_and_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cases=self.cases();clock=[1.0]
            args=types.SimpleNamespace(out=root/'out',historical_fixture=root/'h',fresh_fixture=root/'f',design=root/'d',installed_source_root=root/'app',libcurl=root/'curl.dll',host_proof=self.host_proof(root/'proof.json'))
            original_lock=collector.experiment.owned_model_lock
            original_proof=collector.validate_host_proof
            def invoke(command,timeout,ownership):
                self.assertIn('-I',command);self.assertLessEqual(timeout,25)
                index=int(command[command.index('--worker-index')+1]);case=([collector.experiment.SMOKE]+cases)[index]
                result_path=Path(command[command.index('--worker-result')+1]);result=self.fake_result(case,clock[0]);clock[0]+=.1
                ownership.starting_child();ownership.confirm_stopped(types.SimpleNamespace(poll=lambda:0))
                collector.write_json(result_path,result);return 0
            with patch.object(collector,'validate_host_proof',lambda p:original_proof(p,require_current_python=False)),patch.object(collector,'invoke_owned',invoke),patch.object(collector.time,'monotonic',lambda:clock[0]),patch.object(collector.time,'sleep',lambda n:clock.__setitem__(0,clock[0]+n)),patch.object(collector.experiment,'owned_model_lock',lambda path:original_lock(root/'lock')):
                collector.collect(args,cases)
            with patch.object(validator.experiment,'experiment_cases',return_value=cases):
                meta,_,rows=validator.load_evidence(args.out,args.historical_fixture,args.fresh_fixture,args.design)
                self.assertEqual(len(rows),48);self.assertEqual(meta['actual_calls'],49)
                callfile=args.out/'calls.jsonl';calls=[json.loads(x) for x in callfile.read_text().splitlines()];calls[1]['worker_started']=calls[0]['worker_started'];callfile.write_text('\n'.join(map(json.dumps,calls)))
                manifest=json.loads((args.out/'manifest.json').read_text());manifest['calls.jsonl']=collector.experiment.digest(callfile);collector.write_json(args.out/'manifest.json',manifest)
                with self.assertRaises(ValueError):validator.load_evidence(args.out,args.historical_fixture,args.fresh_fixture,args.design)
    def test_owned_timeout_stops_only_owned_child(self):
        ownership=collector.experiment.ModelOwnership()
        with self.assertRaises(Exception):collector.invoke_owned([sys.executable,'-c','import time; time.sleep(60)'],.05,ownership)
        self.assertTrue(ownership.termination_confirmed)
    def test_failure_stops_before_more_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=types.SimpleNamespace(out=root/'out',historical_fixture=root/'h',fresh_fixture=root/'f',design=root/'d',installed_source_root=root/'app',libcurl=root/'curl.dll',host_proof=self.host_proof(root/'proof.json'));seen=[]
            lock=collector.experiment.owned_model_lock
            original_proof=collector.validate_host_proof
            def fail(command,*args):seen.append(command);return 2
            with patch.object(collector,'validate_host_proof',lambda p:original_proof(p,require_current_python=False)),patch.object(collector,'invoke_owned',fail),patch.object(collector.experiment,'owned_model_lock',lambda path:lock(root/'lock')):
                with self.assertRaises(RuntimeError):collector.collect(args,self.cases())
            self.assertEqual(len(seen),1);meta=json.loads((args.out/'metadata.json').read_text());self.assertEqual(meta['status'],'incomplete');self.assertIsNone(meta['actual_calls']);self.assertEqual(meta['maximum_possible_calls'],1)

if __name__=='__main__':unittest.main()
