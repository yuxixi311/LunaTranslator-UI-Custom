"""Adapted source-only regressions; originals remain unchanged.

Ten obsolete per-chunk download JSON cases are listed as superseded, never passed.
Journal faults are covered by journal_test.py. Subject loads only after all guards.
"""
import _thread
import base64
import copy
import csv
import ctypes
from datetime import datetime, timezone
from email import policy
from email.parser import Parser
import hashlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import time
import types
import unicodedata
from urllib.parse import urlsplit
import zlib


class GuardViolation(BaseException):
    pass


class Guard:
    def __init__(self, allowed_reads=()):
        self.allowed_reads = {str(p) for p in allowed_reads}
        self.counts = dict(network=0, write=0, process=0, exit=0, thread=0, disk=0, read=0, native=0)

    def reject(self, category):
        self.counts[category] += 1
        raise GuardViolation('OFFLINE_GUARD_BLOCKED')

    def hook(self, event, args):
        if event.startswith(('ctypes.dlopen', 'ctypes.dlsym')):
            self.reject('native')
        if event in ('os.listdir', 'os.scandir'):
            self.reject('disk')
        if event.startswith('socket.'):
            self.reject('network')
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn'):
            self.reject('process')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+'))
            writing = writing or (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writing:
                self.reject('write')
            if str(path) not in self.allowed_reads:
                self.reject('read')
        if event in ('os.remove', 'os.rename', 'os.rmdir', 'os.mkdir', 'os.link', 'os.symlink', 'os.chmod', 'os.chown', 'os.truncate', 'os.utime'):
            self.reject('write')


class Patches:
    def __init__(self):
        self.undo = []

    def item(self, mapping, key, value):
        old = mapping[key]
        self.undo.append(lambda: mapping.__setitem__(key, old))
        mapping[key] = value

    def attr(self, owner, key, value):
        old = getattr(owner, key)
        self.undo.append(lambda: setattr(owner, key, old))
        setattr(owner, key, value)

    def close(self):
        for fn in reversed(self.undo):
            fn()

    def __enter__(self):
        return self

    def __exit__(self, *ignored):
        self.close()


SECRET = 'SYNTHETIC_SECRET_DO_NOT_EMIT'


def synthetic_error(cls=OSError, number=5, winerror=32):
    exc = cls(number, SECRET, 'SYNTHETIC_PRIVATE_PATH')
    exc.winerror = winerror
    return exc


class FakeFS:
    def __init__(self):
        self.data = {}
        self.context = 'UNKNOWN'
        self.events = []
        self.rules = []
        self.hits = {}
        self.source_reads = 0
        self.deletes = []
        self.handles = {}

    def path(self, key):
        if isinstance(key, FakePath):
            return key
        return FakePath(self, str(key))

    def seed_json(self, key, value):
        self.data[key] = json.dumps(value).encode('utf-8')

    def inject(self, operation, effect, context=None, occurrence=1, suffix=None):
        self.rules.append(dict(operation=operation, effect=effect, context=context,
                               occurrence=occurrence, suffix=suffix, hit=0))

    def event(self, operation, key):
        self.events.append((operation, self.context, key))
        for rule in self.rules:
            if rule['operation'] != operation:
                continue
            if rule['context'] is not None and rule['context'] != self.context:
                continue
            if rule['suffix'] is not None and not key.endswith(rule['suffix']):
                continue
            rule['hit'] += 1
            if rule['hit'] != rule['occurrence']:
                continue
            effect = rule['effect']
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return 'NORMAL'

    def replace(self, source, destination):
        self.event('JSON_REPLACE', str(destination))
        self.data[str(destination)] = self.data.pop(str(source))

    def rename(self, source, destination):
        self.event('BODY_RENAME', str(destination))
        if str(destination) in self.data:
            raise FileExistsError(17, SECRET)
        self.data[str(destination)] = self.data.pop(str(source))

    def fsync(self, fileno):
        handle = self.handles[fileno]
        self.event(handle.kind + '_FSYNC', handle.key)


class FakePath:
    def __init__(self, fs, key):
        self.fs, self.key = fs, key.replace('\\', '/')

    def __str__(self):
        return self.key

    def __fspath__(self):
        raise GuardViolation('FAKE_PATH_MUST_NOT_REACH_OS')

    def __truediv__(self, name):
        return self.fs.path(self.key.rstrip('/') + '/' + str(name))

    def __eq__(self, other):
        return isinstance(other, FakePath) and self.fs is other.fs and self.key == other.key

    @property
    def parent(self):
        return self.fs.path(self.key.rsplit('/', 1)[0])

    @property
    def anchor(self):
        return 'MEMORY_ONLY'

    def resolve(self, **kwargs):
        return self

    def with_suffix(self, suffix):
        return self.fs.path(self.key.rsplit('.', 1)[0] + suffix)

    def exists(self):
        return self.key in self.fs.data

    def is_file(self):
        return self.exists()

    def is_dir(self):
        return any(key.startswith(self.key.rstrip('/') + '/') for key in self.fs.data)

    @property
    def name(self):
        return self.key.rsplit('/', 1)[-1]

    @property
    def parents(self):
        parts = self.key.split('/')
        return [self.fs.path('/'.join(parts[:-i])) for i in range(1, len(parts))]

    def absolute(self):
        return self

    def with_name(self, name):
        return self.parent / name

    def is_symlink(self):
        return False

    def stat(self, **kwargs):
        return types.SimpleNamespace(st_size=len(self.fs.data.get(self.key, b'')), st_file_attributes=0, st_mode=stat.S_IFREG if self.is_file() else stat.S_IFDIR)

    def lstat(self):
        return self.stat()

    def iterdir(self):
        prefix = self.key.rstrip('/') + '/'
        return iter([self.fs.path(k) for k in self.fs.data if k.startswith(prefix) and '/' not in k[len(prefix):]])

    def read_bytes(self):
        self.fs.source_reads += self.key == 'work/run_check.py'
        return bytes(self.fs.data[self.key])

    def read_text(self, encoding='utf-8'):
        return self.read_bytes().decode(encoding)

    def open(self, mode, buffering=-1):
        kind = 'JOURNAL' if self.key.endswith('.journal') else ('ARCHIVE' if mode == 'rb' else ('BODY' if self.key.endswith('.part') else 'JSON'))
        self.fs.event(kind + '_OPEN', self.key)
        if mode == 'xb' and self.exists():
            raise FileExistsError(17, SECRET)
        if mode not in ('xb', 'wb', 'rb'):
            raise GuardViolation('FAKE_MODE_NOT_SUPPORTED')
        if mode != 'rb':
            self.fs.data[self.key] = b''
        return FakeHandle(self.fs, self.key, kind)

    def unlink(self):
        self.fs.deletes.append(self.key)
        del self.fs.data[self.key]


class FakeHandle:
    def __init__(self, fs, key, kind):
        self.fs, self.key, self.kind = fs, key, kind
        self.closed = False
        self.position = 0
        self.descriptor = len(fs.handles) + 47001
        fs.handles[self.descriptor] = self

    def read(self, amount=-1):
        body = self.fs.data[self.key]
        end = len(body) if amount < 0 else min(len(body), self.position + amount)
        result = body[self.position:end]
        self.position = end
        return result

    def write(self, body):
        effect = self.fs.event(self.kind + '_WRITE', self.key)
        if effect == 'SHORT':
            count = max(0, len(body) - 1)
        elif effect == 'NONE':
            return None
        else:
            count = len(body)
        self.fs.data[self.key] += body[:count]
        return count

    def flush(self):
        self.fs.event(self.kind + '_FLUSH', self.key)

    def fileno(self):
        return self.descriptor

    def close(self):
        self.fs.event(self.kind + '_CLOSE', self.key)
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *ignored):
        self.close()


class Headers:
    def __init__(self, pairs=()):
        self.pairs = list(pairs)

    def get_all(self, key, default):
        result = [v for k, v in self.pairs if k.lower() == key.lower()]
        return result or default


class FakeResponse:
    def __init__(self, payload=b'abc', status=200, error=None):
        self.payload, self.status, self.error = payload, status, error
        self.headers = Headers([('Content-Length', str(len(payload)))])
        self.read_calls = 0
        self.closed = False
        self.close_error = None

    def read1(self, amount):
        self.read_calls += 1
        if self.error:
            raise self.error
        chunk, self.payload = self.payload[:amount], self.payload[amount:]
        return chunk

    def close(self):
        if self.close_error:
            raise self.close_error
        self.closed = True


