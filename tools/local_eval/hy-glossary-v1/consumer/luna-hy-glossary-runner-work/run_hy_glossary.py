"""Bounded Hy1.8B explicit-glossary A/B experiment. No downloads or output repair.

Each invocation owns exactly one CUDA server, one unscored smoke, and 64 outputs.
All source, runtime, model, policy and production-adapter freezes are mandatory.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent / 'luna-threeway-repair-zip-verification'
SUPPORT = ROOT / 'tools/local_eval'
sys.path.insert(0, str(SUPPORT))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'luna-hy-glossary-policy-work'))
sys.path.insert(0, str(ROOT / 'src/LunaTranslator'))
REVIEWED_SOURCE_PINS = {'tools/local_eval/resources.py': '35d69a8339ad2773e4fe0b89acba2092a2710568ff08da58e62e524af900dfbe', 'tools/local_eval/threeway_safety.py': '99de6860d8a6ee1f1839a755049a5041df4b5e46133a83f599dd0296e6563726', 'tools/local_eval/threeway_model_preflight.py': '3022c874ea5e45ccb3b255bb3192678f2f93e6a999b18b970daf788eb281fbbf', 'tools/local_eval/run_threeway_local.py': '5ed0d0f0832462d5a712688142215312dbca13d11d20e8c1e805fa000e762d9e', 'src/LunaTranslator/myutils/local_translation.py': '585983e55e7ede288085b10f8bced19fd519d9e02fd718a9f2abf9c9214d4fa0', 'src/LunaTranslator/myutils/local_translation_integrity.py': '74b9e650d51e38f46db25f26b2018ae4dad2a3d4cbaa086110e0e4fffdbd22de', 'tools/local_eval/hymt_chat_template.jinja': 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee'}
for _relative, _sha in REVIEWED_SOURCE_PINS.items():
    if hashlib.sha256((ROOT / _relative).read_bytes()).hexdigest() != _sha:
        raise ValueError("Reviewed dependency hash mismatch: " + _relative)
from resources import memory_available, RamMonitor, GpuMonitor, NvidiaProbe, stop_owned, MIB
from threeway_safety import digest, check_format, NoRedirect, InferenceDeadline, check_startup_log
from threeway_model_preflight import read_metadata, validate_metadata

EXPERIMENT = 'luna-hy-glossary-v1'
DESIGN_SHA = '492967489479a4756e7df5161a0d952385261094ce7e6e289289d8e8307da2a9'
FRESH_SHA = '29e6d18e8ca8191c87eb2328cf6a4055947d8627cb22ef456199df1fc6bfa092'
RUNTIME_PIN_SHA = 'fe89be67d740dbfaf22f870d77d63782ce283f9a91fbc3addd2d4c9f4b0ed649'
RUNTIME_PINS = Path(__file__).resolve().parent.parent / 'luna-hy-glossary-design/RUNTIME_PINS.private.json'
CANON_SHA = '7cc5bdb3626dd4e781070dca708428c0ef81048d72b067a71f9e15c795814337'
CANON = Path(__file__).resolve().parent.parent / 'luna-hy-glossary-independent/canon.json'
POLICY_PIN = '5e7cbc1b9c875de6a07148e60323cdf3f8183d8007e950effa52bdde07e8173f'
ADAPTER_PIN = 'efdd618ceb43032a7e30693f7192bc22942422faf3ec9b93b219f32089344183'
HISTORICAL_SHA = '051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1'
PROMPT_TEMPLATE = '将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}'
SMOKE = {'id': '__unscored_smoke__', 'split': 'smoke', 'category': 'readiness', 'source': 'これは翻訳の接続確認です。'}
SOURCE_CHAR_LIMIT = 200
PROMPT_TOKEN_LIMIT = 384
STARTUP_BUDGET_SECONDS = 180
INFERENCE_BUDGET_SECONDS = 180
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MODELS = {
    'hy18': {
        'bytes': 1133080448, 'sha256': 'dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699',
        'revision': 'b27182d810fa3ceb6ed04e7c324c54e35c0d209c', 'architecture': 'hunyuan-dense',
        'template_file': 'hymt_chat_template.jinja',
        'template_sha256': 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee',
        'embedded_template_sha256': ['b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee'],
        'sampling': {'temperature': 0.7, 'top_p': 0.6, 'top_k': 20, 'repeat_penalty': 1.05,
                     'min_p': 0.05, 'repeat_last_n': 64}},

}


def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_source(source):
    if not isinstance(source, str) or not source.strip() or len(source) > SOURCE_CHAR_LIMIT:
        raise ValueError('Source character bound or empty source')
    if len(source.splitlines()) != 1 or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in '\u2028\u2029' for c in source):
        raise ValueError('Source must be one line without control characters')
    if any(marker in source for marker in ('<｜', '<|', '<think>', '</think>', '<tool_response>')):
        raise ValueError('Reserved model/template marker in source')


FIXED_OLD_IDS = ('passive-02', 'passive-05', 'relationships-02', 'relationships-05', 'boundaries-02', 'omissions-05', 'placeholders-05', 'literal_text-01')
STRATA = {'name-word-person': 6, 'explicit-named-participant': 6, 'ordinary-named-entity': 4, 'matched-commonword-subword': 4, 'no-match-grammar-format': 4}


def policy():
    adapter_path = Path(__file__).resolve().parent.parent / 'luna-hy-glossary-policy-work/production_adapter.py'
    if digest(adapter_path) != ADAPTER_PIN:
        raise ValueError('Production adapter hash mismatch before import')
    import production_adapter
    if digest(Path(production_adapter.__file__)) != ADAPTER_PIN:
        raise ValueError('Production adapter hash mismatch')
    policy_path = adapter_path.with_name('glossary_policy.py')
    if not valid_hash(POLICY_PIN) or digest(policy_path) != POLICY_PIN:
        raise ValueError('Policy source freeze pending or mismatched before import')
    import glossary_policy
    if not valid_hash(POLICY_PIN) or digest(Path(glossary_policy.__file__)) != POLICY_PIN:
        raise ValueError('Policy source freeze pending or mismatched')
    return glossary_policy


def prepare_case(case):
    pair = policy().prepare_pair(case['source'], CANON)
    return pair


def experiment_cases(historical_fixture, fresh_fixture, design):
    if not valid_hash(FRESH_SHA):
        raise ValueError('Fresh source freeze PENDING; execution blocked')
    for path, expected in ((historical_fixture, HISTORICAL_SHA), (fresh_fixture, FRESH_SHA), (design, DESIGN_SHA), (CANON, CANON_SHA)):
        if digest(path) != expected:
            raise ValueError('Frozen input/design/canon mismatch')
    old = json.loads(historical_fixture.read_text(encoding='utf-8'))['cases']
    public = json.loads(fresh_fixture.read_text(encoding='utf-8'))
    if not isinstance(public, list) or len(public) != 24 or len(old) != 40:
        raise ValueError('Invalid source-only fixture schema/count')
    old_by_id = {case['id']: case for case in old}
    cases, seen, sources, counts = [], set(), set(), {}
    for split, group in (('historical', [old_by_id[i] for i in FIXED_OLD_IDS]), ('fresh', public)):
        for original in group:
            if split == 'fresh' and set(original) != {'id', 'stratum', 'source', 'target_entity_src', 'scenario_id'}:
                raise ValueError('Fresh fixture has non-public or missing fields')
            ident, source = original['id'], original['source']
            validate_source(source)
            if not isinstance(ident, str) or not ident or ident in seen or ident == SMOKE['id']:
                raise ValueError('Duplicate/invalid case identity')
            if source in sources or (split == 'fresh' and source in {c['source'] for c in old}):
                raise ValueError('Duplicate or historical-overlap source')
            seen.add(ident); sources.add(source)
            category = original['stratum'] if split == 'fresh' else 'regression'
            if split == 'fresh' and category not in STRATA:
                raise ValueError('Unknown preregistered stratum')
            if category in ('name-word-person', 'explicit-named-participant') and (not isinstance(original['target_entity_src'], str) or not isinstance(original['scenario_id'], str) or not original['scenario_id']):
                raise ValueError('Missing predeclared scenario/entity identifiers')
            if category in ('name-word-person', 'explicit-named-participant') and not original['target_entity_src']:
                raise ValueError('Target requires declared entity')
            key = (split, category)
            index = counts.get(key, 0); counts[key] = index + 1
            item = {'id': ident, 'source': source, 'category': category, 'split': split,
                    'entity_id': original.get('target_entity_src'), 'scenario_id': original.get('scenario_id')}
            pair = prepare_case(item)
            if category == 'no-match-grammar-format' and pair.matched_count != 0:
                raise ValueError('No-match control activates matcher')
            if category == 'matched-commonword-subword' and pair.matched_count == 0:
                raise ValueError('Homograph control fails to activate matcher')
            for arm in ('AB' if index % 2 == 0 else 'BA'):
                cases.append({**item, 'arm': arm, 'matched': [{'src': e.src, 'dst': e.dst} for e in pair.matched]})
    if counts != {('historical', 'regression'): 8, **{('fresh', k): v for k, v in STRATA.items()}}:
        raise ValueError('Preregistered stratum counts differ')
    return cases


def request_body(case, alias, model='hy18'):
    if model != 'hy18':
        raise ValueError('Only pinned Hy 1.8B is allowed')
    validate_source(case['source'])
    pair = prepare_case(case)
    return {'model': alias, 'messages': pair.messages(case.get('arm', 'A')),
            **MODELS['hy18']['sampling'], 'seed': 42, 'max_tokens': 512, 'cache_prompt': False, 'stream': False}


def template_body(case, alias, model='hy18'):
    return {'messages': request_body(case, alias, model)['messages'], 'add_generation_prompt': True}


def expected_prompt(case, alias, model='hy18'):
    content = request_body(case, alias, model)['messages'][0]['content']
    return '<｜hy_begin▁of▁sentence｜><｜hy_User｜>' + content + '<｜hy_Assistant｜>'


def checked_tokens(response):
    values = response.get('tokens')
    if not isinstance(values, list) or not 1 <= len(values) <= PROMPT_TOKEN_LIMIT or not all(type(t) is int and t >= 0 for t in values):
        raise ValueError('Invalid tokenizer response or full-prompt token bound exceeded')
    return len(values)


def preflight_tokens(cases, alias, model, call, record):
    records = []
    # ALL probes, including the smoke prompt, precede the first completion.
    for case in [SMOKE] + cases:
        request = template_body(case, alias, model)
        rendered = call('apply-template', request)
        if rendered.get('prompt') != expected_prompt(case, alias, model):
            raise ValueError('Applied prompt differs from pinned model template')
        token_request = {'content': rendered['prompt'], 'add_special': False, 'parse_special': True}
        token_response = call('tokenize', token_request)
        row = {'id': case['id'], 'split': case['split'], 'template_request': request,
               'template_response': rendered, 'prompt_request': token_request, 'prompt_response': token_response,
               'prompt_tokens': checked_tokens(token_response), 'arm': case.get('arm', 'A')}
        records.append(row)
        record(row)
    by_case = {}
    for case, record in zip([SMOKE] + cases, records):
        if case['id'] != SMOKE['id']:
            by_case.setdefault(case['id'], {})[case['arm']] = record['prompt_tokens']
    for values in by_case.values():
        policy().check_applied_token_counts(values['A'], values['B'])
    return records


def check_response(response, alias, prompt_tokens, smoke=False):
    if not isinstance(response, dict) or response.get('model') != alias:
        raise ValueError('Response model alias mismatch')
    choices = response.get('choices')
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('Expected exactly one output')
    choice = choices[0]
    message = choice.get('message', {})
    text = message.get('content')
    if choice.get('finish_reason') != 'stop' or not isinstance(text, str) or not text.strip():
        raise ValueError('Incomplete/empty output')
    # Never strip reasoning. Reject both parsed reasoning fields and visible tags.
    def reject_reasoning(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if ('reasoning' in key.lower() or key.lower() in ('thinking', 'thoughts')) and item not in (None, '', 0, False, [], {}):
                    raise ValueError('Hidden reasoning evidence present')
                reject_reasoning(item)
        elif isinstance(value, list):
            for item in value:
                reject_reasoning(item)
    reject_reasoning(response)
    if re.search(r'<\s*/?\s*(?:think|thinking|analysis)\b|<\|(?:im_start|im_end|analysis|channel)', text, re.I):
        raise ValueError('Visible reasoning/template marker in output')
    if message.get('tool_calls') or message.get('function_call'):
        raise ValueError('Unexpected tool output')
    if smoke and re.search(r'[\u3040-\u30ff\u31f0-\u31ff\uff65-\uff9f\U0001aff0-\U0001afff\U0001b000-\U0001b16f]', text):
        raise ValueError('Smoke output still contains Japanese kana')
    if smoke and not re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff\U00030000-\U000323af]', text):
        raise ValueError('Smoke output has no Chinese Han text; this sanity check is not an accuracy grade')
    usage = response.get('usage', {})
    if type(usage.get('prompt_tokens')) is not int or usage['prompt_tokens'] != prompt_tokens:
        raise ValueError('Actual prompt tokens differ from measured applied template')
    if type(usage.get('completion_tokens')) is not int or not 1 <= usage['completion_tokens'] <= 512:
        raise ValueError('Invalid completion token count')
    cached = usage.get('prompt_tokens_details', {}).get('cached_tokens')
    if type(cached) is not int or cached != 0:
        raise ValueError('Uncached-token evidence missing or prompt cache used')
    return text


def full_offload_proof(path, model_info):
    proof = check_startup_log(path, cuda=True, require_gpu=True)
    expected = model_info['expected_offloaded_layers']
    if (proof['offloaded_layers'], proof['total_layers']) != (expected, expected):
        raise RuntimeError('Actual full CUDA offload does not match GGUF block_count + 1')
    return proof


def build_command(server, gguf, port, alias, template, model):
    command = [str(server), '-lv', '4', '--log-colors', 'off', '--no-log-jsonl', '--no-warmup',
               '-m', str(gguf), '--host', '127.0.0.1', '--port', str(port), '--alias', alias,
               '-c', '2048', '-t', '2', '-tb', '2', '-np', '1', '-ngl', '99', '-b', '128', '-ub', '128',
               '--chat-template-file', str(template), '--cors-origins', 'http://127.0.0.1:' + str(port), '--device', 'CUDA0']
    if model != 'hy18':
        raise ValueError('Only Hy1.8B is authorized')
    return command


def code_hashes():
    directory = SUPPORT
    files = [Path(__file__), directory / 'threeway_safety.py', directory / 'threeway_model_preflight.py',
             directory / 'resources.py', ROOT / 'src/LunaTranslator/myutils/local_translation.py',
             ROOT / 'src/LunaTranslator/myutils/local_translation_integrity.py']
    return {**{path.name: digest(path) for path in files}, **{name: digest(ROOT / name) for name in REVIEWED_SOURCE_PINS}}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def append_json(file, value):
    file.write(json.dumps(value, ensure_ascii=False) + '\n')
    file.flush()


class OwnedProcessCleanupError(RuntimeError):
    """Termination was not established; a later model arm must remain blocked."""


class ModelOwnership:
    def __init__(self):
        self.termination_confirmed = True

    def starting_child(self):
        # Claim before Popen: an exception during launch must not imply safety.
        self.termination_confirmed = False

    def confirm_stopped(self, proc):
        if proc.poll() is None:
            raise OwnedProcessCleanupError('Owned child is still running')
        self.termination_confirmed = True


@contextmanager
def owned_model_lock(path=None):
    """One participating runner per machine; never erase another/stale lock."""
    path = Path(path) if path is not None else Path(tempfile.gettempdir()) / 'luna-threeway-model.lock'
    owner = uuid.uuid4().hex
    with path.open('x', encoding='ascii') as lock:
        lock.write(owner)
    ownership = ModelOwnership()
    returned_normally = False
    try:
        yield ownership
        returned_normally = True
    except OwnedProcessCleanupError:
        ownership.termination_confirmed = False
        raise
    finally:
        if ownership.termination_confirmed:
            if path.read_text(encoding='ascii') != owner:
                raise RuntimeError('Owned model lock changed; refusing to delete another owner lock')
            path.unlink()
        elif returned_normally:
            raise OwnedProcessCleanupError('Owned child termination is unconfirmed; model lock retained')


class WireClient:
    def __init__(self, port, wire, start):
        self.port, self.wire, self.start = port, wire, start
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.sequence, self.deadline = 0, None

    def call(self, endpoint, body=None, timeout=5):
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        now = time.perf_counter()
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - now)
        if timeout <= 0:
            raise TimeoutError('Owned-process request budget exhausted')
        self.sequence += 1
        entry = {'sequence': self.sequence, 'endpoint': endpoint, 'started_seconds': now - self.start,
                 'request_base64': base64.b64encode(payload or b'').decode('ascii'),
                 'request_sha256': hashlib.sha256(payload or b'').hexdigest()}
        request = urllib.request.Request('http://127.0.0.1:%d/%s' % (self.port, endpoint),
                                        data=payload, headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                entry.update(status=response.status, response_base64=base64.b64encode(raw).decode('ascii'),
                             response_sha256=hashlib.sha256(raw).hexdigest())
                if len(raw) > MAX_RESPONSE_BYTES or response.status != 200:
                    raise ValueError('Excessive or unsuccessful server response')
                return json.loads(raw)
        except BaseException as exc:
            entry['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            entry['finished_seconds'] = time.perf_counter() - self.start
            append_json(self.wire, entry)


def start_owned_watchdog(proc, deadline):
    """Use the HTTP phase's absolute deadline, including pre-timer setup time."""
    guard = InferenceDeadline(proc, seconds=max(0.0, deadline - time.perf_counter()))
    guard.start()
    return guard


