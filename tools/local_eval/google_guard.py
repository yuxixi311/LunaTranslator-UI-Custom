"""Safety wrapper around an injected existing Luna session, not an HTTP client."""
import json
import time
import threading
from google_existing_provider import ENDPOINT

RESPONSE_LIMIT = 65536
MIN_START_INTERVAL = 2.0
MAX_STARTS = 49


class CollectionStopped(Exception):
    """Only this finite code, never external exception text, may enter evidence."""
    CODES = {'request_shape', 'request_limit', 'concurrent_request', 'deadline',
             'http_status', 'response_type', 'response_size', 'transport_failure',
             'stopped', 'cleanup_failure', 'transport_incomplete'}
    def __init__(self, code):
        if code not in self.CODES:
            raise ValueError('Non-whitelisted failure code')
        self.code = code
        super().__init__(code)


class GuardedExistingSession:
    def __init__(self, session, response_factory, close_response, completion_check, deadline,
                 clock=time.monotonic, sleep=time.sleep):
        self.session = session
        self.response_factory = response_factory
        self.close_response = close_response
        self.completion_check = completion_check
        self.deadline = deadline
        self.clock, self.sleep = clock, sleep
        self.expected_source = None
        self.last_start = None
        self.starts = 0
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.status_code = None
        self.response_bytes = None

    def check_deadline(self):
        if self.stopped.is_set():
            raise CollectionStopped('stopped')
        if self.clock() >= self.deadline:
            raise CollectionStopped('deadline')

    def post(self, url, **kwargs):
        if not self.lock.acquire(blocking=False):
            self.stopped.set()
            raise CollectionStopped('concurrent_request')
        response = None
        self.status_code = None
        self.response_bytes = None
        try:
            self.check_deadline()
            if self.starts >= MAX_STARTS:
                raise CollectionStopped('request_limit')
            # Inspect only the synthetic body/endpoint, never extract headers.
            try:
                payload = json.loads(kwargs['data'])
            except Exception:
                raise CollectionStopped('request_shape') from None
            if (url != ENDPOINT or set(kwargs) != {'headers', 'data'} or
                not isinstance(self.expected_source, str) or not self.expected_source or
                payload != [[[self.expected_source], 'ja', 'zh-CN'], 'wt_lib']):
                raise CollectionStopped('request_shape')
            if self.last_start is not None:
                delay = MIN_START_INTERVAL - (self.clock() - self.last_start)
                if delay > 0:
                    if self.clock() + delay >= self.deadline:
                        raise CollectionStopped('deadline')
                    self.sleep(delay)
            self.check_deadline()
            self.last_start = self.clock()
            self.starts += 1
            response = self.session.post(url, **kwargs, timeout=(10, 10),
                allow_redirects=False, stream=True, verify=True)
            self.check_deadline()
            self.status_code = response.status_code
            if type(self.status_code) is not int or self.status_code != 200:
                raise CollectionStopped('http_status')
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].lower()
            if content_type not in ('application/json', 'application/json+protobuf'):
                raise CollectionStopped('response_type')
            body = bytearray()
            for chunk in response.iter_content(4096):
                self.check_deadline()
                if not isinstance(chunk, bytes) or len(body) + len(chunk) > RESPONSE_LIMIT:
                    raise CollectionStopped('response_size')
                body.extend(chunk)
            self.check_deadline()
            try:
                self.completion_check()
            except Exception:
                raise CollectionStopped('transport_incomplete') from None
            self.response_bytes = len(body)
            # Reuse Luna's Response.json implementation. Headers stay in memory.
            bounded = self.response_factory(False)
            bounded.headers = response.headers
            bounded.status_code = response.status_code
            bounded.content = bytes(body)
            return bounded
        except CollectionStopped:
            self.stopped.set()
            raise
        except Exception:
            self.stopped.set()
            raise CollectionStopped('transport_failure') from None
        finally:
            try:
                if response is not None:
                    self.close_response(response)
            except Exception:
                self.stopped.set()
                raise CollectionStopped('cleanup_failure') from None
            finally:
                self.lock.release()
