"""Source-bound, fake-I/O-only checkpoint-journal acceptance matrix.

The runner reads its candidate before installing process-wide guards. Candidate
source is then exec-loaded only under those guards. No candidate CLI, network,
native process, native file write, disk API, downloaded code, or Windows API runs.
The sole result channel is stdout; a caller may save it as an offline receipt.
"""
import ast
import base64
import builtins
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
    def __init__(self):
        self.counts = dict(network=0, process=0, file=0, disk=0, thread=0, exit=0, native=0)
    def reject(self, kind):
        self.counts[kind] += 1
        raise GuardViolation('FAKE_ONLY_GUARD_BLOCKED_' + kind.upper())
    def blocked(self, kind):
        return lambda *a, **k: self.reject(kind)
    def audit(self, event, args):
        if event.startswith('socket.'):
            self.reject('network')
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn'):
            self.reject('process')
        if event == 'open' or event in ('os.remove', 'os.rename', 'os.rmdir', 'os.mkdir',
                                      'os.link', 'os.symlink', 'os.chmod', 'os.chown',
                                      'os.truncate', 'os.utime', 'os.listdir', 'os.scandir'):
            self.reject('file')
        if event.startswith('ctypes.dlopen') or event.startswith('ctypes.dlsym'):
            self.reject('native')
    def install(self):
        sys.addaudithook(self.audit)
        # Audit hooks do not cover every native disk or process API.
        for owner, names, category in (
            (os, ('open', 'read', 'write', 'close', 'fsync', 'fdatasync', 'stat', 'lstat',
                  'statvfs', 'fstat', 'listdir', 'scandir', 'access', 'replace', 'rename',
                  'unlink', 'remove', 'mkdir', 'rmdir', 'truncate'), 'disk'),
            (shutil, ('disk_usage', 'copyfile', 'rmtree'), 'disk'),
            (socket, ('socket', 'create_connection', 'getaddrinfo'), 'network'),
            (subprocess, ('Popen', 'run', 'call', 'check_call', 'check_output'), 'process'),
            (os, ('system', 'popen', 'fork', 'posix_spawn', 'posix_spawnp'), 'process'),
            (os, ('_exit',), 'exit'),
            (threading.Thread, ('start',), 'thread'),
        ):
            for name in names:
                if hasattr(owner, name):
                    setattr(owner, name, self.blocked(category))


class Patch:
    def __init__(self):
        self.undo = []
    def attr(self, obj, key, val):
        old = getattr(obj, key)
        self.undo.append(lambda: setattr(obj, key, old))
        setattr(obj, key, val)
    def item(self, obj, key, val):
        old = obj[key]
        self.undo.append(lambda: obj.__setitem__(key, old))
        obj[key] = val
    def __enter__(self):
        return self
    def __exit__(self, *ignored):
        for restore in reversed(self.undo):
            restore()


def denied():
    exc = PermissionError(13, 'SYNTHETIC_SECRET_NOT_FOR_DIAGNOSTICS', 'SYNTHETIC_PRIVATE_PATH')
    exc.winerror = 5
    return exc


class FakeFS:
    def __init__(self):
        self.files = {}
        self.events = []
        self.handles = {}
        self.next_fd = 70000
        self.rules = []
        self.reparse = set()
        self.links = set()
    def path(self, key):
        return key if isinstance(key, FakePath) else FakePath(self, str(key))
    def inject(self, op, effect, occurrence=1):
        self.rules.append([op, effect, occurrence, 0])
    def event(self, op, key='', detail=None):
        self.events.append((op, str(key), detail))
        for rule in self.rules:
            if op == rule[0]:
                rule[3] += 1
                if rule[3] == rule[2]:
                    if isinstance(rule[1], BaseException):
                        raise rule[1]
                    if callable(rule[1]):
                        return rule[1]()
                    return rule[1]
        return None
    def fsync(self, fd):
        h = self.handles[fd]
        assert not h.closed
        return self.event(h.kind + '_FSYNC', h.path)
    def replace(self, src, dst):
        self.event('JSON_REPLACE', dst)
        self.files[str(dst)] = self.files.pop(str(src))
    def rename(self, src, dst):
        self.event('BODY_RENAME', dst)
        if str(dst) in self.files:
            raise FileExistsError()
        self.files[str(dst)] = self.files.pop(str(src))
    def count(self, op):
        return sum(x[0] == op for x in self.events)


class FakePath:
    def __init__(self, fs, key):
        self.fs, self.key = fs, key.replace('\\', '/')
    def __str__(self):
        return self.key
    def __fspath__(self):
        raise GuardViolation('FAKE_PATH_REACHED_NATIVE_IO')
    def __truediv__(self, name):
        return self.fs.path(self.key.rstrip('/') + '/' + str(name))
    def __eq__(self, other):
        return isinstance(other, FakePath) and self.fs is other.fs and self.key == other.key
    @property
    def parent(self):
        return self.fs.path(self.key.rsplit('/', 1)[0])
    @property
    def name(self):
        return self.key.rsplit('/', 1)[-1]
    @property
    def anchor(self):
        return 'FAKE'
    def absolute(self):
        return self
    def resolve(self, **kwargs):
        return self
    def with_suffix(self, suffix):
        return self.fs.path(self.key.rsplit('.', 1)[0] + suffix)
    def exists(self):
        self.fs.event('EXISTS', self)
        return self.key in self.fs.files
    def is_file(self):
        return self.key in self.fs.files
    def is_dir(self):
        return not self.is_file()
    def is_symlink(self):
        return self.key in self.fs.links
    def stat(self, **kwargs):
        self.fs.event('STAT', self)
        return types.SimpleNamespace(st_size=len(self.fs.files.get(self.key, b'')),
                    st_mode=stat.S_IFREG if self.is_file() else stat.S_IFDIR,
                    st_file_attributes=1024 if self.key in self.fs.reparse else 0)
    lstat = stat
    def iterdir(self):
        prefix = self.key.rstrip('/') + '/'
        names = {k[len(prefix):].split('/')[0] for k in self.fs.files if k.startswith(prefix)}
        return iter(self / name for name in sorted(names))
    def open(self, mode='r', buffering=-1, **kwargs):
        kind = ('JOURNAL' if self.key.endswith('.journal') else
                'BODY' if self.key.endswith('.part') else 'FINAL')
        op = kind + ('_READ_OPEN' if mode == 'rb' else '_OPEN')
        self.fs.event(op, self, {'mode': mode, 'buffering': buffering})
        if mode == 'xb' and self.key in self.fs.files:
            raise FileExistsError(17, 'fake collision')
        assert mode in ('rb', 'xb', 'wb')
        if mode == 'rb' and self.key not in self.fs.files:
            raise FileNotFoundError()
        if mode != 'rb':
            self.fs.files[self.key] = b''
        h = FakeHandle(self.fs, self, kind)
        self.fs.handles[h.fd] = h
        return h
    def read_bytes(self):
        self.fs.event('READ_BYTES', self)
        return self.fs.files[self.key]
    def read_text(self, encoding='utf-8'):
        return self.read_bytes().decode(encoding)