class FakeSocket:
    def settimeout(self, timeout):
        assert 0 < timeout <= 10


class FakeConnection:
    def __init__(self):
        self.sock = FakeSocket()
        self.closed = False

    def close(self):
        self.closed = True


class FakeDisk:
    def __init__(self, *ignored):
        self.minimum_free = 16 * 1024 ** 3
        self.maximum_owned = 0
        self.calls = []
        self.failure_at = None
        self.failure = None

    def check(self, projected=0, initial=False):
        self.calls.append((projected, initial))
        if self.failure_at == len(self.calls):
            raise self.failure
        return dict(free_bytes=self.minimum_free, owned_file_allocation_upper_bound_bytes=0,
                    control_reserve_bytes=32 * 1024 ** 2, cluster_bytes=4096)


class FakeThread:
    starts = 0

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        FakeThread.starts += 1


class FakeProcess:
    def __init__(self, unconfirmed=False, code=1):
        self.unconfirmed, self.code = unconfirmed, code
        self.waits, self.terminations = 0, 0

    def wait(self, timeout):
        self.waits += 1
        if self.unconfirmed:
            raise subprocess.TimeoutExpired('MEMORY_ONLY', timeout)
        return self.code

    def terminate(self):
        self.terminations += 1

    def poll(self):
        return None if self.unconfirmed else self.code


class MemoryNetwork:
    """Exercise stdlib HTTPS request and restored connect using in-memory leaves."""
    def __init__(self, phase=None, close_error=False, status=200):
        self.phase, self.close_error, self.status = phase, close_error, status
        self.events, self.sent = [], []
        self.patches = Patches()
        owner = self
        class Wire:
            def settimeout(self, timeout):
                assert 0 < timeout <= 10
                owner.events.append('timeout')
            def connect(self, address):
                owner.events.append('connect')
                assert address == ('192.0.2.1', 443)
                if owner.phase == 'connect':
                    raise synthetic_error(number=5, winerror=32)
            def do_handshake(self):
                owner.events.append('handshake')
                if owner.phase == 'handshake':
                    raise synthetic_error(number=5, winerror=32)
            def sendall(self, data):
                owner.events.append('sendall')
                owner.sent.append(bytes(data))
            def makefile(self, mode):
                assert mode == 'rb'
                owner.events.append('makefile')
                return io.BytesIO(('HTTP/1.1 %d MOCK\r\nContent-Length: 3\r\nConnection: close\r\n\r\n' % owner.status).encode() + b'abc')
            def close(self):
                owner.events.append('close')
                if owner.close_error:
                    raise synthetic_error(number=28, winerror=112)
        self.wire = Wire()
        def wrap_socket(raw, server_hostname, do_handshake_on_connect):
            self.events.append('wrap_socket')
            assert raw is self.wire and server_hostname == 'download-r2.pytorch.org'
            assert do_handshake_on_connect is False
            return self.wire
        self.context = types.SimpleNamespace(check_hostname=True, verify_mode=ssl.CERT_REQUIRED, wrap_socket=wrap_socket)

    def __enter__(self):
        def getaddrinfo(host, port, **kwargs):
            self.events.append('dns')
            assert host == 'download-r2.pytorch.org' and port == 443
            assert kwargs == {'type': socket.SOCK_STREAM}
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.2', 443))]
        def make_socket(*args):
            self.events.append('socket')
            assert args == (socket.AF_INET, socket.SOCK_STREAM, 6)
            return self.wire
        self.patches.attr(socket, 'getaddrinfo', getaddrinfo)
        self.patches.attr(socket, 'socket', make_socket)
        self.patches.attr(ssl, 'create_default_context', lambda: self.context)
        return self

    def __exit__(self, *ignored):
        self.patches.close()


class Scenario:
    def __init__(self, g, source_bytes, payload=b'abc'):
        self.g, self.fs, self.patches = g, FakeFS(), Patches()
        self.work, self.out = self.fs.path('work'), self.fs.path('work/output')
        self.checkpoint = self.work / 'download-checkpoint.json'
        self.fs.data['work/run_check.py'] = source_bytes
        self.source_hash = hashlib.sha256(source_bytes).hexdigest()
        self.payload = payload
        self.response = FakeResponse(payload)
        self.connection = FakeConnection()
        self.disk = FakeDisk()
        self.requests = 0
        self.static_calls = 0
        self.save_contexts = []
        self.fs.data['work/offline_test.py'] = b'MEMORY_ONLY_DIAGNOSTIC_TEST'
        self.fs.data['work/safety_test.py'] = b'MEMORY_ONLY_SAFETY_TEST'
        for name in g['TEST_FILES']:
            self.fs.data.setdefault('work/' + name, b'MEMORY_ONLY_TEST_FIXTURE')
        self.test_hashes = {name: hashlib.sha256(self.fs.data['work/' + name]).hexdigest()
                            for name in g['TEST_FILES']}
        self.fs.seed_json('work/candidate-identity.json', dict(schema_version=1, candidate_id=g['CANDIDATE_ID'],
                          status='preparation_only', live_execution_authorized=False))
        self.fs.seed_json('work/execution-authorization.json', dict(candidate_id=g['CANDIDATE_ID'],
                          source_sha256=self.source_hash, action='single_download_and_static_check', authorized=True))
        self.fs.seed_json('work/output/attempt.json', dict(candidate_id=g['CANDIDATE_ID'], source_sha256=self.source_hash,
                          url=g['URL'], expected_sha256=g['EXPECTED'], single_attempt=True))
        self.fs.seed_json('work/output/execution-started.json', dict(candidate_id=g['CANDIDATE_ID'],
                          final_source_sha256=self.source_hash, single_attempt_consumed=True, retry_forbidden=True))
        self.fs.seed_json('work/offline-tests.json', dict(status='passed', candidate_id=g['CANDIDATE_ID'],
                          source_sha256=self.source_hash, network_requests=0,
                          test_source_sha256=self.test_hashes['offline_test.py'], tests_source_sha256=self.test_hashes))
        self.fs.seed_json('work/independent-review.json', dict(status='approved', candidate_id=g['CANDIDATE_ID'],
                          source_sha256=self.source_hash, tests_source_sha256=self.test_hashes))

    def __enter__(self):
        p, g = self.patches, self.g
        original_write_json = g['write_json']
        def contextual_save(path, obj, exclusive=False, context='PROGRESS'):
            prior = self.fs.context
            self.fs.context = context
            self.save_contexts.append(context)
            try:
                return original_write_json(path, obj, exclusive=exclusive, context=context)
            finally:
                self.fs.context = prior
        owner = self
        class Transport:
            def open(self, url, budget, on_send):
                assert url == g['URL']
                owner.requests += 1
                assert owner.requests == 1
                on_send()
                return owner.connection, owner.response
        def static_trap(*args, **kwargs):
            self.static_calls += 1
            raise GuardViolation('STATIC_CHECK_FORBIDDEN')
        p.item(g, 'Path', self.fs.path)
        p.item(g, '__file__', 'work/run_check.py')
        p.item(g, 'write_json', contextual_save)
        original_final_checkpoint = g['final_checkpoint']
        def contextual_final(path, obj, budget, disk):
            prior = self.fs.context
            self.fs.context = 'FINAL_CHECKPOINT'
            self.save_contexts.append('FINAL_CHECKPOINT')
            try:
                return original_final_checkpoint(path, obj, budget, disk)
            finally:
                self.fs.context = prior
        p.item(g, 'final_checkpoint', contextual_final)
        p.item(g, 'DiskGuard', lambda *ignored: self.disk)
        p.item(g, 'OneGET', Transport)
        p.item(g, 'static_check', static_trap)
        p.attr(g['receive_body'], '__defaults__', (hashlib.sha256(self.payload).hexdigest(),))
        p.attr(os, 'replace', self.fs.replace)
        p.attr(os, 'rename', self.fs.rename)
        p.attr(os, 'fsync', self.fs.fsync)
        return self

    def __exit__(self, *ignored):
        self.patches.close()

    def budget(self):
        return self.g['Budget'](100, clock=lambda: 0)

    def download(self):
        result = self.g['download'](self.work, self.out, self.budget(), self.checkpoint)
        assert self.static_calls == 0 and self.requests <= 1
        return result

    def seed_journal_proof(self, prior):
        state = self.g['download_state']()
        state.update(status='running', candidate_id=self.g['CANDIDATE_ID'], source_sha256=self.source_hash)
        journal = self.g['ProgressJournal'](self.work / 'download-progress.journal', state, self.budget(), self.disk)
        journal.save(state, 'PROGRESS_INITIAL')
        state['request_count'] = 1
        journal.save(state, 'PROGRESS_REQUEST')
        state['get_send_attempts'] = 1
        journal.save(state, 'PROGRESS_SENT')
        state['http_status'] = 200
        journal.save(state, 'PROGRESS_HEADERS')
        state.update(received_bytes=prior['received_bytes'], written_bytes=prior['written_bytes'],
                     actual_sha256=prior['actual_sha256'], response_body_complete=True, sha256_matches_expected=True)
        journal.save(state, 'PROGRESS_FINAL')
        state['status'] = 'completed'
        journal.finish(state)
        assert journal.close() is None
        prior.update({key: value for key, value in state.items() if key.startswith('journal_')})

    def seed_static_proof(self):
        """Synthetic proof fixture for gate tests, never a real completed download."""
        g = self.g
        prior = g['download_state']()
        prior.update(status='completed', candidate_id=g['CANDIDATE_ID'], source_sha256=self.source_hash,
                     request_count=1, get_send_attempts=1, http_status=200,
                     received_bytes=3, written_bytes=3, actual_sha256=g['EXPECTED'],
                     response_body_complete=True, sha256_matches_expected=True, artifact_filename=g['FILENAME'],
                     checkpoint_persisted=True, body_fsync_completed=True, body_close_completed=True,
                     finished_at='MEMORY_ONLY_FINISHED')
        self.seed_journal_proof(prior)
        self.fs.seed_json(str(self.checkpoint), prior)
        self.fs.seed_json(str(self.out / 'request-attempt.json'), dict(candidate_id=g['CANDIDATE_ID'],
                          final_source_sha256=self.source_hash, single_attempt_consumed=True,
                          retry_forbidden=True, stage='download', url=g['URL']))
        stage = dict(status='completed', worker_exit_confirmed=True, checkpoint_terminal_confirmed=True,
                     worker_returncode=0, first_error=None, error_code=None, data=prior)
        report = dict(candidate_id=g['CANDIDATE_ID'], final_source_sha256=self.source_hash,
                      first_error=None, report_save_failed=False, report_persisted=True, stages={'download': stage})
        self.fs.seed_json(str(self.out / 'report.json'), report)
        self.fs.data[str(self.out / g['FILENAME'])] = b'abc'
        return prior, report

    def stream(self, expected=None):
        state = self.g['download_state']()
        body = FakeHandle(self.fs, 'work/output/payload.part', 'BODY')
        self.fs.data[body.key] = b''
        def save(obj, context='PROGRESS'):
            self.g['write_json'](self.checkpoint, obj, context=context)
        error = None
        try:
            self.g['receive_body'](self.connection, self.response, body, state,
                                   self.budget(), self.disk, save,
                                   expected=expected or hashlib.sha256(self.payload).hexdigest())
        except self.g['Failure'] as exc:
            error = exc
        return state, error


