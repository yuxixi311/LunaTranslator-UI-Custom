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
import unicodedata
from urllib.parse import urlsplit
import zlib

URL = 'https://download-r2.pytorch.org/whl/cu128/torch-2.10.0%2Bcu128-cp312-cp312-win_amd64.whl'
EXPECTED = 'fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae'
FILENAME = 'torch-2.10.0+cu128-cp312-cp312-win_amd64.whl'
PART = FILENAME + '.part'
DIST = 'torch-2.10.0+cu128.dist-info/'
GIB = 1024 ** 3
BODY_MAX = 4 * GIB
INCREMENT_MAX = 41 * GIB // 10
FREE_START = 8 * GIB
FREE_KEEP = 2 * GIB
CONTROL_RESERVE = 32 * 1024 ** 2
CD_MAX = TEXT_MAX = 16 * 1024 ** 2
JSON_MAX = 4 * 1024 ** 2
MEMBERS_MAX = 10000
CHUNK = 256 * 1024
ERRORS = frozenset(('INTERNAL_ERROR', 'OUTPUT_ERROR', 'JSON_INVALID', 'PROGRAM_NOT_REVIEWED', 'OFFLINE_TESTS_REQUIRED', 'ATTEMPT_INVALID', 'ATTEMPT_ALREADY_USED', 'PYTHON_VERSION_INVALID', 'URL_NOT_ALLOWED', 'REQUEST_ALREADY_USED', 'NETWORK_ERROR', 'DNS_ERROR', 'TLS_ERROR', 'SOCKET_TIMEOUT', 'HTTP_FORBIDDEN', 'HTTP_STATUS_INVALID', 'REDIRECT_REFUSED', 'COMPRESSION_REFUSED', 'HTTP_PROTOCOL_ERROR', 'RESPONSE_HEADER_INVALID', 'BODY_LIMIT', 'BODY_TRUNCATED', 'HASH_MISMATCH', 'FILE_EXISTS', 'DISK_START_LOW', 'DISK_RESERVE_LOW', 'DISK_INCREMENT_LIMIT', 'OWNED_LAYOUT_INVALID', 'DEADLINE_EXCEEDED', 'WORKER_START_FAILED', 'WORKER_EXIT_ERROR', 'WORKER_EXIT_UNCONFIRMED', 'SUPERVISOR_INCOMPLETE', 'CHECKPOINT_INVALID', 'CLEANUP_FAILED', 'ZIP_INVALID', 'ZIP_LAYOUT_UNSUPPORTED', 'ZIP_CENTRAL_LIMIT', 'ZIP_MEMBER_LIMIT', 'ZIP_DUPLICATE', 'ZIP_PATH_INVALID', 'ZIP_ENCRYPTED', 'ZIP_SYMLINK', 'ZIP_COMPRESSION_UNSUPPORTED', 'ZIP_SIZE_MISMATCH', 'ZIP_CRC_MISMATCH', 'TEXT_LIMIT', 'TEXT_ENCODING_INVALID', 'METADATA_INVALID', 'METADATA_VERSION_UNSUPPORTED', 'METADATA_IDENTITY_MISMATCH', 'WHEEL_TAG_MISMATCH', 'LICENSE_LAYOUT_UNSUPPORTED', 'RECORD_INVALID', 'RECORD_SIZE_MISMATCH', 'RECORD_HASH_MISMATCH', 'SELF_TEST_FAILED'))


ERRORS = ERRORS | frozenset(('IO_ERROR', 'SHORT_WRITE', 'OFFLINE_PREPARATION_ONLY'))
OPERATIONS = frozenset(('UNKNOWN', 'RESPONSE_READ', 'BODY_OPEN', 'BODY_WRITE', 'BODY_FLUSH',
    'BODY_FSYNC', 'BODY_CLOSE', 'BODY_RENAME', 'DISK_CHECK', 'JSON_SERIALIZE', 'JSON_OPEN',
    'JSON_WRITE', 'JSON_CLOSE', 'JSON_REPLACE', 'NETWORK_OPEN', 'RESPONSE_CLOSE',
    'CONNECTION_CLOSE', 'WORKER_START', 'WORKER_WAIT', 'WORKER_POLL', 'WORKER_TERMINATE',
    'CHECKPOINT_READ', 'CLEANUP', 'DEADLINE_CHECK', 'HASH_CHECK', 'BODY_LAYOUT',
    'ARCHIVE_OPEN', 'ARCHIVE_CLOSE'))
CONTEXTS = frozenset(('UNKNOWN', 'PROGRESS', 'PROGRESS_INITIAL', 'PROGRESS_REQUEST',
    'PROGRESS_SENT', 'PROGRESS_HEADERS', 'PROGRESS_BEFORE_WRITE', 'PROGRESS_AFTER_WRITE',
    'PROGRESS_FINAL', 'FINAL_CHECKPOINT', 'FINAL_REPORT', 'INITIAL_REPORT', 'ATTEMPT_MARKER',
    'DOWNLOAD', 'STATIC', 'SUPERVISOR', 'CLEANUP'))
EXCEPTION_TYPES = {t: t.__name__ for t in (OSError, PermissionError, FileNotFoundError,
    FileExistsError, IsADirectoryError, NotADirectoryError, BlockingIOError, BrokenPipeError,
    ConnectionError, ConnectionAbortedError, ConnectionRefusedError, ConnectionResetError,
    TimeoutError, EOFError, ValueError, TypeError, OverflowError, MemoryError,
    UnicodeEncodeError, UnicodeDecodeError, RuntimeError, ssl.SSLError,
    ssl.SSLCertVerificationError, socket.gaierror, http.client.HTTPException,
    http.client.IncompleteRead, http.client.RemoteDisconnected, subprocess.TimeoutExpired)}
SECONDARY_MAX = 8
CANDIDATE_ID = '974d95a3-29c7-4294-9f46-33d247dd72f2'
TEST_FILES = ('offline_test.py', 'safety_test.py', 'journal_test.py', 'adapted_offline_test.py', 'adapted_safety_test.py')
ERRORS = ERRORS | frozenset(('CANDIDATE_INVALID', 'CANDIDATE_PATH_INVALID',
                            'EXECUTION_NOT_AUTHORIZED', 'STAGE_INVALID'))


def diagnostic(code, operation='UNKNOWN', context='UNKNOWN', cause=None):
    # Never stringify an exception or serialize its args, path, or arbitrary attributes.
    result = {'error_code': code if code in ERRORS else 'INTERNAL_ERROR',
              'operation': operation if operation in OPERATIONS else 'UNKNOWN',
              'context': context if context in CONTEXTS else 'UNKNOWN',
              'exception_type': EXCEPTION_TYPES.get(type(cause), 'UNKNOWN'),
              'errno': None, 'winerror': None}
    if type(cause) in EXCEPTION_TYPES:
        for key in ('errno', 'winerror'):
            value = getattr(cause, key, None)
            if type(value) is int:
                result[key] = value
    return result


class Failure(Exception):
    def __init__(self, code, operation='UNKNOWN', context='UNKNOWN', cause=None):
        self.code = code if code in ERRORS else 'INTERNAL_ERROR'
        self.diagnostic = diagnostic(self.code, operation, context, cause)
        self.secondary_errors = []
        self.secondary_errors_truncated = False
        super().__init__(self.code)


def fail(code, operation='UNKNOWN', context='UNKNOWN'):
    raise Failure(code, operation, context)


def safe_code(exc, operation='UNKNOWN'):
    if isinstance(exc, Failure):
        return exc.code
    if operation not in ('UNKNOWN', 'NETWORK_OPEN', 'RESPONSE_READ', 'RESPONSE_CLOSE', 'CONNECTION_CLOSE'):
        return 'OUTPUT_ERROR' if operation.startswith('JSON_') else 'IO_ERROR'
    if isinstance(exc, ssl.SSLError):
        return 'TLS_ERROR'
    if isinstance(exc, TimeoutError):
        return 'SOCKET_TIMEOUT'
    if isinstance(exc, socket.gaierror):
        return 'DNS_ERROR'
    if isinstance(exc, http.client.HTTPException):
        return 'HTTP_PROTOCOL_ERROR'
    if isinstance(exc, OSError):
        return 'NETWORK_ERROR'
    return 'INTERNAL_ERROR'


def as_failure(exc, operation='UNKNOWN', context='UNKNOWN'):
    if isinstance(exc, Failure):
        if exc.diagnostic['operation'] == 'UNKNOWN' and operation in OPERATIONS:
            exc.diagnostic['operation'] = operation
        if exc.diagnostic['context'] == 'UNKNOWN' and context in CONTEXTS:
            exc.diagnostic['context'] = context
        return exc
    return Failure(safe_code(exc, operation), operation, context, exc)


def call(operation, context, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BaseException as exc:
        raise as_failure(exc, operation, context) from None


def append_secondary(container, item):
    values = container.setdefault('secondary_errors', [])
    if len(values) < SECONDARY_MAX:
        values.append(copy.deepcopy(item))
    else:
        container['secondary_errors_truncated'] = True


def record_error(state, exc, operation='UNKNOWN', context='UNKNOWN'):
    error = as_failure(exc, operation, context)
    if state.get('first_error') is None:
        state['first_error'] = copy.deepcopy(error.diagnostic)
    else:
        append_secondary(state, error.diagnostic)
    for item in error.secondary_errors:
        append_secondary(state, item)
    if error.secondary_errors_truncated:
        state['secondary_errors_truncated'] = True
    state['status'] = 'failed'
    state['error_code'] = state['first_error']['error_code']
    return error


def close_preserving(handle, first, operation, context):
    try:
        call(operation, context, handle.close)
    except Failure as exc:
        if first is None:
            first = exc
        elif len(first.secondary_errors) < SECONDARY_MAX:
            first.secondary_errors.append(copy.deepcopy(exc.diagnostic))
        else:
            first.secondary_errors_truncated = True
    return first


def restored_failure(data, fallback='WORKER_EXIT_ERROR'):
    """Import only schema-checked diagnostic fields from a worker checkpoint."""
    raw = data.get('first_error') if type(data) is dict else None
    fields = {'error_code', 'operation', 'context', 'exception_type', 'errno', 'winerror'}
    names = set(EXCEPTION_TYPES.values()) | {'UNKNOWN'}
    def valid(item):
        return (type(item) is dict and set(item) == fields and
                all(type(item[key]) is str for key in ('error_code', 'operation', 'context', 'exception_type')) and
                item['error_code'] in ERRORS and item['operation'] in OPERATIONS and
                item['context'] in CONTEXTS and item['exception_type'] in names and
                all(item[key] is None or type(item[key]) is int for key in ('errno', 'winerror')))
    result = Failure(fallback)
    try:
        if not valid(raw):
            return result
        result = Failure(raw['error_code'])
        result.diagnostic = copy.deepcopy(raw)
        secondary = data.get('secondary_errors', [])
        if type(secondary) is list:
            result.secondary_errors = [copy.deepcopy(item) for item in secondary[:SECONDARY_MAX] if valid(item)]
        result.secondary_errors_truncated = (data.get('secondary_errors_truncated') is True or
                                             (type(secondary) is list and len(secondary) > SECONDARY_MAX))
    except (TypeError, KeyError):
        return Failure(fallback)
    return result


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def dumps(obj, context='PROGRESS'):
    try:
        body = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        if len(body) > JSON_MAX:
            fail('OUTPUT_ERROR', 'JSON_SERIALIZE', context)
        return body
    except Failure:
        raise
    except BaseException as exc:
        raise as_failure(exc, 'JSON_SERIALIZE', context) from None


def load_json(path):
    def pairs(items):
        out = {}
        for key, val in items:
            if key in out:
                fail('JSON_INVALID')
            out[key] = val
        return out
    def number(val):
        val = float(val)
        if not math.isfinite(val):
            fail('JSON_INVALID')
        return val
    try:
        if path.stat().st_size > JSON_MAX:
            fail('JSON_INVALID')
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                          parse_float=number, parse_constant=lambda _: fail('JSON_INVALID'))
    except Failure:
        raise
    except BaseException:
        fail('JSON_INVALID')


