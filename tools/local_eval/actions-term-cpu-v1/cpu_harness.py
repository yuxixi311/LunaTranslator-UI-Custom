"""Pure CPU protocol core; native execution belongs to reviewed adapters.

run_real() remains unconditionally disabled. Authorization is defined by the
frozen protocol and separate conditional Actions admission policy. No production
claim writer, acquisition client, Popen, socket or native CLI is present here.
"""
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import posixpath
import re
import statistics
import tempfile
from urllib.parse import urljoin, urlsplit
import uuid
import actions_policy


MIB = 1024 ** 2
GIB = 1024 ** 3
PINS = {'resources': '35d69a8339ad2773e4fe0b89acba2092a2710568ff08da58e62e524af900dfbe', 'integrity': '74b9e650d51e38f46db25f26b2018ae4dad2a3d4cbaa086110e0e4fffdbd22de', 'integrity_dependency': '585983e55e7ede288085b10f8bced19fd519d9e02fd718a9f2abf9c9214d4fa0', 'template': 'b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee', 'model': 'dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699', 'runtime_archive': '7efd2fb72db59f12b05614a709ba6d506b9859e867943955fc9bbd8ee13eccea', 'server': 'f1fe3730c84c6fb397e6807bf6bc7b9572f322dcaa1f342ad1b4c92dca74bce8', 'scope': 'd1fae404199f421ec3111daa854513eb92ff6a1a5609ef8ff1a9a065b0c33ef4', 'design': 'fabd4e3584908ec6bc4bc46b4fd0773092c3a9207a93a850332b256376ca3b12', 'renderer': 'f621ddec3e4cb7d449693f1ffb28a169276eabf5e7e49441d973d0868f3c2cca', 'declarations': 'f7d849ae54ec36d8247aeaadedd633523de92df35313c7bebb3a2073baeccd3b', 'fresh_sources': '83918221ae47cd7be8e863f0f0f5b3b2af8af146fa117ee663093df9ad84fba8', 'sources88': 'a98baa95cb520090d21176f03774c63ce5e0d1caca4e5ff6a10e7ed6bd72c9a8', 'coverage19': 'c754eb4e34f612034a03e646666dd2f707a8cae182762c5364ae9739bbb8e541', 'schedule88': '4aa12fb23ebbc1bb1a2a2fe31f4d4dda400ec0ddb0fc42ed7d11564400e97f2f', 'SOURCE_ONLY_AUDIT': 'a39c8bb5c57d3e86c759693a1829dac93c46cc2f4373087934a09207177e3178'}

ASSETS = (
    ('https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/b27182d810fa3ceb6ed04e7c324c54e35c0d209c/Hy-MT2-1.8B-Q4_K_M.gguf', 1133080448, PINS['model']),
    ('https://github.com/ggml-org/llama.cpp/releases/download/b11349/llama-b11349-bin-ubuntu-x64.tar.gz', 17551895, PINS['runtime_archive']),
)
REDIRECT_POLICY = ()  # Intentionally EMPTY; no acquisition release possible.
SAMPLING = dict(temperature=.7, top_p=.6, top_k=20, repeat_penalty=1.05,
                min_p=.05, repeat_last_n=64, seed=42, max_tokens=512,
                cache_prompt=False, stream=False)
LIMITS = dict(pairs=88, new_rows=19, legacy_rows=40, seen_rows=15, glossary_rows=14, eligible=12,
    completions=176, preflight_counts=176, recurring_counts=24, http=398, planned_http=378,
    health=1, models=1, asset_gets=2, asset_exchanges=8, asset_redirects=3,
    asset_bytes=1150632343, expanded_bytes=512*MIB, archive_members=1024,
    evidence_bytes=64*MIB, staging_growth=2*GIB, initial_disk=3*GIB,
    minimum_disk=GIB, startup_ram=3544805248, runtime_ram=768*MIB,
    server_rss=4*GIB, helper_rss=32*MIB, monitor_ms=50,
    request_bytes=32768, request_headers=8192, response_headers=16384,
    header_fields=64, header_line=2048, chunk_count=1024,
    chunk_line=128, chunk_framing=16384, asset_read_chunk=65536,
    loopback_read_chunk=8192, acquisition_seconds=600, validation_seconds=60,
    version_seconds=15, startup_seconds=180, postready_seconds=600,
    preflight_seconds=60, helper_seconds=15, work_seconds=780,
    lifecycle_seconds=800, cleanup_seconds=20, outer_seconds=1475,
    count_seconds=5, completion_seconds=60, generated_tokens=90112,
    generation_prompt_tokens=67584, combined_tokens=157696,
    helper_priming=0, helper_measured=88, helper_total=176, helper_gate_commands=24, helper_restore_commands=12, helper_parent_commands=214)
ENDPOINTS = {'health': ('GET', '/health', 4096, 5),
             'models': ('GET', '/v1/models', 16384, 5),
             'preflight': ('POST', '/v1/chat/completions/input_tokens', 4096, 5),
             'recurring': ('POST', '/v1/chat/completions/input_tokens', 4096, 5),
             'completion': ('POST', '/v1/chat/completions', 65536, 60)}
