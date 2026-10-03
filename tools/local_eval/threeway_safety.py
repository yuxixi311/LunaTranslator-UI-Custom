"""Exact reviewed safety definitions from run_context_experiment.py."""
import hashlib
import re
import threading
import urllib.request
from collections import Counter
from resources import stop_owned
from myutils.local_translation import LocalTranslationError
from myutils.local_translation_integrity import validate_integrity
INFERENCE_BUDGET_SECONDS = 180
TOKEN = re.compile(r'\$?\{[^{}]+\}|%[sd]|</?b>')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Redirect refused')


def check_format(source, translated):
    try:
        validate_integrity(source, translated)
        protected = True
    except LocalTranslationError:
        protected = False
    return {'legacy_basic_tokens_exact': Counter(TOKEN.findall(source)) == Counter(TOKEN.findall(translated)),
            'newline_count_exact': source.count('\n') == translated.count('\n'),
            'protected_structure_exact': protected}


class InferenceDeadline:
    """Stop only the owned Popen child when the monotonic inference budget expires."""
    def __init__(self, proc, seconds=INFERENCE_BUDGET_SECONDS):
        self.proc = proc
        self.expired = threading.Event()
        self.error = None
        self.timer = threading.Timer(seconds, self._expire)
        self.timer.daemon = True

    def _expire(self):
        self.expired.set()
        try:
            stop_owned(self.proc)
        except Exception as exc:
            self.error = type(exc).__name__ + ': ' + str(exc)

    def start(self):
        self.timer.start()

    def close(self):
        self.timer.cancel()
        if self.timer.ident is not None:
            self.timer.join(timeout=7)
        if self.timer.is_alive():
            self.error = 'Inference deadline cleanup thread did not exit'


def check_startup_log(path, cuda=False, require_gpu=False):
    """Fail closed on runtime security warnings; flags alone are not GPU proof.

    These log forms are pinned to b11349. Unknown/missing CUDA evidence must stop
    the run rather than silently relabel a CPU fallback as GPU execution.
    """
    text = path.read_text(encoding='utf-8', errors='replace')
    if re.search(r'(?im)^.*\bsecurity\s*:', text):
        raise RuntimeError('Runtime security warning: further inference refused; review server.log')
    if require_gpu and cuda:
        devices = re.findall(r'using device CUDA0\b', text)
        offloads = re.findall(r'offloaded (\d+)/(\d+) layers to GPU', text)
        buffers = re.findall(r'CUDA0\s+model buffer size\s*=\s*([0-9.]+) MiB', text)
        positive = [(int(n), int(total)) for n, total in offloads if 0 < int(n) <= int(total)]
        if not devices or not positive or not any(float(n) > 0 for n in buffers):
            raise RuntimeError('CUDA loading/offload proof missing; stopped before inference; review trace server.log')
        return {'device': 'CUDA0', 'offloaded_layers': positive[-1][0],
                'total_layers': positive[-1][1], 'positive_model_buffer': True}
    return None