def write_json(path, obj, exclusive=False, context='PROGRESS'):
    body = dumps(obj, context)
    handle = None
    first = None
    try:
        pending = path if exclusive else call('JSON_OPEN', context, path.with_suffix, '.pending')
        try:
            handle = call('JSON_OPEN', context, pending.open, 'xb' if exclusive else 'wb')
        except Failure as exc:
            if exclusive and exc.diagnostic['exception_type'] == 'FileExistsError':
                exc.code = exc.diagnostic['error_code'] = 'ATTEMPT_ALREADY_USED'
            raise
        written = call('JSON_WRITE', context, handle.write, body)
        if type(written) is not int or written != len(body):
            fail('SHORT_WRITE', 'JSON_WRITE', context)
    except BaseException as exc:
        first = as_failure(exc, 'JSON_WRITE', context)
    finally:
        if handle is not None:
            first = close_preserving(handle, first, 'JSON_CLOSE', context)
    if first is not None:
        raise first from None
    if not exclusive:
        call('JSON_REPLACE', context, os.replace, pending, path)


# Preparation derivative: original identity-bound authorization gates are restored.
# No execution-authorization.json is supplied; this is not live authorization.
SOURCE_ONLY = False
JOURNAL_MAGIC = b'LTJR0001'
JOURNAL_PAYLOAD_MAX = 2048
JOURNAL_RECORD_MAX = 4102
JOURNAL_BYTE_MAX = 8548576
JOURNAL_INTERVAL = 1024 * 1024
JOURNAL_FIELDS = frozenset(('schema', 'candidate_id', 'source_sha256', 'seq', 'event',
    'request_count', 'get_send_attempts', 'http_status', 'received_bytes', 'written_bytes',
    'actual_sha256', 'counters_complete', 'response_body_complete', 'sha256_matches_expected',
    'status', 'first_error'))
OPERATIONS = OPERATIONS | frozenset(('JOURNAL_OPEN', 'JOURNAL_WRITE', 'JOURNAL_FLUSH',
    'JOURNAL_FSYNC', 'JOURNAL_CLOSE', 'JOURNAL_READ', 'FINAL_CHECKPOINT_FLUSH',
    'FINAL_CHECKPOINT_FSYNC'))


def journal_payload(state, seq, event):
    result = {key: state[key] for key in JOURNAL_FIELDS - {'schema', 'seq', 'event'}}
    result.update(schema=1, seq=seq, event=event)
    return result


def journal_payload_valid(item):
    if type(item) is not dict or set(item) != JOURNAL_FIELDS:
        return False
    if type(item['schema']) is not int or item['schema'] != 1:
        return False
    for field in ('source_sha256', 'actual_sha256'):
        value = item[field]
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            return False
    if item['candidate_id'] != CANDIDATE_ID:
        return False
    for field in ('seq', 'request_count', 'get_send_attempts', 'received_bytes', 'written_bytes'):
        if type(item[field]) is not int:
            return False
    if not (0 <= item['seq'] < JOURNAL_RECORD_MAX and
            0 <= item['get_send_attempts'] <= item['request_count'] <= 1 and
            0 <= item['written_bytes'] <= item['received_bytes'] <= BODY_MAX):
        return False
    if item['http_status'] is not None and (type(item['http_status']) is not int or not 100 <= item['http_status'] <= 599):
        return False
    if any(type(item[k]) is not bool for k in ('counters_complete', 'response_body_complete', 'sha256_matches_expected')):
        return False
    if item['status'] not in ('running', 'completed', 'failed'):
        return False
    if item['event'] not in ('INITIAL', 'REQUEST', 'SENT', 'HEADERS', 'BYTE_SNAPSHOT', 'EOF', 'TERMINAL'):
        return False
    if item['event'] != 'TERMINAL' and item['status'] != 'running':
        return False
    if item['event'] == 'TERMINAL' and item['status'] not in ('completed', 'failed'):
        return False
    if item['first_error'] is not None:
        restored = restored_failure({'first_error': item['first_error']})
        if restored.diagnostic != item['first_error']:
            return False
    return True


class ProgressJournal:
    def __init__(self, path, state, budget, disk):
        self.state, self.budget, self.disk = state, budget, disk
        self.handle = None
        self.poisoned = False
        self.closed = False
        self.count, self.size = 0, 0
        self.digest = bytes(32)
        self.next_threshold = JOURNAL_INTERVAL
        self.phase = None
        state.update(journal_format='LTJR0001', journal_frame_count=0,
                     journal_last_digest=self.digest.hex(), journal_terminal_written=False,
                     journal_handle_opened=False, journal_close_completed=False)
        try:
            budget.remaining()
            call('DISK_CHECK', 'DOWNLOAD', disk.check, len(JOURNAL_MAGIC))
            self.handle = call('JOURNAL_OPEN', 'DOWNLOAD', path.open, 'xb', buffering=0)
            state['journal_handle_opened'] = True
            self._write(JOURNAL_MAGIC)
            self.size = len(JOURNAL_MAGIC)
        except BaseException as exc:
            self.poisoned = True
            first = self.close(as_failure(exc))
            raise first from None

    def _write(self, body):
        self.budget.remaining()
        call('DISK_CHECK', 'DOWNLOAD', self.disk.check, len(body))
        written = call('JOURNAL_WRITE', 'DOWNLOAD', self.handle.write, body)
        if type(written) is not int or written != len(body):
            fail('SHORT_WRITE', 'JOURNAL_WRITE', 'DOWNLOAD')
        call('JOURNAL_FLUSH', 'DOWNLOAD', self.handle.flush)
        descriptor = call('JOURNAL_FSYNC', 'DOWNLOAD', self.handle.fileno)
        call('JOURNAL_FSYNC', 'DOWNLOAD', os.fsync, descriptor)

    def append(self, state, event):
        if self.poisoned or self.closed or self.handle is None:
            fail('CHECKPOINT_INVALID', 'JOURNAL_WRITE', 'DOWNLOAD')
        try:
            if event == 'TERMINAL':
                allowed = self.phase is not None and self.phase != 'TERMINAL' and (state['status'] != 'completed' or self.phase == 'EOF')
            elif event == 'BYTE_SNAPSHOT':
                allowed = (self.phase in ('HEADERS', 'BYTE_SNAPSHOT') and
                           self.next_threshold <= state['written_bytes'] < self.next_threshold + CHUNK and
                           state['written_bytes'] == state['received_bytes'])
            elif event == 'EOF':
                allowed = (self.phase in ('HEADERS', 'BYTE_SNAPSHOT') and state['response_body_complete'] is True and
                           state['written_bytes'] < self.next_threshold)
            else:
                allowed = {'INITIAL': None, 'REQUEST': 'INITIAL', 'SENT': 'REQUEST', 'HEADERS': 'SENT'}.get(event, 'INVALID') == self.phase
            if not allowed:
                fail('CHECKPOINT_INVALID', 'JOURNAL_WRITE', 'DOWNLOAD')
            item = journal_payload(state, self.count, event)
            if not journal_payload_valid(item):
                fail('CHECKPOINT_INVALID', 'JOURNAL_WRITE', 'DOWNLOAD')
            body = json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
            if not 1 <= len(body) <= JOURNAL_PAYLOAD_MAX or self.count >= JOURNAL_RECORD_MAX:
                fail('OUTPUT_ERROR', 'JOURNAL_WRITE', 'DOWNLOAD')
            length = struct.pack('>I', len(body))
            digest = hashlib.sha256(self.digest + length + body).digest()
            frame = length + body + digest
            if self.size + len(frame) > JOURNAL_BYTE_MAX:
                fail('OUTPUT_ERROR', 'JOURNAL_WRITE', 'DOWNLOAD')
            self._write(frame)
            self.count += 1
            self.size += len(frame)
            self.digest = digest
            self.phase = event
            if event == 'BYTE_SNAPSHOT':
                self.next_threshold += JOURNAL_INTERVAL
            state.update(journal_frame_count=self.count, journal_last_digest=digest.hex())
            if event == 'TERMINAL':
                state['journal_terminal_written'] = True
            self.budget.remaining()
        except BaseException:
            self.poisoned = True
            raise

    def save(self, state, context='PROGRESS'):
        if context == 'PROGRESS_BEFORE_WRITE':
            return
        if context == 'PROGRESS_AFTER_WRITE':
            if state['written_bytes'] >= self.next_threshold:
                self.append(state, 'BYTE_SNAPSHOT')
            return
        event = {'PROGRESS_INITIAL': 'INITIAL', 'PROGRESS_REQUEST': 'REQUEST',
                 'PROGRESS_SENT': 'SENT', 'PROGRESS_HEADERS': 'HEADERS',
                 'PROGRESS_FINAL': 'EOF'}.get(context)
        if event is None:
            fail('CHECKPOINT_INVALID', 'JOURNAL_WRITE', 'DOWNLOAD')
        self.append(state, event)

    def finish(self, state):
        if not self.poisoned:
            self.append(state, 'TERMINAL')

    def close(self, first=None):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            try:
                call('JOURNAL_CLOSE', 'DOWNLOAD', handle.close)
                self.closed = True
                self.state['journal_close_completed'] = True
            except BaseException as exc:
                failure = as_failure(exc, 'JOURNAL_CLOSE', 'DOWNLOAD')
                if first is None:
                    first = failure
                elif len(first.secondary_errors) < SECONDARY_MAX:
                    first.secondary_errors.append(copy.deepcopy(failure.diagnostic))
                else:
                    first.secondary_errors_truncated = True
        return first