OUTPUT_REVISION_SHA256 = '2582e44d9dffca44c01e9379cdf9e78188dab49b9d83ef732b42def1635101d3'
OUTPUT_POLICY = {
    'schema_version': 3,
    'total_retained_bytes': 64*MIB,
    'fixed_root': '__BOUND_ACTIONS_STATE_ROOT__',
    'fixed_files': {
        'ONE_SHOT_CPU_ATTEMPT.json': {'schema':'immutable_claim_object','max_bytes':32768},
        'ONE_SHOT_CPU_EVENTS.jsonl': {'schema':'append_only_event_jsonl','max_bytes':64*MIB}},
    'output_files': {
        'metadata.json': {'schema':'phase_measurement_status_jsonl','max_bytes':64*MIB},
        'wire.jsonl': {'schema':'request_response_wire_hex_jsonl','max_bytes':64*MIB},
        'results.jsonl': {'schema':'measured_arm_output_usage_jsonl','max_bytes':64*MIB},
        'all_rows.json': {'schema':'fixed_88_row_observation_array','max_bytes':64*MIB},
        'manifest.json': {'schema':'derived_hash_size_manifest_object','max_bytes':64*MIB},
        'server.log': {'schema':'combined_owned_stdout_stderr','max_bytes':64*MIB},
        'version.log': {'schema':'combined_owned_stdout_stderr','max_bytes':65536},
        'validation.log': {'schema':'bounded_validation_diagnostics','max_bytes':65536},
        'archive_members.json': {'schema':'pinned_archive_member_manifest','max_bytes':MIB},
        'helper.log': {'schema':'helper_measurement_object','max_bytes':65536},
        'helper_input.json': {'schema':'legacy_disabled_helper_input','max_bytes':MIB},
        'helper_closure.json': {'schema':'immutable_term_helper_source_closure','max_bytes':32768},
        'helper_binding.json': {'schema':'immutable_term_helper_parent_source_deadline_binding','max_bytes':32768},
        'protocol_reconciliation.json': {'schema':'complete_protocol_cost_evidence_object','max_bytes':64*MIB},
        **{name:{'schema':'closed_finite_diagnostic' if name=='public/diagnostic.json' else 'closed_authorized_public_evidence',
                'max_bytes':4096 if name=='public/diagnostic.json' else 16*MIB} for name in actions_policy.PUBLIC_FILES}},
    'creation':'exclusive_no_follow_owner_only',
    'unknown_files':'reject',
    'already_created_claim':'charge_before_later_stages',
}


class TerminalFailure(Exception):
    """No later phase, retry, repair, or row omission is permitted."""


class Disabled(TerminalFailure):
    pass