def budget_exceeded(guard, deadline, observed_at):
    """A due deadline remains exceeded even if its timer callback was delayed."""
    return guard.expired.is_set() or observed_at >= deadline


def base_metadata(model, cases):
    spec = MODELS[model]
    return {'schema_version': 1, 'experiment': EXPERIMENT, 'status': 'incomplete', 'model': model,
            'model_spec': spec, 'design_sha256': DESIGN_SHA, 'fresh_fixture_sha256': FRESH_SHA,
            'historical_fixture_sha256': HISTORICAL_SHA, 'code_sha256': code_hashes(),
            'prompt_template': PROMPT_TEMPLATE, 'prompt_template_sha256': sha_text(PROMPT_TEMPLATE),
            'source_char_limit': SOURCE_CHAR_LIMIT, 'prompt_token_limit': PROMPT_TOKEN_LIMIT,
            'context': 2048, 'threads': 2, 'batch': 128, 'ubatch': 128, 'slots': 1,
            'backend': 'cuda', 'gpu_layers': 99, 'runtime_warmup': False,
            'cors_policy': 'owned loopback origin only', 'startup_budget_seconds': STARTUP_BUDGET_SECONDS,
            'inference_budget_seconds': INFERENCE_BUDGET_SECONDS, 'case_count': 32,
            'smoke_request_count': 1, 'scored_request_count': 64, 'probe_count': 130,
            'order': 'historical8 then fresh24; within-stratum alternating AB/BA; all130 probes then smoke then64 outputs',
            'canon_sha256': CANON_SHA, 'policy_sha256': POLICY_PIN, 'adapter_sha256': ADAPTER_PIN, 'production_source_sha256': policy().SOURCE_HASHES, 'runtime_pin_sha256': RUNTIME_PIN_SHA,
            'cases': [{**case, 'source_sha256': sha_text(case['source'])} for case in cases],
            'startup_checks': {'security_warning_gate': 'pending', 'cuda_proof': None},
            'smoke_status': 'pending', 'owned_process_stopped': False}


