"""Preregistered source-context experiment for existing pinned 1.8B Q4 only.

Downloads nothing. Starts and terminates only its own localhost llama-server.
Uses the same gates/runtime/sampling as run.py; compares empty versus bounded original source context.
No default provider configuration is modified. No application context/default behavior changes.
This measures model inference, not the application's Windows/Qt integration.
"""
import argparse
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
import threading
from resources import memory_available, RamMonitor, GpuMonitor, NvidiaProbe, stop_owned, MIB
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/LunaTranslator'))
from myutils.local_translation import LocalTranslationError
from myutils.local_translation_integrity import validate_integrity

TEMPLATES = {'1.8b': ('hymt_chat_template.jinja', 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee')}
MODELS = {'1.8b': (1133080448, 'dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699', 'b27182d810fa3ceb6ed04e7c324c54e35c0d209c')}
DESIGN_SHA = '65cae85be40227e10c924d14613586bd8c3af50e97557c4adea58c76df1e6e02'
DESIGN = ROOT / 'docs/local-eval/source-context-v1/PREREGISTRATION.md'
FRESH_SHA = '4a1c87edcfea6ac8542d721aaa5a72dc8565d4efd5956245103014f27978dbfe'
EXPERIMENT = 'hymt18-source-context-v1'
PROMPT_TEMPLATE = '〖背景信息〗\n{background}\n请结合背景信息将以下文本翻译为简体中文。\n〖待翻译文本〗\n{source}'
INFERENCE_BUDGET_SECONDS = 180
STARTUP_BUDGET_SECONDS = 180
CONTEXT_CHAR_LIMIT = 128
CONTEXT_TOKEN_LIMIT = 128
SOURCE_CHAR_LIMIT = 128
PROMPT_TOKEN_LIMIT = 384


def experiment_cases(fresh_fixture):
    if digest(fresh_fixture) != FRESH_SHA or digest(DESIGN) != DESIGN_SHA:
        raise ValueError('Frozen source-context fixture hash mismatch')
    cases = json.loads(fresh_fixture.read_text(encoding='utf-8'))['cases']
    if len(cases) != 32:
        raise ValueError('Expected exactly 32 cases')
    result, seen, families, controls = [], set(), {}, 0
    for case in cases:
        if set(case) != {'id', 'family_id', 'kind', 'alternative', 'source', 'context_sentences'}:
            raise ValueError('Unexpected fixture fields')
        source, sentences = case['source'], case['context_sentences']
        if not isinstance(source, str) or not source.strip() or len(source) > SOURCE_CHAR_LIMIT:
            raise ValueError('Source character limit or empty source')
        if not isinstance(sentences, list) or not 1 <= len(sentences) <= 2 or not all(isinstance(t, str) and t.strip() for t in sentences):
            raise ValueError('Expected one or two original source sentences')
        context = '\n'.join(sentences)
        if len(context) > CONTEXT_CHAR_LIMIT or any(t in source + context for t in ('〖背景信息〗', '〖待翻译文本〗', '<｜')):
            raise ValueError('Context bound or reserved prompt marker')
        if case['id'] in seen or not isinstance(case['id'], str) or not case['id']:
            raise ValueError('Duplicate/invalid case ID')
        seen.add(case['id'])
        if case['kind'] == 'family':
            if case['alternative'] not in ('a', 'b') or not isinstance(case['family_id'], str) or not case['family_id']:
                raise ValueError('Invalid family metadata')
            families.setdefault(case['family_id'], []).append(case)
        elif case['kind'] == 'control' and case['alternative'] == 'control':
            controls += 1
        else:
            raise ValueError('Invalid case kind')
        variants = ('baseline', 'candidate') if len(seen) % 2 else ('candidate', 'baseline')
        for variant in variants:
            result.append(dict(case, split=case['kind'], variant=variant))
    if len(families) != 12 or controls != 8:
        raise ValueError('Expected 12 families and 8 controls')
    for pair in families.values():
        if len(pair) != 2 or {r['alternative'] for r in pair} != {'a', 'b'} or pair[0]['source'] != pair[1]['source'] or pair[0]['context_sentences'] == pair[1]['context_sentences']:
            raise ValueError('Invalid alternate-context pair')
    return result


TOKEN = re.compile(r'\$?\{[^{}]+\}|%[sd]|</?b>')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def request_body(case, alias, variant="baseline"):
    if variant not in ("baseline", "candidate"):
        raise ValueError("Unknown preregistered context variant")
    background = '\n'.join(case['context_sentences']) if variant == 'candidate' else ''
    return {'model': alias, 'messages': [{'role': 'user', 'content':
        PROMPT_TEMPLATE.format(background=background, source=case['source'])}],
        'temperature': 0.7, 'top_p': 0.6, 'top_k': 20,
        'repeat_penalty': 1.05, 'min_p': 0.05, 'repeat_last_n': 64,
        'seed': 42, 'max_tokens': 512, 'cache_prompt': False, 'stream': False}


def token_probe_bodies(case, alias):
    body = request_body(case, alias, case['variant'])
    background = '\n'.join(case['context_sentences']) if case['variant'] == 'candidate' else ''
    return {'content': background, 'add_special': False, 'parse_special': False}, {'messages': body['messages']}


def checked_tokens(response, maximum, minimum=0):
    values = response.get('tokens')
    if not isinstance(values, list) or not all(type(t) is int and t >= 0 for t in values) or not minimum <= len(values) <= maximum:
        raise ValueError('Invalid tokenizer response or token limit exceeded')
    return len(values)


def preflight_tokens(cases, alias, call, wire):
    records = []
    for case in cases:
        context_body, template_body = token_probe_bodies(case, alias)
        context_response = call('tokenize', context_body, wire)
        context_count = checked_tokens(context_response, CONTEXT_TOKEN_LIMIT, int(bool(context_body['content'])))
        rendered = call('apply-template', template_body, wire)
        expected = '<｜hy_begin▁of▁sentence｜><｜hy_User｜>' + template_body['messages'][0]['content'] + '<｜hy_Assistant｜>'
        if rendered.get('prompt') != expected:
            raise ValueError('Applied chat template differs from pinned single-user rendering')
        prompt_body = {'content': rendered['prompt'], 'add_special': False, 'parse_special': True}
        prompt_response = call('tokenize', prompt_body, wire)
        prompt_count = checked_tokens(prompt_response, PROMPT_TOKEN_LIMIT, 1)
        records.append({'id': case['id'], 'variant': case['variant'],
            'context_tokens': context_count, 'prompt_tokens': prompt_count,
            'context_request': context_body, 'context_response': context_response,
            'template_request': template_body, 'template_response': rendered,
            'prompt_request': prompt_body, 'prompt_response': prompt_response})
    return records


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', choices=('1.8b',), default='1.8b')
    p.add_argument('--gguf', type=Path, required=True)
    p.add_argument('--server', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fresh-fixture', type=Path, required=True, help='Separately transferred locked source-context fixture')
    p.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--nvidia-smi', type=Path, help='Explicit verified existing NVIDIA driver tool; required for CUDA')
    p.add_argument('--gpu-index', type=int, default=0)
    p.add_argument('--restrict-cors-to-loopback', action='store_true',
                   help='Explicit owner-approved process-only CORS restriction; required before launch')
    a = p.parse_args()
    if not a.restrict_cors_to_loopback:
        p.error('Startup blocked: explicit approval for --restrict-cors-to-loopback is required; no server started')
    if a.gpu_index < 0:
        p.error('GPU index must be nonnegative')
    if a.backend == 'cuda' and a.nvidia_smi is None:
        p.error('CUDA requires --nvidia-smi pointing to the verified existing driver tool')
    try:
        cases = experiment_cases(a.fresh_fixture)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    size, sha, revision = MODELS[a.model]
    template_name, template_sha = TEMPLATES[a.model]
    template = Path(__file__).with_name(template_name)
    if digest(template) != template_sha:
        p.error('Frozen fixture or official template hash mismatch')
    if a.gguf.stat().st_size != size or digest(a.gguf) != sha:
        p.error('Model bytes do not match pinned official GGUF')
    # Conservative resource gate, not a claimed universal minimum. Never bypass to force a run.
    try:
        available = memory_available()
    except (OSError, ValueError):
        p.error('Cannot measure available physical RAM; refusing to start')
    reserve = 2300 * 1024**2
    if available is not None and available < size + reserve:
        p.error('Insufficient available RAM for weights plus 2300 MiB working/safety reserve')
    if available is None:
        p.error('Available physical RAM is unknown; refusing to start')
    probe = NvidiaProbe(a.nvidia_smi, a.gpu_index) if a.backend == 'cuda' else None
    gpu = probe.gpu() if probe else None
    if gpu and gpu['free_bytes'] < size + 1024 * MIB:
        p.error('Insufficient measured free VRAM for weights plus 1024 MiB reserve')
    child_env = os.environ.copy()
    if gpu:
        child_env['CUDA_VISIBLE_DEVICES'] = gpu['uuid']
    version = subprocess.check_output([str(a.server.resolve()), '--version'],
        stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=15, env=child_env)
    if 'build 11349, commit fb4b2737a' not in version:
        p.error('Use pinned official b11349 runtime; version is additional evidence, not signature verification')
    # Bind check prevents targeting an existing server; alias/readiness plus owned process check cover races.
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    alias = 'luna-eval-' + a.model + '-' + str(port)
    cmd = [str(a.server.resolve()), '-lv', '4', '--log-colors', 'off', '--no-log-jsonl', '--no-warmup', '-m', str(a.gguf.resolve()), '--host', '127.0.0.1',
           '--port', str(port), '--alias', alias, '-c', '2048', '-t', '2', '-tb', '2',
           '-np', '1', '-ngl', '99' if gpu else '0', '-b', '128', '-ub', '128', '--chat-template-file', str(template)]
    cmd += ['--cors-origins', 'http://127.0.0.1:%d' % port]
    if gpu:
        cmd += ['--device', 'CUDA0']
    runtime_files = {f.name: digest(f) for f in sorted(a.server.resolve().parent.glob('*.dll'))}
    runtime_files[a.server.name] = digest(a.server)
    # Keep the safety check fresh after hashing files/version probes, before launch.
    available = memory_available()
    fresh_gpu = probe.gpu() if probe else None
    if available < size + reserve or (fresh_gpu and (fresh_gpu['uuid'] != gpu['uuid'] or fresh_gpu['free_bytes'] < size + 1024 * MIB)):
        p.error('Available RAM or VRAM fell below the preflight reserve')
    gpu = fresh_gpu
    a.out.mkdir(parents=True, exist_ok=False)
    meta = {'schema_version': 3, 'experiment': EXPERIMENT, 'design_sha256': DESIGN_SHA,
            'prompt_template': PROMPT_TEMPLATE,
            'prompt_template_sha256': hashlib.sha256(PROMPT_TEMPLATE.encode('utf-8')).hexdigest(),
            'fresh_fixture_sha256': FRESH_SHA, 'context_char_limit': CONTEXT_CHAR_LIMIT,
            'context_token_limit': CONTEXT_TOKEN_LIMIT, 'prompt_token_limit': PROMPT_TOKEN_LIMIT, 'case_count': len(cases) // 2,
            'request_count': len(cases), 'inference_budget_seconds': INFERENCE_BUDGET_SECONDS,
            'startup_budget_seconds': STARTUP_BUDGET_SECONDS, 'order': 'paired alternating AB/BA, no output caching', 'backend': a.backend, 'gpu_layers': 99 if gpu else 0,
            'gpu': gpu, 'nvidia_smi_sha256': digest(a.nvidia_smi) if probe else None, 'runtime_files_sha256': runtime_files,
            'resource_probe_sha256': digest(Path(__file__).with_name('resources.py')),
            'integrity_checker_sha256': digest(ROOT / 'src/LunaTranslator/myutils/local_translation_integrity.py'),
            'command': cmd, 'model': a.model, 'model_sha256': sha,
            'model_revision': revision, 'runtime_version': version, 'server_sha256': digest(a.server),
            'template_sha256': template_sha, 'harness_sha256': digest(__file__),
            'base_app_revision': '1b8dc70a2d7c4653b61f2d55acc877c6ec2f5576',
            'platform': platform.platform(), 'memory_available_before': available,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
            'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'timing_clock': vars(time.get_clock_info('perf_counter')),
            'startup_checks': {'security_warning_gate': 'pending', 'cuda_proof': None},
            'runtime_warmup': False, 'cors_policy': 'owned loopback origin only',
            'status': 'incomplete'}
    meta_path = a.out / 'metadata.json'
    meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def call(path, body=None, wire=None, timeout=180):
        payload = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:%d/%s' % (port, path),
              data=payload, headers={'Content-Type': 'application/json'})
        with opener.open(req, timeout=timeout) as r:
            raw = r.read()
            if wire is not None:
                wire.write(json.dumps({'endpoint': path, 'request_base64': base64.b64encode(payload).decode('ascii'),
                    'response_base64': base64.b64encode(raw).decode('ascii'),
                    'request_sha256': hashlib.sha256(payload).hexdigest(),
                    'response_sha256': hashlib.sha256(raw).hexdigest()}) + '\n')
                wire.flush()
            return json.loads(raw)
    log_path = a.out / 'server.log'
    with log_path.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, env=child_env)
        ram = RamMonitor(proc, available)
        monitors = [ram] + ([GpuMonitor(proc, probe, gpu['uuid'])] if gpu else [])
        deadline_guard = None
        startup_guard = InferenceDeadline(proc, seconds=STARTUP_BUDGET_SECONDS)
        try:
            startup_guard.start()
            for monitor in monitors:
                monitor.thread.start()
            start = time.perf_counter()
            while True:
                if startup_guard.expired.is_set():
                    raise TimeoutError('Owned-process startup watchdog expired')
                if proc.poll() is not None or ram.samples['resource_guard_stopped_process']:
                    raise RuntimeError('Owned model process exited or resource guard stopped readiness')
                check_startup_log(log_path)
                try:
                    ready = call('health', timeout=5)['status'] == 'ok'
                    names = [x['id'] for x in call('v1/models', timeout=5)['data']]
                    if ready and alias in names:
                        meta['startup_checks']['cuda_proof'] = check_startup_log(log_path, cuda=bool(gpu), require_gpu=True)
                        meta['startup_checks']['security_warning_gate'] = 'passed'
                        break
                except (OSError, ValueError, KeyError):
                    pass
                if time.perf_counter() - start > 180:
                    raise TimeoutError('Model readiness timeout')
                time.sleep(.2)
            startup_guard.close()
            if startup_guard.expired.is_set() or startup_guard.error:
                raise TimeoutError('Startup watchdog expired or failed to stop cleanly')
            meta['warm_cache_load_seconds'] = time.perf_counter() - start
            inference_deadline = time.perf_counter() + INFERENCE_BUDGET_SECONDS
            deadline_guard = InferenceDeadline(proc, seconds=INFERENCE_BUDGET_SECONDS)
            deadline_guard.start()
            probe_start = time.perf_counter()
            with (a.out / 'token-wire.jsonl').open('w', encoding='utf-8') as token_wire:
                token_records = preflight_tokens(cases, alias, call, token_wire)
            (a.out / 'token-preflight.json').write_text(json.dumps(token_records, ensure_ascii=False, indent=2), encoding='utf-8')
            meta['token_probe_seconds'] = time.perf_counter() - probe_start
            meta['token_probe_count'] = 3 * len(token_records)
            with (a.out / 'results.jsonl').open('w', encoding='utf-8') as out, (a.out / 'wire.jsonl').open('w', encoding='utf-8') as wire:
                for index, case in enumerate(cases):
                    if proc.poll() is not None or ram.samples['resource_guard_stopped_process']:
                        raise RuntimeError('Owned model process exited or resource guard stopped the run')
                    check_startup_log(log_path)
                    body = request_body(case, alias, case['variant'])
                    start = time.perf_counter()
                    remaining = inference_deadline - start
                    if remaining <= 0:
                        raise TimeoutError('Preregistered inference time budget exhausted')
                    response = call('v1/chat/completions', body, wire, timeout=min(180, remaining))
                    elapsed = time.perf_counter() - start
                    choice = response['choices'][0]
                    text = choice['message']['content']
                    if choice.get('finish_reason') != 'stop' or not isinstance(text, str) or not text.strip():
                        raise RuntimeError('Incomplete or empty model output; experiment stopped')
                    if response.get('usage', {}).get('prompt_tokens_details', {}).get('cached_tokens') != 0:
                        raise RuntimeError('Uncached-token evidence missing or prompt cache used; stopped')
                    if response.get('usage', {}).get('prompt_tokens') != token_records[index]['prompt_tokens']:
                        raise RuntimeError('Actual prompt tokens differ from measured applied template; stopped')
                    row = {'id': case['id'], 'split': case['split'], 'variant': case['variant'], 'request': body,
                           'response': response, 'seconds': elapsed, 'format': check_format(case['source'], text)}
                    out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
                    print(case['id'], case['variant'], round(elapsed, 3), flush=True)
            if ram.samples['resource_guard_stopped_process'] or proc.poll() is not None or deadline_guard.expired.is_set():
                raise RuntimeError('Owned process exited or resource guard stopped the run')
            check_startup_log(log_path)
            meta['status'] = 'complete'
        except Exception as exc:
            meta['failure'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            startup_guard.close()
            meta['startup_budget_exceeded'] = startup_guard.expired.is_set()
            if startup_guard.error:
                meta['startup_stop_error'] = startup_guard.error
            if startup_guard.expired.is_set() or startup_guard.error:
                meta['status'] = 'incomplete'
            if deadline_guard is not None:
                deadline_guard.close()
                meta['inference_budget_exceeded'] = deadline_guard.expired.is_set()
                if deadline_guard.error:
                    meta['budget_stop_error'] = deadline_guard.error
                if deadline_guard.expired.is_set() or deadline_guard.error:
                    meta['status'] = 'incomplete'
            for monitor in monitors:
                monitor.stop.set()
            for monitor in monitors:
                if monitor.thread.ident is not None:
                    monitor.thread.join(timeout=7)
            try:
                stop_owned(proc)
            except BaseException as exc:
                meta['status'] = 'incomplete'
                meta['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
                raise
            finally:
                for monitor in monitors:
                    meta.update(monitor.samples)
                if proc.poll() is None or ram.samples['resource_guard_stopped_process'] or any(m.thread.is_alive() for m in monitors):
                    meta['status'] = 'incomplete'
                meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
                log.flush()
                manifest = {f.name: digest(f) for f in a.out.iterdir() if f.is_file()}
                (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')



if __name__ == '__main__':
    main()