def require(condition, message):
    if not condition:
        raise TerminalFailure(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def digest(data):
    return sha256(data).hexdigest()


def alias_for(attempt_id):
    require(type(attempt_id) is str and re.fullmatch('[0-9a-f]{32}', attempt_id), 'attempt ID')
    parsed = uuid.UUID(hex=attempt_id)
    require(parsed.version == 4 and parsed.variant == uuid.RFC_4122, 'UUIDv4 required')
    return 'luna-term-lock-v1-hymt18-q4-' + attempt_id


def validate_alias(alias):
    require(type(alias) is str and re.fullmatch(r'luna-term-lock-v1-hymt18-q4-[0-9a-f]{32}', alias), 'alias')
    require(alias_for(alias[-32:]) == alias, 'alias UUID')


# Explicit copied arm-order data from the hash-bound reviewed V2 projection.
# Native input loading independently verifies the projection's exact raw hash.
SCHEDULE = (('R001', 'baseline'), ('R001', 'candidate'), ('R002', 'candidate'), ('R002', 'baseline'), ('R003', 'baseline'), ('R003', 'candidate'), ('R004', 'candidate'), ('R004', 'baseline'), ('R005', 'baseline'), ('R005', 'candidate'), ('R006', 'candidate'), ('R006', 'baseline'), ('R007', 'baseline'), ('R007', 'candidate'), ('R008', 'candidate'), ('R008', 'baseline'), ('R009', 'baseline'), ('R009', 'candidate'), ('R010', 'candidate'), ('R010', 'baseline'), ('R011', 'baseline'), ('R011', 'candidate'), ('R012', 'candidate'), ('R012', 'baseline'), ('R013', 'baseline'), ('R013', 'candidate'), ('R014', 'candidate'), ('R014', 'baseline'), ('R015', 'baseline'), ('R015', 'candidate'), ('R016', 'candidate'), ('R016', 'baseline'), ('R017', 'baseline'), ('R017', 'candidate'), ('R018', 'candidate'), ('R018', 'baseline'), ('R019', 'baseline'), ('R019', 'candidate'), ('R020', 'candidate'), ('R020', 'baseline'), ('R021', 'baseline'), ('R021', 'candidate'), ('R022', 'candidate'), ('R022', 'baseline'), ('R023', 'baseline'), ('R023', 'candidate'), ('R024', 'candidate'), ('R024', 'baseline'), ('R025', 'baseline'), ('R025', 'candidate'), ('R026', 'candidate'), ('R026', 'baseline'), ('R027', 'baseline'), ('R027', 'candidate'), ('R028', 'candidate'), ('R028', 'baseline'), ('R029', 'baseline'), ('R029', 'candidate'), ('R030', 'candidate'), ('R030', 'baseline'), ('R031', 'baseline'), ('R031', 'candidate'), ('R032', 'candidate'), ('R032', 'baseline'), ('R033', 'baseline'), ('R033', 'candidate'), ('R034', 'candidate'), ('R034', 'baseline'), ('R035', 'baseline'), ('R035', 'candidate'), ('R036', 'candidate'), ('R036', 'baseline'), ('R037', 'baseline'), ('R037', 'candidate'), ('R038', 'candidate'), ('R038', 'baseline'), ('R039', 'baseline'), ('R039', 'candidate'), ('R040', 'candidate'), ('R040', 'baseline'), ('S001', 'baseline'), ('S001', 'candidate'), ('S002', 'candidate'), ('S002', 'baseline'), ('S003', 'baseline'), ('S003', 'candidate'), ('S004', 'candidate'), ('S004', 'baseline'), ('S005', 'baseline'), ('S005', 'candidate'), ('S006', 'candidate'), ('S006', 'baseline'), ('S007', 'baseline'), ('S007', 'candidate'), ('S008', 'candidate'), ('S008', 'baseline'), ('S009', 'baseline'), ('S009', 'candidate'), ('S010', 'candidate'), ('S010', 'baseline'), ('S011', 'baseline'), ('S011', 'candidate'), ('S012', 'candidate'), ('S012', 'baseline'), ('S013', 'baseline'), ('S013', 'candidate'), ('S014', 'candidate'), ('S014', 'baseline'), ('S015', 'baseline'), ('S015', 'candidate'), ('person-01', 'baseline'), ('person-01', 'candidate'), ('person-03', 'candidate'), ('person-03', 'baseline'), ('participant-01', 'baseline'), ('participant-01', 'candidate'), ('participant-02', 'candidate'), ('participant-02', 'baseline'), ('participant-03', 'baseline'), ('participant-03', 'candidate'), ('participant-04', 'candidate'), ('participant-04', 'baseline'), ('participant-05', 'baseline'), ('participant-05', 'candidate'), ('participant-06', 'candidate'), ('participant-06', 'baseline'), ('entity-02', 'baseline'), ('entity-02', 'candidate'), ('negative-01', 'baseline'), ('negative-01', 'candidate'), ('negative-02', 'candidate'), ('negative-02', 'baseline'), ('negative-03', 'baseline'), ('negative-03', 'candidate'), ('negative-04', 'candidate'), ('negative-04', 'baseline'), ('nomatch-01', 'candidate'), ('nomatch-01', 'baseline'), ('tl-fresh-01', 'baseline'), ('tl-fresh-01', 'candidate'), ('tl-fresh-02', 'candidate'), ('tl-fresh-02', 'baseline'), ('tl-fresh-03', 'baseline'), ('tl-fresh-03', 'candidate'), ('tl-fresh-04', 'candidate'), ('tl-fresh-04', 'baseline'), ('tl-fresh-05', 'baseline'), ('tl-fresh-05', 'candidate'), ('tl-fresh-06', 'candidate'), ('tl-fresh-06', 'baseline'), ('tl-fresh-07', 'baseline'), ('tl-fresh-07', 'candidate'), ('tl-fresh-08', 'candidate'), ('tl-fresh-08', 'baseline'), ('tl-fresh-09', 'baseline'), ('tl-fresh-09', 'candidate'), ('tl-fresh-10', 'candidate'), ('tl-fresh-10', 'baseline'), ('tl-fresh-11', 'baseline'), ('tl-fresh-11', 'candidate'), ('tl-fresh-12', 'candidate'), ('tl-fresh-12', 'baseline'), ('tl-fresh-13', 'candidate'), ('tl-fresh-13', 'baseline'), ('tl-fresh-14', 'baseline'), ('tl-fresh-14', 'candidate'), ('tl-fresh-15', 'candidate'), ('tl-fresh-15', 'baseline'), ('tl-fresh-16', 'baseline'), ('tl-fresh-16', 'candidate'), ('tl-fresh-17', 'candidate'), ('tl-fresh-17', 'baseline'), ('tl-fresh-18', 'baseline'), ('tl-fresh-18', 'candidate'), ('tl-fresh-19', 'candidate'), ('tl-fresh-19', 'baseline'))
ROW_IDS = tuple(row for row,_ in SCHEDULE[::2])
SCHEDULE_SHA256 = digest(canonical(SCHEDULE))
ELIGIBLE_IDS = frozenset(('tl-fresh-01', 'tl-fresh-02', 'tl-fresh-03', 'tl-fresh-04', 'tl-fresh-05', 'tl-fresh-06', 'tl-fresh-07', 'tl-fresh-08', 'tl-fresh-09', 'tl-fresh-10', 'tl-fresh-11', 'tl-fresh-12'))


def serialize_request(messages, alias):
    validate_alias(alias)
    require(type(messages) is list and len(messages) == 1 and
            type(messages[0]) is dict and set(messages[0]) == {'role', 'content'} and
            messages[0]['role'] == 'user' and type(messages[0]['content']) is str, 'one-user messages')
    body = canonical(dict(model=alias, messages=messages, **SAMPLING))
    require(len(body) <= LIMITS['request_bytes'], 'request body cap')
    return body


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def strict_json(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=no_duplicate_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(TerminalFailure('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise TerminalFailure('invalid JSON') from exc


def token_response(raw):
    data = strict_json(raw)
    require(type(data) is dict and set(data) == {'object', 'input_tokens'} and
            data['object'] == 'response.input_tokens' and
            type(data['input_tokens']) is int and data['input_tokens'] > 0, 'token response schema')
    return data['input_tokens']


def readiness_response(kind, raw, alias):
    data = strict_json(raw)
    require(type(data) is dict, 'readiness schema')
    if kind == 'health':
        require(data.get('status') == 'ok', 'unhealthy owned server')
    else:
        require(kind == 'models' and type(data.get('data')) is list and len(data['data']) == 1 and
                type(data['data'][0]) is dict and data['data'][0].get('id') == alias, 'unique alias mismatch')


@dataclass(frozen=True)
class CountReceipt:
    body: bytes
    count: int
    runtime: str = PINS['server']
    model_tokenizer: str = PINS['model']
    template: str = PINS['template']

    @property
    def binding(self):
        return dict(request_sha256=digest(self.body), input_tokens=self.count,
                    runtime=self.runtime, model_tokenizer=self.model_tokenizer, template=self.template)


@dataclass(frozen=True)
class PairPlan:
    row_id: str
    baseline: CountReceipt
    provisional: CountReceipt
    candidate: CountReceipt
    eligible: bool
    active: bool
    reason: str


def preflight_pair(row_id, source, alias, lexicon, lexicon_sha, renderer, count):
    """Exactly TWO real counts. count(bytes) returns strict verified integer.

    The renderer's first callback reuses the count just made for the baseline.
    No preflight count may substitute for either measured eligible callback.
    """
    raise Disabled('Superseded broad-prefix study path; use UsageCore')
    baseline_messages = renderer.baseline_messages(source)
    body = serialize_request(baseline_messages, alias)
    base_count = count(body)
    require(type(base_count) is int and 1 <= base_count <= 384, 'baseline token budget')
    baseline = CountReceipt(body, base_count)
    calls, errors, receipts = [], [], []

    def counter(messages):
        try:
            request = body if messages == baseline_messages else serialize_request(messages, alias)
            calls.append(request)
            if len(calls) == 1:
                require(request == body, 'first callback must be baseline')
                value = base_count
            else:
                require(len(calls) == 2, 'extra renderer callback')
                value = count(request)
                require(type(value) is int and value >= base_count, 'inconsistent candidate count')
            receipts.append(CountReceipt(request, value))
            return value
        except Exception as exc:
            errors.append(exc)
            raise

    decision = renderer.render_candidate(source, baseline_messages, lexicon,
        reviewed_sha256=lexicon_sha, count_prompt_tokens=counter)
    require(not errors and len(calls) in (0, 2), 'renderer swallowed counter failure')
    eligible = bool(calls)
    if not eligible:
        repeated = count(body)
        require(type(repeated) is int and repeated == base_count, 'identical count mismatch')
        provisional = CountReceipt(body, repeated)
    else:
        provisional = receipts[1]
    require(decision.reason in ('hint', 'token_budget', 'no_match', 'multiple_distinct_headwords',
                               'overlapping_occurrences'), 'unexpected renderer abstention')
    final = provisional if decision.hint_active else baseline
    require(serialize_request(decision.messages, alias) == final.body, 'candidate bytes drift')
    return PairPlan(row_id, baseline, provisional, final, eligible, decision.hint_active, decision.reason)


def measured_candidate(plan, source, alias, lexicon, lexicon_sha, renderer, count):
    """Fresh render and two uncached HTTP counts iff structurally eligible."""
    raise Disabled('Superseded broad-prefix study path; use UsageCore')
    calls, errors = [], []

    def counter(messages):
        try:
            body = serialize_request(messages, alias)
            index = len(calls)
            require(index < 2, 'extra recurring count')
            reference = (plan.baseline, plan.provisional)[index]
            require(body == reference.body, 'recurring request bytes drift before send')
            value = count(body)  # Never use a preflight lookup in the timed arm.
            calls.append((body, value))
            require(type(value) is int and body == reference.body and value == reference.count,
                    'recurring count binding drift')
            return value
        except Exception as exc:
            errors.append(exc)
            raise

    decision = renderer.render_candidate(source, renderer.baseline_messages(source), lexicon,
        reviewed_sha256=lexicon_sha, count_prompt_tokens=counter)
    require(not errors and len(calls) == (2 if plan.eligible else 0), 'recurring count failure')
    require((decision.hint_active, decision.reason) == (plan.active, plan.reason), 'decision drift')
    require(serialize_request(decision.messages, alias) == plan.candidate.body, 'measured request drift')
    return plan.candidate.body


def validate_preflight(plans):
    raise Disabled('Superseded broad-prefix study path; use UsageCore')
    require(tuple(p.row_id for p in plans) == ROW_IDS, '88 fixed rows required')
    require({p.row_id for p in plans if p.eligible} == ELIGIBLE_IDS, 'E=44 eligibility schedule mismatch')
    active = {p.row_id for p in plans if p.active}
    contrasts = [f'N{n:03d}' for n in range(1, 37) if n % 3 != 0]
    complete = [family for family in range(12) if
                {f'N{3*family+1:03d}', f'N{3*family+2:03d}'} <= active]
    require(len(set(contrasts) & active) >= 18 and len(complete) >= 8, 'contrast coverage')
    for headword in range(6):
        require(any(f in complete for f in (2*headword, 2*headword+1)), 'headword pair coverage')
        require(any(f'N{3*f+3:03d}' in active for f in (2*headword, 2*headword+1)), 'ambiguity coverage')
    require({f'N{n:03d}' for n in range(41, 49)} <= active, 'active control coverage')
    require(not active.intersection({f'N{n:03d}' for n in (37, 38, 39, 40)}) and
            not any(row.startswith('R') for row in active), 'inactive control/legacy mismatch')


def completion_response(raw, alias, receipt, source, integrity, expected_error):
    data = strict_json(raw)
    require(type(data) is dict and data.get('model') == alias, 'completion identity')
    choices, usage = data.get('choices'), data.get('usage')
    require(type(choices) is list and len(choices) == 1 and type(choices[0]) is dict, 'choice count')
    choice = choices[0]
    require(type(choice.get('message')) is dict and type(choice['message'].get('content')) is str and
            choice.get('finish_reason') in ('stop', 'length'), 'choice schema')
    require(type(usage) is dict and type(usage.get('prompt_tokens_details')) is dict, 'usage missing')
    p, c, t = (usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
    cached = usage['prompt_tokens_details'].get('cached_tokens')
    require(all(type(v) is int for v in (p, c, t, cached)) and p == receipt.count and
            1 <= p <= 384 and 0 <= c <= 512 and cached == 0 and t == p+c, 'usage/count/cache mismatch')
    if 'timings' in data:
        require(type(data['timings']) is dict, 'timings schema')
        if 'cache_n' in data['timings']:
            require(type(data['timings']['cache_n']) is int and data['timings']['cache_n'] == 0, 'cache contradiction')
    text = choice['message']['content']
    flags = []
    if not text.strip():
        flags.append('empty_output')
    if choice['finish_reason'] == 'length':
        flags.append('length_finish')
    try:
        integrity(source, text)
    except expected_error:
        flags.append('integrity_rejection')
    except Exception as exc:
        raise TerminalFailure('unexpected integrity exception') from exc
    return dict(raw_response=raw, output=text, usage=usage, flags=flags,
                scoreable_generation_failure=bool(flags), definite_faithful_pass_eligible=not flags)


class RequestLedger:
    """Counts attempted requests BEFORE send, with exact fixed order."""
    def __init__(self, persist=lambda event: None):
        raise Disabled('Use the exact UsageCore ledger; legacy constructor is disabled')
        self.persist = persist
        self.counts = Counter()
        self.total = 0
        self.terminal = None
        self.cleanup_errors = []
        self.preflight_sealed = False
        self.queue = [('health', None, None), ('models', None, None)]
        self.queue += [('preflight', row, side) for row in ROW_IDS for side in ('baseline', 'second')]
        for row, arm in SCHEDULE:
            if arm == 'candidate' and row in ELIGIBLE_IDS:
                self.queue += [('recurring', row, side) for side in ('baseline', 'provisional')]
            self.queue.append(('completion', row, arm))
        require(len(self.queue) == 442, 'internal accounting')

    def consume(self, kind, row=None, arm=None):
        try:
            require(self.terminal is None, 'attempt already terminal')
            require(kind not in ('recurring', 'completion') or self.preflight_sealed,
                    'generation blocked before full token/coverage validation')
            require(self.total < 398 and (kind, row, arm) == self.queue[self.total], 'request order/cap')
        except BaseException:
            self.fail('request_order_or_preflight_failure')
            raise
        self.total += 1
        self.counts[kind] += 1
        try:
            self.persist(dict(event='request_intent', number=self.total, kind=kind, row=row, arm=arm))
        except BaseException:
            self.terminal = 'journal_failure'
            raise

    def seal_preflight(self, plans):
        try:
            require(self.terminal is None and self.total == 178 and not self.preflight_sealed,
                    'preflight phase/order')
            validate_preflight(plans)
            self.persist(dict(event='preflight_sealed', eligibility=sorted(ELIGIBLE_IDS),
                              request_bindings_sha256=digest(canonical([
                                  dict(row=p.row_id, baseline=p.baseline.binding,
                                       provisional=p.provisional.binding, candidate=p.candidate.binding,
                                       active=p.active, reason=p.reason) for p in plans]))))
            self.preflight_sealed = True
        except BaseException:
            self.fail('preflight_validation_or_journal_failure')
            raise

    def fail(self, cause):
        if self.terminal is None:
            self.terminal = cause
            try:
                self.persist(dict(event='terminal', status='incomplete', cause=cause, consumed=self.total))
            except BaseException as exc:
                self.cleanup_errors.append('terminal journal: ' + type(exc).__name__)

    def assert_complete(self):
        require(self.terminal is None and self.total == 442 and self.counts ==
                Counter(health=1, models=1, preflight=176, recurring=88, completion=176), 'incomplete requests')


class Deadline:
    """Monotonic absolute bound, also checked after parsing/checker work."""
    def __init__(self, now, seconds, *parent_deadlines):
        self.now = now
        self.end = min((now() + seconds,) + tuple(parent_deadlines))

    def remaining(self):
        remaining = self.end - self.now()
        require(remaining > 0, 'absolute deadline expired')
        return remaining


class BoundedWire:
    """Incremental HTTP decoder for an INJECTED synthetic reader only.

    The adapter must provide read(n, remaining), and an independently armed
    supervisor must close it at expiry. No real transport is supplied here.
    """
    def __init__(self, reader, deadline, retain=lambda data: None):
        self.reader, self.deadline, self.retain = reader, deadline, retain
        self.header_bytes = 0
        self.framing_bytes = 0

    def read(self, n):
        data = self.reader.read(n, self.deadline.remaining())
        self.deadline.remaining()
        require(type(data) is bytes and 0 < len(data) <= n, 'short/invalid wire read')
        self.retain(data)
        return data

    def exact(self, n):
        pieces = []
        while n:
            part = self.read(min(n, 8192))
            pieces.append(part)
            n -= len(part)
        return b''.join(pieces)

    def line(self, limit, framing=False):
        line = bytearray()
        while True:
            require(len(line) < limit, 'HTTP line cap')
            if framing:
                require(self.framing_bytes < 16384, 'chunk framing cap')
            else:
                require(self.header_bytes < 16384, 'header block cap')
            byte = self.read(1)
            line.extend(byte)
            if framing:
                self.framing_bytes += 1
            else:
                self.header_bytes += 1
            if byte == b'\n':
                require(line.endswith(b'\r\n'), 'HTTP requires CRLF')
                return bytes(line[:-2])

    def response(self, cap, *, asset_size=None):
        try:
            status = self.line(2048)
            require(re.fullmatch(rb'HTTP/1\.[01] [0-9]{3}(?: [\x20-\x7e]*)?', status), 'status line')
            status_code = int(status.split(b' ')[1])
            headers = {}
            count = 0
            while True:
                line = self.line(2048)
                if not line:
                    break
                count += 1
                require(count <= 64 and b':' in line and not line.startswith((b' ', b'\t')), 'header fields')
                key, value = line.split(b':', 1)
                require(re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key) and
                        not re.search(rb'[\x00-\x08\x0a-\x1f\x7f]', value), 'header syntax')
                key, value = key.lower(), value.strip()
                require(key not in headers, 'duplicate header')
                headers[key] = value
            require(status_code == 200, 'non-200/redirect; body deliberately unread')
            require(headers.get(b'content-encoding', b'identity').lower() == b'identity', 'encoding')
            length, transfer = headers.get(b'content-length'), headers.get(b'transfer-encoding')
            require(not (length is not None and transfer is not None), 'conflicting framing')
            if length is not None:
                require(re.fullmatch(rb'0|[1-9][0-9]*', length), 'invalid length')
                n = int(length)
                require(n <= cap and (asset_size is None or n == asset_size), 'length cap/pin')
                body = self.exact(n)
            else:
                require(asset_size is None and transfer == b'chunked', 'unsupported/missing framing')
                body = bytearray()
                chunks = 0
                while True:
                    size_line = self.line(128, True)
                    require(re.fullmatch(rb'[0-9a-fA-F]+', size_line), 'chunk size/extensions')
                    n = int(size_line, 16)
                    if n == 0:
                        # Trailers are unnecessary here; safely reject any.
                        require(self.line(2048, True) == b'', 'trailers unsupported')
                        break
                    chunks += 1
                    require(chunks <= 1024 and len(body) + n <= cap, 'chunk/body cap')
                    body.extend(self.exact(n))
                    require(self.framing_bytes + 2 <= 16384, 'framing cap')
                    require(self.exact(2) == b'\r\n', 'chunk terminator')
                    self.framing_bytes += 2
                body = bytes(body)
            self.deadline.remaining()
            return body
        except BaseException:
            self.reader.close()
            raise


class EvidenceBudget:
    def __init__(self, cap=64*MIB):
        self.cap, self.retained = cap, 0

    def retain(self, data):
        require(self.retained + len(data) <= self.cap, 'global evidence cap')
        self.retained += len(data)


def resource_gate(host_available, effective_headroom, *, startup=False, rss=None,
                  free_disk=3*GIB, growth=0):
    floor = LIMITS['startup_ram' if startup else 'runtime_ram']
    require(all(type(n) is int and n >= floor for n in (host_available, effective_headroom)),
            'unknown/insufficient host or effective cgroup headroom')
    require((startup and rss is None) or (type(rss) is int and 0 <= rss <= 4*GIB), 'server RSS unknown/exceeded')
    require(type(free_disk) is int and free_disk >= (3*GIB if startup else GIB), 'disk floor')
    require(type(growth) is int and 0 <= growth <= 2*GIB, 'owned growth cap')


def checked_exchange(ledger, kind, row, arm, prepare, transport, now, parent_deadlines, validate,
                     evidence):
    """Synthetic adapter boundary; serialization and validation share deadline.

    transport is a deterministic test double. Real network implementation is
    intentionally absent. Its arm_watchdog must run independently of reads.
    """
    method, endpoint, cap, seconds = ENDPOINTS[kind]
    deadline = Deadline(now, seconds, *parent_deadlines)
    monitor = reader = None
    cleanup_errors = []
    try:
        monitor = transport.arm_watchdog(deadline)
        body = prepare()
        require((method == 'GET' and body is None) or
                (method == 'POST' and type(body) is bytes and len(body) <= 32768), 'request payload')
        deadline.remaining()
        ledger.consume(kind, row, arm)  # Persist before any send, failure consumes it.
        reader = transport.send(method, endpoint, body, deadline.remaining(),
                                proxy=False, redirects=False, request_header_cap=8192)
        wire = BoundedWire(reader, deadline, evidence.retain)
        raw = wire.response(cap)
        result = validate(raw)
        deadline.remaining()  # Never accept late parsing/identity/checker results.
        return result
    except BaseException as exc:
        ledger.fail(type(exc).__name__)
        raise
    finally:
        # Each owned cleanup action is attempted even if another fails. The
        # synthetic adapter's methods must honor these explicit time budgets.
        # A real adapter additionally needs independently enforced OS cleanup.
        cleanup_end = min(now()+20, min(parent_deadlines) if parent_deadlines else now()+20)
        if reader is not None:
            try:
                reader.close()
            except BaseException as exc:
                cleanup_errors.append('reader close: ' + type(exc).__name__)
        if monitor is not None:
            try:
                monitor.cancel()
            except BaseException as exc:
                cleanup_errors.append('watchdog cancel: ' + type(exc).__name__)
            try:
                monitor.join(timeout=max(0, min(7, cleanup_end-now())))
            except BaseException as exc:
                cleanup_errors.append('watchdog join: ' + type(exc).__name__)
            try:
                require(not monitor.is_alive(), 'watchdog still alive')
            except BaseException as exc:
                cleanup_errors.append('watchdog exit: ' + type(exc).__name__)
        if now() > cleanup_end:
            cleanup_errors.append('request cleanup deadline')
        if cleanup_errors:
            ledger.cleanup_errors.extend(cleanup_errors)
            ledger.fail('request_cleanup_unconfirmed')
            raise TerminalFailure('request cleanup unconfirmed: ' + '; '.join(cleanup_errors))


def validate_archive_members(members):
    """Pure bounded metadata validator, no archive open/extraction/execution."""
    require(type(members) is list and len(members) <= 1024, 'archive member cap')
    names, expanded = {}, 0
    for member in members:
        name = member['name']
        require(type(name) is str and name and not name.startswith('/') and '\\' not in name and
                not re.search(r'[\x00-\x1f\x7f]', name) and
                all(p not in ('', '.', '..') for p in name.rstrip('/').split('/')), 'archive path')
        name = name.rstrip('/')
        require(name not in names and member['type'] in ('file', 'directory', 'symlink'), 'archive type/duplicate')
        require(type(member['size']) is int and member['size'] >= 0, 'archive size')
        if member['type'] == 'file':
            expanded += member['size']
            require(expanded <= 512*MIB, 'archive expanded cap')
        else:
            require(member['size'] == 0, 'nonregular archive payload')
        names[name] = member
    for name, member in names.items():
        parents = name.split('/')[:-1]
        require(all('/'.join(parents[:i]) not in names or
                    names['/'.join(parents[:i])]['type'] == 'directory'
                    for i in range(1, len(parents)+1)), 'archive parent is not directory')
        if member['type'] == 'symlink':
            require('.so' in posixpath.basename(name), 'only relative library symlinks')
            current, visited = name, set()
            while names[current]['type'] == 'symlink':
                require(current not in visited, 'symlink cycle')
                visited.add(current)
                target = names[current].get('target')
                require(type(target) is str and target and not target.startswith('/') and
                        '\\' not in target and not re.search(r'[\x00-\x1f\x7f]', target), 'symlink target')
                current = posixpath.normpath(posixpath.join(posixpath.dirname(current), target))
                require(current != '..' and not current.startswith('../') and current in names,
                        'escaping/missing symlink target')
            require(names[current]['type'] == 'file', 'library target not regular')
    return dict(member_count=len(members), expanded_bytes=expanded)


CLAIM_EXTRA_HASHES = ('harness_manifest', 'source_plan', 'source_author_receipt',
    'literal_audit_receipt', 'parent_preregistration', 'criteria_commitment',
    'redirect_policy', 'license_notice_evidence', 'output_schemas', 'output_binding_revision')
CLAIM_PATHS = ('acquisition', 'extraction', 'output', 'evidence', 'source', 'claim_root', 'public')


def validate_claim_plan(plan):
    """Pure full-binding check. Does not grant release or write a real claim."""
    roots=actions_policy.validate_roots(plan.get('roots'))
    require(plan.get('executor') == actions_policy.EXECUTOR and plan.get('workspace')==str(roots['workspace']),
            'executor scope')
    require(plan.get('alias') == alias_for(plan.get('attempt_id')), 'claim alias')
    require(type(plan.get('claimed_utc')) is str and
            re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', plan['claimed_utc']), 'UTC claim time')
    require(plan.get('pins') == PINS and plan.get('assets') == [list(a) for a in ASSETS] and
            plan.get('limits') == LIMITS and plan.get('sampling') == SAMPLING and
            plan.get('schedule_sha256') == SCHEDULE_SHA256, 'claim frozen identity/config')
    commitments = plan.get('commitments')
    require(type(commitments) is dict and set(commitments) == set(CLAIM_EXTRA_HASHES) and
            all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in commitments.values()),
            'full digest-only preregistration/receipt/schema commitments required')
    paths = plan.get('paths')
    require(type(paths) is dict and set(paths) == set(CLAIM_PATHS) and
            all(type(p) is str and Path(p).is_absolute() for p in paths.values()), 'absolute claimed paths')
    require(plan.get('eligibility') == sorted(ELIGIBLE_IDS), 'claim frozen E=12 schedule')
    expected_policy=json.loads(json.dumps(OUTPUT_POLICY));expected_policy['fixed_root']=str(roots['state'])
    require(plan.get('output_files') == list(expected_policy['output_files']) and
            plan.get('output_policy') == expected_policy and
            commitments['output_schemas'] == digest(canonical(expected_policy)) and
            commitments['output_binding_revision'] == OUTPUT_REVISION_SHA256, 'output identities/schemas')
    require(paths['evidence']==paths['output']==str(roots['output']) and paths['source']==str(roots['source']) and
            paths['claim_root']==str(roots['state']) and paths['public']==str(roots['output']/'public'),
            'bound source/state/public paths')
    require(plan.get('redirect_policy') == [] and plan.get('execution_policy')==actions_policy.EXECUTION_POLICY,
            'exact conditional execution policy; this validator grants no release')
    return {'valid_conditional_plan': True, 'execution_released': False}


def child_spec(executable, argv, cwd, *, library_dirs=()):
    require(Path(executable).is_absolute() and Path(cwd).is_absolute(), 'absolute child paths')
    require(not library_dirs, 'LD_LIBRARY_PATH requires separate frozen compatibility review')
    return dict(executable=executable, argv=[executable, *argv], cwd=cwd,
                env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'},
                shell=False, close_fds=True, pass_fds=[], preexec_fn=None)


def server_spec(server, model, template, cwd, port, alias):
    validate_alias(alias)
    require(type(port) is int and 1024 <= port <= 65535 and
            Path(model).is_absolute() and Path(template).is_absolute(), 'server paths/port')
    return child_spec(server, ['-lv', '4', '--log-colors', 'off', '--no-log-jsonl', '--no-warmup',
        '-m', model, '--host', '127.0.0.1', '--port', str(port), '--alias', alias,
        '-c', '2048', '-t', '2', '-tb', '2', '-np', '1', '-ngl', '0', '-b', '128',
        '-ub', '128', '--chat-template-file', template, '--cors-origins', f'http://127.0.0.1:{port}'], cwd)


class SyntheticSupervisor:
    """Deterministic fake lifecycle model, NOT an OS supervisor.

    Preserves the owned-handle, independent deadline, 3+3 stop and join patterns
    of the audited runner/resources. A real watchdog/OS adapter remains blocked.
    """
    def __init__(self, now, journal=lambda event: None):
        self.now, self.journal = now, journal
        self.outer = Deadline(now, 1475)
        self.handles, self.intents, self.monitors, self.sockets = {}, {}, [], []
        self.failure = None
        self.failure_at = None
        self.cleanup_errors = []
        self.lifecycle = None
        self.postready = None

    def launch(self, name, spec, seconds, fake_factory):
        require(self.failure is None and name not in self.intents, 'no repeat/late launch')
        if name == 'server':
            self.lifecycle = Deadline(self.now, 800, self.outer.end)
        bounds = [self.outer.end]
        if self.lifecycle:
            bounds.append(self.lifecycle.end - 20)
        if self.postready:
            bounds.append(self.postready.end)
        deadline = Deadline(self.now, seconds, *bounds)
        intent = dict(event='launch_intent', name=name, spec=spec, deadline=deadline.end,
                      pending_handle=True, monitor_armed=True)
        self.intents[name] = intent
        try:
            self.journal(intent.copy())  # Registration/monitor arming precedes factory.
            handle = fake_factory(self, deadline)
        except BaseException:
            self.fail('launch_state_unknown')
            raise
        self.handles[name] = handle  # Adopt even a late handle before cleanup.
        intent['pending_handle'] = False
        if self.failure is not None or self.now() >= deadline.end:
            self.fail('late_launch_return')
            raise TerminalFailure('late launch, adopted and stopped')
        return handle

    def ready(self):
        require(self.failure is None and self.postready is None and self.lifecycle is not None, 'readiness state')
        self.postready = Deadline(self.now, 600, self.lifecycle.end-20, self.outer.end)

    def fail(self, cause):
        if self.failure is None:
            self.failure = cause
            self.failure_at = self.now()
            try:
                self.journal(dict(event='first_failure', cause=cause))
            except BaseException as exc:
                self.cleanup_errors.append('failure journal: ' + type(exc).__name__)
        for connection in self.sockets:
            try:
                connection.close()
            except BaseException as exc:
                self.cleanup_errors.append('socket close: ' + type(exc).__name__)
        for handle in self.handles.values():
            try:
                self.stop(handle, min(self.failure_at+20, self.outer.end,
                                     self.lifecycle.end if self.lifecycle else self.outer.end), self.now)
            except BaseException as exc:
                self.cleanup_errors.append('child stop: ' + type(exc).__name__)

    def tick(self, deadline):
        # Called independently by fake clock while a factory/read is blocked.
        if self.now() >= deadline.end:
            self.fail('watchdog_expired')

    @staticmethod
    def stop(handle, cleanup_end=None, now=None):
        def timeout():
            return 3 if cleanup_end is None else max(0, min(3, cleanup_end-now()))
        if handle.poll() is None:
            handle.terminate()
            try:
                handle.wait(timeout())
            except TimeoutError:
                handle.kill()
                handle.wait(timeout())

    def finalize(self, flush=lambda: None):
        deadline = Deadline(self.now, 20, (self.failure_at+20) if self.failure_at is not None else self.outer.end, self.outer.end,
                            self.lifecycle.end if self.lifecycle else self.outer.end)
        unresolved = list(self.cleanup_errors)
        for name, intent in self.intents.items():
            if intent['pending_handle']:
                unresolved.append(name + ':unknown launch state')
        for name, handle in self.handles.items():
            try:
                deadline.remaining()
                self.stop(handle, deadline.end, self.now)
                require(handle.poll() is not None, 'exit unconfirmed')
            except BaseException:
                unresolved.append(name + ':exit unconfirmed')
        for monitor in self.monitors:
            try:
                monitor.cancel()
                monitor.join(deadline.remaining())
                require(not monitor.is_alive(), 'monitor remains alive')
            except BaseException:
                unresolved.append('monitor:unconfirmed')
        for connection in self.sockets:
            try:
                connection.close()
            except BaseException as exc:
                unresolved.append('socket close: ' + type(exc).__name__)
        try:
            flush()
            deadline.remaining()
        except BaseException:
            unresolved.append('evidence finalization incomplete')
        if unresolved and self.failure is None:
            self.failure = 'cleanup_unconfirmed'
        return dict(status='incomplete' if self.failure or unresolved else 'synthetic_complete',
                    cause=self.failure, unresolved=unresolved,
                    cleanup_confirmed=not unresolved)


def redirect_target(previous, location):
    """Pure rejection gate. No actual redirect is currently authorized."""
    require(type(location) is str and not re.search(r'[\x00-\x20\x7f]', location), 'redirect controls')
    target = urljoin(previous, location)
    parsed = urlsplit(target)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and
            not parsed.fragment and parsed.port in (None, 443), 'redirect URL')
    raise Disabled('Exact reviewed downstream redirect policy is empty')


class SyntheticClaimStore:
    """Persistent exclusive claim/journal mechanics confined to private /tmp fakes.

    Deliberately cannot address the approved real claim location. A claim failure
    leaves partial bytes in place; no method resets, removes or replaces them.
    """
    def __init__(self, root):
        root = Path(root)
        require(root.is_absolute() and root.parent == Path(tempfile.gettempdir()) and
                root.name.startswith('luna-sense-fake-') and not root.is_symlink(), 'fake root only')
        require(root.stat().st_mode & 0o777 == 0o700, 'private fake root required')
        self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.journal_fd = None

    def claim(self, bindings, *, fail_after_claim=False):
        require(bindings.get('synthetic_only') is True, 'synthetic binding required')
        data = canonical(bindings)
        fd = os.open('ONE_SHOT_CPU_ATTEMPT.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                     0o600, dir_fd=self.root_fd)
        try:
            self._write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.root_fd)
        if fail_after_claim:
            raise TerminalFailure('synthetic journal creation failure; claim consumed')
        self.journal_fd = os.open('ONE_SHOT_CPU_EVENTS.jsonl', os.O_CREAT | os.O_EXCL | os.O_APPEND |
                                  os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=self.root_fd)
        os.fsync(self.root_fd)
        self.append(dict(event='claimed', synthetic_only=True))

    @staticmethod
    def _write(fd, data):
        while data:
            written = os.write(fd, data)
            require(written > 0, 'short persistent write')
            data = data[written:]

    def append(self, event):
        require(self.journal_fd is not None, 'journal unavailable')
        self._write(self.journal_fd, canonical(event) + b'\n')
        os.fsync(self.journal_fd)

    def close(self):
        if self.journal_fd is not None:
            os.close(self.journal_fd)
            self.journal_fd = None
        os.close(self.root_fd)


def quantiles(values):
    require(bool(values) and all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values),
            'empty/missing/nonfinite timing')
    ordered = sorted(values)
    return dict(n=len(values), median=statistics.median(ordered), p95=ordered[math.ceil(.95*len(ordered))-1])


def paired_cost(rows, clock_resolution_seconds, *, material_noise=False):
    raise Disabled('Superseded broad-prefix study path; use UsageCore')
    require(len(rows) == 88 and tuple(row['id'] for row in rows) == ROW_IDS, 'all-row timing denominator')
    require(type(clock_resolution_seconds) in (int, float) and math.isfinite(clock_resolution_seconds) and
            clock_resolution_seconds > 0, 'clock resolution')
    for row in rows:
        require(row.get('complete') is True and type(row.get('active')) is bool, 'partial timing')
        quantiles([row.get('baseline'), row.get('candidate')])
        require(min(row['baseline'], row['candidate']) >= 100*clock_resolution_seconds, 'timer resolution limited')
    groups = dict(all_new=[r for r in rows if r['id'].startswith('N')],
                  active_new=[r for r in rows if r['id'].startswith('N') and r['active']],
                  all_rows=rows, all_active=[r for r in rows if r['active']])
    result = {}
    for name, group in groups.items():
        ratios = quantiles([r['candidate']/r['baseline'] for r in group])
        result[name] = dict(ratios=ratios, baseline=quantiles([r['baseline'] for r in group]),
                            candidate=quantiles([r['candidate'] for r in group]))
    strata = {}
    for order, parity in (('AB', 1), ('BA', 0)):
        group = [r for r in rows if int(r['id'][1:]) % 2 == parity]
        strata[order] = quantiles([r['candidate']/r['baseline'] for r in group])
    passed = all(v['ratios']['median'] <= 1.25 and v['ratios']['p95'] <= 1.25 for v in result.values())
    return dict(status='inconclusive' if material_noise else ('pass' if passed else 'fail'),
                groups=result, order_strata=strata, cold_first_generation=True,
                raw_rows=rows, quality_failures_included=True)


def all_row_accounting(observations):
    require(set(observations) <= set(SCHEDULE), 'unexpected observed arm')
    return [dict(id=row, arms={arm: observations.get((row, arm), {'status': 'unobserved'})
                              for arm in ('baseline', 'candidate')}) for row in ROW_IDS]


def run_real(*args, **kwargs):
    raise Disabled('SOURCE ONLY: no acquisition, executable use, real claim, or inference release; '
                   'official notices, exact redirects, integration and independent review remain required')


if __name__ == '__main__':
    run_real()