def read_journal(path, expected_source=None):
    result = {'complete': False, 'frame_count': 0, 'last_digest': bytes(32).hex(),
              'last': None, 'counters_complete': False, 'evidence': 'validated_prefix_lower_bound_only'}
    try:
        handle = None
        raw, extra, first = b'', b'', None
        try:
            handle = call('JOURNAL_READ', 'SUPERVISOR', path.open, 'rb', buffering=0)
            raw = call('JOURNAL_READ', 'SUPERVISOR', handle.read, JOURNAL_BYTE_MAX + 1)
            if type(raw) is not bytes or len(raw) > JOURNAL_BYTE_MAX:
                fail('CHECKPOINT_INVALID', 'JOURNAL_READ', 'SUPERVISOR')
            # Reject a short read that happens to end at a valid terminal frame.
            extra = call('JOURNAL_READ', 'SUPERVISOR', handle.read, 1)
            if extra != b'':
                fail('CHECKPOINT_INVALID', 'JOURNAL_READ', 'SUPERVISOR')
        except BaseException as exc:
            first = as_failure(exc, 'JOURNAL_READ', 'SUPERVISOR')
        finally:
            if handle is not None:
                first = close_preserving(handle, first, 'JOURNAL_CLOSE', 'SUPERVISOR')
        if first is not None:
            return result
        if len(raw) > JOURNAL_BYTE_MAX or raw[:8] != JOURNAL_MAGIC:
            return result
        at, digest, phase, threshold = 8, bytes(32), None, JOURNAL_INTERVAL
        def pairs(items):
            obj = {}
            for key, value in items:
                if key in obj:
                    raise ValueError('duplicate')
                obj[key] = value
            return obj
        while at < len(raw):
            if result['frame_count'] >= JOURNAL_RECORD_MAX or len(raw) - at < 4:
                return result
            length_raw = raw[at:at + 4]
            length = struct.unpack('>I', length_raw)[0]
            if not 1 <= length <= JOURNAL_PAYLOAD_MAX or len(raw) - at < 4 + length + 32:
                return result
            body = raw[at + 4:at + 4 + length]
            actual = raw[at + 4 + length:at + 4 + length + 32]
            expected = hashlib.sha256(digest + length_raw + body).digest()
            if actual != expected:
                return result
            item = json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
            if (not journal_payload_valid(item) or item['seq'] != result['frame_count'] or
                    (expected_source is not None and item['source_sha256'] != expected_source)):
                return result
            previous = result['last']
            if previous is not None and (item['source_sha256'] != previous['source_sha256'] or
                    any(item[k] < previous[k] for k in ('received_bytes', 'written_bytes', 'request_count', 'get_send_attempts'))):
                return result
            event = item['event']
            if event == 'TERMINAL':
                if phase is None or phase == 'TERMINAL' or (item['status'] == 'completed' and phase != 'EOF'):
                    return result
            elif event == 'BYTE_SNAPSHOT':
                if phase not in ('HEADERS', 'BYTE_SNAPSHOT') or not threshold <= item['written_bytes'] < threshold + CHUNK:
                    return result
                if item['written_bytes'] != item['received_bytes']:
                    return result
                threshold += JOURNAL_INTERVAL
            elif event == 'EOF':
                if (phase not in ('HEADERS', 'BYTE_SNAPSHOT') or not item['response_body_complete'] or
                        item['written_bytes'] >= threshold):
                    return result
            elif {'INITIAL': None, 'REQUEST': 'INITIAL', 'SENT': 'REQUEST', 'HEADERS': 'SENT'}.get(event, 'INVALID') != phase:
                return result
            if ((event == 'INITIAL' and (item['request_count'] != 0 or item['received_bytes'] != 0)) or
                    (event == 'REQUEST' and (item['request_count'] != 1 or item['get_send_attempts'] != 0)) or
                    (event in ('SENT', 'HEADERS', 'BYTE_SNAPSHOT', 'EOF') and item['get_send_attempts'] != 1)):
                return result
            phase, digest = event, actual
            at += 4 + length + 32
            result.update(frame_count=result['frame_count'] + 1, last_digest=digest.hex(), last=item)
        result['complete'] = phase == 'TERMINAL'
        return result
    except BaseException:
        return result


def validate_download_journal(path, data):
    journal = read_journal(path)
    last = journal['last']
    keys = JOURNAL_FIELDS - {'schema', 'seq', 'event'}
    if (not journal['complete'] or last is None or data.get('journal_close_completed') is not True or
            data.get('journal_terminal_written') is not True or data.get('journal_format') != 'LTJR0001' or
            type(data.get('journal_frame_count')) is not int or data['journal_frame_count'] != journal['frame_count'] or
            data.get('journal_last_digest') != journal['last_digest'] or
            any(data.get(key) != last[key] for key in keys)):
        fail('CHECKPOINT_INVALID', 'JOURNAL_READ', 'SUPERVISOR')
    return journal


def final_checkpoint(path, state, budget, disk):
    if state.get('journal_handle_opened') is True and state.get('journal_close_completed') is not True:
        fail('CHECKPOINT_INVALID', 'JSON_OPEN', 'FINAL_CHECKPOINT')
    if disk is None:
        fail('CHECKPOINT_INVALID', 'DISK_CHECK', 'FINAL_CHECKPOINT')
    body = dumps(state, 'FINAL_CHECKPOINT')
    handle, first = None, None
    try:
        budget.remaining()
        call('DISK_CHECK', 'DOWNLOAD', disk.check, len(body))
        handle = call('JSON_OPEN', 'FINAL_CHECKPOINT', path.open, 'xb', buffering=0)
        written = call('JSON_WRITE', 'FINAL_CHECKPOINT', handle.write, body)
        if type(written) is not int or written != len(body):
            fail('SHORT_WRITE', 'JSON_WRITE', 'FINAL_CHECKPOINT')
        call('FINAL_CHECKPOINT_FLUSH', 'FINAL_CHECKPOINT', handle.flush)
        descriptor = call('FINAL_CHECKPOINT_FSYNC', 'FINAL_CHECKPOINT', handle.fileno)
        call('FINAL_CHECKPOINT_FSYNC', 'FINAL_CHECKPOINT', os.fsync, descriptor)
        budget.remaining()
    except BaseException as exc:
        first = as_failure(exc, 'JSON_WRITE', 'FINAL_CHECKPOINT')
    finally:
        if handle is not None:
            first = close_preserving(handle, first, 'JSON_CLOSE', 'FINAL_CHECKPOINT')
    try:
        budget.remaining()
    except BaseException as exc:
        failure = as_failure(exc, 'DEADLINE_CHECK', 'FINAL_CHECKPOINT')
        if first is None:
            first = failure
        elif len(first.secondary_errors) < SECONDARY_MAX:
            first.secondary_errors.append(copy.deepcopy(failure.diagnostic))
        else:
            first.secondary_errors_truncated = True
    if first is not None:
        raise first from None


class Budget:
    def __init__(self, deadline, clock=time.monotonic):
        self.deadline, self.clock = deadline, clock
    def remaining(self):
        left = self.deadline - self.clock()
        if left <= 0:
            fail('DEADLINE_EXCEEDED')
        return left
    def socket_timeout(self):
        return min(10.0, self.remaining())


def watchdog(deadline, stop, code, clock=time.monotonic, exit_fn=os._exit):
    if not stop.wait(max(0, deadline - clock())):
        exit_fn(code)


def disk_limits(free, owned, projected=0, initial=False):
    if initial and free < FREE_START:
        fail('DISK_START_LOW', 'DISK_CHECK')
    if free - projected - CONTROL_RESERVE < FREE_KEEP:
        fail('DISK_RESERVE_LOW', 'DISK_CHECK')
    if owned + projected + CONTROL_RESERVE > INCREMENT_MAX:
        fail('DISK_INCREMENT_LIMIT', 'DISK_CHECK')


