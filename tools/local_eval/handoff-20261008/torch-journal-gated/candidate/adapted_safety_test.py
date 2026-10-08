"""Original 63 download and ZIP safety cases, migrated to guarded memory IO."""
import _thread
import base64
import copy
import csv
import encodings.cp437  # Preload the ZIP name codec before strict read guards.
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import shutil
import warnings
import zipfile

ORIGINAL_CASES = ['valid_static_metadata_license_CRC_RECORD_no_code_execution', 'valid_stored_members', 'valid_local_ZIP64_layout', 'supported_legacy_license_layout_2.1', 'supported_legacy_license_layout_2.2', 'supported_legacy_license_layout_2.3', 'invalid_ZIP', 'unknown_ZIP_trailing_layout', 'unsupported_metadata_version', 'wrong_metadata_identity', 'wrong_WHEEL_Tag', 'duplicate_critical_metadata', 'license_path_traversal', 'ZIP_member_path_traversal', 'ZIP_casefold_duplicate', 'ZIP_exact_duplicate', 'ZIP_symlink_refusal', 'encrypted_ZIP_refusal', 'unsupported_compression', '16_MiB_central_directory_limit', '10000_member_limit', '16_MiB_selected_text_limit', 'RECORD_duplicate_row', 'RECORD_wrong_length', 'RECORD_wrong_digest', 'RECORD_invalid_digest_encoding', 'RECORD_self_entry_must_be_empty', 'selected_member_CRC_failure', 'unread_DLL_not_claimed_verified', 'streaming_hash_and_actual_bytes', 'wrong_full_download_hash', '403_stops_without_reading_body_or_opening_file', 'redirect_not_followed', 'compressed_body_refused', 'oversized_declared_body_before_download', 'ambiguous_HTTP_framing', 'hard_body_limit_no_overread_unknown_length', 'truncated_HTTP_body', 'initial_8_GiB_disk_requirement', 'running_2_GiB_disk_reserve', '4_point_1_GiB_increment_limit', 'disk_drop_after_receive_before_write', 'download_deadline_during_receive', 'static_deadline_before_ZIP', 'exact_one_verified_TLS_GET_no_proxy_auth_cookie_range', 'download_870_work_30_termination_reserve', 'static_50_work_10_termination_reserve', 'unconfirmed_exit_reported', 'unconfirmed_exit_blocks_ZIP_and_all_cleanup_path_access', 'independent_watchdog_870', 'independent_watchdog_900', 'independent_watchdog_50', 'independent_watchdog_60', 'fixed_error_code_redaction', 'worker_reentry_after_403_one_GET_marker_and_evidence_preserved', 'worker_changed_execution_evidence_blocks_GET_and_checkpoint_overwrite', 'worker_changed_review_blocks_GET', 'worker_changed_offline_evidence_blocks_GET', 'supervisor_reentry_preserves_original_report_without_IO', 'worker_deadline_reject_NaN', 'worker_deadline_reject_Infinity', 'worker_deadline_reject_expired', 'worker_deadline_reject_overlong']