class FakeHandle:
    def __init__(self, fs, path, kind):
        self.fs, self.path, self.kind = fs, path, kind
        self.closed, self.pos = False, 0
        self.fd = fs.next_fd
        fs.next_fd += 1
    def write(self, data):
        assert not self.closed
        effect = self.fs.event(self.kind + '_WRITE', self.path, len(data))
        if effect == 'SHORT':
            n = max(0, len(data) - 1)
        elif effect == 'NONE':
            return None
        elif effect == 'BOOL':
            return True
        else:
            n = len(data)
        self.fs.files[str(self.path)] += data[:n]
        return n
    def read(self, amount=-1):
        assert not self.closed
        self.fs.event(self.kind + '_READ', self.path, amount)
        data = self.fs.files[str(self.path)]
        if amount < 0:
            amount = len(data)
        result = data[self.pos:self.pos + amount]
        self.pos += len(result)
        return result
    def flush(self):
        assert not self.closed
        return self.fs.event(self.kind + '_FLUSH', self.path)
    def fileno(self):
        assert not self.closed
        self.fs.event(self.kind + '_FILENO', self.path)
        return self.fd
    def close(self):
        assert not self.closed
        self.fs.event(self.kind + '_CLOSE', self.path)
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *ignored):
        self.close()


class FakeBudget:
    def __init__(self, fs, subject):
        self.fs, self.subject, self.calls = fs, subject, 0
        self.expired = False
    def remaining(self):
        self.calls += 1
        self.fs.event('BUDGET')
        if self.expired:
            self.subject['fail']('DEADLINE_EXCEEDED')
        return 870
    def socket_timeout(self):
        self.remaining()
        return 10


class FakeDisk:
    cluster = 4096
    minimum_free = 20 * 1024 ** 3
    maximum_owned = 0
    def __init__(self, fs):
        self.fs = fs
    def check(self, projected=0, initial=False):
        self.fs.event('DISK_CHECK', detail={'projected': projected, 'initial': initial})
        return {'free_bytes': self.minimum_free}


class Fixture:
    def __init__(self, g, source_sha):
        self.g, self.fs = g, FakeFS()
        self.budget, self.disk = FakeBudget(self.fs, g), FakeDisk(self.fs)
        self.path = self.fs.path('work/download-progress.journal')
        self.final = self.fs.path('work/download-checkpoint.json')
        self.state = g['download_state']()
        self.state.update(candidate_id=g['CANDIDATE_ID'], source_sha256=source_sha,
                          status='running', started_at='2026-10-08T00:00:00+00:00')
        self.patch = Patch()
    def __enter__(self):
        self.patch.__enter__()
        self.patch.attr(os, 'fsync', self.fs.fsync)
        self.patch.attr(os, 'replace', self.fs.replace)
        self.patch.attr(os, 'rename', self.fs.rename)
        return self
    def __exit__(self, *args):
        self.patch.__exit__(*args)
    def journal(self):
        journal = self.g['ProgressJournal'](self.path, self.state, self.budget, self.disk)
        journal.save(self.state, 'PROGRESS_INITIAL')
        return journal
    def lifecycle(self, journal):
        self.state['request_count'] = 1
        journal.save(self.state, 'PROGRESS_REQUEST')
        self.state['get_send_attempts'] = 1
        journal.save(self.state, 'PROGRESS_SENT')
        self.state['http_status'] = 200
        journal.save(self.state, 'PROGRESS_HEADERS')
    def counter(self, count):
        self.state['received_bytes'] = self.state['written_bytes'] = count
        self.state['actual_sha256'] = 'a' * 64
    def eof(self, journal, count=1):
        self.counter(count)
        self.state.update(response_body_complete=True, sha256_matches_expected=True,
                          actual_sha256=self.g['EXPECTED'])
        journal.save(self.state, 'PROGRESS_FINAL')
    def completed(self, journal, count=1):
        self.eof(journal, count)
        self.state.update(status='completed', body_fsync_completed=True,
                          body_close_completed=True, artifact_filename=self.g['FILENAME'],
                          finished_at='2026-10-08T00:00:01+00:00')
        journal.finish(self.state)
        first = journal.close()
        assert first is None
        return self.state


def decode_raw(raw):
    """Independent exact-frame decoder, never the candidate reader."""
    assert raw[:8] == b'LTJR0001'
    pos, previous, values = 8, bytes(32), []
    while pos < len(raw):
        length_bytes = raw[pos:pos + 4]
        assert len(length_bytes) == 4
        size = int.from_bytes(length_bytes, 'big')
        assert 1 <= size <= 2048
        payload = raw[pos + 4:pos + 4 + size]
        digest = raw[pos + 4 + size:pos + 4 + size + 32]
        assert len(digest) == 32
        assert digest == hashlib.sha256(previous + length_bytes + payload).digest()
        value = json.loads(payload)
        assert payload == json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()
        values.append(value)
        pos += 4 + size + 32
        previous = digest
    assert pos == len(raw)
    return values, previous.hex()


def encode_frames(values):
    out, previous = bytearray(b'LTJR0001'), bytes(32)
    for value in values:
        payload = (value if isinstance(value, bytes) else
                   json.dumps(value, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=True, allow_nan=False).encode())
        length = len(payload).to_bytes(4, 'big')
        digest = hashlib.sha256(previous + length + payload).digest()
        out.extend(length + payload + digest)
        previous = digest
    return bytes(out)