class DiskGuard:
    def __init__(self, work, out):
        self.work, self.out = work, out
        self.cluster = self.cluster_size(out)
        self.minimum_free = None
        self.maximum_owned = 0
    @staticmethod
    def cluster_size(path):
        if os.name != 'nt':
            fail('OWNED_LAYOUT_INVALID')
        sectors = ctypes.c_ulong()
        bytes_per_sector = ctypes.c_ulong()
        free_clusters = ctypes.c_ulong()
        total_clusters = ctypes.c_ulong()
        fn = ctypes.windll.kernel32.GetDiskFreeSpaceW
        fn.argtypes = [ctypes.c_wchar_p] + [ctypes.POINTER(ctypes.c_ulong)] * 4
        fn.restype = ctypes.c_int
        if not fn(str(path.resolve().anchor), ctypes.byref(sectors), ctypes.byref(bytes_per_sector), ctypes.byref(free_clusters), ctypes.byref(total_clusters)):
            fail('OWNED_LAYOUT_INVALID')
        size = sectors.value * bytes_per_sector.value
        if size <= 0 or size > 2 * 1024 ** 2:
            fail('OWNED_LAYOUT_INVALID')
        return size
    def check(self, projected=0, initial=False):
        total = 0
        for directory in (self.work, self.out):
            for p in directory.iterdir():
                if directory == self.work and p == self.out:
                    # The candidate's single bound output directory is counted separately.
                    regular_path(p, directory=True)
                    continue
                if p.is_symlink() or not p.is_file():
                    fail('OWNED_LAYOUT_INVALID')
                if getattr(p.stat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
                    fail('OWNED_LAYOUT_INVALID')
                total += ((p.stat().st_size + self.cluster - 1) // self.cluster) * self.cluster
        free = shutil.disk_usage(self.out).free
        disk_limits(free, total, projected + self.cluster, initial)
        self.minimum_free = free if self.minimum_free is None else min(self.minimum_free, free)
        self.maximum_owned = max(self.maximum_owned, total)
        return {'free_bytes': free, 'owned_file_allocation_upper_bound_bytes': total,
                'control_reserve_bytes': CONTROL_RESERVE, 'cluster_bytes': self.cluster}


class DirectHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, context, budget):
        self.budget = budget
        self.connect_used = False
        super().__init__(host, port=443, timeout=budget.socket_timeout(), context=context)
        self.auto_open = 0
    def connect(self):
        if self.connect_used:
            fail('REQUEST_ALREADY_USED', 'NETWORK_OPEN', 'DOWNLOAD')
        self.connect_used = True
        # An authorization document is intentionally absent from the preparation.
        work = Path(__file__).absolute().parent
        candidate_preflight(work, work / 'output', require_execution=True)
        request = candidate_json(work / 'output' / 'request-attempt.json')
        check_consumed(request, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'download')
        if (self.host != urlsplit(URL).hostname or self.port != 443 or self._tunnel_host is not None or
                not self._context.check_hostname or self._context.verify_mode != ssl.CERT_REQUIRED):
            fail('URL_NOT_ALLOWED', 'NETWORK_OPEN', 'DOWNLOAD')
        self.budget.remaining()
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        self.budget.remaining()
        if not addresses:
            fail('DNS_ERROR')
        family, kind, proto, _, address = addresses[0]
        raw = socket.socket(family, kind, proto)
        wrapped = None
        try:
            raw.settimeout(self.budget.socket_timeout())
            raw.connect(address)
            wrapped = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            wrapped.settimeout(self.budget.socket_timeout())
            wrapped.do_handshake()
            self.budget.remaining()
            self.sock = wrapped
        except BaseException as exc:
            first = as_failure(exc, 'NETWORK_OPEN', 'DOWNLOAD')
            first = close_preserving(wrapped if wrapped is not None else raw,
                                     first, 'CONNECTION_CLOSE', 'DOWNLOAD')
            raise first from None


class OneGET:
    def __init__(self, factory=DirectHTTPS):
        self.used = False
        self.factory = factory
    def open(self, url, budget, on_send):
        if self.used:
            fail('REQUEST_ALREADY_USED')
        self.used = True
        if url != URL:
            fail('URL_NOT_ALLOWED')
        parts = urlsplit(url)
        context = ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            fail('TLS_ERROR')
        conn = self.factory(parts.hostname, context, budget)
        try:
            conn.connect()
            conn.sock.settimeout(budget.socket_timeout())
            on_send()
            conn.request('GET', parts.path, body=None, headers={
                'Accept': 'application/octet-stream', 'Accept-Encoding': 'identity',
                'Connection': 'close', 'User-Agent': 'Luna-Approved-Wheel-Static-Check/1.0'})
            conn.sock.settimeout(budget.socket_timeout())
            response = conn.getresponse()
            return conn, response
        except BaseException as exc:
            first = as_failure(exc, 'NETWORK_OPEN', 'DOWNLOAD')
            first = close_preserving(conn, first, 'CONNECTION_CLOSE', 'DOWNLOAD')
            raise first from None


def content_length(response):
    if response.status == 403:
        fail('HTTP_FORBIDDEN')
    if 300 <= response.status <= 399:
        fail('REDIRECT_REFUSED')
    if response.status != 200:
        fail('HTTP_STATUS_INVALID')
    encoding = response.headers.get_all('Content-Encoding', [])
    lengths = response.headers.get_all('Content-Length', [])
    transfers = response.headers.get_all('Transfer-Encoding', [])
    if len(encoding) > 1 or (encoding and encoding[0].strip().lower() != 'identity'):
        fail('COMPRESSION_REFUSED')
    if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
        fail('RESPONSE_HEADER_INVALID')
    if transfers and transfers[0].strip().lower() != 'chunked':
        fail('RESPONSE_HEADER_INVALID')
    if not lengths:
        return None
    val = lengths[0].strip()
    if not re.fullmatch('[0-9]+', val):
        fail('RESPONSE_HEADER_INVALID')
    if len(val) > 12 or int(val) > BODY_MAX:
        fail('BODY_LIMIT')
    return int(val)


def receive_body(conn, response, destination, state, budget, disk, save, expected=EXPECTED):
    length = call('RESPONSE_READ', 'DOWNLOAD', content_length, response)
    digest = hashlib.sha256()
    while True:
        budget.remaining()
        if length is not None and state['received_bytes'] == length:
            break
        remaining = BODY_MAX - state['received_bytes']
        if remaining <= 0:
            fail('BODY_LIMIT')
        amount = min(CHUNK, remaining)
        if length is not None:
            amount = min(amount, length - state['received_bytes'])
        call('DISK_CHECK', 'DOWNLOAD', disk.check, amount)
        if conn.sock is not None:
            call('RESPONSE_READ', 'DOWNLOAD', conn.sock.settimeout, budget.socket_timeout())
        try:
            chunk = call('RESPONSE_READ', 'DOWNLOAD', response.read1, amount)
        except Failure:
            state['counters_complete'] = False
            raise
        if type(chunk) is not bytes or len(chunk) > amount:
            fail('HTTP_PROTOCOL_ERROR', 'RESPONSE_READ', 'DOWNLOAD')
        if not chunk:
            if length is not None and state['received_bytes'] != length:
                fail('BODY_TRUNCATED', 'RESPONSE_READ', 'DOWNLOAD')
            break
        state['received_bytes'] += len(chunk)
        digest.update(chunk)
        state['actual_sha256'] = digest.hexdigest()
        save(state, context='PROGRESS_BEFORE_WRITE')
        budget.remaining()
        call('DISK_CHECK', 'DOWNLOAD', disk.check, len(chunk))
        try:
            written = call('BODY_WRITE', 'DOWNLOAD', destination.write, chunk)
        except Failure:
            # A throwing write may have accepted an unreported partial count.
            state['counters_complete'] = False
            raise
        if type(written) is not int or written != len(chunk):
            if type(written) is int and 0 <= written <= len(chunk):
                state['written_bytes'] += written
            else:
                state['counters_complete'] = False
            fail('SHORT_WRITE', 'BODY_WRITE', 'DOWNLOAD')
        state['written_bytes'] += written
        save(state, context='PROGRESS_AFTER_WRITE')
        call('DISK_CHECK', 'DOWNLOAD', disk.check)
    state['response_body_complete'] = True
    state['actual_sha256'] = digest.hexdigest()
    state['sha256_matches_expected'] = state['actual_sha256'] == expected
    save(state, context='PROGRESS_FINAL')
    if not state['sha256_matches_expected']:
        fail('HASH_MISMATCH', 'HASH_CHECK', 'DOWNLOAD')


def download_state():
    return {'status': 'pending', 'error_code': None, 'request_count': 0, 'get_send_attempts': 0,
            'http_status': None, 'received_bytes': 0, 'written_bytes': 0,
            'actual_sha256': hashlib.sha256(b'').hexdigest(), 'sha256_scope': 'actually_received_response_body_bytes',
            'response_body_complete': False, 'sha256_matches_expected': False,
            'artifact_filename': None, 'counters_complete': True, 'started_at': None, 'finished_at': None,
            'first_error': None, 'secondary_errors': [], 'checkpoint_persisted': False,
            'body_fsync_completed': False, 'body_close_completed': False,
            'received_bytes_scope': 'bytes_returned_by_successful_read1_calls; failed_read_may_have_consumed_unknown_bytes',
            'written_bytes_scope': 'valid_byte_counts_returned_by_write; not_proof_of_durable_storage'}


def regular_path(path, directory=False):
    """Reject aliases, links and Windows reparse points before reading controls."""
    try:
        if path.is_symlink() or path.resolve(strict=True) != path.absolute():
            fail('CANDIDATE_PATH_INVALID')
        info = path.stat()
        if getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
            fail('CANDIDATE_PATH_INVALID')
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            fail('CANDIDATE_PATH_INVALID')
    except Failure:
        raise
    except BaseException:
        fail('CANDIDATE_PATH_INVALID')


def candidate_json(path):
    regular_path(path)
    value = load_json(path)
    if type(value) is not dict:
        fail('CANDIDATE_INVALID')
    return value


def check_consumed(marker, source_hash, stage=None):
    if (marker.get('candidate_id') != CANDIDATE_ID or marker.get('final_source_sha256') != source_hash or
            marker.get('single_attempt_consumed') is not True or marker.get('retry_forbidden') is not True):
        fail('ATTEMPT_INVALID')
    if stage is not None and (marker.get('stage') != stage or marker.get('url') != URL):
        fail('ATTEMPT_INVALID')


def candidate_preflight(work, out, require_execution=False):
    """Read-only gate shared by all executable entrances; never creates authorization."""
    if sys.version_info[:2] != (3, 12):
        fail('PYTHON_VERSION_INVALID')
    source = Path(__file__).absolute()
    expected_work = source.parent
    expected_out = expected_work / 'output'
    if work.absolute() != expected_work or out.absolute() != expected_out:
        fail('CANDIDATE_PATH_INVALID')
    regular_path(source)
    regular_path(work, directory=True)
    regular_path(out, directory=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    identity = candidate_json(work / 'candidate-identity.json')
    if (type(identity.get('schema_version')) is not int or identity.get('schema_version') != 1 or
            identity.get('candidate_id') != CANDIDATE_ID or identity.get('status') != 'preparation_only' or
            identity.get('live_execution_authorized') is not False):
        fail('CANDIDATE_INVALID')
    authorization_path = work / 'execution-authorization.json'
    if not authorization_path.exists():
        fail('EXECUTION_NOT_AUTHORIZED')
    authorization = candidate_json(authorization_path)
    if (set(authorization) != {'candidate_id', 'source_sha256', 'action', 'authorized'} or
            authorization.get('candidate_id') != CANDIDATE_ID or authorization.get('source_sha256') != source_hash or
            authorization.get('action') != 'single_download_and_static_check' or authorization.get('authorized') is not True):
        fail('EXECUTION_NOT_AUTHORIZED')
    marker = candidate_json(out / 'attempt.json')
    if (marker.get('candidate_id') != CANDIDATE_ID or marker.get('source_sha256') != source_hash or
            marker.get('url') != URL or marker.get('expected_sha256') != EXPECTED or marker.get('single_attempt') is not True):
        fail('ATTEMPT_INVALID')
    test_hashes = {}
    for filename in TEST_FILES:
        test_path = work / filename
        regular_path(test_path)
        test_hashes[filename] = hashlib.sha256(test_path.read_bytes()).hexdigest()
    tests = candidate_json(work / 'offline-tests.json')
    review = candidate_json(work / 'independent-review.json')
    if (tests.get('status') != 'passed' or tests.get('candidate_id') != CANDIDATE_ID or
            tests.get('source_sha256') != source_hash or tests.get('tests_source_sha256') != test_hashes or
            tests.get('test_source_sha256') != test_hashes['offline_test.py'] or
            type(tests.get('network_requests')) is not int or tests.get('network_requests') != 0):
        fail('OFFLINE_TESTS_REQUIRED')
    if (review.get('status') != 'approved' or review.get('candidate_id') != CANDIDATE_ID or
            review.get('source_sha256') != source_hash or review.get('tests_source_sha256') != test_hashes):
        fail('PROGRAM_NOT_REVIEWED')
    if require_execution:
        check_consumed(candidate_json(out / 'execution-started.json'), source_hash)
    return {'source_hash': source_hash, 'tests': tests, 'review': review}


def worker_claim(stage, work, out):
    if stage not in ('download', 'static'):
        fail('STAGE_INVALID')
    checked = candidate_preflight(work, out, require_execution=True)
    source_hash = checked['source_hash']
    filename = 'request-attempt.json' if stage == 'download' else 'static-attempt.json'
    if (out / filename).exists():
        fail('ATTEMPT_ALREADY_USED')
    if stage == 'static':
        check_consumed(candidate_json(out / 'request-attempt.json'), source_hash, 'download')
        prior = candidate_json(work / 'download-checkpoint.json')
        report = candidate_json(out / 'report.json')
        stage_result = report.get('stages', {}).get('download', {})
        if (report.get('candidate_id') != CANDIDATE_ID or report.get('final_source_sha256') != source_hash or
                report.get('first_error') is not None or report.get('report_save_failed') is not False or
                report.get('report_persisted') is not True or
                stage_result.get('status') != 'completed' or stage_result.get('worker_exit_confirmed') is not True or
                stage_result.get('first_error') is not None or stage_result.get('error_code') is not None or
                stage_result.get('checkpoint_terminal_confirmed') is not True or
                type(stage_result.get('worker_returncode')) is not int or stage_result.get('worker_returncode') != 0 or
                stage_result.get('data') != prior or prior.get('candidate_id') != CANDIDATE_ID or
                prior.get('source_sha256') != source_hash or not can_inspect(prior, True)):
            fail('CHECKPOINT_INVALID')
        validate_download_journal(work / 'download-progress.journal', prior)
    write_json(out / filename, {'claimed_at': utc(), 'candidate_id': CANDIDATE_ID, 'stage': stage, 'url': URL,
               'final_source_sha256': source_hash, 'single_attempt_consumed': True, 'retry_forbidden': True},
               exclusive=True, context='ATTEMPT_MARKER')
    return source_hash


def download(work, out, budget, checkpoint):
    if checkpoint.absolute() != (work / 'download-checkpoint.json').absolute():
        fail('CANDIDATE_PATH_INVALID')
    source_hash = worker_claim('download', work, out)
    state = download_state()
    state.update(candidate_id=CANDIDATE_ID, source_sha256=source_hash)
    state['status'] = 'running'
    state['started_at'] = utc()
    start = time.monotonic()
    journal = disk = None
    def save(obj, context='PROGRESS'):
        journal.save(obj, context)
    conn = response = target = None
    try:
        disk = call('DISK_CHECK', 'DOWNLOAD', DiskGuard, work, out)
        state['disk_start'] = call('DISK_CHECK', 'DOWNLOAD', disk.check, initial=True)
        journal = ProgressJournal(work / 'download-progress.journal', state, budget, disk)
        save(state, context='PROGRESS_INITIAL')
        if (call('BODY_LAYOUT', 'DOWNLOAD', (out / PART).exists) or
                call('BODY_LAYOUT', 'DOWNLOAD', (out / FILENAME).exists)):
            fail('FILE_EXISTS', 'BODY_LAYOUT', 'DOWNLOAD')
        state['request_count'] = 1
        save(state, context='PROGRESS_REQUEST')
        def on_send():
            state['get_send_attempts'] = 1
            save(state, context='PROGRESS_SENT')
        conn, response = call('NETWORK_OPEN', 'DOWNLOAD', OneGET().open, URL, budget, on_send)
        state['http_status'] = response.status
        save(state, context='PROGRESS_HEADERS')
        call('RESPONSE_READ', 'DOWNLOAD', content_length, response)
        call('DISK_CHECK', 'DOWNLOAD', disk.check)
        target = call('BODY_OPEN', 'DOWNLOAD', (out / PART).open, 'xb')
        first = None
        try:
            receive_body(conn, response, target, state, budget, disk, save)
            call('BODY_FLUSH', 'DOWNLOAD', target.flush)
            descriptor = call('BODY_FSYNC', 'DOWNLOAD', target.fileno)
            call('BODY_FSYNC', 'DOWNLOAD', os.fsync, descriptor)
            state['body_fsync_completed'] = True
        except BaseException as exc:
            first = as_failure(exc)
        finally:
            first = close_preserving(target, first, 'BODY_CLOSE', 'DOWNLOAD')
            target = None
            if first is None or first.diagnostic['operation'] != 'BODY_CLOSE':
                state['body_close_completed'] = not any(e['operation'] == 'BODY_CLOSE' for e in (first.secondary_errors if first else []))
        if first is not None:
            raise first from None
        budget.remaining()
        call('DISK_CHECK', 'DOWNLOAD', disk.check)
        if call('BODY_LAYOUT', 'DOWNLOAD', (out / FILENAME).exists):
            fail('FILE_EXISTS', 'BODY_LAYOUT', 'DOWNLOAD')
        call('BODY_RENAME', 'DOWNLOAD', os.rename, out / PART, out / FILENAME)
        state['artifact_filename'] = FILENAME
        state['disk_end'] = call('DISK_CHECK', 'DOWNLOAD', disk.check)
        state['minimum_sampled_free_bytes'] = disk.minimum_free
        state['maximum_sampled_owned_file_allocation_upper_bound_bytes'] = disk.maximum_owned
        state['status'] = 'completed'
    except BaseException as exc:
        record_error(state, exc)
    finally:
        for handle, operation in ((response, 'RESPONSE_CLOSE'), (conn, 'CONNECTION_CLOSE')):
            if handle is not None:
                try:
                    call(operation, 'DOWNLOAD', handle.close)
                except BaseException as exc:
                    record_error(state, exc)
    state['finished_at'] = utc()
    state['elapsed_seconds'] = round(time.monotonic() - start, 6)
    # Journal and terminal checkpoint are separate one-shot outputs, never retries.
    if journal is not None:
        try:
            journal.finish(state)
        except BaseException as exc:
            record_error(state, exc)
        close_error = journal.close()
        if close_error is not None:
            record_error(state, close_error)
    if state.get('journal_handle_opened') is True and state.get('journal_close_completed') is not True:
        state['checkpoint_persisted'] = False
        return state
    state['checkpoint_persisted'] = True
    try:
        final_checkpoint(checkpoint, state, budget, disk)
    except BaseException as exc:
        state['checkpoint_persisted'] = False
        record_error(state, exc)
    return state


def safe_path(name, directory=False):
    if type(name) is not str or not name or '\\' in name or ':' in name or name.startswith('/'):
        fail('ZIP_PATH_INVALID')
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        fail('ZIP_PATH_INVALID')
    if directory:
        if not name.endswith('/'):
            fail('ZIP_PATH_INVALID')
        name = name[:-1]
    pieces = name.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in pieces):
        fail('ZIP_PATH_INVALID')
    reserved = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}
    if any(p.split('.')[0].casefold() in reserved for p in pieces):
        fail('ZIP_PATH_INVALID')
    return unicodedata.normalize('NFC', name).casefold()