def suite(h, g, source_bytes, guard):
    m = g
    Failure = g['Failure']
    DIST = g['DIST']
    results = []
    Scenario = h['Scenario']
    Patches = h['Patches']
    def ensure(value):
        if not value:
            raise AssertionError('SAFETY_ASSERTION_FAILED')
    def check(name, action):
        try:
            action()
            ensure(not any(guard.counts.values()))
            results.append({'name': name, 'status': 'passed'})
        except BaseException as exc:
            item = {'name': name, 'status': 'failed', 'error_code': 'SAFETY_ASSERTION_FAILED'}
            if isinstance(exc, Failure):
                item['subject_diagnostic'] = exc.diagnostic
            results.append(item)
    def raises(code, action):
        try:
            action()
        except Failure as exc:
            ensure(exc.code == code)
            return exc
        raise AssertionError('EXPECTED_FAILURE_MISSING')
    def budget(clock=lambda: 0, deadline=870):
        return g['Budget'](deadline, clock)
    def encoded(data):
        return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()

    def fixture(version='2.4', name='torch', tag='cp312-cp312-win_amd64', meta_extra='', ref='LICENSE',
                compression=zipfile.ZIP_DEFLATED, record_change=None, additions=None, force64=False):
        license_header = 'License-Expression: BSD-3-Clause\n' if version == '2.4' else 'License: BSD-3-Clause\n'
        metadata = (f'Metadata-Version: {version}\nName: {name}\nVersion: 2.10.0+cu128\n'
                    'Requires-Python: >=3.10\nRequires-Dist: filelock\nRequires-Dist: typing-extensions>=4.10\n' +
                    license_header + f'License-File: {ref}\n' + meta_extra + '\nDescription\n').encode()
        wheel = ('Wheel-Version: 1.0\nGenerator: offline-fixture\nRoot-Is-Purelib: false\nTag: ' + tag + '\n\n').encode()
        license_name = DIST + ('licenses/' if version == '2.4' else '') + ref
        files = {DIST + 'METADATA': metadata, DIST + 'WHEEL': wheel, license_name: b'License text\n',
                 'torch/__init__.py': b'raise RuntimeError("DO_NOT_EXECUTE_WHEEL_CODE")\n',
                 'torch/lib/example.dll': b'unread DLL fixture'}
        if additions:
            files.update(additions)
        rows = [[n, encoded(data), str(len(data))] for n, data in files.items()]
        rows.append([DIST + 'RECORD', '', ''])
        if record_change:
            record_change(rows)
        import csv
        text = io.StringIO(newline='')
        csv.writer(text, lineterminator='\n').writerows(rows)
        files[DIST + 'RECORD'] = text.getvalue().encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', compression=compression) as archive:
            for member, body in files.items():
                if force64:
                    with archive.open(member, 'w', force_zip64=True) as stream:
                        stream.write(body)
                else:
                    archive.writestr(member, body)
        return out.getvalue()

    def inspect(data):
        return m['inspect_archive'](io.BytesIO(data), len(data), budget(deadline=50))


    def valid_archive():
        result = inspect(fixture())
        ensure(result['name'] == 'torch' and result['version'] == '2.10.0+cu128' and result['metadata_version'] == '2.4')
        ensure(result['requires_python'] == '>=3.10' and len(result['requires_dist']) == 2)
        ensure(result['referenced_license_files'][0]['record_verified'] is True)
        ensure(all(x['crc_verified'] for x in result['selected_members']))
        ensure(not result['unread_DLL_payloads_individually_verified'] and result['member_count'] == 6)
        ensure('torch/__init__.py' not in [x['member'] for x in result['selected_members']])
    check('valid_static_metadata_license_CRC_RECORD_no_code_execution', valid_archive)
    check('valid_stored_members', lambda: ensure(inspect(fixture(compression=zipfile.ZIP_STORED))['name'] == 'torch'))
    check('valid_local_ZIP64_layout', lambda: ensure(inspect(fixture(force64=True))['name'] == 'torch'))
    for version in ('2.1', '2.2', '2.3'):
        check('supported_legacy_license_layout_' + version, lambda version=version: ensure(inspect(fixture(version=version))['metadata_version'] == version))
    check('invalid_ZIP', lambda: raises('ZIP_INVALID', lambda: inspect(b'not a zip')))
    check('unknown_ZIP_trailing_layout', lambda: raises('ZIP_LAYOUT_UNSUPPORTED', lambda: inspect(fixture() + b'trailing')))
    check('unsupported_metadata_version', lambda: raises('METADATA_VERSION_UNSUPPORTED', lambda: inspect(fixture(version='2.5'))))
    check('wrong_metadata_identity', lambda: raises('METADATA_IDENTITY_MISMATCH', lambda: inspect(fixture(name='other'))))
    check('wrong_WHEEL_Tag', lambda: raises('WHEEL_TAG_MISMATCH', lambda: inspect(fixture(tag='cp311-cp311-win_amd64'))))
    check('duplicate_critical_metadata', lambda: raises('METADATA_INVALID', lambda: inspect(fixture(meta_extra='Name: torch\n'))))
    check('license_path_traversal', lambda: raises('ZIP_PATH_INVALID', lambda: inspect(fixture(ref='../LICENSE'))))
    check('ZIP_member_path_traversal', lambda: raises('ZIP_PATH_INVALID', lambda: inspect(fixture(additions={'../evil.txt': b'bad'}))))
    check('ZIP_casefold_duplicate', lambda: raises('ZIP_DUPLICATE', lambda: inspect(fixture(additions={'torch/X.txt': b'x', 'torch/x.txt': b'y'}))))
    def duplicate_zip():
        out = io.BytesIO(fixture())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(out, 'a') as archive:
                archive.writestr(DIST + 'METADATA', b'duplicate')
        raises('ZIP_DUPLICATE', lambda: inspect(out.getvalue()))
    check('ZIP_exact_duplicate', duplicate_zip)
    def symlink():
        out = io.BytesIO(fixture())
        with zipfile.ZipFile(out, 'a') as archive:
            entry = zipfile.ZipInfo('torch/link')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, 'target')
        raises('ZIP_SYMLINK', lambda: inspect(out.getvalue()))
    check('ZIP_symlink_refusal', symlink)
    def mutate_central(field, value, code):
        raw = bytearray(fixture())
        position = raw.index(b'PK\x01\x02')
        struct.pack_into('<H', raw, position + field, value)
        raises(code, lambda: inspect(bytes(raw)))
    check('encrypted_ZIP_refusal', lambda: mutate_central(8, 1, 'ZIP_ENCRYPTED'))
    check('unsupported_compression', lambda: mutate_central(10, 99, 'ZIP_COMPRESSION_UNSUPPORTED'))
    def central_limit():
        raw = bytearray(fixture())
        struct.pack_into('<L', raw, len(raw) - 22 + 12, m['CD_MAX'] + 1)
        raises('ZIP_CENTRAL_LIMIT', lambda: inspect(bytes(raw)))
    check('16_MiB_central_directory_limit', central_limit)
    def member_limit():
        raw = bytearray(fixture())
        struct.pack_into('<HH', raw, len(raw) - 22 + 8, 10001, 10001)
        raises('ZIP_MEMBER_LIMIT', lambda: inspect(bytes(raw)))
    check('10000_member_limit', member_limit)
    def text_limit():
        raw = fixture(additions={DIST + 'licenses/LICENSE': b'x' * (m['TEXT_MAX'] + 1)})
        raises('TEXT_LIMIT', lambda: inspect(raw))
    check('16_MiB_selected_text_limit', text_limit)
    check('RECORD_duplicate_row', lambda: raises('RECORD_INVALID', lambda: inspect(fixture(record_change=lambda rows: rows.append(copy.deepcopy(rows[0]))))))
    check('RECORD_wrong_length', lambda: raises('RECORD_SIZE_MISMATCH', lambda: inspect(fixture(record_change=lambda rows: rows[0].__setitem__(2, str(int(rows[0][2]) + 1))))))
    check('RECORD_wrong_digest', lambda: raises('RECORD_HASH_MISMATCH', lambda: inspect(fixture(record_change=lambda rows: rows[0].__setitem__(1, encoded(b'wrong'))))))
    check('RECORD_invalid_digest_encoding', lambda: raises('RECORD_INVALID', lambda: inspect(fixture(record_change=lambda rows: rows[0].__setitem__(1, 'sha256=bad')))))
    check('RECORD_self_entry_must_be_empty', lambda: raises('RECORD_INVALID', lambda: inspect(fixture(record_change=lambda rows: rows[-1].__setitem__(2, '0')))))
    def crc_failure():
        raw = bytearray(fixture(compression=zipfile.ZIP_STORED))
        location = raw.index(b'License text\n')
        raw[location] ^= 1
        raises('ZIP_CRC_MISMATCH', lambda: inspect(bytes(raw)))
    check('selected_member_CRC_failure', crc_failure)
    def unread_digest():
        def change(rows):
            row = next(r for r in rows if r[0].endswith('.dll'))
            row[1] = encoded(b'not the DLL')
        result = inspect(fixture(record_change=change))
        ensure(result['unread_DLL_payloads_individually_verified'] is False)
    check('unread_DLL_not_claimed_verified', unread_digest)

    class Response:
        def __init__(self, body=b'', status=200, headers=None, tick=None):
            self.body, self.status, self.position, self.tick = body, status, 0, tick
            self.headers = h['Headers'](headers if headers is not None else [('Content-Length', str(len(body)))])
            self.closed = False
        def read1(self, size):
            chunk = self.body[self.position:self.position + size]
            self.position += len(chunk)
            if self.tick:
                self.tick()
            return chunk
        def close(self):
            self.closed = True

    def receive(response, expected=None, clock=lambda: 0, deadline=870, disk=None):
        with Scenario(g, source_bytes, payload=response.body) as s:
            state = g['download_state']()
            state['http_status'] = response.status
            sink = io.BytesIO()
            def save(obj, context='PROGRESS'):
                g['write_json'](s.checkpoint, obj, context=context)
            g['receive_body'](s.connection, response, sink, state, budget(clock, deadline),
                              disk or s.disk, save,
                              expected if expected is not None else hashlib.sha256(response.body).hexdigest())
            ensure(s.save_contexts and 'PROGRESS_FINAL' in s.save_contexts)
            return state, sink.getvalue()

    def download_refusal(response, expected):
        with Scenario(g, source_bytes) as s:
            s.response = response
            state = s.download()
            ensure(state['error_code'] == expected and s.requests == 1)
            ensure(state['received_bytes'] == state['written_bytes'] == response.position == 0)
            ensure(state['request_count'] == state['get_send_attempts'] == 1)
            ensure(not any(event[0] == 'BODY_OPEN' for event in s.fs.events))
            ensure(s.save_contexts)

    check('streaming_hash_and_actual_bytes', lambda: ensure(receive(Response(b'body'))[0]['actual_sha256'] == hashlib.sha256(b'body').hexdigest()))
    check('wrong_full_download_hash', lambda: raises('HASH_MISMATCH', lambda: receive(Response(b'body'), expected='0' * 64)))
    check('403_stops_without_reading_body_or_opening_file', lambda: download_refusal(Response(b'forbidden', status=403), 'HTTP_FORBIDDEN'))
    check('redirect_not_followed', lambda: download_refusal(Response(status=302, headers=[('Location', 'https://other.invalid/')]), 'REDIRECT_REFUSED'))
    check('compressed_body_refused', lambda: download_refusal(Response(headers=[('Content-Encoding', 'gzip')]), 'COMPRESSION_REFUSED'))
    check('oversized_declared_body_before_download', lambda: download_refusal(Response(headers=[('Content-Length', str(g['BODY_MAX'] + 1))]), 'BODY_LIMIT'))
    check('ambiguous_HTTP_framing', lambda: download_refusal(Response(headers=[('Content-Length', '1'), ('Transfer-Encoding', 'chunked')]), 'RESPONSE_HEADER_INVALID'))

    def body_boundary():
        with Patches() as p:
            p.item(g, 'BODY_MAX', 8)
            result, written = receive(Response(b'12345678'))
            ensure(result['received_bytes'] == len(written) == 8)
            response = Response(b'123456789', headers=[])
            raises('BODY_LIMIT', lambda: receive(response))
            ensure(response.position == 8)
    check('hard_body_limit_no_overread_unknown_length', body_boundary)
    check('truncated_HTTP_body', lambda: raises('BODY_TRUNCATED', lambda: receive(Response(b'abc', headers=[('Content-Length', '4')]))))
    check('initial_8_GiB_disk_requirement', lambda: raises('DISK_START_LOW', lambda: g['disk_limits'](g['FREE_START'] - 1, 0, initial=True)))
    check('running_2_GiB_disk_reserve', lambda: raises('DISK_RESERVE_LOW', lambda: g['disk_limits'](g['FREE_KEEP'], 0)))
    check('4_point_1_GiB_increment_limit', lambda: raises('DISK_INCREMENT_LIMIT', lambda: g['disk_limits'](10 * g['GIB'], g['INCREMENT_MAX'])))

    def write_disk_guard():
        with Scenario(g, source_bytes, payload=b'body') as s:
            state, sink = g['download_state'](), io.BytesIO()
            class DropDisk:
                calls = 0
                def check(self, *args, **kwargs):
                    self.calls += 1
                    if self.calls == 2:
                        raise Failure('DISK_RESERVE_LOW')
            def save(obj, context='PROGRESS'):
                g['write_json'](s.checkpoint, obj, context=context)
            raises('DISK_RESERVE_LOW', lambda: g['receive_body'](s.connection, Response(b'body'), sink,
                    state, budget(), DropDisk(), save))
            ensure(state['received_bytes'] == 4 and state['written_bytes'] == len(sink.getvalue()) == 0)
            ensure(state['actual_sha256'] == hashlib.sha256(b'body').hexdigest())
            ensure(s.save_contexts == ['PROGRESS_BEFORE_WRITE'])
    check('disk_drop_after_receive_before_write', write_disk_guard)

    def reading_deadline():
        ticks = [0]
        response = Response(b'body', tick=lambda: ticks.__setitem__(0, 870))
        raises('DEADLINE_EXCEEDED', lambda: receive(response, clock=lambda: ticks[0]))
    check('download_deadline_during_receive', reading_deadline)
    check('static_deadline_before_ZIP', lambda: raises('DEADLINE_EXCEEDED', lambda: g['inspect_archive'](io.BytesIO(fixture()), len(fixture()), budget(deadline=0))))

    def wire_request():
        calls = []
        class Context:
            check_hostname = True
            verify_mode = ssl.CERT_REQUIRED
        class Wire:
            def __init__(self, host, context, time_budget):
                self.sock = h['FakeSocket']()
                ensure(host == 'download-r2.pytorch.org' and context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED)
            def connect(self):
                pass
            def close(self):
                pass
            def request(self, method, path, body, headers):
                calls.append((method, path, body, headers))
            def getresponse(self):
                return Response()
        with Patches() as p:
            p.attr(ssl, 'create_default_context', lambda: Context())
            get = g['OneGET'](Wire)
            get.open(g['URL'], budget(), lambda: None)
            ensure(len(calls) == 1 and calls[0][0] == 'GET' and calls[0][2] is None)
            ensure(set(k.lower() for k in calls[0][3]) == {'accept', 'accept-encoding', 'connection', 'user-agent'})
            ensure(calls[0][3]['Accept-Encoding'] == 'identity')
            ensure(calls[0][1] == '/whl/cu128/torch-2.10.0%2Bcu128-cp312-cp312-win_amd64.whl')
            raises('REQUEST_ALREADY_USED', lambda: get.open(g['URL'], budget(), lambda: None))
            other = g['OneGET'](Wire)
            raises('URL_NOT_ALLOWED', lambda: other.open(g['URL'] + '?changed=1', budget(), lambda: None))
            raises('REQUEST_ALREADY_USED', lambda: other.open(g['URL'], budget(), lambda: None))
            ensure(len(calls) == 1)
    check('exact_one_verified_TLS_GET_no_proxy_auth_cookie_range', wire_request)

    def deadline_process(active_seconds, total, confirmed):
        ticks = [0]
        class Process:
            code = None
            calls = 0
            def wait(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    ensure(timeout == active_seconds)
                    ticks[0] = active_seconds
                    raise subprocess.TimeoutExpired('MEMORY_ONLY', timeout)
                ensure(0 <= timeout <= total - active_seconds)
                if not confirmed:
                    ticks[0] = total - 1
                    raise subprocess.TimeoutExpired('MEMORY_ONLY', timeout)
                self.code = 1
            def terminate(self):
                pass
            def poll(self):
                return self.code
        result = g['wait_process'](Process(), active_seconds, total, lambda: ticks[0])
        ensure(result['worker_exit_confirmed'] is confirmed)
        ensure(result['error_code'] == 'DEADLINE_EXCEEDED')
        if not confirmed:
            ensure(result['exit_confirmation_status'] == 'UNKNOWN')
            ensure(any(item['error_code'] == 'WORKER_EXIT_UNCONFIRMED' for item in result['secondary_errors']))
    check('download_870_work_30_termination_reserve', lambda: deadline_process(870, 900, True))
    check('static_50_work_10_termination_reserve', lambda: deadline_process(50, 60, True))
    check('unconfirmed_exit_reported', lambda: deadline_process(870, 900, False))

    def unconfirmed_no_cleanup():
        class NoPathAccess:
            def __truediv__(self, value):
                raise AssertionError('PATH_ACCESS_FORBIDDEN')
        result = g['cleanup_partial'](NoPathAccess(), False)
        ensure(result['status'] == 'UNKNOWN' and not result['partial_cleanup_attempted'])
        data = {'status': 'completed', 'response_body_complete': True, 'sha256_matches_expected': True,
                'actual_sha256': g['EXPECTED'], 'received_bytes': 1, 'written_bytes': 1,
                'artifact_filename': g['FILENAME'], 'checkpoint_persisted': True, 'first_error': None,
                'journal_format': 'LTJR0001', 'journal_terminal_written': True,
                'journal_close_completed': True, 'journal_frame_count': 1,
                'error_code': None,
                'body_fsync_completed': True, 'body_close_completed': True, 'counters_complete': True}
        ensure(not g['can_inspect'](data, False) and g['can_inspect'](data, True))
        data['actual_sha256'] = '0' * 64
        ensure(not g['can_inspect'](data, True))
    check('unconfirmed_exit_blocks_ZIP_and_all_cleanup_path_access', unconfirmed_no_cleanup)

    def guard_budget(seconds, code):
        seen = []
        class Stop:
            def wait(self, timeout):
                ensure(timeout == seconds)
                return False
        g['watchdog'](seconds, Stop(), code, clock=lambda: 0, exit_fn=seen.append)
        ensure(seen == [code])
    for seconds, code in ((870, 124), (900, 125), (50, 124), (60, 125)):
        check('independent_watchdog_' + str(seconds), lambda seconds=seconds, code=code: guard_budget(seconds, code))

    def redact():
        code = g['safe_code'](RuntimeError('SYNTHETIC_SECRET_DO_NOT_EMIT'))
        raw = g['dumps']({'error_code': code})
        ensure(code == 'INTERNAL_ERROR' and b'SYNTHETIC_SECRET' not in raw)
    check('fixed_error_code_redaction', redact)

    def marker_integration(mode):
        with Scenario(g, source_bytes) as s:
            s.response = Response(status=403)
            if mode == 'repeat':
                state = s.download()
                ensure(state['error_code'] == 'HTTP_FORBIDDEN')
                previous = copy.deepcopy(s.fs.data)
                raises('ATTEMPT_ALREADY_USED', s.download)
                ensure(s.fs.data == previous and s.requests == 1)
                marker = json.loads(s.fs.data[str(s.out / 'request-attempt.json')])
                ensure(marker['single_attempt_consumed'] is True)
            else:
                target, code, key = {
                    'execution': (s.out / 'execution-started.json', 'ATTEMPT_INVALID', 'final_source_sha256'),
                    'review': (s.work / 'independent-review.json', 'PROGRAM_NOT_REVIEWED', 'source_sha256'),
                    'tests': (s.work / 'offline-tests.json', 'OFFLINE_TESTS_REQUIRED', 'source_sha256'),
                }[mode]
                value = json.loads(s.fs.data[str(target)])
                value[key] = '0' * 64
                s.fs.seed_json(str(target), value)
                previous = copy.deepcopy(s.fs.data)
                raises(code, s.download)
                ensure(s.requests == 0 and s.fs.data == previous)
    check('worker_reentry_after_403_one_GET_marker_and_evidence_preserved', lambda: marker_integration('repeat'))
    check('worker_changed_execution_evidence_blocks_GET_and_checkpoint_overwrite', lambda: marker_integration('execution'))
    check('worker_changed_review_blocks_GET', lambda: marker_integration('review'))
    check('worker_changed_offline_evidence_blocks_GET', lambda: marker_integration('tests'))

    def supervisor_reentry():
        with Scenario(g, source_bytes) as s:
            previous = copy.deepcopy(s.fs.data)
            raises('ATTEMPT_ALREADY_USED', lambda: g['supervise'](s.work, s.out))
            ensure(s.requests == 0 and not s.fs.events and s.fs.data == previous)
    check('supervisor_reentry_preserves_original_report_without_IO', supervisor_reentry)
    for label, deadline in (('NaN', float('nan')), ('Infinity', float('inf')), ('expired', -1),
                            ('overlong', g['time'].monotonic() + 10000)):
        def reject_deadline(deadline=deadline):
            with Scenario(g, source_bytes) as s:
                previous = copy.deepcopy(s.fs.data)
                raises('DEADLINE_EXCEEDED', lambda: g['worker']('download', s.work, s.out, deadline))
                ensure(s.requests == 0 and s.fs.data == previous)
        check('worker_deadline_reject_' + label, reject_deadline)
    ensure(len(results) == len(ORIGINAL_CASES) == 63)
    ensure([item['name'] for item in results] == ORIGINAL_CASES)

    def static_proof(s):
        prior = dict(status='completed', error_code=None, first_error=None, secondary_errors=[],
                     checkpoint_persisted=True, response_body_complete=True, sha256_matches_expected=True,
                     actual_sha256=g['EXPECTED'], received_bytes=1, written_bytes=1,
                     artifact_filename=g['FILENAME'], body_fsync_completed=True, body_close_completed=True,
                     counters_complete=True, candidate_id=g['CANDIDATE_ID'], source_sha256=s.source_hash,
                     finished_at='2026-10-08T00:00:00+00:00')
        stage = dict(status='completed', error_code=None, first_error=None, worker_exit_confirmed=True,
                     checkpoint_terminal_confirmed=True, worker_returncode=0, data=copy.deepcopy(prior))
        report = dict(candidate_id=g['CANDIDATE_ID'], final_source_sha256=s.source_hash,
                      first_error=None, report_save_failed=False, report_persisted=True,
                      stages={'download': stage})
        request = dict(candidate_id=g['CANDIDATE_ID'], final_source_sha256=s.source_hash,
                       single_attempt_consumed=True, retry_forbidden=True, stage='download', url=g['URL'])
        s.fs.seed_json(str(s.out / 'request-attempt.json'), request)
        prior.update(request_count=1, get_send_attempts=1, http_status=200)
        s.seed_journal_proof(prior)
        stage['data'] = copy.deepcopy(prior)
        return prior, stage, report

    def save_static_proof(s, prior, report):
        s.fs.seed_json(str(s.checkpoint), prior)
        s.fs.seed_json(str(s.out / 'report.json'), report)

    def static_once():
        with Scenario(g, source_bytes) as s:
            prior, stage, report = static_proof(s)
            save_static_proof(s, prior, report)
            result = g['worker_claim']('static', s.work, s.out)
            ensure(result == s.source_hash)
            marker = json.loads(s.fs.data[str(s.out / 'static-attempt.json')])
            ensure(marker['candidate_id'] == g['CANDIDATE_ID'] and marker['single_attempt_consumed'] is True)
            before = copy.deepcopy(s.fs.data)
            raises('ATTEMPT_ALREADY_USED', lambda: g['worker_claim']('static', s.work, s.out))
            ensure(s.fs.data == before and s.requests == s.static_calls == 0)
    check('candidate_static_claim_valid_proof_once_only', static_once)

    variants = (
        ('exit_unconfirmed', 'stage', 'worker_exit_confirmed', False),
        ('terminal_unconfirmed', 'stage', 'checkpoint_terminal_confirmed', False),
        ('worker_failed', 'stage', 'worker_returncode', 1),
        ('boolean_returncode', 'stage', 'worker_returncode', False),
        ('stage_first_error', 'stage', 'first_error', {'error_code': 'IO_ERROR'}),
        ('stage_error_code', 'stage', 'error_code', 'IO_ERROR'),
        ('report_first_error', 'report', 'first_error', {'error_code': 'IO_ERROR'}),
        ('report_save_failed', 'report', 'report_save_failed', True),
        ('report_not_persisted', 'report', 'report_persisted', False),
        ('old_candidate', 'report', 'candidate_id', 'OLD_CANDIDATE'),
        ('old_source', 'report', 'final_source_sha256', '0' * 64),
        ('body_incomplete', 'prior', 'response_body_complete', False),
        ('hash_unmatched', 'prior', 'sha256_matches_expected', False),
        ('actual_hash_wrong', 'prior', 'actual_sha256', '0' * 64),
        ('body_not_fsynced', 'prior', 'body_fsync_completed', False),
        ('body_not_closed', 'prior', 'body_close_completed', False),
        ('counters_incomplete', 'prior', 'counters_complete', False),
        ('boolean_byte_count', 'prior', 'received_bytes', True),
        ('mismatched_byte_count', 'prior', 'written_bytes', 2),
        ('old_checkpoint_candidate', 'prior', 'candidate_id', 'OLD_CANDIDATE'),
        ('old_checkpoint_source', 'prior', 'source_sha256', '0' * 64),
    )
    for label, target, field, value in variants:
        def reject_static(target=target, field=field, value=value):
            with Scenario(g, source_bytes) as s:
                prior, stage, report = static_proof(s)
                {'stage': stage, 'report': report, 'prior': prior}[target][field] = value
                stage['data'] = copy.deepcopy(prior)
                save_static_proof(s, prior, report)
                before = copy.deepcopy(s.fs.data)
                raises('CHECKPOINT_INVALID', lambda: g['worker_claim']('static', s.work, s.out))
                ensure(s.fs.data == before and s.requests == s.static_calls == 0)
        check('candidate_static_gate_reject_' + label, reject_static)

    def static_data_mismatch():
        with Scenario(g, source_bytes) as s:
            prior, stage, report = static_proof(s)
            stage['data']['finished_at'] = 'DIFFERENT'
            save_static_proof(s, prior, report)
            before = copy.deepcopy(s.fs.data)
            raises('CHECKPOINT_INVALID', lambda: g['worker_claim']('static', s.work, s.out))
            ensure(s.fs.data == before and s.requests == s.static_calls == 0)
    check('candidate_static_gate_reject_report_checkpoint_mismatch', static_data_mismatch)
    return results


def main():
    if sys.version_info[:2] != (3, 12):
        print('{"status":"failed","error_code":"PYTHON_VERSION_INVALID"}')
        return 1
    root = Path(__file__).parent
    paths = {name: root / name for name in ('run_check.py', 'adapted_offline_test.py', 'adapted_safety_test.py')}
    paths['offline_test.py'] = paths.pop('adapted_offline_test.py')
    paths['safety_test.py'] = paths.pop('adapted_safety_test.py')
    raw = {name: path.read_bytes() for name, path in paths.items()}
    h = {'__name__': 'safety_harness', '__file__': str(paths['offline_test.py'])}
    exec(compile(raw['offline_test.py'], 'offline_test.py', 'exec'), h)
    guard = h['Guard']()
    sys.addaudithook(guard.hook)
    with h['Patches']() as protection:
        protection.attr(os, '_exit', lambda *a, **k: guard.reject('exit'))
        protection.attr(os, 'fsync', lambda *a, **k: guard.reject('write'))
        protection.attr(shutil, 'disk_usage', lambda *a, **k: guard.reject('disk'))
        protection.attr(socket, 'socket', lambda *a, **k: guard.reject('network'))
        protection.attr(socket, 'getaddrinfo', lambda *a, **k: guard.reject('network'))
        protection.attr(ssl, 'create_default_context', lambda *a, **k: guard.reject('network'))
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
        g = {'__name__': 'safety_subject', '__file__': str(paths['run_check.py'])}
        exec(compile(raw['run_check.py'], 'run_check.py', 'exec'), g)
        results = suite(h, g, raw['run_check.py'], guard)
    passed = all(item['status'] == 'passed' for item in results) and not any(guard.counts.values())
    report = {'status': 'passed' if passed else 'failed', 'suite': 'adapted_download_zip_safety',
              'candidate_id': g['CANDIDATE_ID'],
              'source_sha256': hashlib.sha256(raw['run_check.py']).hexdigest(),
              'tests_source_sha256': {paths[name].name: hashlib.sha256(raw[name]).hexdigest() for name in ('offline_test.py', 'safety_test.py')},
              'python_version': '.'.join(map(str, sys.version_info[:3])),
              'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'test_count': len(results), 'passed_count': sum(item['status'] == 'passed' for item in results),
              'original_expected_count': len(ORIGINAL_CASES),
              'original_names_preserved': [x['name'] for x in results[:len(ORIGINAL_CASES)]] == ORIGINAL_CASES,
              'additional_candidate_safety_count': len(results) - len(ORIGINAL_CASES),
              'network_requests': 0, 'guard_counts': guard.counts, 'filesystem_model': 'memory_only', 'tests': results}
    h['assert_clean'](report)
    print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        result = main()
    except BaseException:
        print('{"status":"failed","error_code":"SAFETY_HARNESS_FAILED"}')
        result = 1
    sys.exit(result)