def assert_clean(value):
    text = json.dumps(value, ensure_ascii=True, allow_nan=False)
    assert SECRET not in text
    assert 'SYNTHETIC_PRIVATE_PATH' not in text
    assert 'Traceback' not in text
    assert not re.search(r'(?:^|[\s"\x27])[A-Za-z]:[\\/]|[\\/]Users[\\/]', text)
    return text


def assert_diagnostic(diag, operation, context=None, exception_type=None, errno=None, winerror=None):
    assert diag['operation'] == operation
    if context is not None:
        assert diag['context'] == context
    if exception_type is not None:
        assert diag['exception_type'] == exception_type
    if errno is not None:
        assert type(diag['errno']) is int and diag['errno'] == errno
    if winerror is not None:
        assert type(diag['winerror']) is int and diag['winerror'] == winerror
    assert_clean(diag)


def suite(g, source_bytes, guard):
    results = []
    def test(name, fn):
        if name.startswith(('download_progress_before_write_', 'download_progress_after_write_')):
            results.append(dict(name=name, status='superseded', replacement_suite='journal_test.py',
                                reason='Download now writes an append-only journal, not per-chunk JSON replacement'))
            return
        before = dict(guard.counts)
        try:
            fn()
            assert guard.counts == before and not any(guard.counts.values())
            results.append(dict(name=name, status='passed'))
        except BaseException as exc:
            tb = exc.__traceback__
            lines = []
            while tb is not None:
                lines.append(tb.tb_lineno); tb = tb.tb_next
            results.append(dict(name=name, status='failed', error_code='OFFLINE_ASSERTION_FAILED', exception_type=type(exc).__name__, lines=lines, subject_diagnostic=getattr(exc, 'diagnostic', None)))

    def guard_selfcheck():
        probe = Guard()
        for event, args in [('socket.connect', ()), ('subprocess.Popen', ()), ('open', ('SYNTHETIC', 'wb', 0)), ('os.rename', ())]:
            try:
                probe.hook(event, args)
            except GuardViolation:
                pass
            else:
                raise AssertionError
        assert probe.counts['network'] == 1 and probe.counts['write'] == 2 and probe.counts['process'] == 1
    test('guard_synthetic_events_without_real_io', guard_selfcheck)

    def json_success():
        with Scenario(g, source_bytes) as s:
            g['write_json'](s.checkpoint, {'a': 1}, context='PROGRESS_AFTER_WRITE')
            assert json.loads(s.fs.data[str(s.checkpoint)]) == {'a': 1}
            assert [e[0] for e in s.fs.events] == ['JSON_OPEN', 'JSON_WRITE', 'JSON_CLOSE', 'JSON_REPLACE']
    test('json_real_serialization_full_memory_chain', json_success)

    for operation in ('JSON_OPEN', 'JSON_WRITE', 'JSON_CLOSE', 'JSON_REPLACE'):
        def case(operation=operation):
            with Scenario(g, source_bytes) as s:
                s.fs.inject(operation, synthetic_error())
                try:
                    g['write_json'](s.checkpoint, {'a': 1}, context='PROGRESS_AFTER_WRITE')
                except g['Failure'] as exc:
                    assert_diagnostic(exc.diagnostic, operation, 'PROGRESS_AFTER_WRITE', 'OSError', 5, 32)
                else:
                    raise AssertionError
                assert str(s.checkpoint) not in s.fs.data
        test(operation.lower() + '_fault', case)

    for effect in ('SHORT', 'NONE'):
        def case(effect=effect):
            with Scenario(g, source_bytes) as s:
                s.fs.inject('JSON_WRITE', effect)
                try:
                    g['write_json'](s.checkpoint, {'a': 1}, context='PROGRESS_AFTER_WRITE')
                except g['Failure'] as exc:
                    assert_diagnostic(exc.diagnostic, 'JSON_WRITE', 'PROGRESS_AFTER_WRITE')
                else:
                    raise AssertionError
                assert not any(e[0] == 'JSON_REPLACE' for e in s.fs.events)
        test('json_write_' + effect.lower(), case)

    for label, obj, exception_type in [('type', {'x': object()}, 'TypeError'), ('nonfinite', {'x': float('nan')}, 'ValueError'), ('unicode', {'x': '\ud800'}, 'UnicodeEncodeError')]:
        def case(obj=obj, exception_type=exception_type):
            with Scenario(g, source_bytes) as s:
                try:
                    g['write_json'](s.checkpoint, obj, context='PROGRESS_BEFORE_WRITE')
                except g['Failure'] as exc:
                    assert_diagnostic(exc.diagnostic, 'JSON_SERIALIZE', 'PROGRESS_BEFORE_WRITE', exception_type)
                else:
                    raise AssertionError
                assert not s.fs.events
        test('json_serialize_' + label, case)

    def json_limit():
        with Scenario(g, source_bytes) as s:
            s.patches.item(g, 'JSON_MAX', 16)
            try:
                g['write_json'](s.checkpoint, {'oversized': 'x' * 17}, context='PROGRESS')
            except g['Failure'] as exc:
                assert_diagnostic(exc.diagnostic, 'JSON_SERIALIZE')
            else:
                raise AssertionError
            assert not s.fs.events
    test('json_serialized_size_limit', json_limit)

    def json_first_error():
        with Scenario(g, source_bytes) as s:
            s.fs.inject('JSON_WRITE', synthetic_error(number=5, winerror=32))
            s.fs.inject('JSON_CLOSE', synthetic_error(number=28, winerror=112))
            try:
                g['write_json'](s.checkpoint, {'a': 1}, context='PROGRESS_BEFORE_WRITE')
            except g['Failure'] as exc:
                assert_diagnostic(exc.diagnostic, 'JSON_WRITE', errno=5, winerror=32)
                assert_diagnostic(exc.secondary_errors[0], 'JSON_CLOSE', errno=28, winerror=112)
            else:
                raise AssertionError
    test('json_write_first_error_survives_close_error', json_first_error)

    def successful_stream():
        with Scenario(g, source_bytes) as s:
            state, error = s.stream()
            assert error is None
            assert state['received_bytes'] == state['written_bytes'] == 3
            assert state['response_body_complete'] is True
            assert s.save_contexts == ['PROGRESS_BEFORE_WRITE', 'PROGRESS_AFTER_WRITE', 'PROGRESS_FINAL']
            assert len([e for e in s.fs.events if e[0] == 'JSON_REPLACE']) == 3
            assert len(s.disk.calls) >= 3
    test('stream_keeps_all_progress_and_disk_protection', successful_stream)

    for context in ('PROGRESS_BEFORE_WRITE', 'PROGRESS_AFTER_WRITE'):
        for operation in ('JSON_OPEN', 'JSON_WRITE', 'JSON_CLOSE', 'JSON_REPLACE'):
            def case(context=context, operation=operation):
                with Scenario(g, source_bytes) as s:
                    s.fs.inject(operation, synthetic_error(), context=context)
                    state, error = s.stream()
                    assert error is not None
                    assert_diagnostic(error.diagnostic, operation, context, 'OSError', 5, 32)
                    assert state['received_bytes'] == 3
                    assert state['written_bytes'] == (0 if context == 'PROGRESS_BEFORE_WRITE' else 3)
                    assert not state['response_body_complete']
                    assert s.response.read_calls == 1
                    assert s.static_calls == 0 and s.requests == 0
            test(context.lower() + '_' + operation.lower(), case)

    for effect in ('SHORT', 'NONE', 'EXCEPTION'):
        def case(effect=effect):
            with Scenario(g, source_bytes) as s:
                s.fs.inject('BODY_WRITE', synthetic_error() if effect == 'EXCEPTION' else effect)
                state, error = s.stream()
                assert error is not None
                assert_diagnostic(error.diagnostic, 'BODY_WRITE')
                assert state['received_bytes'] == 3
                assert state['written_bytes'] == (2 if effect == 'SHORT' else 0)
                if effect == 'NONE':
                    assert state['counters_complete'] is False
                if effect == 'EXCEPTION':
                    assert state['counters_complete'] is False
                assert s.save_contexts == ['PROGRESS_BEFORE_WRITE']
                assert len([e for e in s.fs.events if e[0] == 'BODY_WRITE']) == 1
        test('body_write_' + effect.lower(), case)

    def response_read_error():
        with Scenario(g, source_bytes) as s:
            s.response.error = synthetic_error()
            state, error = s.stream()
            assert_diagnostic(error.diagnostic, 'RESPONSE_READ', exception_type='OSError', errno=5, winerror=32)
            assert state['received_bytes'] == state['written_bytes'] == 0
            assert state['counters_complete'] is False
            assert not s.save_contexts
    test('response_read_error_is_distinct', response_read_error)

    def disk_error():
        with Scenario(g, source_bytes) as s:
            s.disk.failure_at, s.disk.failure = 1, synthetic_error()
            state, error = s.stream()
            assert_diagnostic(error.diagnostic, 'DISK_CHECK', exception_type='OSError', errno=5, winerror=32)
            assert s.response.read_calls == 0 and state['received_bytes'] == 0
    test('disk_check_error_is_distinct', disk_error)

    def record_first():
        state = g['download_state']()
        first = g['Failure']('OUTPUT_ERROR', operation='BODY_WRITE', context='DOWNLOAD', cause=synthetic_error(number=5, winerror=32))
        second = g['Failure']('OUTPUT_ERROR', operation='JSON_REPLACE', context='FINAL_CHECKPOINT', cause=synthetic_error(number=28, winerror=112))
        g['record_error'](state, first)
        for ignored in range(20):
            g['record_error'](state, second)
        assert_diagnostic(state['first_error'], 'BODY_WRITE', errno=5, winerror=32)
        assert 1 <= len(state['secondary_errors']) <= 8
        assert_clean(state)
    test('first_error_preserved_secondary_errors_bounded', record_first)

    def unknown_exception_sanitized():
        class SecretException(Exception):
            pass
        exc = SecretException(SECRET)
        exc.errno, exc.winerror = True, SECRET
        state = g['download_state']()
        g['record_error'](state, exc, operation='BODY_WRITE', context='DOWNLOAD')
        diag = state['first_error']
        assert diag['exception_type'] not in ('SecretException', SECRET)
        assert diag['errno'] is None and diag['winerror'] is None
        assert_clean(state)
    test('unknown_exception_and_noninteger_codes_are_redacted', unknown_exception_sanitized)

    def known_exception_invalid_numbers():
        exc = synthetic_error()
        exc.errno, exc.winerror = True, SECRET
        state = g['download_state']()
        g['record_error'](state, exc, operation='BODY_WRITE', context='DOWNLOAD')
        assert state['first_error']['exception_type'] == 'OSError'
        assert state['first_error']['errno'] is None and state['first_error']['winerror'] is None
        assert_clean(state)
    test('known_exception_bool_and_string_codes_are_redacted', known_exception_invalid_numbers)

    def final_report_failure():
        with Scenario(g, source_bytes) as s:
            s.fs.inject('JSON_REPLACE', synthetic_error(), suffix='report.json')
            report = dict(status='completed', error_code=None, first_error=None, secondary_errors=[], cleanup={'status': 'NO_PARTIAL_FILE'})
            result = g['finish'](s.out, report)
            assert result == 1 and report['report_persisted'] is False
            assert_diagnostic(report['first_error'], 'JSON_REPLACE', exception_type='OSError', errno=5, winerror=32)
            assert not any(e[0] == 'BODY_WRITE' for e in s.fs.events)
    test('final_report_save_failure_is_retained_in_memory', final_report_failure)

    def final_report_preserves_first():
        with Scenario(g, source_bytes) as s:
            report = dict(status='failed', error_code=None, first_error=None, secondary_errors=[], cleanup={'status': 'NO_PARTIAL_FILE'})
            g['record_error'](report, g['Failure']('OUTPUT_ERROR', operation='BODY_WRITE', context='DOWNLOAD', cause=synthetic_error()))
            s.fs.inject('JSON_CLOSE', synthetic_error(number=28, winerror=112), suffix='report.pending')
            assert g['finish'](s.out, report) == 1
            assert_diagnostic(report['first_error'], 'BODY_WRITE', errno=5, winerror=32)
            assert_diagnostic(report['secondary_errors'][-1], 'JSON_CLOSE', errno=28, winerror=112)
            assert report['report_persisted'] is False
    test('final_report_failure_does_not_overwrite_first_error', final_report_preserves_first)

    for operation in ('BODY_OPEN', 'BODY_WRITE', 'BODY_FLUSH', 'BODY_FSYNC', 'BODY_CLOSE'):
        def case(operation=operation):
            with Scenario(g, source_bytes) as s:
                s.fs.inject(operation, synthetic_error())
                state = s.download()
                assert state['status'] == 'failed' and state['checkpoint_persisted'] is True
                assert_diagnostic(state['first_error'], operation, 'DOWNLOAD', 'OSError', 5, 32)
                assert state['request_count'] == state['get_send_attempts'] == s.requests == 1
                if operation == 'BODY_WRITE':
                    assert state['counters_complete'] is False
                assert s.static_calls == 0 and s.save_contexts.count('FINAL_CHECKPOINT') == 1
                assert json.loads(s.fs.data[str(s.checkpoint)])['first_error'] == state['first_error']
        test('download_' + operation.lower() + '_fault', case)

    def download_response_error():
        with Scenario(g, source_bytes) as s:
            s.response.error = synthetic_error()
            state = s.download()
            assert_diagnostic(state['first_error'], 'RESPONSE_READ', 'DOWNLOAD', 'OSError', 5, 32)
            assert state['received_bytes'] == state['written_bytes'] == 0
            assert s.requests == 1 and s.static_calls == 0
    test('download_receive_error_single_request', download_response_error)

    def download_disk_error():
        with Scenario(g, source_bytes) as s:
            s.disk.failure_at, s.disk.failure = 1, synthetic_error()
            state = s.download()
            assert_diagnostic(state['first_error'], 'DISK_CHECK', 'DOWNLOAD', 'OSError', 5, 32)
            assert s.requests == 0 and s.static_calls == 0
    test('download_disk_error_before_request', download_disk_error)

    for context in ('PROGRESS_BEFORE_WRITE', 'PROGRESS_AFTER_WRITE'):
        for operation in ('JSON_OPEN', 'JSON_WRITE', 'JSON_CLOSE', 'JSON_REPLACE'):
            def case(context=context, operation=operation):
                with Scenario(g, source_bytes) as s:
                    s.fs.inject(operation, synthetic_error(), context=context)
                    state = s.download()
                    assert_diagnostic(state['first_error'], operation, context, 'OSError', 5, 32)
                    assert state['checkpoint_persisted'] is True
                    assert state['received_bytes'] == 3
                    assert state['written_bytes'] == (0 if context == 'PROGRESS_BEFORE_WRITE' else 3)
                    assert s.requests == 1 and s.static_calls == 0
                    assert s.save_contexts.count(context) == 1
                    assert s.save_contexts.count('FINAL_CHECKPOINT') == 1
            test('download_' + context.lower() + '_' + operation.lower(), case)

    for context in ('PROGRESS_BEFORE_WRITE', 'PROGRESS_AFTER_WRITE', 'FINAL_CHECKPOINT'):
        def case(context=context):
            with Scenario(g, source_bytes) as s:
                real_dumps = json.dumps
                calls = []
                def leaf_serializer(*args, **kwargs):
                    body = real_dumps(*args, **kwargs)
                    if s.fs.context == context:
                        calls.append(context)
                        raise TypeError(SECRET)
                    return body
                s.patches.attr(json, 'dumps', leaf_serializer)
                state = s.download()
                assert_diagnostic(state['first_error'], 'JSON_SERIALIZE', context, 'TypeError')
                assert calls == [context]
                assert state['checkpoint_persisted'] is (context != 'FINAL_CHECKPOINT')
                assert s.static_calls == 0 and s.requests == 1
        test('download_' + context.lower() + '_serialize_fault', case)

    def body_first_with_close_and_final():
        with Scenario(g, source_bytes) as s:
            s.fs.inject('BODY_WRITE', synthetic_error(number=5, winerror=32))
            s.fs.inject('BODY_CLOSE', synthetic_error(number=28, winerror=112))
            s.fs.inject('JSON_OPEN', synthetic_error(number=13, winerror=5), context='FINAL_CHECKPOINT')
            state = s.download()
            assert_diagnostic(state['first_error'], 'BODY_WRITE', errno=5, winerror=32)
            assert [x['operation'] for x in state['secondary_errors']] == ['BODY_CLOSE', 'JSON_OPEN']
            assert state['checkpoint_persisted'] is False
            assert str(s.checkpoint) not in s.fs.data
            journal = g['read_journal'](s.work / 'download-progress.journal')
            assert journal['last']['first_error'] == state['first_error']
            assert journal['last']['written_bytes'] == 0 and journal['last']['received_bytes'] == 3
            assert s.save_contexts.count('FINAL_CHECKPOINT') == 1
            assert s.static_calls == 0 and s.requests == 1
    test('body_first_survives_close_and_final_save_failure', body_first_with_close_and_final)

    def no_worker_retry():
        with Scenario(g, source_bytes) as s:
            s.response.status = 403
            first = s.download()
            marker = bytes(s.fs.data['work/output/request-attempt.json'])
            checkpoint = bytes(s.fs.data[str(s.checkpoint)])
            try:
                s.download()
            except g['Failure'] as exc:
                assert exc.code == 'ATTEMPT_ALREADY_USED'
            else:
                raise AssertionError
            assert first['error_code'] == 'HTTP_FORBIDDEN'
            assert s.requests == 1 and s.static_calls == 0
            assert s.fs.data['work/output/request-attempt.json'] == marker
            assert s.fs.data[str(s.checkpoint)] == checkpoint
    test('worker_attempt_marker_blocks_second_memory_request', no_worker_retry)

    def cleanup_failure_preserves_first():
        with Scenario(g, source_bytes) as s:
            report = dict(status='failed', first_error=None, secondary_errors=[], cleanup={'status': 'FAILED'})
            g['record_error'](report, g['Failure']('IO_ERROR', 'BODY_WRITE', 'DOWNLOAD', synthetic_error()))
            assert g['finish'](s.out, report) == 1
            assert_diagnostic(report['first_error'], 'BODY_WRITE', errno=5, winerror=32)
            assert report['error_code'] == 'IO_ERROR'
            assert any(x['error_code'] == 'CLEANUP_FAILED' for x in report['secondary_errors'])
    test('cleanup_failure_does_not_replace_first_error', cleanup_failure_preserves_first)

    for phase in ('connect', 'request'):
        def case(phase=phase):
            with Patches() as p:
                events = []
                p.attr(ssl, 'create_default_context', lambda: types.SimpleNamespace(check_hostname=True, verify_mode=ssl.CERT_REQUIRED))
                class Connection:
                    sock = FakeSocket()
                    def connect(self):
                        events.append('connect')
                        if phase == 'connect':
                            raise synthetic_error(number=5, winerror=32)
                    def request(self, method, path, body, headers):
                        events.append('request')
                        assert method == 'GET' and body is None
                        assert not any(k.lower() in ('authorization', 'cookie', 'range') for k in headers)
                        raise synthetic_error(number=5, winerror=32)
                    def close(self):
                        events.append('close')
                        raise synthetic_error(number=28, winerror=112)
                one = g['OneGET'](factory=lambda *ignored: Connection())
                try:
                    one.open(g['URL'], g['Budget'](100, clock=lambda: 0), lambda: events.append('sent'))
                except g['Failure'] as exc:
                    assert_diagnostic(exc.diagnostic, 'NETWORK_OPEN', errno=5, winerror=32)
                    assert_diagnostic(exc.secondary_errors[0], 'CONNECTION_CLOSE', errno=28, winerror=112)
                else:
                    raise AssertionError
                previous = list(events)
                try:
                    one.open(g['URL'], g['Budget'](100, clock=lambda: 0), lambda: events.append('retry'))
                except g['Failure'] as exc:
                    assert exc.code == 'REQUEST_ALREADY_USED'
                else:
                    raise AssertionError
                assert events == previous
        test('oneget_' + phase + '_first_error_preserved_no_retry', case)

    def exit_unconfirmed():
        proc = FakeProcess(unconfirmed=True)
        result = g['wait_process'](proc, 5, 10, clock=lambda: 0)
        assert result['worker_exit_confirmed'] is False
        assert result['error_code'] == 'DEADLINE_EXCEEDED'
        assert result['exit_confirmation_status'] == 'UNKNOWN'
        assert any(item['error_code'] == 'WORKER_EXIT_UNCONFIRMED' for item in result['secondary_errors'])
        assert proc.waits == 2 and proc.terminations == 1
        with Scenario(g, source_bytes) as s:
            s.fs.data['work/output/' + g['PART']] = b'abc'
            cleanup = g['cleanup_partial'](s.out, False)
            assert cleanup['status'] == 'UNKNOWN' and cleanup['partial_cleanup_attempted'] is False
            assert not s.fs.deletes
            assert g['can_inspect'](dict(status='completed', response_body_complete=True, sha256_matches_expected=True,
                                        actual_sha256=g['EXPECTED'], received_bytes=3, written_bytes=3,
                                        artifact_filename=g['FILENAME']), False) is False
    test('unconfirmed_exit_blocks_cleanup_and_static_gate', exit_unconfirmed)

    def supervise_memory(s, process):
        # Prior worker output is a fixture, materialized only when mocked Popen runs.
        # No real attempt marker is read, removed or reset by this memory fixture.
        s.fs.data.pop(str(s.out / 'execution-started.json'), None)
        deferred = {}
        for path in [s.checkpoint, s.work / 'static-checkpoint.json',
                     s.out / 'request-attempt.json', s.out / 'static-attempt.json',
                     s.out / g['PART'], s.out / g['FILENAME'], s.work / 'download-progress.journal']:
            if str(path) in s.fs.data:
                deferred[str(path)] = s.fs.data.pop(str(path))
        events, stops, reports = [], [], []
        class Stop:
            def __init__(self):
                self.stopped = False
                stops.append(self)
            def set(self):
                self.stopped = True
        def popen(command, **kwargs):
            assert command[5] == 'worker'
            events.append(command[6])
            assert command[6] == 'download'
            s.fs.data.update(deferred)
            return process
        real_finish = g['finish']
        def capture_finish(out, report):
            result = real_finish(out, report)
            reports.append(copy.deepcopy(report))
            return result
        s.patches.attr(subprocess, 'Popen', popen)
        s.patches.attr(threading, 'Thread', FakeThread)
        s.patches.attr(threading, 'Event', Stop)
        s.patches.item(g, 'finish', capture_finish)
        result = g['supervise'](s.work, s.out)
        assert result == 1 and all(stop.stopped for stop in stops)
        assert reports and reports[-1]['stages']['static']['status'] == 'not_started'
        assert s.static_calls == 0 and events in ([], ['download'])
        return reports[-1], events

    def stale_checkpoint_supervisor():
        with Scenario(g, source_bytes) as s:
            s.fs.inject('BODY_WRITE', synthetic_error())
            s.fs.inject('JSON_OPEN', synthetic_error(), context='FINAL_CHECKPOINT')
            worker = s.download()
            assert worker['checkpoint_persisted'] is False
            report, events = supervise_memory(s, FakeProcess(code=1))
            data = report['stages']['download']
            assert events == ['download']
            assert data['checkpoint_terminal_confirmed'] is False
            assert data['worker_error_details'] == 'RECORDED_FROM_JOURNAL'
            assert data.get('data', 'UNKNOWN') == 'UNKNOWN'
            assert data['journal_crash_evidence']['last']['first_error'] == worker['first_error']
            assert data['first_error'] == worker['first_error']
            assert any(item['operation'] == 'CHECKPOINT_READ' for item in data['secondary_errors'])
            assert s.requests == 1
    test('supervisor_missing_checkpoint_preserves_validated_journal_first_error', stale_checkpoint_supervisor)

    def supervisor_exit_unconfirmed():
        with Scenario(g, source_bytes) as s:
            s.fs.data['work/output/' + g['PART']] = b'abc'
            report, events = supervise_memory(s, FakeProcess(unconfirmed=True))
            assert events == ['download']
            assert report['worker_exit_unconfirmed'] is True
            assert report['cleanup']['status'] == 'UNKNOWN'
            assert report['cleanup']['partial_cleanup_attempted'] is False
            assert report['report_persisted'] is False
            assert not s.fs.deletes and s.requests == 0
            assert s.save_contexts.count('INITIAL_REPORT') == 1
            assert s.save_contexts.count('FINAL_REPORT') == 0
            assert report['stages']['download']['data'] == 'UNKNOWN'
    test('supervisor_unconfirmed_exit_has_no_later_save_cleanup_or_static', supervisor_exit_unconfirmed)

    for context in ('INITIAL_REPORT', 'FINAL_REPORT'):
        def case(context=context):
            with Scenario(g, source_bytes) as s:
                state = g['download_state']()
                state.update(status='completed', checkpoint_persisted=True, finished_at='SYNTHETIC_TIME',
                             candidate_id=g['CANDIDATE_ID'], source_sha256=s.source_hash,
                             body_fsync_completed=True, body_close_completed=True,
                             request_count=1, get_send_attempts=1, http_status=200,
                             response_body_complete=True, sha256_matches_expected=True,
                             actual_sha256=g['EXPECTED'], received_bytes=3, written_bytes=3,
                             artifact_filename=g['FILENAME'])
                s.seed_journal_proof(state)
                s.fs.seed_json(str(s.checkpoint), state)
                s.fs.data['work/output/' + g['PART']] = b'abc'
                s.fs.inject('JSON_REPLACE', synthetic_error(), context=context, suffix='report.json')
                report, events = supervise_memory(s, FakeProcess(code=0))
                assert report['report_save_failed'] is True and report['report_persisted'] is False
                assert_diagnostic(report['first_error'], 'JSON_REPLACE', context, 'OSError', 5, 32)
                assert report['cleanup']['status'] == 'UNKNOWN'
                assert report['cleanup']['partial_cleanup_attempted'] is False
                assert s.save_contexts.count(context) == 1 and not s.fs.deletes
                if context == 'INITIAL_REPORT':
                    assert events == [] and 'FINAL_REPORT' not in s.save_contexts
                else:
                    assert events == ['download']
        test('supervisor_' + context.lower() + '_failure_stops_future_actions', case)

    for operation in ('BODY_WRITE', 'JOURNAL_WRITE'):
        def case(operation=operation):
            with Scenario(g, source_bytes) as s:
                s.fs.inject(operation, synthetic_error(), occurrence=3 if operation == 'JOURNAL_WRITE' else 1)
                worker = s.download()
                report, events = supervise_memory(s, FakeProcess(code=1))
                stage = report['stages']['download']
                assert events == ['download'] and s.requests == (0 if operation == 'JOURNAL_WRITE' else 1)
                assert stage['checkpoint_terminal_confirmed'] is True
                assert stage['worker_error_details'] == 'RECORDED'
                assert stage['first_error'] == worker['first_error'] == report['first_error']
        test('supervisor_retains_' + operation.lower() + '_first_error_and_blocks_static', case)

    def restored_connect_memory_leaves():
        with Scenario(g, source_bytes) as s, MemoryNetwork() as net:
            g['worker_claim']('download', s.work, s.out)
            connection = g['DirectHTTPS']('download-r2.pytorch.org', net.context, s.budget())
            before = dict(s.fs.data)
            for ignored in range(2):
                try:
                    connection.connect()
                except g['Failure'] as exc:
                    assert exc.code == 'OFFLINE_PREPARATION_ONLY'
                else:
                    raise AssertionError
            assert not net.events and not net.sent and connection.auto_open == 0
            assert s.fs.data == before and not s.requests
    test('source_only_connect_blocks_before_memory_dns_socket_tls', restored_connect_memory_leaves)

    def candidate_cli_missing_authorization():
        with Scenario(g, source_bytes) as s:
            s.fs.data.pop('work/execution-authorization.json')
            capture = io.StringIO()
            s.patches.attr(sys, 'stdout', capture)
            s.patches.attr(sys, 'argv', ['run_check.py', 'supervise', str(s.work), str(s.out)])
            before = dict(s.fs.data)
            assert g['main']() == 1
            result = json.loads(capture.getvalue())
            assert result['error_code'] == 'OFFLINE_PREPARATION_ONLY'
            assert s.fs.data == before and not s.fs.events and not s.requests and not s.static_calls
    test('source_only_cli_missing_authorization_stops_before_actions', candidate_cli_missing_authorization)

    for phase in ('connect', 'handshake'):
        def case(phase=phase):
            actual_oneget = g['OneGET']
            with Scenario(g, source_bytes) as s, MemoryNetwork(phase=phase, close_error=True) as net:
                g['worker_claim']('download', s.work, s.out)
                one = actual_oneget()
                try:
                    one.open(g['URL'], g['Budget'](100, clock=lambda: 0), lambda: None)
                except g['Failure'] as exc:
                    assert exc.code == 'OFFLINE_PREPARATION_ONLY'
                    assert exc.secondary_errors == []
                else:
                    raise AssertionError
                assert not net.events
                assert not net.sent
        test('restored_' + phase + '_first_error_survives_close_failure', case)

    for field, value in [('host', 'invalid.example'), ('port', 444), ('_tunnel_host', 'invalid.example'),
                         ('check_hostname', False), ('verify_mode', ssl.CERT_NONE)]:
        def case(field=field, value=value):
            with Scenario(g, source_bytes) as s, MemoryNetwork() as net:
                g['worker_claim']('download', s.work, s.out)
                connection = g['DirectHTTPS']('download-r2.pytorch.org', net.context, g['Budget'](100, clock=lambda: 0))
                if field in ('check_hostname', 'verify_mode'):
                    setattr(net.context, field, value)
                else:
                    setattr(connection, field, value)
                try:
                    connection.connect()
                except g['Failure'] as exc:
                    assert exc.code == 'OFFLINE_PREPARATION_ONLY'
                else:
                    raise AssertionError
                assert net.events == [] and not net.sent
        test('direct_connect_' + field + '_invalid_before_dns', case)

    def direct_connect_unauthorized():
        with Scenario(g, source_bytes) as s, MemoryNetwork() as net:
            del s.fs.data['work/execution-authorization.json']
            connection = g['DirectHTTPS']('download-r2.pytorch.org', net.context, g['Budget'](100, clock=lambda: 0))
            try:
                connection.connect()
            except g['Failure'] as exc:
                assert exc.code == 'OFFLINE_PREPARATION_ONLY'
            else:
                raise AssertionError
            assert not net.events and not net.sent and not s.fs.events
    test('direct_connect_missing_authorization_before_dns', direct_connect_unauthorized)

    def direct_connect_single_use():
        with Scenario(g, source_bytes) as s, MemoryNetwork() as net:
            g['worker_claim']('download', s.work, s.out)
            connection = g['DirectHTTPS']('download-r2.pytorch.org', net.context, s.budget())
            before = dict(s.fs.data)
            for ignored in range(2):
                try:
                    connection.connect()
                except g['Failure'] as exc:
                    assert exc.code == 'OFFLINE_PREPARATION_ONLY'
                else:
                    raise AssertionError
            assert not net.events and not net.sent and connection.auto_open == 0
            assert s.fs.data == before and not s.requests
    test('source_only_connect_repeated_calls_never_reach_network', direct_connect_single_use)

    def restored_one_get_exact_wire():
        with Scenario(g, source_bytes) as s, MemoryNetwork() as net:
            g['worker_claim']('download', s.work, s.out)
            connection = g['DirectHTTPS']('download-r2.pytorch.org', net.context, s.budget())
            before = dict(s.fs.data)
            for ignored in range(2):
                try:
                    connection.connect()
                except g['Failure'] as exc:
                    assert exc.code == 'OFFLINE_PREPARATION_ONLY'
                else:
                    raise AssertionError
            assert not net.events and not net.sent and connection.auto_open == 0
            assert s.fs.data == before and not s.requests
    test('source_only_direct_connection_has_no_wire_request', restored_one_get_exact_wire)

    def restored_cli_supervise_dispatch_blocked():
        with Scenario(g, source_bytes) as s:
            s.fs.data.pop(str(s.out / 'execution-started.json'))
            calls, capture = [], io.StringIO()
            s.patches.item(g, 'supervise', lambda work, out: calls.append((work, out)) or 0)
            s.patches.attr(sys, 'stdout', capture)
            s.patches.attr(sys, 'argv', ['run_check.py', 'supervise', str(s.work), str(s.out)])
            assert g['main']() == 1
            assert json.loads(capture.getvalue())['error_code'] == 'OFFLINE_PREPARATION_ONLY'
            assert calls == []
            assert not s.requests and not s.fs.events and not s.static_calls
    test('source_only_cli_authorized_memory_supervise_dispatch_blocked', restored_cli_supervise_dispatch_blocked)

    for phase in ('download', 'static'):
        def case(phase=phase):
            with Scenario(g, source_bytes) as s:
                calls, capture = [], io.StringIO()
                s.patches.item(g, 'worker', lambda *args: calls.append(args) or 0)
                s.patches.attr(sys, 'stdout', capture)
                s.patches.attr(sys, 'argv', ['run_check.py', 'worker', phase, str(s.work), str(s.out), '10'])
                assert g['main']() == 1
                assert json.loads(capture.getvalue())['error_code'] == 'OFFLINE_PREPARATION_ONLY'
                assert calls == []
                assert not s.requests and not s.fs.events and not s.static_calls
        test('source_only_cli_authorized_memory_' + phase + '_worker_dispatch_blocked', case)

    for filename in ('execution-started.json', 'request-attempt.json', 'static-attempt.json', 'report.json', 'payload.part', 'download-checkpoint.json'):
        def case(filename=filename):
            with Scenario(g, source_bytes) as s:
                s.fs.data.pop(str(s.out / 'execution-started.json'))
                path = s.work / filename if filename == 'download-checkpoint.json' else s.out / (g['PART'] if filename == 'payload.part' else filename)
                s.fs.data[str(path)] = b'CONSUMED_MEMORY_FIXTURE'
                before = dict(s.fs.data)
                try:
                    g['supervise'](s.work, s.out)
                except g['Failure'] as exc:
                    assert exc.code == 'ATTEMPT_ALREADY_USED'
                else:
                    raise AssertionError
                assert before == s.fs.data and not s.fs.events and not s.requests and not s.static_calls
        test('candidate_consumed_' + filename.replace('.', '_') + '_blocks_supervisor', case)

    def fixed_limits():
        assert g['URL'] == 'https://download-r2.pytorch.org/whl/cu128/torch-2.10.0%2Bcu128-cp312-cp312-win_amd64.whl'
        assert g['EXPECTED'] == 'fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae'
        assert g['BODY_MAX'] == 4 * 1024 ** 3
        assert g['FREE_START'] == 8 * 1024 ** 3 and g['FREE_KEEP'] == 2 * 1024 ** 3
        assert g['CD_MAX'] == g['TEXT_MAX'] == 16 * 1024 ** 2 and g['MEMBERS_MAX'] == 10000
    test('candidate_fixed_url_sha_and_resource_constants', fixed_limits)

    def preflight_memory_valid():
        with Scenario(g, source_bytes) as s:
            before = dict(s.fs.data)
            approved = g['candidate_preflight'](s.work, s.out, require_execution=True)
            assert approved['source_hash'] == s.source_hash
            assert before == s.fs.data and not s.fs.events and s.requests == 0
    test('candidate_preflight_all_evidence_memory_only', preflight_memory_valid)

    def expect_preflight_failure(s, code=None, work=None, out=None, require_execution=False):
        before = dict(s.fs.data)
        try:
            g['candidate_preflight'](work or s.work, out or s.out, require_execution=require_execution)
        except g['Failure'] as exc:
            if code is not None:
                assert exc.code == code
            assert_clean(exc.diagnostic)
        else:
            raise AssertionError
        assert before == s.fs.data and not s.fs.events and not s.requests and not s.static_calls

    for field, value in [('candidate_id', 'OTHER_CANDIDATE'), ('source_sha256', '0' * 64),
                         ('action', 'retry_download'), ('authorized', False)]:
        def case(field=field, value=value):
            with Scenario(g, source_bytes) as s:
                path = 'work/execution-authorization.json'
                auth = json.loads(s.fs.data[path]); auth[field] = value
                s.fs.seed_json(path, auth)
                expect_preflight_failure(s)
        test('authorization_' + field + '_mismatch_rejected', case)

    for filename, field, value in [
            ('candidate-identity.json', 'candidate_id', 'OLD_CANDIDATE'),
            ('candidate-identity.json', 'live_execution_authorized', True),
            ('output/attempt.json', 'candidate_id', 'OLD_CANDIDATE'),
            ('output/attempt.json', 'source_sha256', '0' * 64),
            ('output/attempt.json', 'url', 'https://invalid.example/'),
            ('output/attempt.json', 'expected_sha256', '0' * 64),
            ('offline-tests.json', 'source_sha256', '0' * 64),
            ('offline-tests.json', 'candidate_id', 'OLD_CANDIDATE'),
            ('offline-tests.json', 'network_requests', True),
            ('independent-review.json', 'source_sha256', '0' * 64),
            ('independent-review.json', 'candidate_id', 'OLD_CANDIDATE')]:
        def case(filename=filename, field=field, value=value):
            with Scenario(g, source_bytes) as s:
                path = 'work/' + filename
                item = json.loads(s.fs.data[path]); item[field] = value
                s.fs.seed_json(path, item)
                expect_preflight_failure(s)
        test('candidate_' + filename.replace('/', '_').replace('.', '_') + '_' + field + '_mismatch_rejected', case)

    for filename in ('offline_test.py', 'safety_test.py'):
        def case(filename=filename):
            with Scenario(g, source_bytes) as s:
                s.fs.data['work/' + filename] += b'CHANGED'
                expect_preflight_failure(s)
        test('candidate_changed_' + filename.replace('.', '_') + '_rejected', case)

    for role in ('work', 'out'):
        def case(role=role):
            with Scenario(g, source_bytes) as s:
                expect_preflight_failure(s, work=s.fs.path('OTHER') if role == 'work' else s.work,
                                         out=s.fs.path('OTHER') if role == 'out' else s.out)
        test('candidate_other_' + role + '_directory_rejected', case)

    def missing_identity():
        with Scenario(g, source_bytes) as s:
            del s.fs.data['work/candidate-identity.json']
            expect_preflight_failure(s)
    test('candidate_missing_identity_rejected', missing_identity)

    def old_execution_marker():
        with Scenario(g, source_bytes) as s:
            path = str(s.out / 'execution-started.json')
            item = json.loads(s.fs.data[path]); item['candidate_id'] = 'OLD_CANDIDATE'
            s.fs.seed_json(path, item)
            expect_preflight_failure(s, require_execution=True)
    test('candidate_old_execution_identity_rejected', old_execution_marker)

    for arguments in [[], ['execute'], ['worker', 'OTHER', 'work', 'work/output', '10']]:
        def case(arguments=arguments):
            with Scenario(g, source_bytes) as s:
                capture = io.StringIO()
                s.patches.attr(sys, 'stdout', capture)
                s.patches.attr(sys, 'argv', ['run_check.py'] + arguments)
                before = dict(s.fs.data)
                assert g['main']() == 1
                assert json.loads(capture.getvalue())['status'] == 'failed'
                assert s.fs.data == before and not s.fs.events and not s.requests and not s.static_calls
        test('candidate_invalid_cli_' + ('none' if not arguments else arguments[0]) + '_rejected', case)

    for operation in ('ARCHIVE_OPEN', 'ARCHIVE_CLOSE'):
        def case(operation=operation):
            actual_static = g['static_check']
            with Scenario(g, source_bytes) as s:
                s.seed_static_proof()
                calls = []
                s.patches.item(g, 'inspect_archive', lambda *args: calls.append('inspect') or {'synthetic': True})
                s.fs.inject(operation, synthetic_error())
                state = actual_static(s.work, s.out, s.budget(), s.work / 'static-checkpoint.json')
                assert state['status'] == 'failed' and state['checkpoint_persisted'] is True
                assert_diagnostic(state['first_error'], operation, 'STATIC', 'OSError', 5, 32)
                assert calls == ([] if operation == 'ARCHIVE_OPEN' else ['inspect'])
                assert s.requests == 0
                assert s.save_contexts == ['ATTEMPT_MARKER', 'PROGRESS_INITIAL', 'FINAL_CHECKPOINT']
        test('static_' + operation.lower() + '_diagnostic_memory_only', case)

    def static_first_preserved_on_close_and_final_failure():
        actual_static = g['static_check']
        with Scenario(g, source_bytes) as s:
            s.seed_static_proof()
            def inspect_fault(*args):
                raise g['Failure']('ZIP_INVALID', operation='ARCHIVE_OPEN', context='STATIC', cause=synthetic_error(number=5, winerror=32))
            s.patches.item(g, 'inspect_archive', inspect_fault)
            s.fs.inject('ARCHIVE_CLOSE', synthetic_error(number=28, winerror=112))
            s.fs.inject('JSON_REPLACE', synthetic_error(number=13, winerror=5), context='FINAL_CHECKPOINT')
            state = actual_static(s.work, s.out, s.budget(), s.work / 'static-checkpoint.json')
            assert state['status'] == 'failed' and state['checkpoint_persisted'] is False
            assert_diagnostic(state['first_error'], 'ARCHIVE_OPEN', 'STATIC', 'OSError', 5, 32)
            assert [x['operation'] for x in state['secondary_errors']] == ['ARCHIVE_CLOSE', 'JSON_REPLACE']
            assert s.requests == 0 and s.save_contexts.count('FINAL_CHECKPOINT') == 1
    test('static_inspect_first_error_survives_close_and_final_save_failure', static_first_preserved_on_close_and_final_failure)

    for free, owned, projected, initial, code in [
            (g['FREE_START'] - 1, 0, 0, True, 'DISK_START_LOW'),
            (g['FREE_KEEP'], 0, 1, False, 'DISK_RESERVE_LOW'),
            (32 * g['GIB'], g['INCREMENT_MAX'], 1, False, 'DISK_INCREMENT_LIMIT')]:
        def case(free=free, owned=owned, projected=projected, initial=initial, code=code):
            try:
                g['call']('DISK_CHECK', 'DOWNLOAD', g['disk_limits'], free, owned, projected, initial)
            except g['Failure'] as exc:
                assert exc.code == code
                assert_diagnostic(exc.diagnostic, 'DISK_CHECK', 'DOWNLOAD')
            else:
                raise AssertionError
        test(code.lower() + '_remains_enforced', case)

    return results