def claim_record(out):
    return {'experiment': EXPERIMENT, 'design_sha256': DESIGN_SHA, 'fresh_fixture_sha256': FRESH_SHA,
            'runner_sha256': digest(__file__), 'run_id': uuid.uuid4().hex,
            'requested_output': str(out.resolve()), 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


def check_claim(record):
    expected = {'experiment': EXPERIMENT, 'design_sha256': DESIGN_SHA, 'fresh_fixture_sha256': FRESH_SHA,
                'runner_sha256': digest(__file__)}
    if set(record) != set(expected) | {'run_id', 'requested_output', 'created_utc'} or any(record.get(k) != v for k, v in expected.items()):
        raise ValueError('Persistent claim experiment/source/code identity mismatch')
    if not isinstance(record['run_id'], str) or not re.fullmatch('[0-9a-f]{32}', record['run_id']):
        raise ValueError('Invalid persistent claim run identity')
    if not isinstance(record['requested_output'], str) or not record['requested_output'] or not isinstance(record['created_utc'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', record['created_utc']):
        raise ValueError('Invalid persistent claim destination/timestamp')
    return record


def run_owned(a, cases, spec, model_record, model_info, available, probe, gpu, version, runtime_files, ownership=None):
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1', 0))
        port = port_probe.getsockname()[1]
    alias = 'luna-threeway-' + a.model + '-' + uuid.uuid4().hex
    template = (SUPPORT / spec['template_file']).resolve()
    command = build_command(a.server.resolve(), a.gguf.resolve(), port, alias, template, a.model)
    child_env = os.environ.copy()
    child_env['CUDA_VISIBLE_DEVICES'] = gpu['uuid']
    # Explicit command determines behavior; inherited llama.cpp setting overrides are prohibited.
    inherited = [key for key in child_env if key.startswith('LLAMA_ARG_')]
    if inherited:
        raise ValueError('Remove inherited LLAMA_ARG_* overrides before this experiment')
    claim_bytes = a.claim_path.read_bytes()
    claim = check_claim(json.loads(claim_bytes))
    if claim['requested_output'] != str(a.out.resolve()):
        raise ValueError('Persistent claim output destination mismatch')
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'run-claim.json').write_bytes(claim_bytes)
    meta = base_metadata(a.model, cases)
    meta.update(run_id=claim['run_id'], claim_sha256=hashlib.sha256(claim_bytes).hexdigest(), claimed_output=claim['requested_output'], command=command, alias=alias, runtime_version=version, runtime_files_sha256=runtime_files,
                server_sha256=digest(a.server), nvidia_smi_sha256=digest(a.nvidia_smi),
                model_metadata=model_info, memory_available_before=available, gpu=gpu,
                model_bytes_observed=a.gguf.stat().st_size, model_sha256_observed=digest(a.gguf),
                template_sha256_observed=digest(template), platform=platform.platform(),
                started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                timing_clock=vars(time.get_clock_info('perf_counter')))
    write_json(a.out / 'model-metadata.json', model_record)
    write_json(a.out / 'metadata.json', meta)
    proc, monitors, startup_guard, inference_guard, ready_start = None, [], None, None, None
    start = time.perf_counter()
    startup_deadline = start + STARTUP_BUDGET_SECONDS
    inference_deadline = None
    with (a.out / 'server.log').open('w', encoding='utf-8') as log, (a.out / 'wire.jsonl').open('w', encoding='utf-8') as wire, (a.out / 'token-preflight.jsonl').open('w', encoding='utf-8') as probes_out, (a.out / 'results.jsonl').open('w', encoding='utf-8') as results:
        client = WireClient(port, wire, start)
        try:
            # Fresh resource gate after every hash/version probe, immediately before Popen.
            fresh_ram, fresh_gpu = memory_available(), probe.gpu()
            if fresh_ram < spec['bytes'] + 2300 * MIB or fresh_gpu['uuid'] != gpu['uuid'] or fresh_gpu['free_bytes'] < spec['bytes'] + 1024 * MIB:
                raise ValueError('Available RAM/VRAM fell below model-specific reserve')
            meta.update(memory_available_before=fresh_ram, gpu=fresh_gpu)
            if ownership is not None:
                ownership.starting_child()
            proc = subprocess.Popen(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=child_env)
            startup_guard = start_owned_watchdog(proc, startup_deadline)
            ram = RamMonitor(proc, fresh_ram)
            monitors = [ram, GpuMonitor(proc, probe, gpu['uuid'])]
            for monitor in monitors:
                monitor.thread.start()
            def alive():
                if proc.poll() is not None or ram.samples['resource_guard_stopped_process']:
                    raise RuntimeError('Owned process exited or resource guard stopped execution')
                check_startup_log(a.out / 'server.log')
            client.deadline = startup_deadline
            while True:
                alive()
                if budget_exceeded(startup_guard, startup_deadline, time.perf_counter()):
                    raise TimeoutError('Owned-process startup watchdog expired')
                try:
                    health = client.call('health')
                    models = client.call('v1/models')
                    ready = health.get('status') == 'ok' and alias in [item['id'] for item in models['data']]
                except (OSError, ValueError, KeyError):
                    ready = False
                if ready:
                    meta['startup_checks'] = {'security_warning_gate': 'passed', 'cuda_proof': full_offload_proof(a.out / 'server.log', model_info)}
                    break
                if time.perf_counter() >= client.deadline:
                    raise TimeoutError('Model readiness timeout')
                time.sleep(.2)
            startup_guard.close()
            ready_start = time.perf_counter()
            if budget_exceeded(startup_guard, startup_deadline, ready_start) or startup_guard.error:
                raise TimeoutError('Startup watchdog expired or cleanup failed')
            meta['startup_seconds'] = ready_start - start
            meta['ready_at_seconds'] = ready_start - start
            inference_deadline = ready_start + INFERENCE_BUDGET_SECONDS
            client.deadline = inference_deadline
            inference_guard = start_owned_watchdog(proc, inference_deadline)
            def bounded_call(endpoint, body):
                alive()
                return client.call(endpoint, body, timeout=INFERENCE_BUDGET_SECONDS)
            token_start = time.perf_counter()
            token_records = preflight_tokens(cases, alias, a.model, bounded_call, lambda row: append_json(probes_out, row))
            meta['token_probe_seconds'] = time.perf_counter() - token_start
            for index, case in enumerate([SMOKE] + cases):
                alive()
                body = request_body(case, alias, a.model)
                request_start = time.perf_counter()
                response = bounded_call('v1/chat/completions', body)
                row = {'id': case['id'], 'split': case['split'], 'category': case['category'], 'arm': case.get('arm', 'A'), 'request': body,
                       'response': response, 'wire_sequence': client.sequence,
                       'seconds': time.perf_counter() - request_start, 'validation': 'pending'}
                try:
                    text = check_response(response, alias, token_records[index]['prompt_tokens'], smoke=index == 0)
                    row.update(format=check_format(case['source'], text), validation='passed')
                except BaseException as exc:
                    row['validation'] = type(exc).__name__ + ': ' + str(exc)
                    raise
                finally:
                    if index == 0:
                        write_json(a.out / 'smoke.json', row)
                    else:
                        append_json(results, row)
                if index == 0:
                    meta['smoke_status'] = 'passed'
                    meta['smoke_seconds'] = row['seconds']
                    meta['batch_started_at_seconds'] = time.perf_counter() - start
            alive()
            if budget_exceeded(inference_guard, inference_deadline, time.perf_counter()):
                raise TimeoutError('Post-readiness watchdog expired')
            full_offload_proof(a.out / 'server.log', model_info)
            if budget_exceeded(inference_guard, inference_deadline, time.perf_counter()):
                raise TimeoutError('Post-readiness budget expired during final validation')
            meta['status'] = 'complete'
        except BaseException as exc:
            meta['failure'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            # Snapshot callbacks before the operation-end clock. A callback that
            # runs during cleanup must not retroactively overrun a completed phase.
            fired_at_end = {field: guard.expired.is_set() for guard, field in
                            ((startup_guard, 'startup'), (inference_guard, 'inference')) if guard is not None}
            end = time.perf_counter()
            meta['post_ready_seconds'] = None if ready_start is None else end - ready_start
            late_failure = None
            for guard, field, deadline, observed_at in (
                    (startup_guard, 'startup', startup_deadline, ready_start if ready_start is not None else end),
                    (inference_guard, 'inference', inference_deadline, end)):
                if guard is not None:
                    guard.close()
                    meta[field + '_watchdog_fired'] = guard.expired.is_set()
                    meta[field + '_budget_exceeded'] = fired_at_end[field] or observed_at >= deadline
                    if guard.error:
                        meta[field + '_stop_error'] = guard.error
                    if meta[field + '_budget_exceeded'] or guard.error:
                        meta['status'] = 'incomplete'
                        if 'failure' not in meta:
                            late_failure = (TimeoutError(field + ' budget expired before cleanup')
                                            if meta[field + '_budget_exceeded'] else RuntimeError(guard.error))
                            meta['failure'] = type(late_failure).__name__ + ': ' + str(late_failure)
            for monitor in monitors:
                monitor.stop.set()
            for monitor in monitors:
                if monitor.thread.ident is not None:
                    monitor.thread.join(timeout=7)
            try:
                if proc is not None:
                    stop_owned(proc)
                    meta['owned_process_stopped'] = proc.poll() is not None
                    if ownership is not None:
                        ownership.confirm_stopped(proc)
            except BaseException as exc:
                meta['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
                meta['status'] = 'incomplete'
            for monitor in monitors:
                meta.update(monitor.samples)
            if not meta['owned_process_stopped'] or meta.get('resource_guard_stopped_process') or any(m.thread.is_alive() for m in monitors):
                meta['status'] = 'incomplete'
            write_json(a.out / 'metadata.json', meta)
            log.flush()
            write_json(a.out / 'manifest.json', {f.name: digest(f) for f in a.out.iterdir() if f.is_file() and f.name != 'manifest.json'})
            if meta.get('cleanup_error') or (proc is not None and not meta['owned_process_stopped']):
                raise OwnedProcessCleanupError('Owned process termination is unconfirmed; model lock retained; review incomplete evidence')
            if late_failure is not None:
                raise late_failure


def verify_runtime_pins(path, server, driver):
    if not valid_hash(RUNTIME_PIN_SHA) or digest(path) != RUNTIME_PIN_SHA:
        raise ValueError('Runtime/server/driver pin freeze PENDING or mismatched')
    pins = json.loads(path.read_text(encoding='utf-8'))
    if not {'runtime_files_sha256', 'nvidia_smi_sha256', 'server_sha256', 'runtime_version'} <= set(pins):
        raise ValueError('Runtime pins must specify full runtime inventory and driver hash')
    actual = {f.name: digest(f) for f in server.resolve().parent.iterdir() if f.is_file() and (f.suffix.lower() == '.dll' or '.so' in f.name or f.suffix.lower() == '.dylib')}
    actual[server.name] = digest(server)
    if not pins['runtime_files_sha256'] or actual != pins['runtime_files_sha256'] or digest(driver) != pins['nvidia_smi_sha256']:
        raise ValueError('Full runtime/server/driver hashes differ from frozen pins')
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('hy18',), default='hy18')
    parser.add_argument('--runtime-pins', type=Path, required=True)
    for flag in ('gguf', 'server', 'out', 'historical-fixture', 'fresh-fixture', 'design', 'nvidia-smi'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--gpu-index', type=int, default=0)
    parser.add_argument('--restrict-cors-to-loopback', action='store_true')
    a = parser.parse_args()
    if not a.restrict_cors_to_loopback or a.gpu_index < 0:
        parser.error('Explicit owned-loopback CORS restriction and nonnegative GPU index are required')
    try:
        pins = verify_runtime_pins(a.runtime_pins, a.server, a.nvidia_smi)
        cases = experiment_cases(a.historical_fixture, a.fresh_fixture, a.design)
        spec = MODELS[a.model]
        template = SUPPORT / spec['template_file']
        if digest(template) != spec['template_sha256']:
            raise ValueError('Official template hash mismatch')
        if a.gguf.stat().st_size != spec['bytes'] or digest(a.gguf) != spec['sha256']:
            raise ValueError('Model bytes differ from pinned GGUF')
        model_record = read_metadata(a.gguf)
        model_info = validate_metadata(model_record, spec)
        available = memory_available()
        if type(available) is not int or available < spec['bytes'] + 2300 * MIB:
            raise ValueError('Insufficient/unknown RAM for weights plus 2300 MiB')
        probe = NvidiaProbe(a.nvidia_smi, a.gpu_index)
        gpu = probe.gpu()
        if gpu['free_bytes'] < spec['bytes'] + 1024 * MIB:
            raise ValueError('Insufficient measured VRAM for weights plus 1024 MiB')
        version = subprocess.check_output([str(a.server.resolve()), '--version'], stderr=subprocess.STDOUT,
                                         encoding='utf-8', errors='replace', timeout=15)
        if version != pins['runtime_version']:
            raise ValueError('Pinned b11349 runtime required; version is not a signature')
        runtime_files = {f.name: digest(f) for f in sorted(a.server.resolve().parent.iterdir()) if f.is_file() and (f.suffix == '.dll' or '.so' in f.name or f.suffix == '.dylib')}
        runtime_files[a.server.name] = digest(a.server)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    with owned_model_lock() as ownership:
        if a.out.exists():
            raise FileExistsError('Output must be a new directory')
        claim_path = Path(tempfile.gettempdir()) / (EXPERIMENT + '-' + DESIGN_SHA + '.claimed')
        with claim_path.open('x', encoding='utf-8') as claim:
            json.dump(claim_record(a.out), claim, ensure_ascii=False, indent=2)
        a.claim_path = claim_path
        run_owned(a, cases, spec, model_record, model_info, available, probe, gpu, version, runtime_files, ownership)


if __name__ == '__main__':
    main()
