import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import summarize_threeway as summary

class SummaryTests(unittest.TestCase):
    def records(self):
        cases=[{'id':str(i),'split':'historical' if i<24 else 'fresh','category':'synthetic','source':'合成例。'} for i in range(48)]
        data={}
        for arm in summary.ARMS:
            meta={'model':arm,'runtime_files_sha256':{'server':'a'},'server_sha256':'a','nvidia_smi_sha256':'b','gpu':{'uuid':'synthetic'}}
            rows=[{'id':c['id'],'split':c['split'],'seconds':.1,'format':{'protected_structure_exact':True,'newline_count_exact':True},'output':arm+' output','response':{'choices':[{'message':{'content':arm+' output'}}]}} for c in cases]
            data[arm]=(meta,cases,rows)
        return data
    def test_masking_retains_exact_three_outputs_and_all_preferences(self):
        data=self.records()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for arm in summary.ARMS:(root/arm).mkdir();(root/arm/'manifest.json').write_text('{}')
            with patch.object(summary.google,'load_evidence',return_value=data['google']),patch.object(summary.local,'load_evidence',side_effect=[data['hy18'],data['qwen35_2b']]):
                result=summary.summarize(root/'google',root/'hy18',root/'qwen35_2b',root/'h',root/'f',root/'d',root/'out')
            self.assertEqual(result['semantic_review'],'not performed')
            rows=[json.loads(x) for x in (root/'out/threeway-masked.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),48)
            for r in rows:
                self.assertEqual({r[x] for x in 'ABC'},{a+' output' for a in summary.ARMS})
                self.assertEqual(set(r['pair_preferences']),{'A/B','A/C','B/C'})
                self.assertNotIn('model',r);self.assertNotIn('request',r)
    def test_wrong_model_or_runtime_blocks_before_export(self):
        data=self.records();data['qwen35_2b'][0]['server_sha256']='changed'
        with tempfile.TemporaryDirectory() as tmp,patch.object(summary.google,'load_evidence',return_value=data['google']),patch.object(summary.local,'load_evidence',side_effect=[data['hy18'],data['qwen35_2b']]):
            root=Path(tmp)
            with self.assertRaises(ValueError):summary.summarize(root/'g',root/'h',root/'q',root/'hist',root/'fresh',root/'design',root/'out')
            self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