def extras(raw):
    fields = {}
    pos = 0
    while pos < len(raw):
        if pos + 4 > len(raw):
            fail('ZIP_INVALID')
        ident, count = struct.unpack_from('<HH', raw, pos)
        pos += 4
        if pos + count > len(raw) or ident in fields:
            fail('ZIP_INVALID')
        if ident == 0x9901:
            fail('ZIP_ENCRYPTED')
        if ident not in (1, 0x5455, 0x7875, 0x000a):
            fail('ZIP_LAYOUT_UNSUPPORTED')
        fields[ident] = raw[pos:pos + count]
        pos += count
    return fields


class Archive:
    def __init__(self, handle, size, budget):
        self.f, self.size, self.budget = handle, size, budget
        self.entries = {}
        self.actual_text_bytes = 0
        self.read_results = []
        self.preflight()
    def read_at(self, offset, count):
        self.budget.remaining()
        if offset < 0 or count < 0 or offset + count > self.size:
            fail('ZIP_INVALID')
        self.f.seek(offset)
        result = self.f.read(count)
        self.budget.remaining()
        if len(result) != count:
            fail('ZIP_INVALID')
        return result
    def preflight(self):
        if self.size < 22 or self.size > BODY_MAX:
            fail('ZIP_INVALID')
        end = self.read_at(self.size - 22, 22)
        if end[:4] != b'PK\x05\x06':
            fail('ZIP_LAYOUT_UNSUPPORTED')
        sig, disk, cd_disk, per_disk, count, cd_size, cd_offset, comment = struct.unpack('<4s4H2LH', end)
        if disk or cd_disk or per_disk != count or comment:
            fail('ZIP_LAYOUT_UNSUPPORTED')
        end_offset = self.size - 22
        has64 = end_offset >= 20 and self.read_at(end_offset - 20, 4) == b'PK\x06\x07'
        if has64:
            _, loc_disk, zip64_at, disks = struct.unpack('<4sLQL', self.read_at(end_offset - 20, 20))
            if loc_disk or disks != 1 or zip64_at + 56 != end_offset - 20:
                fail('ZIP_LAYOUT_UNSUPPORTED')
            values = struct.unpack('<4sQ2H2L4Q', self.read_at(zip64_at, 56))
            if values[0] != b'PK\x06\x06' or values[1] != 44 or values[3] > 45 or values[4] or values[5] or values[6] != values[7]:
                fail('ZIP_LAYOUT_UNSUPPORTED')
            real_count, real_size, real_offset = values[7:10]
            if (count != min(real_count, 65535) or cd_size != min(real_size, 0xffffffff) or cd_offset != min(real_offset, 0xffffffff)):
                fail('ZIP_INVALID')
            count, cd_size, cd_offset, end_offset = real_count, real_size, real_offset, zip64_at
        elif count == 65535 or cd_size == 0xffffffff or cd_offset == 0xffffffff:
            fail('ZIP_LAYOUT_UNSUPPORTED')
        if count > MEMBERS_MAX:
            fail('ZIP_MEMBER_LIMIT')
        if cd_size > CD_MAX:
            fail('ZIP_CENTRAL_LIMIT')
        if count == 0 or cd_offset + cd_size != end_offset:
            fail('ZIP_INVALID')
        raw = self.read_at(cd_offset, cd_size)
        self.central_directory_bytes = cd_size
        self.zip64 = has64
        pos, names = 0, set()
        for _ in range(count):
            self.budget.remaining()
            if pos + 46 > len(raw):
                fail('ZIP_INVALID')
            v = struct.unpack_from('<4s6H3L5H2L', raw, pos)
            if v[0] != b'PK\x01\x02':
                fail('ZIP_INVALID')
            made, needed, flags, method, crc, compressed, size = v[1], v[2], v[3], v[4], v[7], v[8], v[9]
            nlen, xlen, clen, member_disk, attrs, offset = v[10], v[11], v[12], v[13], v[15], v[16]
            if pos + 46 + nlen + xlen + clen > len(raw) or not nlen:
                fail('ZIP_INVALID')
            name_raw = raw[pos + 46:pos + 46 + nlen]
            try:
                name = name_raw.decode('utf-8' if flags & 0x800 else 'cp437')
            except UnicodeError:
                fail('ZIP_PATH_INVALID')
            fields = extras(raw[pos + 46 + nlen:pos + 46 + nlen + xlen])
            pos += 46 + nlen + xlen + clen
            if flags & (1 | 64):
                fail('ZIP_ENCRYPTED')
            if flags & ~0x80e or needed > 45 or made >> 8 not in (0, 3) or clen:
                fail('ZIP_LAYOUT_UNSUPPORTED')
            if method not in (0, 8) or (method == 0 and flags & 6):
                fail('ZIP_COMPRESSION_UNSUPPORTED')
            values64 = fields.get(1, b'')
            cursor = 0
            sizes = [size, compressed, offset, member_disk]
            for index, (sentinel, width) in enumerate(((0xffffffff, 8), (0xffffffff, 8), (0xffffffff, 8), (65535, 4))):
                if sizes[index] == sentinel:
                    if cursor + width > len(values64):
                        fail('ZIP_INVALID')
                    sizes[index] = int.from_bytes(values64[cursor:cursor + width], 'little')
                    cursor += width
            if cursor != len(values64):
                fail('ZIP_LAYOUT_UNSUPPORTED')
            size, compressed, offset, member_disk = sizes
            if member_disk:
                fail('ZIP_LAYOUT_UNSUPPORTED')
            directory = name.endswith('/')
            key = safe_path(name, directory)
            if key in names:
                fail('ZIP_DUPLICATE')
            names.add(key)
            mode = attrs >> 16 if made >> 8 == 3 else 0
            kind = stat.S_IFMT(mode)
            if kind == stat.S_IFLNK:
                fail('ZIP_SYMLINK')
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR and not directory) or (attrs & 0x400):
                fail('ZIP_LAYOUT_UNSUPPORTED')
            if directory and (size or compressed or crc):
                fail('ZIP_LAYOUT_UNSUPPORTED')
            self.entries[name] = {'name': name, 'name_raw': name_raw, 'size': size, 'compressed_size': compressed,
                                  'crc': crc, 'flags': flags, 'method': method, 'offset': offset, 'directory': directory}
        if pos != len(raw):
            fail('ZIP_LAYOUT_UNSUPPORTED')
        ordered = sorted(self.entries.values(), key=lambda e: e['offset'])
        if ordered[0]['offset'] != 0:
            fail('ZIP_LAYOUT_UNSUPPORTED')
        for i, entry in enumerate(ordered):
            self.budget.remaining()
            v = struct.unpack('<4s5H3L2H', self.read_at(entry['offset'], 30))
            if v[0] != b'PK\x03\x04' or v[1] > 45 or v[2] != entry['flags'] or v[3] != entry['method']:
                fail('ZIP_LAYOUT_UNSUPPORTED')
            nlen, xlen = v[9], v[10]
            if self.read_at(entry['offset'] + 30, nlen) != entry['name_raw']:
                fail('ZIP_INVALID')
            local_extra = extras(self.read_at(entry['offset'] + 30 + nlen, xlen))
            local_size, local_compressed = v[8], v[7]
            local64 = local_extra.get(1, b'')
            cursor = 0
            sizes = [local_size, local_compressed]
            for j in range(2):
                if sizes[j] == 0xffffffff:
                    if cursor + 8 > len(local64):
                        fail('ZIP_INVALID')
                    sizes[j] = int.from_bytes(local64[cursor:cursor + 8], 'little')
                    cursor += 8
            if cursor != len(local64):
                fail('ZIP_LAYOUT_UNSUPPORTED')
            local_size, local_compressed = sizes
            descriptor = bool(entry['flags'] & 8)
            if not descriptor:
                if (v[6], local_compressed, local_size) != (entry['crc'], entry['compressed_size'], entry['size']):
                    fail('ZIP_INVALID')
            elif v[6] not in (0, entry['crc']) or local_compressed not in (0, entry['compressed_size']) or local_size not in (0, entry['size']):
                fail('ZIP_LAYOUT_UNSUPPORTED')
            entry['data_offset'] = entry['offset'] + 30 + nlen + xlen
            data_end = entry['data_offset'] + entry['compressed_size']
            next_offset = ordered[i + 1]['offset'] if i + 1 < len(ordered) else cd_offset
            gap = next_offset - data_end
            if data_end > cd_offset or gap < 0:
                fail('ZIP_INVALID')
            if descriptor:
                if gap not in (12, 16, 20, 24):
                    fail('ZIP_LAYOUT_UNSUPPORTED')
                desc = self.read_at(data_end, gap)
                if gap in (16, 24):
                    if desc[:4] != b'PK\x07\x08':
                        fail('ZIP_INVALID')
                    desc = desc[4:]
                parsed = struct.unpack('<LLL' if len(desc) == 12 else '<LQQ', desc)
                if parsed != (entry['crc'], entry['compressed_size'], entry['size']):
                    fail('ZIP_INVALID')
            elif gap != 0:
                fail('ZIP_LAYOUT_UNSUPPORTED')
    def read_text(self, name):
        self.budget.remaining()
        if name not in self.entries or self.entries[name]['directory']:
            fail('METADATA_INVALID')
        entry = self.entries[name]
        if entry['size'] <= 0 or entry['size'] > TEXT_MAX - self.actual_text_bytes:
            fail('TEXT_LIMIT')
        remaining, position = entry['compressed_size'], entry['data_offset']
        decompressor = zlib.decompressobj(-15) if entry['method'] == 8 else None
        chunks, size, crc = [], 0, 0
        digest = hashlib.sha256()
        pending = b''
        try:
            while remaining or pending:
                self.budget.remaining()
                if not pending:
                    length = min(65536, remaining)
                    pending = self.read_at(position, length)
                    position += length
                    remaining -= length
                room = min(65536, entry['size'] - size, TEXT_MAX - self.actual_text_bytes)
                if room <= 0:
                    fail('TEXT_LIMIT')
                if decompressor is None:
                    data, pending = pending[:room], pending[room:]
                else:
                    data = decompressor.decompress(pending, room)
                    pending = decompressor.unconsumed_tail
                    if decompressor.unused_data or (decompressor.eof and (remaining or pending)):
                        fail('ZIP_LAYOUT_UNSUPPORTED')
                size += len(data)
                self.actual_text_bytes += len(data)
                crc = zlib.crc32(data, crc)
                digest.update(data)
                chunks.append(data)
            if decompressor is not None and not decompressor.eof:
                fail('ZIP_INVALID')
        except zlib.error:
            fail('ZIP_INVALID')
        if size != entry['size']:
            fail('ZIP_SIZE_MISMATCH')
        if crc & 0xffffffff != entry['crc']:
            fail('ZIP_CRC_MISMATCH')
        data = b''.join(chunks)
        try:
            text = data.decode('utf-8')
        except UnicodeError:
            fail('TEXT_ENCODING_INVALID')
        result = {'member': name, 'actual_size_bytes': size, 'sha256': digest.hexdigest(),
                  'crc32': format(crc & 0xffffffff, '08x'), 'crc_verified': True, 'record_verified': False}
        self.read_results.append(result)
        return text, result


