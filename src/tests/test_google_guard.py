import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/local_eval'))
import json
import unittest
from google_existing_provider import ENDPOINT
from google_guard import GuardedExistingSession, CollectionStopped

class Response:
    def __init__(self,stream=False):
        self.headers={'Content-Type':'application/json; charset=utf-8'};self.status_code=200;self.content=b'[["ok"]]'
    def iter_content(self,n):yield self.content
    def json(self):return json.loads(self.content)
class Session:
    def __init__(self):self.response=Response();self.calls=[]
    def post(self,url,**kwargs):self.calls.append((url,kwargs));return self.response
class GuardTests(unittest.TestCase):
    def setup_guard(self):
        clock=[0.0];session=Session();guard=GuardedExistingSession(session,Response,lambda r:setattr(r,"closed",True),lambda:None,240,lambda:clock[0],lambda n:clock.__setitem__(0,clock[0]+n));guard.expected_source='合成例。'
        kwargs={'data':json.dumps([[['合成例。'],'ja','zh-CN'],'wt_lib']),'headers':{'Content-Type':'application/json+protobuf'}}
        return guard,session,clock,kwargs
    def test_pacing_and_existing_transport_arguments(self):
        g,s,c,k=self.setup_guard();self.assertEqual(g.post(ENDPOINT,**k).json(),[['ok']]);g.post(ENDPOINT,**k)
        self.assertEqual(c[0],2);self.assertEqual(g.starts,2)
        self.assertEqual(s.calls[0][1]['data'],k['data']);self.assertIs(s.calls[0][1]['headers'],k['headers'])
        self.assertFalse(s.calls[0][1]['allow_redirects']);self.assertTrue(s.calls[0][1]['verify'])
    def test_bad_status_type_size_and_limits_stop(self):
        for field,value,code in [('status_code',429,'http_status'),('headers',{'Content-Type':'text/html'},'response_type'),('content',b'x'*65537,'response_size')]:
            g,s,c,k=self.setup_guard();setattr(s.response,field,value)
            with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
            self.assertEqual(e.exception.code,code);self.assertEqual(len(s.calls),1);self.assertTrue(s.response.closed);self.assertTrue(g.stopped.is_set())
        g,s,c,k=self.setup_guard();g.starts=49
        with self.assertRaises(CollectionStopped):g.post(ENDPOINT,**k)
        self.assertEqual(s.calls,[])
    def test_sanitized_error_and_wrong_endpoint(self):
        g,s,c,k=self.setup_guard()
        def fail(*a,**kw):raise RuntimeError('PRIVATE CONFIG MUST NOT APPEAR')
        s.post=fail
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(str(e.exception),'transport_failure')
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(e.exception.code,'stopped')
        g,s,c,k=self.setup_guard()
        with self.assertRaises(CollectionStopped) as e:g.post('https://other.invalid/',**k)
        self.assertEqual(e.exception.code,'request_shape')

    def test_deadline_and_concurrent_rejection_are_terminal(self):
        g,s,c,k=self.setup_guard();c[0]=241
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(e.exception.code,'deadline');self.assertEqual(s.calls,[])
        self.assertTrue(g.stopped.is_set())
        g,s,c,k=self.setup_guard();g.lock.acquire()
        try:
            with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
            self.assertEqual(e.exception.code,'concurrent_request')
        finally:g.lock.release()
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(e.exception.code,'stopped');self.assertEqual(s.calls,[])

    def test_rate_delay_cannot_start_past_deadline(self):
        g,s,c,k=self.setup_guard();g.post(ENDPOINT,**k);g.deadline=1
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(e.exception.code,'deadline');self.assertEqual(len(s.calls),1)

    def test_cleanup_failure_is_terminal_and_sanitized(self):
        g,s,c,k=self.setup_guard()
        def fail(r):raise RuntimeError('private details')
        g.close_response=fail
        with self.assertRaises(CollectionStopped) as e:g.post(ENDPOINT,**k)
        self.assertEqual(str(e.exception),'cleanup_failure');self.assertTrue(g.stopped.is_set())

if __name__=='__main__':unittest.main()
