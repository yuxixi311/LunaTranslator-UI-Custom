"""Observe original Python libcurl wrappers; do not replace HTTP or touch handles."""
import threading

BODY_LIMIT = 65536
HEADER_LIMIT = 16384


class CurlCompletion:
    def __init__(self):
        self.finished = threading.Event()
        self.success = False
        self.exceeded = False
        self.body_bytes = 0
        self.header_bytes = 0
        self.perform_calls = 0

    def require_success(self):
        if self.perform_calls != 1 or not self.finished.is_set() or not self.success or self.exceeded:
            raise RuntimeError('Original curl transfer did not complete successfully')


def install_observer(requester_module):
    state=CurlCompletion()
    original_perform=requester_module.curl_easy_perform
    original_callback=requester_module.Requester._Requester__WriteMemoryCallback
    def perform(*args,**kwargs):
        state.perform_calls+=1
        if state.perform_calls!=1:raise RuntimeError('Unexpected extra transport perform')
        try:
            result=original_perform(*args,**kwargs)
            state.success=True
            return result
        finally:
            state.finished.set()
    def callback(self,headerqueue,que,contents,size,nmemb,userp):
        # In the pinned STREAMING path the body callback has headerqueue!=None;
        # header callbacks have None. Bound before the original copies/queues bytes.
        amount=int(size)*int(nmemb)
        field='body_bytes' if headerqueue is not None else 'header_bytes'
        limit=BODY_LIMIT if headerqueue is not None else HEADER_LIMIT
        if amount<0 or getattr(state,field)+amount>limit:
            state.exceeded=True
            return 0  # Standard libcurl callback abort, observed as perform failure.
        setattr(state,field,getattr(state,field)+amount)
        return original_callback(self,headerqueue,que,contents,size,nmemb,userp)
    requester_module.curl_easy_perform=perform
    requester_module.Requester._Requester__WriteMemoryCallback=callback
    return state