def metadata_message(text):
    message = Parser(policy=policy.default).parsestr(text)
    if message.defects or any(getattr(value, 'defects', ()) for _, value in message.items()):
        fail('METADATA_INVALID')
    return message


def single(message, key, required=True):
    values = message.get_all(key, [])
    if len(values) > 1 or (required and not values):
        fail('METADATA_INVALID')
    if not values:
        return None
    value = str(values[0]).strip()
    if required and not value:
        fail('METADATA_INVALID')
    return value


def parse_record(text, entries):
    records = {}
    seen = set()
    try:
        for row in csv.reader(io.StringIO(text, newline=''), strict=True):
            if len(row) != 3:
                fail('RECORD_INVALID')
            name, digest, size = row
            key = safe_path(name)
            if key in seen or name not in entries or entries[name]['directory']:
                fail('RECORD_INVALID')
            seen.add(key)
            if name == DIST + 'RECORD':
                if digest or size:
                    fail('RECORD_INVALID')
                records[name] = None
                continue
            if not re.fullmatch('[0-9]+', size) or len(size) > 20:
                fail('RECORD_INVALID')
            if not re.fullmatch('sha256=[A-Za-z0-9_-]{43}', digest):
                fail('RECORD_INVALID')
            decoded = base64.urlsafe_b64decode(digest[7:] + '=')
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b'=').decode() != digest[7:]:
                fail('RECORD_INVALID')
            records[name] = (int(size), decoded.hex())
    except Failure:
        raise
    except BaseException:
        fail('RECORD_INVALID')
    if DIST + 'RECORD' not in records:
        fail('RECORD_INVALID')
    return records


def verify_record(result, records):
    name = result['member']
    if name not in records:
        fail('RECORD_INVALID')
    if name == DIST + 'RECORD':
        result['record_verified'] = 'STANDARD_SELF_ENTRY_EMPTY_HASH_AND_SIZE'
        return
    size, digest = records[name]
    if result['actual_size_bytes'] != size:
        fail('RECORD_SIZE_MISMATCH')
    if result['sha256'] != digest:
        fail('RECORD_HASH_MISMATCH')
    result['record_verified'] = True


