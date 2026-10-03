import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import google_existing_provider as adapter


class ExistingProviderTests(unittest.TestCase):
    def test_modified_provider_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'google.py';p.write_text('raise AssertionError("executed")')
            with self.assertRaises(ValueError):adapter.load_existing_provider(p,object())

    def test_exact_existing_provider_uses_own_request_and_parsing(self):
        # Optional source-integration test: fixture is NOT copied into the kit.
        import os
        path=os.environ.get('LUNA_EXISTING_GOOGLE_SOURCE')
        if not path:self.skipTest('Existing checkout source is not supplied')
        class Session:
            def __init__(self):self.payloads=[]
            def post(self,url,**kwargs):
                self.assert_endpoint=url
                # Never retain/print headers or the client-header value.
                payload=json.loads(kwargs['data']);self.payloads.append(payload)
                return type('Response',(),{'json':lambda _: [['你好 &amp; %s']]})()
        session=Session()
        # Public checkout LF form is only used by this no-network test. Runtime
        # accepts only the installed raw-byte pin, never this alternate hash.
        sha=adapter.digest(path)
        self.assertIn(sha,('6f7bcc1278e14d042d7b6297d26ec0ff7929c958457c8a3581c72e4eb00a2428',adapter.PROVIDER_SHA256))
        with patch.object(adapter,'PROVIDER_SHA256',sha):
            provider=adapter.load_existing_provider(path,session)
        self.assertEqual(provider.translate('一行。\r\n\r\n二行。'),'你好 & %s\n\n你好 & %s')
        self.assertEqual(session.assert_endpoint,adapter.ENDPOINT)
        self.assertEqual(session.payloads,[[[['一行。'],'ja','zh-CN'],'wt_lib'],[[['二行。'],'ja','zh-CN'],'wt_lib']])
        self.assertEqual(provider.translate(''),'')

if __name__=='__main__':unittest.main()