def main():
    if sys.version_info[:2] != (3, 12):
        print(json.dumps({'status': 'failed', 'error_code': 'PYTHON_VERSION_INVALID'}))
        return 1
    source_path = Path(__file__).with_name('run_check.py')
    test_path = Path(__file__)
    source_bytes = source_path.read_bytes()
    test_bytes = test_path.read_bytes()
    guard = Guard()
    sys.addaudithook(guard.hook)
    with Patches() as protection:
        protection.attr(os, '_exit', lambda *a, **k: guard.reject('exit'))
        protection.attr(os, 'fsync', lambda *a, **k: guard.reject('write'))
        protection.attr(shutil, 'disk_usage', lambda *a, **k: guard.reject('disk'))
        protection.attr(socket, 'socket', lambda *a, **k: guard.reject('network'))
        protection.attr(ssl, 'create_default_context', lambda *a, **k: guard.reject('network'))
        protection.attr(socket, 'getaddrinfo', lambda *a, **k: guard.reject('network'))
        protection.attr(subprocess, 'Popen', lambda *a, **k: guard.reject('process'))
        protection.attr(threading.Thread, 'start', lambda *a, **k: guard.reject('thread'))
        for owner, names, category in (
            (os, ('open', 'read', 'write', 'close', 'fdatasync', 'stat', 'lstat', 'fstat',
                  'statvfs', 'access', 'listdir', 'scandir'), 'disk'),
            (os, ('system', 'popen', 'fork', 'posix_spawn', 'posix_spawnp'), 'process'),
            (_thread, ('start_new_thread',), 'thread'),
        ):
            for name in names:
                if hasattr(owner, name):
                    protection.attr(owner, name, lambda *a, _kind=category, **k: guard.reject(_kind))
        g = {'__name__': 'offline_subject', '__file__': str(source_path)}
        exec(compile(source_bytes, 'run_check.py', 'exec'), g)
        results = suite(g, source_bytes, guard)
    passed = all(item['status'] in ('passed', 'superseded') for item in results) and not any(guard.counts.values())
    report = dict(status='passed' if passed else 'failed', source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                  test_source_sha256=hashlib.sha256(test_bytes).hexdigest(),
                  python_version='.'.join(map(str, sys.version_info[:3])),
                  collected_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  test_count=sum(item['status'] != 'superseded' for item in results), legacy_registered_count=len(results),
                  superseded_count=sum(item['status'] == 'superseded' for item in results), passed_count=sum(item['status'] == 'passed' for item in results),
                  network_requests=0, real_network_attempts=guard.counts['network'],
                  real_write_probe_attempts=guard.counts['write'], real_subprocess_attempts=guard.counts['process'],
                  guard_counts=guard.counts, filesystem_model='memory_only',
                  tests=results)
    assert_clean(report)
    print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        result = main()
    except BaseException:
        print('{"status":"failed","error_code":"OFFLINE_HARNESS_FAILED"}')
        result = 1
    sys.exit(result)