def main():
    source_path = Path(__file__).absolute().with_name('run_check.py')
    source = source_path.read_bytes()
    test_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    source_sha = hashlib.sha256(source).hexdigest()
    tree = ast.parse(source, filename='guarded_candidate_run_check.py')
    code = compile(tree, 'guarded_candidate_run_check.py', 'exec')
    guard = Guard()
    guard.install()
    g = {'__name__': 'guarded_journal_subject', '__file__': 'work/run_check.py'}
    exec(code, g)
    results = []
    Failure = g['Failure']
    def ensure(value, msg='ASSERTION_FAILED'):
        if not value:
            raise AssertionError(msg)
    def raises(action, operation=None, code=None):
        try:
            action()
        except Failure as exc:
            if operation is not None:
                ensure(exc.diagnostic['operation'] == operation, 'WRONG_OPERATION')
            if code is not None:
                ensure(exc.code == code, 'WRONG_CODE')
            return exc
        raise AssertionError('EXPECTED_FAILURE_MISSING')
    def check(name, action):
        try:
            action()
            ensure(not any(guard.counts.values()), 'GUARD_VIOLATION')
            results.append({'name': name, 'status': 'passed'})
        except BaseException as exc:
            item = {'name': name, 'status': 'failed', 'exception_type': type(exc).__name__}
            if isinstance(exc, Failure):
                item['diagnostic'] = exc.diagnostic
            elif isinstance(exc, AssertionError):
                item['assertion'] = str(exc)
            # Only runner-created diagnostics are output; never exception paths/args.
            results.append(item)
    def fixture():
        return Fixture(g, source_sha)

    def constants():
        ensure(g['JOURNAL_MAGIC'] == b'LTJR0001')
        ensure(g['JOURNAL_PAYLOAD_MAX'] == 2048)
        ensure(g['JOURNAL_RECORD_MAX'] == 4102)
        ensure(g['JOURNAL_BYTE_MAX'] == 8548576)
        ensure(g['JOURNAL_BYTE_MAX'] == 8 + 4102 * (4 + 2048 + 32))
        ensure((g['BODY_MAX'], g['INCREMENT_MAX'], g['FREE_START'], g['FREE_KEEP'],
                g['CONTROL_RESERVE'], g['CHUNK']) ==
               (4294967296, 4402341478, 8589934592, 2147483648, 33554432, 262144))
    check('constants_exact_4102_records_8548576_bytes_limits_unchanged', constants)

    def deterministic(count):
        with fixture() as f:
            j = f.journal()
            f.lifecycle(j)
            # Simulated successful chunks; no body is allocated or received.
            for n in range(g['CHUNK'], count + 1, g['CHUNK']):
                f.counter(n)
                j.save(f.state, 'PROGRESS_BEFORE_WRITE')
                j.save(f.state, 'PROGRESS_AFTER_WRITE')
            if count % g['CHUNK']:
                f.counter(count)
                j.save(f.state, 'PROGRESS_AFTER_WRITE')
            f.completed(j, count)
            values, digest = decode_raw(f.fs.files[str(f.path)])
            events = [v['event'] for v in values]
            expected = ['INITIAL', 'REQUEST', 'SENT', 'HEADERS'] + \
                ['BYTE_SNAPSHOT'] * (count // 1048576) + ['EOF', 'TERMINAL']
            ensure(events == expected, 'WRONG_EVENT_SCHEDULE')
            ensure([v['seq'] for v in values] == list(range(len(values))))
            ensure(f.fs.count('JOURNAL_OPEN') == 1)
            ensure(f.fs.count('JOURNAL_CLOSE') == 1)
            ensure(f.fs.count('JOURNAL_WRITE') == len(values) + 1)
            ensure(f.fs.count('JOURNAL_FLUSH') == len(values) + 1)
            ensure(f.fs.count('JOURNAL_FSYNC') == len(values) + 1)
            opened = next(e for e in f.fs.events if e[0] == 'JOURNAL_OPEN')
            ensure(opened[2] == {'mode': 'xb', 'buffering': 0})
            ensure(not f.fs.count('JSON_REPLACE'))
    for n in (0, 1, 1048575, 1048576, 1048577, 3 * 1048576 + 17, 4294967296):
        check('deterministic_byte_schedule_' + str(n), lambda n=n: deterministic(n))

    def one_byte_storm():
        with fixture() as f:
            j = f.journal()
            f.lifecycle(j)
            before = f.fs.count('JOURNAL_WRITE')
            for n in range(1, 1048580):
                f.counter(n)
                j.save(f.state, 'PROGRESS_AFTER_WRITE')
            ensure(f.fs.count('JOURNAL_WRITE') == before + 1)
            f.completed(j, 1048579)
            values, _ = decode_raw(f.fs.files[str(f.path)])
            ensure([v['written_bytes'] for v in values if v['event'] == 'BYTE_SNAPSHOT'] == [1048576])
    check('one_million_single_byte_updates_emit_one_sample', one_byte_storm)

    # Additional parser, fault and gate matrices are defined below.
    extra_matrix(g, fixture, check, raises, ensure, source, tree)
    receipt = {'schema_version': 1, 'status': 'passed' if all(v['status'] == 'passed' for v in results) else 'failed',
               'scope': 'guarded_fake_only_journal_matrix', 'candidate_id': g['CANDIDATE_ID'],
               'source_sha256': source_sha, 'test_source_sha256': test_sha,
               'network_requests': 0, 'native_candidate_execution': False,
               'windows_reproduction': False, 'live_download_pass': False,
               'guards_installed_before_candidate_import': True,
               'guard_counts': guard.counts, 'test_count': len(results),
               'passed_count': sum(v['status'] == 'passed' for v in results), 'tests': results}
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if receipt['status'] == 'passed' else 1


def extra_matrix(g, fixture, check, raises, ensure, source, tree):
    def original_source_preserved():
        # Exact definition bytes from independently verified original b6f8e0f5….
        # Only parsed source is compared; original or downloaded code never runs.
        expected = {
            'disk_limits': 'b285ceb5c4b4939da3ae56c1bfb566a4c40c70aed3b24733d320a55bf6850554',
            'DiskGuard': '7b2a246ca7c073d13dddb04225df216d1d8e6164b288db9e54ec50de377b0f4b',
            'OneGET': '5f373f38765eb27f54867c387a57790ca72c450851f642a6e8ff19b13640430d',
            'receive_body': '45049740e9977063b85f5680ed12d07c8c39cf75a7a3c040a927e01a789acf88',
            'Archive': 'ecfeae4891ccf60cf857901f5d0cf1e262b72d3debb87fae986d71206b94519b',
            'inspect_archive': 'b8a34ac3a39f409c904551bb3fc8da5aae599f1c5ee91cf19fcf634601c97791',
        }
        text = source.decode('utf-8')
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in expected:
                ensure(hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == expected.pop(node.name),
                       'ORIGINAL_DEFINITION_CHANGED_' + node.name)
        ensure(not expected)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ('download', 'ProgressJournal', 'final_checkpoint'):
                for item in ast.walk(node):
                    if isinstance(item, ast.Call):
                        if isinstance(item.func, ast.Attribute):
                            ensure(item.func.attr not in ('replace', 'sleep'), 'FORBIDDEN_PROGRESS_PERSISTENCE')
                        if isinstance(item.func, ast.Name):
                            ensure(item.func.id != 'write_json', 'OLD_PROGRESS_WRITER_REUSED')
    check('original_receive_disk_get_and_static_source_definitions_exactly_preserved', original_source_preserved)

    def valid_file(f):
        j = f.journal()
        f.lifecycle(j)
        f.completed(j)
        return j, f.fs.files[str(f.path)]

    def parser_happy():
        with fixture() as f:
            j, raw = valid_file(f)
            result = g['read_journal'](f.path)
            ensure(result['complete'] is True and result['frame_count'] == 6)
            ensure(result['last_digest'] == j.digest.hex())
            ensure(result['counters_complete'] is False)
            ensure(result['evidence'] == 'validated_prefix_lower_bound_only')
            ensure(g['validate_download_journal'](f.path, f.state) == result)
    check('complete_journal_independent_digest_and_final_consistency', parser_happy)

    def truncate_every_offset():
        with fixture() as f:
            j, raw = valid_file(f)
            bounds, pos = [], 8
            while pos < len(raw):
                pos += 4 + int.from_bytes(raw[pos:pos + 4], 'big') + 32
                bounds.append(pos)
            for offset in range(len(raw)):
                f.fs.files[str(f.path)] = raw[:offset]
                result = g['read_journal'](f.path)
                ensure(result['complete'] is False, 'TORN_JOURNAL_COMPLETE')
                ensure(result['frame_count'] == sum(p <= offset for p in bounds), 'PREFIX_COUNT_WRONG')
                ensure(result['counters_complete'] is False)
                if result['last'] is not None:
                    ensure(result['last']['seq'] + 1 == result['frame_count'])
                raises(lambda: g['validate_download_journal'](f.path, f.state), code='CHECKPOINT_INVALID')
    check('truncate_every_byte_of_magic_six_frames_and_terminal_digest', truncate_every_offset)

    def corruption(kind):
        with fixture() as f:
            _, raw = valid_file(f)
            values, _ = decode_raw(raw)
            bad = copy.deepcopy(values)
            index = 2
            if kind == 'unknown_field':
                bad[index]['extra'] = 1
            elif kind == 'sequence':
                bad[index]['seq'] += 1
            elif kind == 'bool_counter':
                bad[index]['request_count'] = True
            elif kind == 'negative_counter':
                bad[index]['written_bytes'] = -1
            elif kind == 'write_exceeds_receive':
                bad[index]['written_bytes'] = 1
            elif kind == 'oversize_counter':
                bad[index]['received_bytes'] = g['BODY_MAX'] + 1
            elif kind == 'candidate_identity':
                bad[index]['candidate_id'] = '00000000-0000-0000-0000-000000000000'
            elif kind == 'source_identity':
                bad[index]['source_sha256'] = 'b' * 64
            elif kind == 'hash_shape':
                bad[index]['actual_sha256'] = 'A' * 64
            elif kind == 'unknown_diagnostic':
                bad[index]['first_error'] = {'error_code': 'IO_ERROR', 'leak': 'private'}
            elif kind == 'duplicate_phase':
                bad[index]['event'] = 'REQUEST'
            elif kind == 'phase_skipped':
                bad[index]['event'] = 'HEADERS'
            elif kind == 'terminal_before_eof':
                bad[index].update(event='TERMINAL', status='completed')
            elif kind == 'receive_decreases':
                bad[3]['received_bytes'] = 20
                index = 4
            elif kind == 'duplicate_key':
                payload = json.dumps(bad[index], separators=(',', ':'), sort_keys=True).encode()
                bad[index] = payload[:-1] + b',"seq":2}'
            elif kind == 'nan':
                payload = json.dumps(bad[index], separators=(',', ':'), sort_keys=True).encode()
                bad[index] = payload.replace(b'"http_status":null', b'"http_status":NaN')
            else:
                raise AssertionError('UNKNOWN_CORRUPTION_CASE')
            f.fs.files[str(f.path)] = encode_frames(bad)
            result = g['read_journal'](f.path)
            ensure(result['complete'] is False, 'CORRUPT_JOURNAL_COMPLETE')
            ensure(result['frame_count'] == index, 'READER_RESYNCHRONIZED')
            raises(lambda: g['validate_download_journal'](f.path, f.state))
    for kind in ('unknown_field', 'sequence', 'bool_counter', 'negative_counter',
                 'write_exceeds_receive', 'oversize_counter', 'candidate_identity',
                 'source_identity', 'hash_shape', 'unknown_diagnostic', 'duplicate_phase',
                 'phase_skipped', 'terminal_before_eof', 'receive_decreases', 'duplicate_key', 'nan'):
        check('reader_reject_' + kind + '_without_resynchronization', lambda kind=kind: corruption(kind))

    def raw_corruption(kind):
        with fixture() as f:
            _, raw = valid_file(f)
            if kind == 'magic':
                mutated = b'X' + raw[1:]
                prefix = 0
            elif kind == 'zero_length':
                mutated = raw[:8] + bytes(4) + raw[12:]
                prefix = 0
            elif kind == 'oversize_length':
                mutated = raw[:8] + (2049).to_bytes(4, 'big') + raw[12:]
                prefix = 0
            elif kind == 'digest':
                end = 12 + int.from_bytes(raw[8:12], 'big')
                mutated = raw[:end] + bytes([raw[end] ^ 1]) + raw[end + 1:]
                prefix = 0
            elif kind == 'trailing_byte':
                mutated, prefix = raw + b'x', 6
            elif kind == 'duplicate_terminal':
                values, _ = decode_raw(raw)
                duplicate = copy.deepcopy(values[-1])
                duplicate['seq'] += 1
                mutated, prefix = encode_frames(values + [duplicate]), 6
            elif kind == 'file_cap':
                mutated, prefix = b'X' * (g['JOURNAL_BYTE_MAX'] + 1), 0
            f.fs.files[str(f.path)] = mutated
            result = g['read_journal'](f.path)
            ensure(result['complete'] is False and result['frame_count'] == prefix)
    for kind in ('magic', 'zero_length', 'oversize_length', 'digest', 'trailing_byte', 'duplicate_terminal', 'file_cap'):
        check('reader_reject_raw_' + kind, lambda kind=kind: raw_corruption(kind))

    def fault_journal(phase, op, effect):
        with fixture() as f:
            j = None
            if phase == 'frame':
                j = f.journal()
                f.state['request_count'] = 1
            before = f.fs.count(op)
            f.fs.inject(op, effect)
            action = (lambda: g['ProgressJournal'](f.path, f.state, f.budget, f.disk)) if j is None else \
                     (lambda: j.save(f.state, 'PROGRESS_REQUEST'))
            error = raises(action, operation=op)
            ensure(f.fs.count(op) == before + 1, 'JOURNAL_RETRY')
            if isinstance(effect, PermissionError):
                ensure(error.diagnostic['errno'] == 13 and error.diagnostic['winerror'] == 5)
            if j is not None:
                ensure(j.poisoned)
                durable_count = j.count
                ensure(durable_count == 1, 'FAILED_FRAME_COUNTED_DURABLE')
                writes = f.fs.count('JOURNAL_WRITE')
                j.finish(f.state)
                raises(lambda: j.save(f.state, 'PROGRESS_REQUEST'))
                ensure(f.fs.count('JOURNAL_WRITE') == writes, 'POISONED_JOURNAL_WRITTEN')
                ensure(j.close(error) is error)
                ensure(j.close(error) is error)
                ensure(f.fs.count('JOURNAL_CLOSE') == 1)
            else:
                ensure(f.fs.count('JOURNAL_CLOSE') == (0 if op == 'JOURNAL_OPEN' else 1))
            ensure('SYNTHETIC_SECRET' not in json.dumps(error.diagnostic))
    for phase in ('magic', 'frame'):
        for op in (('JOURNAL_OPEN',) if phase == 'magic' else ()) + ('JOURNAL_WRITE', 'JOURNAL_FLUSH', 'JOURNAL_FSYNC'):
            check('fault_' + phase + '_' + op + '_permission',
                  lambda phase=phase, op=op: fault_journal(phase, op, denied()))
        for effect in ('SHORT', 'NONE', 'BOOL'):
            check('fault_' + phase + '_write_' + effect.lower(),
                  lambda phase=phase, effect=effect: fault_journal(phase, 'JOURNAL_WRITE', effect))

    def close_first_error():
        with fixture() as f:
            j = f.journal()
            first = g['as_failure'](denied(), 'BODY_WRITE', 'DOWNLOAD')
            original = copy.deepcopy(first.diagnostic)
            f.fs.inject('JOURNAL_CLOSE', denied())
            result = j.close(first)
            ensure(result is first and first.diagnostic == original)
            ensure(first.secondary_errors[0]['operation'] == 'JOURNAL_CLOSE')
            ensure(f.state['journal_close_completed'] is False)
            ensure(j.close(first) is first and f.fs.count('JOURNAL_CLOSE') == 1)
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk))
            ensure(f.fs.count('FINAL_OPEN') == 0)
    check('journal_close_once_preserves_first_error_and_suppresses_final_open', close_first_error)

    def bounded_secondaries():
        with fixture() as f:
            first = g['as_failure'](denied(), 'BODY_WRITE', 'DOWNLOAD')
            original = copy.deepcopy(first.diagnostic)
            g['record_error'](f.state, first)
            for n in range(11):
                g['record_error'](f.state, denied(), 'JOURNAL_FSYNC', 'DOWNLOAD')
            ensure(f.state['first_error'] == original)
            ensure(len(f.state['secondary_errors']) == 8)
            ensure(f.state['secondary_errors_truncated'] is True)
            restored = g['restored_failure'](f.state)
            ensure(restored.diagnostic == original and len(restored.secondary_errors) == 8)
            for op in ('JOURNAL_OPEN', 'JOURNAL_WRITE', 'JOURNAL_FLUSH', 'JOURNAL_FSYNC',
                       'JOURNAL_CLOSE', 'JOURNAL_READ', 'FINAL_CHECKPOINT_FLUSH', 'FINAL_CHECKPOINT_FSYNC'):
                item = g['diagnostic']('IO_ERROR', op, 'DOWNLOAD', denied())
                ensure(g['restored_failure']({'first_error': item}).diagnostic == item)
    check('first_error_unchanged_eight_secondary_cap_and_new_enum_restore', bounded_secondaries)

    def fault_final(op, effect):
        with fixture() as f:
            valid_file(f)
            f.state['checkpoint_persisted'] = True
            f.fs.inject(op, effect)
            mapped = {'FINAL_OPEN': 'JSON_OPEN', 'FINAL_WRITE': 'JSON_WRITE',
                      'FINAL_FLUSH': 'FINAL_CHECKPOINT_FLUSH', 'FINAL_FSYNC': 'FINAL_CHECKPOINT_FSYNC',
                      'FINAL_CLOSE': 'JSON_CLOSE'}[op]
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk), operation=mapped)
            ensure(f.fs.count(op) == 1)
            ensure(f.fs.count('FINAL_CLOSE') == (0 if op == 'FINAL_OPEN' else 1))
            ensure(f.fs.count('JSON_REPLACE') == 0)
    for op in ('FINAL_OPEN', 'FINAL_WRITE', 'FINAL_FLUSH', 'FINAL_FSYNC', 'FINAL_CLOSE'):
        check('fault_' + op.lower() + '_permission_no_retry', lambda op=op: fault_final(op, denied()))
    for effect in ('SHORT', 'NONE', 'BOOL'):
        check('fault_final_write_' + effect.lower(), lambda effect=effect: fault_final('FINAL_WRITE', effect))

    def final_closed_order():
        with fixture() as f:
            j = f.journal()
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk))
            ensure(f.fs.count('FINAL_OPEN') == 0)
            f.lifecycle(j)
            f.completed(j)
            f.state['checkpoint_persisted'] = True
            g['final_checkpoint'](f.final, f.state, f.budget, f.disk)
            ops = [e[0] for e in f.fs.events]
            ensure(ops.index('JOURNAL_CLOSE') < ops.index('FINAL_OPEN'))
            ensure(f.fs.count('FINAL_OPEN') == f.fs.count('FINAL_WRITE') == f.fs.count('FINAL_FLUSH') ==
                   f.fs.count('FINAL_FSYNC') == f.fs.count('FINAL_CLOSE') == 1)
            ensure(json.loads(f.fs.files[str(f.final)]) == f.state)
            ensure(g['load_json'](f.final) == f.state)
            ensure(g['validate_download_journal'](f.path, f.state)['complete'])
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk), operation='JSON_OPEN')
            ensure(f.fs.count('FINAL_WRITE') == 1)
    check('exclusive_final_close_before_open_flush_fsync_no_replace_collision', final_closed_order)

    def final_serialization(kind):
        with fixture() as f:
            valid_file(f)
            f.state['extra'] = float('nan') if kind == 'nan' else 'x' * g['JSON_MAX']
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk), operation='JSON_SERIALIZE')
            ensure(f.fs.count('FINAL_OPEN') == 0)
    for kind in ('nan', 'json_cap'):
        check('final_serialize_' + kind + '_before_open', lambda kind=kind: final_serialization(kind))

    def truncate_final():
        with fixture() as f:
            valid_file(f)
            f.state['checkpoint_persisted'] = True
            g['final_checkpoint'](f.final, f.state, f.budget, f.disk)
            raw = f.fs.files[str(f.final)]
            # Final writer ends with a newline: removing only whitespace is still valid JSON.
            json_end = raw.rfind(b'}') + 1
            for offset in range(json_end):
                f.fs.files[str(f.final)] = raw[:offset]
                raises(lambda: g['load_json'](f.final), code='JSON_INVALID')
    check('truncate_final_json_at_every_semantic_byte', truncate_final)

    def mismatch(field, value):
        with fixture() as f:
            valid_file(f)
            bad = copy.deepcopy(f.state)
            bad[field] = value
            raises(lambda: g['validate_download_journal'](f.path, bad), code='CHECKPOINT_INVALID')
    for field, value in (('journal_close_completed', False), ('journal_terminal_written', False),
                         ('journal_frame_count', 5), ('journal_frame_count', True),
                         ('journal_last_digest', 'b' * 64), ('candidate_id', 'wrong'),
                         ('source_sha256', 'b' * 64), ('received_bytes', 2),
                         ('written_bytes', 2), ('status', 'failed'), ('actual_sha256', 'b' * 64)):
        check('terminal_consistency_' + field + '_' + str(value)[:8],
              lambda field=field, value=value: mismatch(field, value))

    def bounded_write(kind):
        with fixture() as f:
            j = f.journal()
            f.state['request_count'] = 1
            if kind == 'record_cap':
                j.count = g['JOURNAL_RECORD_MAX']
            elif kind == 'byte_cap':
                j.size = g['JOURNAL_BYTE_MAX']
            elif kind == 'payload_cap':
                # Existing bounded field keys with an enormous integer cannot exceed the frame cap.
                f.state['first_error'] = g['diagnostic']('IO_ERROR', 'JOURNAL_WRITE', 'DOWNLOAD', denied())
                f.state['first_error']['errno'] = 10 ** 2500
            count = f.fs.count('JOURNAL_WRITE')
            raises(lambda: j.save(f.state, 'PROGRESS_REQUEST'))
            ensure(j.poisoned and f.fs.count('JOURNAL_WRITE') == count)
            j.close()
    for kind in ('record_cap', 'byte_cap', 'payload_cap'):
        check('writer_' + kind + '_fails_before_write', lambda kind=kind: bounded_write(kind))

    def maximal_fields():
        with fixture() as f:
            j = f.journal()
            diagnostic = g['diagnostic'](max(g['ERRORS'], key=len), max(g['OPERATIONS'], key=len),
                                         max(g['CONTEXTS'], key=len), denied())
            diagnostic.update(exception_type=max(g['EXCEPTION_TYPES'].values(), key=len),
                              errno=-(2 ** 63), winerror=2 ** 63 - 1)
            f.state.update(status='failed', first_error=diagnostic, error_code=diagnostic['error_code'])
            j.finish(f.state)
            j.close()
            values, _ = decode_raw(f.fs.files[str(f.path)])
            ensure(values[-1]['first_error'] == diagnostic)
            ensure(g['read_journal'](f.path)['complete'])
    check('maximum_fixed_enum_lengths_and_int64_diagnostic_fit_payload', maximal_fields)

    def elapsed_fsync(which):
        with fixture() as f:
            if which == 'journal':
                j = f.journal()
                f.state['request_count'] = 1
                f.fs.inject('JOURNAL_FSYNC', lambda: setattr(f.budget, 'expired', True))
                raises(lambda: j.save(f.state, 'PROGRESS_REQUEST'), code='DEADLINE_EXCEEDED')
                ensure(j.poisoned)
                j.close()
            else:
                valid_file(f)
                f.fs.inject('FINAL_FSYNC', lambda: setattr(f.budget, 'expired', True))
                raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk), code='DEADLINE_EXCEEDED')
                ensure(f.fs.count('FINAL_CLOSE') == 1)
    for which in ('journal', 'final'):
        check('deadline_consumed_during_' + which + '_fsync', lambda which=which: elapsed_fsync(which))

    def duplicate_writer(which):
        with fixture() as f:
            j = f.journal()
            if which == 'initial':
                action = lambda: j.save(f.state, 'PROGRESS_INITIAL')
            else:
                f.lifecycle(j)
                if which == 'headers':
                    action = lambda: j.save(f.state, 'PROGRESS_HEADERS')
                else:
                    f.eof(j)
                    f.state['status'] = 'completed'
                    j.finish(f.state)
                    action = lambda: j.finish(f.state)
            writes = f.fs.count('JOURNAL_WRITE')
            raises(action)
            ensure(f.fs.count('JOURNAL_WRITE') == writes and j.poisoned)
            j.close()
    for which in ('initial', 'headers', 'terminal'):
        check('writer_duplicate_' + which + '_poisons_before_write', lambda which=which: duplicate_writer(which))

    def no_disk_final():
        with fixture() as f:
            valid_file(f)
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, None), operation='DISK_CHECK')
            ensure(f.fs.count('FINAL_OPEN') == 0)
    check('final_checkpoint_without_disk_guard_refuses_before_open', no_disk_final)

    def final_close_deadline():
        with fixture() as f:
            valid_file(f)
            f.fs.inject('FINAL_CLOSE', lambda: setattr(f.budget, 'expired', True))
            raises(lambda: g['final_checkpoint'](f.final, f.state, f.budget, f.disk), code='DEADLINE_EXCEEDED')
            ensure(f.fs.count('FINAL_CLOSE') == 1)
    check('deadline_consumed_during_final_close_fails_after_single_close', final_close_deadline)

    def bounded_reader():
        with fixture() as f:
            valid_file(f)
            result = g['read_journal'](f.path, expected_source='b' * 64)
            ensure(result['frame_count'] == 0 and result['complete'] is False)
            ensure(f.fs.count('READ_BYTES') == 0)
            reads = [e[2] for e in f.fs.events if e[0] == 'JOURNAL_READ']
            ensure(reads and all(0 < n <= g['JOURNAL_BYTE_MAX'] + 1 for n in reads))
            ensure(g['JOURNAL_BYTE_MAX'] + 1 in reads)
    check('reader_bounded_handle_read_and_expected_source_binding', bounded_reader)

    def journal_collision():
        with fixture() as f:
            f.fs.files[str(f.path)] = b'previous audit evidence'
            raises(lambda: g['ProgressJournal'](f.path, f.state, f.budget, f.disk), operation='JOURNAL_OPEN')
            ensure(f.fs.files[str(f.path)] == b'previous audit evidence')
            ensure(f.fs.count('JOURNAL_WRITE') == f.fs.count('JOURNAL_CLOSE') == 0)
    check('journal_existing_path_exclusive_refusal_preserves_evidence', journal_collision)

    def reader_io_fault(op):
        with fixture() as f:
            valid_file(f)
            f.fs.inject(op, denied())
            result = g['read_journal'](f.path)
            ensure(result['complete'] is False and result['frame_count'] == 0)
            ensure(f.fs.count(op) == (2 if op == 'JOURNAL_CLOSE' else 1))
    for op in ('JOURNAL_READ_OPEN', 'JOURNAL_READ', 'JOURNAL_CLOSE'):
        check('reader_io_fault_' + op.lower() + '_fail_closed', lambda op=op: reader_io_fault(op))

    def alias_disk(which):
        with fixture() as f:
            f.fs.files['work/download-progress.journal'] = b'audit'
            getattr(f.fs, 'links' if which == 'link' else 'reparse').add('work/download-progress.journal')
            disk = g['DiskGuard'].__new__(g['DiskGuard'])
            disk.work, disk.out, disk.cluster = f.fs.path('work'), f.fs.path('work/output'), 4096
            disk.minimum_free, disk.maximum_owned = None, 0
            raises(lambda: disk.check(), code='OWNED_LAYOUT_INVALID')
    for which in ('link', 'reparse'):
        check('disk_reject_journal_' + which, lambda which=which: alias_disk(which))

    def disk_allocation(cluster, near):
        with fixture() as f:
            valid_file(f)
            f.fs.files['work/output/marker.json'] = b'x'
            disk = g['DiskGuard'].__new__(g['DiskGuard'])
            disk.work, disk.out, disk.cluster = f.fs.path('work'), f.fs.path('work/output'), cluster
            disk.minimum_free, disk.maximum_owned = None, 0
            free = g['FREE_KEEP'] + g['CONTROL_RESERVE'] + cluster if near else 20 * g['GIB']
            f.patch.attr(shutil, 'disk_usage', lambda path: types.SimpleNamespace(free=free))
            if near:
                raises(lambda: disk.check(1), code='DISK_RESERVE_LOW')
            else:
                result = disk.check()
                expected = sum(((len(v) + cluster - 1) // cluster) * cluster for v in f.fs.files.values())
                ensure(result['owned_file_allocation_upper_bound_bytes'] == expected)
                ensure(expected >= len(f.fs.files[str(f.path)]) + 1)
    for cluster in (4096, 2 * 1024 ** 2):
        for near in (False, True):
            check('disk_counts_journal_cluster_' + str(cluster) + '_near_' + str(near),
                  lambda cluster=cluster, near=near: disk_allocation(cluster, near))

    integration_matrix(g, fixture, check, raises, ensure)


class Headers:
    def __init__(self, length):
        self.length = length
    def get_all(self, name, default):
        return [str(self.length)] if name.lower() == 'content-length' and self.length is not None else default


class Response:
    status = 200
    def __init__(self, fs, payload=b'abc', read_sizes=None, length=None):
        self.fs, self.payload, self.pos, self.calls = fs, payload, 0, 0
        self.sizes = iter(read_sizes) if read_sizes is not None else None
        self.headers = Headers(len(payload) if length is None else length)
    def read1(self, amount):
        self.calls += 1
        self.fs.event('RESPONSE_READ', detail=amount)
        if self.sizes is not None:
            amount = min(amount, next(self.sizes, amount))
        body = self.payload[self.pos:self.pos + amount]
        self.pos += len(body)
        return body
    def close(self):
        self.fs.event('RESPONSE_CLOSE')


class Connection:
    sock = None
    def __init__(self, fs):
        self.fs = fs
    def close(self):
        self.fs.event('CONNECTION_CLOSE')


def integration_matrix(g, fixture, check, raises, ensure):
    def download_fixture(f):
        response = Response(f.fs)
        connection = Connection(f.fs)
        class FakeGET:
            def open(self, url, budget, on_send):
                ensure(url == g['URL'])
                f.fs.event('FAKE_GET')
                on_send()
                return connection, response
        original = g['receive_body']
        expected = hashlib.sha256(b'abc').hexdigest()
        def receive(*args, **kwargs):
            return original(*args, **kwargs, expected=expected)
        f.patch.item(g, 'worker_claim', lambda *args: f.state['source_sha256'])
        f.patch.item(g, 'DiskGuard', lambda *args: f.disk)
        f.patch.item(g, 'OneGET', FakeGET)
        f.patch.item(g, 'receive_body', receive)
        f.patch.item(g, 'EXPECTED', expected)
        f.patch.attr(time, 'monotonic', lambda: 0)
        return response

    def run_download(f):
        return g['download'](f.fs.path('work'), f.fs.path('work/output'), f.budget, f.final)

    def happy_download():
        with fixture() as f:
            response = download_fixture(f)
            state = run_download(f)
            ensure(state['status'] == 'completed', 'FAKE_DOWNLOAD_FAILED')
            ensure(state['received_bytes'] == state['written_bytes'] == 3)
            ensure(state['checkpoint_persisted'] is True)
            ensure(g['can_inspect'](state, True))
            ensure(not g['can_inspect'](state, False))
            ensure(g['validate_download_journal'](f.path, state)['complete'])
            ensure(response.calls == 1 and f.fs.count('FAKE_GET') == 1)
            ensure(f.fs.count('JSON_REPLACE') == 0)
            ensure(f.fs.count('FINAL_OPEN') == f.fs.count('JOURNAL_OPEN') == 1)
            ops = [e[0] for e in f.fs.events]
            ensure(ops.index('BODY_CLOSE') < ops.index('RESPONSE_CLOSE') < ops.index('CONNECTION_CLOSE') <
                   ops.index('JOURNAL_CLOSE') < ops.index('FINAL_OPEN'))
    check('fake_download_complete_exact_counters_close_order_no_progress_replace', happy_download)

    def download_fault(op):
        with fixture() as f:
            download_fixture(f)
            f.fs.inject(op, denied())
            state = run_download(f)
            ensure(state['status'] == 'failed')
            ensure(not g['can_inspect'](state, True))
            ensure(state['first_error']['errno'] == 13 and state['first_error']['winerror'] == 5)
            ensure(f.fs.count(op) == 1, 'DOWNLOAD_OPERATION_RETRIED')
            if op == 'JOURNAL_OPEN':
                ensure(f.fs.count('FAKE_GET') == 0)
            if op == 'JOURNAL_CLOSE':
                ensure(f.fs.count('FINAL_OPEN') == 0 and state['checkpoint_persisted'] is False)
            if op.startswith('FINAL_'):
                ensure(state['checkpoint_persisted'] is False)
                # Parseable bytes after failed fsync/close are not a success claim.
                if op in ('FINAL_FSYNC', 'FINAL_CLOSE'):
                    ensure(json.loads(f.fs.files[str(f.final)])['checkpoint_persisted'] is True)
    for op in ('JOURNAL_OPEN', 'JOURNAL_WRITE', 'JOURNAL_FLUSH', 'JOURNAL_FSYNC', 'JOURNAL_CLOSE',
               'BODY_WRITE', 'BODY_FLUSH', 'BODY_FSYNC', 'BODY_CLOSE',
               'FINAL_OPEN', 'FINAL_WRITE', 'FINAL_FLUSH', 'FINAL_FSYNC', 'FINAL_CLOSE'):
        check('fake_download_fault_' + op.lower() + '_blocks_inspection', lambda op=op: download_fault(op))

    def original_error_then_journal_close():
        with fixture() as f:
            download_fixture(f)
            f.fs.inject('BODY_WRITE', denied())
            f.fs.inject('JOURNAL_CLOSE', denied())
            state = run_download(f)
            ensure(state['first_error']['operation'] == 'BODY_WRITE')
            ensure(state['secondary_errors'][0]['operation'] == 'JOURNAL_CLOSE')
            ensure(state['counters_complete'] is False)
            ensure(f.fs.count('FINAL_OPEN') == 0)
    check('fake_download_body_error_primary_close_secondary_no_final', original_error_then_journal_close)

    def old_replace_comparison():
        with fixture() as f:
            f.fs.inject('JSON_REPLACE', denied())
            error = raises(lambda: g['write_json'](f.final, f.state, context='PROGRESS'), operation='JSON_REPLACE')
            ensure(error.diagnostic['errno'] == 13 and error.diagnostic['winerror'] == 5)
        with fixture() as f:
            download_fixture(f)
            f.fs.inject('JSON_REPLACE', denied())
            ensure(run_download(f)['status'] == 'completed')
            ensure(f.fs.count('JSON_REPLACE') == 0)
    check('old_replace_permission_fixture_new_progress_never_calls_replace', old_replace_comparison)

    def receive_order(kind):
        with fixture() as f:
            response = Response(f.fs)
            conn = Connection(f.fs)
            handle = (f.fs.path('work/output') / g['PART']).open('xb')
            checkpoints = []
            def save(state, context):
                f.fs.event(context, detail=(state['received_bytes'], state['written_bytes'], state['actual_sha256']))
                checkpoints.append(context)
            if kind == 'read_error':
                f.fs.inject('RESPONSE_READ', denied())
            if kind == 'write_error':
                f.fs.inject('BODY_WRITE', denied())
            action = lambda: g['receive_body'](conn, response, handle, f.state, f.budget, f.disk, save,
                                             expected=hashlib.sha256(b'abc').hexdigest())
            if kind != 'normal':
                raises(action)
                ensure(f.state['counters_complete'] is False)
                ensure(f.state['received_bytes'] == (0 if kind == 'read_error' else 3))
                ensure(f.state['written_bytes'] == 0)
                ensure(not f.state['response_body_complete'])
            else:
                action()
                ops = [e[0] for e in f.fs.events]
                start = ops.index('RESPONSE_READ')
                ensure(ops[start:start + 8] == ['RESPONSE_READ', 'PROGRESS_BEFORE_WRITE', 'BUDGET',
                    'DISK_CHECK', 'BODY_WRITE', 'PROGRESS_AFTER_WRITE', 'DISK_CHECK', 'BUDGET'])
                before = next(e[2] for e in f.fs.events if e[0] == 'PROGRESS_BEFORE_WRITE')
                after = next(e[2] for e in f.fs.events if e[0] == 'PROGRESS_AFTER_WRITE')
                ensure(before == (3, 0, hashlib.sha256(b'abc').hexdigest()))
                ensure(after == (3, 3, hashlib.sha256(b'abc').hexdigest()))
                ensure(checkpoints[-1] == 'PROGRESS_FINAL')
            handle.close()
    for kind in ('normal', 'read_error', 'write_error'):
        check('receive_order_counters_hash_disk_budget_' + kind, lambda kind=kind: receive_order(kind))

    def irregular_reads():
        with fixture() as f:
            payload = b'x' * (1048576 + 517)
            response = Response(f.fs, payload, [1, 19, 262144, 2, 1111, 200000, 17, 250001])
            j = f.journal()
            f.lifecycle(j)
            body = (f.fs.path('work/output') / g['PART']).open('xb')
            g['receive_body'](Connection(f.fs), response, body, f.state, f.budget, f.disk, j.save,
                              expected=hashlib.sha256(payload).hexdigest())
            f.state.update(status='completed', body_close_completed=True, body_fsync_completed=True,
                           artifact_filename=g['FILENAME'])
            body.close()
            j.finish(f.state)
            j.close()
            values, _ = decode_raw(f.fs.files[str(f.path)])
            snapshots = [v for v in values if v['event'] == 'BYTE_SNAPSHOT']
            ensure(len(snapshots) == 1)
            ensure(1048576 <= snapshots[0]['written_bytes'] < 1048576 + g['CHUNK'])
            ensure(f.state['received_bytes'] == f.state['written_bytes'] == len(payload))
            ensure(f.fs.files['work/output/' + g['PART']] == payload)
            ensure(g['read_journal'](f.path)['complete'])
    check('irregular_short_reads_real_hash_exact_counters_single_crossing_sample', irregular_reads)

    def cap_no_read(known):
        with fixture() as f:
            response = Response(f.fs)
            response.headers = Headers(g['BODY_MAX'] if known else None)
            f.counter(g['BODY_MAX'])
            handle = (f.fs.path('work/output') / g['PART']).open('xb')
            action = lambda: g['receive_body'](Connection(f.fs), response, handle, f.state,
                                             f.budget, f.disk, lambda *a, **k: None,
                                             expected=hashlib.sha256(b'').hexdigest())
            if known:
                action()
                ensure(f.state['response_body_complete'])
            else:
                raises(action, code='BODY_LIMIT')
                ensure(not f.state['response_body_complete'])
            ensure(response.calls == 0)
            handle.close()
    for known in (False, True):
        check('body_max_model_no_extra_read_known_length_' + str(known), lambda known=known: cap_no_read(known))

    def supervisor(f, mode):
        class FakeThread:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                f.fs.event('FAKE_WATCHDOG_START')
        def wait(*args):
            f.fs.event('WAIT_CONFIRMED' if mode != 'unconfirmed' else 'WAIT_UNCONFIRMED')
            failure = mode == 'nonzero'
            return {'worker_exit_confirmed': mode != 'unconfirmed', 'worker_returncode': 1 if failure else 0,
                    'termination_requested': False, 'exit_confirmation_status': 'CONFIRMED',
                    'error_code': 'WORKER_EXIT_ERROR' if failure else None, 'first_error': None}
        f.patch.item(g, 'candidate_preflight', lambda *a, **k: {'source_hash': f.state['source_sha256']})
        f.patch.item(g, 'Path', f.fs.path)
        f.patch.item(g, 'wait_process', wait)
        f.patch.attr(threading, 'Thread', FakeThread)
        f.patch.attr(subprocess, 'Popen', lambda *a, **k: object())
        f.patch.attr(time, 'monotonic', lambda: 0)
        report = {'candidate_id': g['CANDIDATE_ID'], 'final_source_sha256': f.state['source_sha256'],
                  'stages': {}, 'first_error': None, 'secondary_errors': [], 'report_save_failed': False,
                  'report_persisted': False}
        result = g['run_stage']('download', f.fs.path('work'), f.fs.path('work/output'), report)
        return result, report

    def stage_gate(mode):
        with fixture() as f:
            j = f.journal()
            f.lifecycle(j)
            f.completed(j)
            f.state['checkpoint_persisted'] = True
            g['final_checkpoint'](f.final, f.state, f.budget, f.disk)
            if mode == 'missing_final':
                del f.fs.files[str(f.final)]
            elif mode == 'incomplete_journal':
                f.fs.files[str(f.path)] = f.fs.files[str(f.path)][:-1]
            elif mode == 'mismatch':
                state = copy.deepcopy(f.state)
                state['journal_last_digest'] = 'b' * 64
                f.fs.files[str(f.final)] = json.dumps(state).encode()
            elif mode == 'report_save_failure':
                f.fs.inject('JSON_REPLACE', denied(), occurrence=2)
            mark = len(f.fs.events)
            result, report = supervisor(f, mode)
            ensure(result is (mode == 'valid'), 'WRONG_STAGE_GATE')
            reads = [i for i, e in enumerate(f.fs.events[mark:]) if e[0] in ('READ_BYTES', 'JOURNAL_READ_OPEN')]
            if mode == 'unconfirmed':
                ensure(not reads, 'READ_BEFORE_EXIT_CONFIRMED')
            elif reads:
                waited = next(i for i, e in enumerate(f.fs.events[mark:]) if e[0] == 'WAIT_CONFIRMED')
                ensure(min(reads) > waited, 'READ_BEFORE_EXIT_CONFIRMED')
            if mode == 'report_save_failure':
                ensure(report['report_save_failed'] is True)
    for mode in ('valid', 'missing_final', 'nonzero', 'incomplete_journal', 'mismatch', 'unconfirmed', 'report_save_failure'):
        check('supervisor_gate_' + mode, lambda mode=mode: stage_gate(mode))

    def recover_failed_terminal(foreign):
        with fixture() as f:
            j = f.journal()
            first = g['as_failure'](denied(), 'BODY_WRITE', 'DOWNLOAD')
            g['record_error'](f.state, first)
            j.finish(f.state)
            j.close()
            if foreign:
                values, _ = decode_raw(f.fs.files[str(f.path)])
                for value in values:
                    value['source_sha256'] = 'b' * 64
                f.fs.files[str(f.path)] = encode_frames(values)
            result, report = supervisor(f, 'missing_final')
            ensure(result is False)
            stage = report['stages']['download']
            if foreign:
                ensure(stage['first_error']['error_code'] == 'CHECKPOINT_INVALID')
                ensure(stage['worker_error_details'] == 'UNKNOWN')
            else:
                ensure(stage['first_error'] == first.diagnostic)
                ensure(stage['worker_error_details'] == 'RECORDED_FROM_JOURNAL')
                ensure(stage['secondary_errors'][0]['error_code'] == 'CHECKPOINT_INVALID')
                ensure(stage['journal_crash_evidence']['counters_complete'] is False)
    for foreign in (False, True):
        check('missing_final_failed_terminal_recovery_foreign_' + str(foreign),
              lambda foreign=foreign: recover_failed_terminal(foreign))


if __name__ == '__main__':
    sys.exit(main())
