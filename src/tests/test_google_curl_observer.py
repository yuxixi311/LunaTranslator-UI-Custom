import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
import types
import unittest
from google_curl_observer import install_observer
from google_guard import GuardedExistingSession, CollectionStopped
import test_google_guard as guard_tests

class ObserverTests(unittest.TestCase):
    def module(self,fail=False):
        observed=[]
        class Requester:
            def _Requester__WriteMemoryCallback(self,h,q,c,size,nmemb,u):observed.append(bytes(c));return size*nmemb
        def perform(handle):
            if fail:raise RuntimeError('private curl diagnostic')
        return types.SimpleNamespace(Requester=Requester,curl_easy_perform=perform),observed
    def test_success_observed_and_partial_failure_not_eof_success(self):
        module,_=self.module();state=install_observer(module)
        with self.assertRaises(RuntimeError):state.require_success()
        module.curl_easy_perform(None);state.require_success()
        module,_=self.module(True);state=install_observer(module)
        with self.assertRaises(RuntimeError):module.curl_easy_perform(None)
        self.assertTrue(state.finished.is_set())
        with self.assertRaises(RuntimeError):state.require_success()
        g,s,c,k=guard_tests.GuardTests().setup_guard();g.completion_check=state.require_success
        from google_existing_provider import ENDPOINT
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(e.exception.code,'transport_incomplete')
    def test_callback_bound_applies_before_original_copy_queue(self):
        module,seen=self.module();state=install_observer(module);obj=module.Requester()
        cb=obj._Requester__WriteMemoryCallback
        self.assertEqual(cb(object(),[],b'a',1,1,None),1)
        self.assertEqual(cb(object(),[],b'x'*65536,1,65536,None),0)
        self.assertEqual(seen,[b'a']);self.assertTrue(state.exceeded)
        module,seen=self.module();state=install_observer(module)
        self.assertEqual(module.Requester()._Requester__WriteMemoryCallback(None,[],b'x'*16385,1,16385,None),0)
        self.assertEqual(seen,[])

if __name__=='__main__':unittest.main()
