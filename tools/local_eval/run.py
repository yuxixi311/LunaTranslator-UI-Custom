"""Pinned Hy-MT2 synthetic comparison runner; Python standard library only.

Downloads nothing. Starts and terminates only its own localhost llama-server.
Uses the official Hy-MT2 chat template and general Chinese translation prompt.
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
from resources import memory_available, RamMonitor, GpuMonitor, NvidiaProbe, stop_owned, MIB
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'src/tests/fixtures/local_translation_eval_20261003.json'
FIXTURE_SHA = '051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1'
TEMPLATES = {
    '1.8b': ('hymt_chat_template.jinja', 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee'),
    '1.8b-q6': ('hymt_chat_template.jinja', 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee'),
    '1.8b-q8': ('hymt_chat_template.jinja', 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee'),
    '7b': ('hymt7_chat_template.jinja', '788ac16c5d7bfefc28655928ad524c8f378a44cb24d24fb125d6a5859b167677'),
}
MODELS = {
    '1.8b': (1133080448, 'dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699', 'b27182d810fa3ceb6ed04e7c324c54e35c0d209c'),
    '1.8b-q6': (1474785120, 'd98fe604dec1f28f58f80d7d560f7177e584d3b8e5835862687660e5ff97cb40', 'b27182d810fa3ceb6ed04e7c324c54e35c0d209c'),
    '1.8b-q8': (1908528192, '5c3fe0b1408a5ceb0143184ef247b11b579c525f4b02b060e6c851bb76fef1a4', 'b27182d810fa3ceb6ed04e7c324c54e35c0d209c'),
    '7b': (4624648896, '9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b', '707464294cf5b2a5a69982855020858ed58cf1d1'),
}
TOKEN = re.compile(r'\$?\{[^{}]+\}|%[sd]|</?b>')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def request_body(source, alias):
    return {'model': alias, 'messages': [{'role': 'user', 'content':
        '将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n' + source}],
        'temperature': 0.7, 'top_p': 0.6, 'top_k': 20,
        'repeat_penalty': 1.05, 'min_p': 0.05, 'repeat_last_n': 64,
        'seed': 42, 'max_tokens': 512, 'cache_prompt': False, 'stream': False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Redirect refused')


def check_format(source, translated):
    return {'tokens_exact': Counter(TOKEN.findall(source)) == Counter(TOKEN.findall(translated)),
            'newline_count_exact': source.count('\n') == translated.count('\n')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', choices=MODELS, required=True)
    p.add_argument('--gguf', type=Path, required=True)
    p.add_argument('--server', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--backend', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--nvidia-smi', type=Path, help='Explicit verified existing NVIDIA driver tool; required for CUDA')
    p.add_argument('--gpu-index', type=int, default=0)
    a = p.parse_args()
    if a.gpu_index < 0:
        p.error('GPU index must be nonnegative')
    if a.backend == 'cuda' and a.nvidia_smi is None:
        p.error('CUDA requires --nvidia-smi pointing to the verified existing driver tool')
    size, sha, revision = MODELS[a.model]
    template_name, template_sha = TEMPLATES[a.model]
    template = Path(__file__).with_name(template_name)
    if digest(FIXTURE) != FIXTURE_SHA or digest(template) != template_sha:
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
    cmd = [str(a.server.resolve()), '-m', str(a.gguf.resolve()), '--host', '127.0.0.1',
           '--port', str(port), '--alias', alias, '-c', '2048', '-t', '2', '-tb', '2',
           '-np', '1', '-ngl', '99' if gpu else '0', '-b', '128', '-ub', '128', '--chat-template-file', str(template)]
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
    meta = {'schema_version': 2, 'backend': a.backend, 'gpu_layers': 99 if gpu else 0,
            'gpu': gpu, 'nvidia_smi_sha256': digest(a.nvidia_smi) if probe else None, 'runtime_files_sha256': runtime_files,
            'resource_probe_sha256': digest(Path(__file__).with_name('resources.py')),
            'command': cmd, 'fixture_sha256': FIXTURE_SHA, 'model': a.model, 'model_sha256': sha,
            'model_revision': revision, 'runtime_version': version, 'server_sha256': digest(a.server),
            'template_sha256': template_sha, 'harness_sha256': digest(__file__),
            'base_app_revision': 'e27cd93471f06b290f6f5f427d35b66ff3c4adb1',
            'platform': platform.platform(), 'memory_available_before': available,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128,
            'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
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
                wire.write(json.dumps({'request_base64': base64.b64encode(payload).decode('ascii'),
                    'response_base64': base64.b64encode(raw).decode('ascii'),
                    'request_sha256': hashlib.sha256(payload).hexdigest(),
                    'response_sha256': hashlib.sha256(raw).hexdigest()}) + '\n')
                wire.flush()
            return json.loads(raw)
    with (a.out / 'server.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, env=child_env)
        ram = RamMonitor(proc, available)
        monitors = [ram] + ([GpuMonitor(proc, probe, gpu['uuid'])] if gpu else [])
        try:
            for monitor in monitors:
                monitor.thread.start()
            start = time.monotonic()
            while True:
                if proc.poll() is not None or ram.samples['resource_guard_stopped_process']:
                    raise RuntimeError('Owned model process exited or resource guard stopped readiness')
                try:
                    ready = call('health', timeout=5)['status'] == 'ok'
                    names = [x['id'] for x in call('v1/models', timeout=5)['data']]
                    if ready and alias in names:
                        break
                except (OSError, ValueError, KeyError):
                    pass
                if time.monotonic() - start > 180:
                    raise TimeoutError('Model readiness timeout')
                time.sleep(.2)
            meta['warm_cache_load_seconds'] = time.monotonic() - start
            with (a.out / 'results.jsonl').open('w', encoding='utf-8') as out, (a.out / 'wire.jsonl').open('w', encoding='utf-8') as wire:
                for case in json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']:
                    if proc.poll() is not None or ram.samples['resource_guard_stopped_process']:
                        raise RuntimeError('Owned model process exited or resource guard stopped the run')
                    body = request_body(case['source'], alias)
                    start = time.monotonic()
                    response = call('v1/chat/completions', body, wire)
                    elapsed = time.monotonic() - start
                    text = response['choices'][0]['message']['content']
                    row = {'id': case['id'], 'split': case['split'], 'request': body,
                           'response': response, 'seconds': elapsed, 'format': check_format(case['source'], text)}
                    out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
                    print(case['id'], round(elapsed, 3), flush=True)
            if ram.samples['resource_guard_stopped_process'] or proc.poll() is not None:
                raise RuntimeError('Owned process exited or resource guard stopped the run')
            meta['status'] = 'complete'
        finally:
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
