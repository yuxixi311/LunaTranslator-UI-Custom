import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
from pathlib import Path
import types
import unittest
from google_installed_host import compile_proxy_session, read_sources

class ProxyClassTests(unittest.TestCase):
    def test_original_class_preserves_pair_lookup(self):
        source='''class proxysession(requests.Session):
    def __init__(self,a,b):
        super().__init__()
        self.proxyconf=a,b
    def request(self,*args,**kwargs):
        kwargs['proxies']=getproxy(self.proxyconf)
        return super().request(*args,**kwargs)
'''
        calls=[]
        class Base:
            def request(self,*args,**kwargs):return args,kwargs
        def lookup(pair):calls.append(pair);return {'https':'synthetic proxy'}
        cls=compile_proxy_session(source,types.SimpleNamespace(Session=Base),lookup)
        result=cls('fanyi','google').request('POST','synthetic',data='source')
        self.assertEqual(calls,[('fanyi','google')]);self.assertEqual(result[1]['proxies'],{'https':'synthetic proxy'})
    def test_nonclass_rejected_without_executing_module_imports(self):
        with self.assertRaises(ValueError):compile_proxy_session('raise RuntimeError()',object(),object())

if __name__=='__main__':unittest.main()