def inspect_archive(handle, size, budget):
    archive = Archive(handle, size, budget)
    roots = {n.split('/')[0] + '/' for n in archive.entries if n.split('/')[0].endswith('.dist-info')}
    if roots != {DIST} or any(DIST + name not in archive.entries for name in ('METADATA', 'WHEEL', 'RECORD')):
        fail('METADATA_INVALID')
    record_text, record_result = archive.read_text(DIST + 'RECORD')
    records = parse_record(record_text, archive.entries)
    verify_record(record_result, records)
    meta_text, meta_result = archive.read_text(DIST + 'METADATA')
    verify_record(meta_result, records)
    meta = metadata_message(meta_text)
    version = single(meta, 'Metadata-Version')
    if version not in ('2.1', '2.2', '2.3', '2.4'):
        fail('METADATA_VERSION_UNSUPPORTED')
    if single(meta, 'Name') != 'torch' or single(meta, 'Version') != '2.10.0+cu128':
        fail('METADATA_IDENTITY_MISMATCH')
    requires_python = single(meta, 'Requires-Python', False)
    requires_dist = [str(v).strip() for v in meta.get_all('Requires-Dist', [])]
    if any(not value for value in requires_dist):
        fail('METADATA_INVALID')
    license_value = single(meta, 'License', False)
    license_expression = single(meta, 'License-Expression', False)
    if license_expression is not None and (version != '2.4' or license_value is not None):
        fail('LICENSE_LAYOUT_UNSUPPORTED')
    license_refs = [str(v).strip() for v in meta.get_all('License-File', [])]
    if not license_refs and not license_value and not license_expression:
        fail('LICENSE_LAYOUT_UNSUPPORTED')
    license_paths, seen = [], set()
    for ref in license_refs:
        key = safe_path(ref)
        if key in seen:
            fail('LICENSE_LAYOUT_UNSUPPORTED')
        seen.add(key)
        path = DIST + ('licenses/' if version == '2.4' else '') + ref
        if path not in archive.entries or archive.entries[path]['directory']:
            fail('LICENSE_LAYOUT_UNSUPPORTED')
        license_paths.append(path)
    selected = [DIST + 'METADATA', DIST + 'WHEEL', DIST + 'RECORD'] + license_paths
    if len(set(selected)) != len(selected):
        fail('LICENSE_LAYOUT_UNSUPPORTED')
    if sum(archive.entries[name]['size'] for name in selected) > TEXT_MAX:
        fail('TEXT_LIMIT')
    wheel_text, wheel_result = archive.read_text(DIST + 'WHEEL')
    verify_record(wheel_result, records)
    wheel = metadata_message(wheel_text)
    if single(wheel, 'Wheel-Version') != '1.0' or single(wheel, 'Root-Is-Purelib') != 'false':
        fail('METADATA_INVALID')
    if single(wheel, 'Tag') != 'cp312-cp312-win_amd64':
        fail('WHEEL_TAG_MISMATCH')
    licenses = []
    for name in license_paths:
        _, result = archive.read_text(name)
        verify_record(result, records)
        licenses.append(copy.deepcopy(result))
    budget.remaining()
    result = {'metadata_version': version, 'name': 'torch', 'version': '2.10.0+cu128',
              'wheel_version': '1.0', 'tag': 'cp312-cp312-win_amd64', 'requires_python': requires_python,
              'requires_dist': requires_dist, 'license_fields': {'License': license_value, 'License-Expression': license_expression, 'License-File': license_refs},
              'referenced_license_files': licenses, 'selected_members': archive.read_results,
              'total_selected_uncompressed_text_bytes': archive.actual_text_bytes,
              'central_directory_bytes': archive.central_directory_bytes, 'member_count': len(archive.entries),
              'zip64_layout': archive.zip64, 'all_member_paths_and_layout_checked': True,
              'unread_DLL_payloads_individually_verified': False,
              'unread_members_note': 'Only structure was checked for unread members; their payload CRC and RECORD digest were not recomputed.',
              'full_transitive_dependencies': 'UNKNOWN', 'license_reference_policy': '2.4: dist-info/licenses/reference; 2.1-2.3: dist-info/reference; no guessed alternatives'}
    dumps(result)
    return result


def static_check(work, out, budget, checkpoint):
    if checkpoint.absolute() != (work / 'static-checkpoint.json').absolute():
        fail('CANDIDATE_PATH_INVALID')
    source_hash = worker_claim('static', work, out)
    state = {'status': 'running', 'error_code': None, 'started_at': utc(), 'result': None,
             'first_error': None, 'secondary_errors': [], 'checkpoint_persisted': False,
             'candidate_id': CANDIDATE_ID, 'source_sha256': source_hash}
    start = time.monotonic()
    try:
        write_json(checkpoint, state, context='PROGRESS_INITIAL')
        prior = load_json(work / 'download-checkpoint.json')
        if not can_inspect(prior, True):
            fail('HASH_MISMATCH')
        disk = call('DISK_CHECK', 'STATIC', DiskGuard, work, out)
        call('DISK_CHECK', 'STATIC', disk.check)
        path = out / FILENAME
        if path.is_symlink() or path.stat().st_size != prior['written_bytes']:
            fail('ZIP_SIZE_MISMATCH')
        archive_handle = call('ARCHIVE_OPEN', 'STATIC', path.open, 'rb')
        first = None
        try:
            state['result'] = inspect_archive(archive_handle, prior['written_bytes'], budget)
        except BaseException as exc:
            first = as_failure(exc, context='STATIC')
        finally:
            first = close_preserving(archive_handle, first, 'ARCHIVE_CLOSE', 'STATIC')
        if first is not None:
            raise first from None
        call('DISK_CHECK', 'STATIC', disk.check)
        state['status'] = 'completed'
    except BaseException as exc:
        record_error(state, exc)
    state['finished_at'] = utc()
    state['elapsed_seconds'] = round(time.monotonic() - start, 6)
    state['checkpoint_persisted'] = True
    try:
        write_json(checkpoint, state, context='FINAL_CHECKPOINT')
    except BaseException as exc:
        state['checkpoint_persisted'] = False
        record_error(state, exc)
    return state


def can_inspect(download_result, exit_confirmed):
    return (exit_confirmed is True and download_result.get('status') == 'completed' and
            download_result.get('error_code') is None and download_result.get('counters_complete') is True and
            download_result.get('body_fsync_completed') is True and download_result.get('body_close_completed') is True and
            download_result.get('first_error') is None and download_result.get('checkpoint_persisted') is True and
            download_result.get('journal_format') == 'LTJR0001' and
            download_result.get('journal_terminal_written') is True and
            download_result.get('journal_close_completed') is True and
            type(download_result.get('journal_frame_count')) is int and
            1 <= download_result.get('journal_frame_count') <= JOURNAL_RECORD_MAX and
            download_result.get('response_body_complete') is True and download_result.get('sha256_matches_expected') is True and
            type(download_result.get('received_bytes')) is int and type(download_result.get('written_bytes')) is int and
            0 < download_result.get('received_bytes') <= BODY_MAX and
            download_result.get('actual_sha256') == EXPECTED and download_result.get('received_bytes') == download_result.get('written_bytes') and
            download_result.get('artifact_filename') == FILENAME)


def wait_process(proc, work_deadline, stage_deadline, clock=time.monotonic):
    result = {'worker_exit_confirmed': False, 'worker_returncode': None, 'termination_requested': False,
              'error_code': None, 'first_error': None, 'secondary_errors': []}
    try:
        proc.wait(timeout=max(0, work_deadline - clock()))
    except subprocess.TimeoutExpired as exc:
        record_error(result, Failure('DEADLINE_EXCEEDED', 'WORKER_WAIT', 'SUPERVISOR', exc))
        result['termination_requested'] = True
        try:
            proc.terminate()
        except BaseException as exc:
            record_error(result, exc, 'WORKER_TERMINATE', 'SUPERVISOR')
        try:
            proc.wait(timeout=max(0, stage_deadline - clock() - 1.0))
        except BaseException as exc:
            record_error(result, exc, 'WORKER_WAIT', 'SUPERVISOR')
    except BaseException as exc:
        record_error(result, Failure('WORKER_EXIT_ERROR', 'WORKER_WAIT', 'SUPERVISOR', exc))
        result['termination_requested'] = True
        try:
            proc.terminate()
            proc.wait(timeout=max(0, stage_deadline - clock() - 1.0))
        except BaseException as exc:
            record_error(result, exc, 'WORKER_TERMINATE', 'SUPERVISOR')
    try:
        code = proc.poll()
    except BaseException as exc:
        record_error(result, exc, 'WORKER_POLL', 'SUPERVISOR')
        code = None
    if code is None:
        record_error(result, Failure('WORKER_EXIT_UNCONFIRMED', 'WORKER_POLL', 'SUPERVISOR'))
        result['exit_confirmation_status'] = 'UNKNOWN'
    else:
        result['worker_exit_confirmed'] = True
        result['worker_returncode'] = code
        result['exit_confirmation_status'] = 'CONFIRMED'
        if code == 124:
            record_error(result, Failure('DEADLINE_EXCEEDED', 'WORKER_WAIT', 'SUPERVISOR'))
        elif code != 0 and result['error_code'] is None:
            record_error(result, Failure('WORKER_EXIT_ERROR', 'WORKER_WAIT', 'SUPERVISOR'))
    return result


def cleanup_partial(out, exit_confirmed):
    if exit_confirmed is not True:
        return {'status': 'UNKNOWN', 'partial_cleanup_attempted': False, 'attempt_markers_retained': True}
    part = out / PART
    try:
        if part.exists():
            if part.is_symlink() or part.resolve().parent != out.resolve():
                fail('CLEANUP_FAILED')
            part.unlink()
            status = 'PARTIAL_REMOVED'
        else:
            status = 'NO_PARTIAL_FILE'
        return {'status': status, 'partial_cleanup_attempted': True, 'attempt_markers_retained': True,
                'hash_verified_wheel_retained': (out / FILENAME).is_file()}
    except BaseException as exc:
        error = Failure('CLEANUP_FAILED', 'CLEANUP', 'CLEANUP', exc)
        return {'status': 'FAILED', 'error_code': 'CLEANUP_FAILED', 'attempt_markers_retained': True,
                'first_error': error.diagnostic, 'secondary_errors': []}


def worker(stage, work, out, deadline):
    if stage not in ('download', 'static'):
        fail('STAGE_INVALID')
    candidate_preflight(work, out, require_execution=True)
    remaining = deadline - time.monotonic()
    maximum = 870 if stage == 'download' else 50
    if not math.isfinite(deadline) or not math.isfinite(remaining) or not 0 < remaining <= maximum:
        fail('DEADLINE_EXCEEDED')
    stop = threading.Event()
    threading.Thread(target=watchdog, args=(deadline, stop, 124), daemon=True).start()
    try:
        fn = download if stage == 'download' else static_check
        state = fn(work, out, Budget(deadline), work / (stage + '-checkpoint.json'))
        return 0 if state['status'] == 'completed' else 1
    finally:
        stop.set()


def run_stage(stage, work, out, report):
    if stage not in ('download', 'static'):
        fail('STAGE_INVALID')
    candidate_preflight(work, out, require_execution=True)
    start = time.monotonic()
    active, total = (870, 900) if stage == 'download' else (50, 60)
    stop = threading.Event()
    threading.Thread(target=watchdog, args=(start + total, stop, 125), daemon=True).start()
    stage_result = {'status': 'failed', 'error_code': None, 'first_error': None, 'secondary_errors': [],
                    'started_at': utc(), 'active_budget_seconds': active, 'total_budget_seconds': total,
                    'worker_started': False, 'worker_exit_confirmed': False,
                    'termination_requested': False, 'worker_returncode': None,
                    'worker_error_details': 'UNKNOWN', 'checkpoint_terminal_confirmed': False}
    report['stages'][stage] = stage_result
    report['status'], report['failure_stage'] = 'failed', stage
    report['cleanup'] = {'status': 'UNKNOWN', 'partial_cleanup_attempted': False, 'attempt_markers_retained': True}
    success = False
    safe_to_persist = True
    try:
        try:
            write_json(out / 'report.json', report, context='INITIAL_REPORT')
            report['report_persisted'] = True
        except BaseException:
            report['report_save_failed'] = True
            report['report_persisted'] = False
            raise
        try:
            proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()),
                                     'worker', stage, str(work), str(out), str(start + active)],
                                    cwd=str(work), env={'SystemRoot': r'C:\Windows', 'WINDIR': r'C:\Windows'},
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
        except BaseException as exc:
            raise Failure('WORKER_START_FAILED', 'WORKER_START', 'SUPERVISOR', exc) from None
        stage_result['worker_started'] = True
        outcome = wait_process(proc, start + active, start + total)
        for key in ('worker_exit_confirmed', 'worker_returncode', 'termination_requested', 'exit_confirmation_status'):
            stage_result[key] = outcome.get(key)
        if not outcome['worker_exit_confirmed']:
            record_error(stage_result, restored_failure(outcome, 'WORKER_EXIT_UNCONFIRMED'))
            stage_result['data'] = 'UNKNOWN'
            report['worker_exit_unconfirmed'] = True
            report['report_persisted'] = False
            safe_to_persist = False
        else:
            try:
                data = call('CHECKPOINT_READ', 'SUPERVISOR', load_json, work / (stage + '-checkpoint.json'))
                if type(data) is not dict or data.get('status') not in ('completed', 'failed', 'running'):
                    fail('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR')
            except BaseException as exc:
                if stage == 'download':
                    evidence = read_journal(work / 'download-progress.journal', expected_source=report.get('final_source_sha256', 'INVALID'))
                    stage_result['journal_crash_evidence'] = evidence
                    last = evidence.get('last')
                    if (type(last) is dict and last.get('event') == 'TERMINAL' and
                            last.get('status') == 'failed' and last.get('first_error') is not None):
                        record_error(stage_result, restored_failure(last))
                        stage_result['worker_error_details'] = 'RECORDED_FROM_JOURNAL'
                raise Failure('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR', exc) from None
            stage_result['data'] = data
            terminal = (data.get('checkpoint_persisted') is True and
                        data.get('status') in ('completed', 'failed') and type(data.get('finished_at')) is str)
            stage_result['checkpoint_terminal_confirmed'] = terminal
            if not terminal:
                # A failed final save can leave a valid but stale running checkpoint.
                # Its counters and the original worker failure cannot be reconstructed.
                data['counters_complete'] = False
                stage_result['worker_error_details'] = 'UNKNOWN'
                record_error(stage_result, restored_failure(outcome) if outcome.get('first_error') else
                             Failure('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR'))
            elif data.get('status') == 'failed':
                failure = restored_failure(data)
                stage_result['worker_error_details'] = 'RECORDED' if failure.diagnostic['operation'] != 'UNKNOWN' else 'UNKNOWN'
                record_error(stage_result, failure)
                if outcome.get('error_code') not in (None, 'WORKER_EXIT_ERROR'):
                    record_error(stage_result, restored_failure(outcome))
            elif outcome.get('error_code'):
                data['counters_complete'] = False
                record_error(stage_result, restored_failure(outcome))
            elif data.get('first_error') is not None:
                record_error(stage_result, Failure('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR'))
            else:
                if stage == 'download':
                    if data.get('candidate_id') != CANDIDATE_ID or data.get('source_sha256') != report.get('final_source_sha256'):
                        fail('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR')
                    validate_download_journal(work / 'download-progress.journal', data)
                    if not can_inspect(data, True):
                        fail('CHECKPOINT_INVALID', 'CHECKPOINT_READ', 'SUPERVISOR')
                stage_result['status'] = 'completed'
                success = True
    except BaseException as exc:
        record_error(stage_result, exc)
    finally:
        stage_result['finished_at'] = utc()
        stage_result['elapsed_seconds_at_final_commit_start'] = round(time.monotonic() - start, 6)
        if stage_result.get('first_error') is not None:
            record_error(report, restored_failure(stage_result))
        if safe_to_persist and not report.get('report_save_failed'):
            report['report_persisted'] = True
            try:
                write_json(out / 'report.json', report, context='FINAL_REPORT')
            except BaseException as exc:
                report['report_persisted'] = False
                report['report_save_failed'] = True
                record_error(stage_result, exc)
                record_error(report, exc)
                success = False
        stop.set()
    return success and report.get('first_error') is None and not report.get('report_save_failed')


def supervise(work, out):
    checked = candidate_preflight(work, out)
    for filename in ('execution-started.json', 'request-attempt.json', 'static-attempt.json',
                     'report.json', PART, FILENAME):
        if (out / filename).exists():
            fail('ATTEMPT_ALREADY_USED')
    for filename in ('download-checkpoint.json', 'static-checkpoint.json', 'download-progress.journal'):
        if (work / filename).exists():
            fail('ATTEMPT_ALREADY_USED')
    source_hash = checked['source_hash']
    report = {'schema_version': 2, 'status': 'failed', 'failure_stage': 'preflight', 'error_code': None,
              'first_error': None, 'secondary_errors': [], 'report_persisted': False, 'report_save_failed': False,
              'program_provenance': 'single_attempt_candidate; requires_new_identity_bound_execution_authorization',
              'candidate_id': CANDIDATE_ID,
              'final_source_sha256': source_hash, 'collection_started_at': utc(), 'collection_finished_at': None,
              'python_version': '.'.join(map(str, sys.version_info[:3])), 'url': URL, 'expected_sha256': EXPECTED,
              'single_GET_limit': 1, 'proxy_inheritance': False, 'redirects_allowed': False, 'retries': 0,
              'TLS_certificate_and_hostname_verification': True, 'full_transitive_dependencies': 'UNKNOWN',
              'limits': {'download_body_bytes': BODY_MAX, 'initial_free_bytes': FREE_START, 'minimum_free_bytes': FREE_KEEP,
                         'owned_disk_increment_bytes': INCREMENT_MAX, 'members': MEMBERS_MAX,
                         'central_directory_bytes': CD_MAX, 'selected_uncompressed_text_bytes': TEXT_MAX,
                         'metadata_versions': ['2.1', '2.2', '2.3', '2.4']},
              'deadline_note': 'Windows system stalls can delay watchdog scheduling; absolute real-time deadlines are not guaranteed.',
              'stages': {'download': {'status': 'not_started'}, 'static': {'status': 'not_started'}},
              'cleanup': {'status': 'UNKNOWN', 'attempt_markers_retained': True}}
    try:
        report['offline_tests'], report['independent_review'] = checked['tests'], checked['review']
        write_json(out / 'execution-started.json', {'started_at': utc(), 'final_source_sha256': source_hash,
                   'candidate_id': CANDIDATE_ID, 'single_attempt_consumed': True, 'retry_forbidden': True},
                   exclusive=True, context='ATTEMPT_MARKER')
        if not run_stage('download', work, out, report):
            if report.get('report_save_failed') or report.get('worker_exit_unconfirmed'):
                report['cleanup'] = {'status': 'UNKNOWN', 'partial_cleanup_attempted': False, 'attempt_markers_retained': True}
                return finish(out, report)
            confirmed = report['stages']['download'].get('worker_exit_confirmed')
            if confirmed is not True:
                report['cleanup'] = cleanup_partial(out, False)
                return finish(out, report)
            report['cleanup'] = cleanup_partial(out, True)
            return finish(out, report)
        downloaded = report['stages']['download']['data']
        if not can_inspect(downloaded, True):
            fail('HASH_MISMATCH')
        if not run_stage('static', work, out, report):
            if report.get('report_save_failed') or report.get('worker_exit_unconfirmed'):
                report['cleanup'] = {'status': 'UNKNOWN', 'partial_cleanup_attempted': False, 'attempt_markers_retained': True}
                return finish(out, report)
            confirmed = report['stages']['static'].get('worker_exit_confirmed')
            report['cleanup'] = cleanup_partial(out, confirmed is True)
            return finish(out, report)
        report['status'], report['failure_stage'], report['error_code'] = 'completed', None, None
        report['cleanup'] = cleanup_partial(out, True)
        return finish(out, report)
    except BaseException as exc:
        record_error(report, exc)
        report['cleanup'] = {'status': 'NOT_ATTEMPTED', 'attempt_markers_retained': True}
        return finish(out, report)


def finish(out, report):
    report['collection_finished_at'] = utc()
    if report.get('cleanup', {}).get('status') == 'FAILED':
        record_error(report, restored_failure(report['cleanup'], 'CLEANUP_FAILED'))
    if report.get('worker_exit_unconfirmed') or report.get('report_save_failed'):
        report['report_persisted'] = False
        return 1
    report['report_persisted'] = True
    try:
        write_json(out / 'report.json', report, context='FINAL_REPORT')
    except BaseException as exc:
        report['report_persisted'] = False
        report['report_save_failed'] = True
        record_error(report, exc)
    return 0 if report['status'] == 'completed' else 1


def main():
    try:
        if sys.version_info[:2] != (3, 12):
            fail('PYTHON_VERSION_INVALID')
        if len(sys.argv) == 4 and sys.argv[1] == 'supervise':
            work, out = Path(sys.argv[2]), Path(sys.argv[3])
            candidate_preflight(work, out)
            result = supervise(work, out)
            print(json.dumps({'status': 'supervisor_finished', 'success': result == 0}))
            return result
        if len(sys.argv) == 6 and sys.argv[1] == 'worker':
            if sys.argv[2] not in ('download', 'static'):
                fail('STAGE_INVALID')
            work, out = Path(sys.argv[3]), Path(sys.argv[4])
            candidate_preflight(work, out, require_execution=True)
            return worker(sys.argv[2], work, out, float(sys.argv[5]))
        fail('STAGE_INVALID')
    except BaseException as exc:
        print(json.dumps({'status': 'failed', 'error_code': safe_code(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
