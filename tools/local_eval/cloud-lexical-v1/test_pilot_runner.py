"""Fake-only tests. No package download, install, parser or model execution."""
import base64
import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

import pilot_runner as r


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def wheel(self, additions=None, record_bad=False, duplicate=False):
        metadata = b'Name: SudachiPy\nVersion: 0.6.11\n\n'
        files = {'sudachipy/__init__.py': b'# fake, never imported\n',
                 'sudachipy-0.6.11.dist-info/METADATA': metadata,
                 'sudachipy-0.6.11.dist-info/WHEEL': b'Wheel-Version: 1.0\nTag: cp312-cp312-manylinux2014_x86_64\nTag: cp312-cp312-manylinux_2_17_x86_64\n',
                 'sudachipy-0.6.11.dist-info/LICENSE': b'fake test notice'}
        files.update(additions or {})
        record = 'sudachipy-0.6.11.dist-info/RECORD'
        text = io.StringIO()
        writer = csv.writer(text)
        for name, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            writer.writerow([name, 'sha256=' + ('0' * 43 if record_bad else digest), len(data)])
        writer.writerow([record, '', ''])
        files[record] = text.getvalue().encode()
        path = self.tmp / 'fake.whl'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            if duplicate:
                archive.writestr('sudachipy/__init__.py', b'x')
        pin = {'name': 'SudachiPy', 'version': '0.6.11', 'size_bytes': path.stat().st_size,
               'sha256': r.digest_file(path)['sha256'], 'requires_dist': [],
               'wheel_core_metadata_size_bytes': len(metadata),
               'wheel_core_metadata_sha256': hashlib.sha256(metadata).hexdigest()}
        return path, pin

    def test_frozen_preparation_still_exact(self):
        self.assertEqual(len(r.prepared_files()), 13)
        self.assertEqual(len(r.batch_sources()), 48)
        self.assertEqual(sum(p['size_bytes'] for p in r.package_pins()), 73904174)

    def test_archive_all_record_members_verified(self):
        path, pin = self.wheel()
        result = r.inspect_wheels([path], [pin])
        self.assertTrue(result['wheels'][0]['record_verified'])

    def test_archive_record_corruption(self):
        path, pin = self.wheel(record_bad=True)
        with self.assertRaisesRegex(RuntimeError, 'RECORD hash'):
            r.inspect_wheels([path], [pin])

    def test_archive_path_traversal_hook_and_relocation(self):
        for name in ('../evil', '/tmp/evil', 'a\\evil', 'a//evil', 'a/./evil',
                     'sudachipy.pth', 'sudachipy-0.6.11.data/scripts/tool'):
            with self.subTest(name=name):
                path, pin = self.wheel({name: b'x'})
                with self.assertRaises(RuntimeError):
                    r.inspect_wheels([path], [pin])

    def test_archive_duplicate_and_symlink(self):
        with self.assertWarns(UserWarning):
            path, pin = self.wheel(duplicate=True)
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            r.inspect_wheels([path], [pin])
        path, pin = self.wheel()
        with zipfile.ZipFile(path, 'a') as archive:
            member = zipfile.ZipInfo('sudachipy/link')
            member.external_attr = 0o120777 << 16
            archive.writestr(member, 'elsewhere')
        pin.update(size_bytes=path.stat().st_size, sha256=r.digest_file(path)['sha256'])
        with self.assertRaisesRegex(RuntimeError, 'link/special'):
            r.inspect_wheels([path], [pin])

    def test_archive_payload_limit_before_read(self):
        path, pin = self.wheel()
        with patch.object(r, 'MIB', 1), self.assertRaises(RuntimeError):
            r.inspect_wheels([path], [pin])

    def test_archive_hash_mismatch(self):
        path, pin = self.wheel()
        pin['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'integrity mismatch'):
            r.inspect_wheels([path], [pin])

    def test_download_two_exact_urls_no_retry(self):
        import urllib.request
        from unittest.mock import Mock
        (self.tmp / 'wheels').mkdir()
        pins = []
        replies = []
        for i, body in enumerate((b'abc', b'defg')):
            url = 'https://files.pythonhosted.org/packages/fake/' + str(i) + '.whl'
            pins.append({'url': url, 'filename': str(i) + '.whl', 'size_bytes': len(body),
                         'sha256': hashlib.sha256(body).hexdigest()})
            response = io.BytesIO(body)
            response.status, response.url, response.headers = 200, url, {'Content-Length': str(len(body))}
            replies.append(response)
        opener = Mock()
        opener.open.side_effect = replies
        with patch.object(r, 'package_pins', return_value=pins), patch.object(urllib.request, 'build_opener', return_value=opener) as build:
            r.download(self.tmp)
        self.assertEqual([call.args[0].full_url for call in opener.open.call_args_list], [p['url'] for p in pins])
        redirect = build.call_args.args[1]
        with self.assertRaisesRegex(RuntimeError, 'redirect forbidden'):
            redirect.redirect_request(None, None, None, None, None, None)
        self.assertEqual(r.read_json(self.tmp / 'download.json')['compressed_bytes'], 7)

    def test_download_failure_no_second_attempt(self):
        import urllib.request
        from unittest.mock import Mock
        (self.tmp / 'wheels').mkdir()
        opener = Mock()
        opener.open.side_effect = OSError('fake denial')
        pin = {'url': 'https://files.pythonhosted.org/fake.whl', 'filename': 'fake.whl', 'size_bytes': 1, 'sha256': '0' * 64}
        with patch.object(r, 'package_pins', return_value=[pin]), patch.object(urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(OSError, 'fake denial'):
                r.download(self.tmp)
        self.assertEqual(opener.open.call_count, 1)

    def test_claim_is_persistent_and_exclusive(self):
        with patch.object(r, 'ROOT', self.tmp):
            lock, state = r.claim_run('a' * 64, 'download')
            with self.assertRaises(BlockingIOError):
                r.claim_run('a' * 64, 'download')
            state['state'] = 'parse_running'
            r.save_state(state)
            lock.close()
            with self.assertRaisesRegex(RuntimeError, 'terminal/stale'):
                r.claim_run('a' * 64, 'all')
            self.assertTrue((self.tmp / 'RUN_CLAIM.json').exists())

    def test_claim_manifest_cannot_change(self):
        with patch.object(r, 'ROOT', self.tmp):
            lock, state = r.claim_run('a' * 64, 'download')
            lock.close()
            with self.assertRaisesRegex(RuntimeError, 'different manifest'):
                r.claim_run('b' * 64, 'download')

    def test_offline_socket_hook(self):
        for event in ('socket.__new__', 'socket.getaddrinfo', 'socket.connect'):
            with self.assertRaisesRegex(RuntimeError, 'forbidden'):
                r.block_network(event, ())
        r.block_network('open', ())

    def test_clean_environment_no_private_values(self):
        env = r.clean_environment(self.tmp)
        self.assertNotIn('PYTHONPATH', env)
        self.assertNotIn('HTTPS_PROXY', env)
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(env['PIP_NO_INDEX'], '1')

    def fake_parser(self, fail=False):
        parent = self
        class Morpheme:
            def __init__(self, source): self.source = source
            def begin(self): return 0
            def end(self): return len(self.source)
            def raw_surface(self): return 'WRONG' if fail else self.source
            def part_of_speech(self): return ['名詞', '普通名詞', '一般', '*', '*', '*']
            def is_oov(self): return False
            def dictionary_id(self): return 0
        class Tokenizer:
            SplitMode = types.SimpleNamespace(C='C')
            calls = []
            def tokenize(self, source):
                self.calls.append(source)
                return [Morpheme(source)]
        class Dictionary:
            def __init__(self, **kwargs):
                parent.assertEqual(json.loads(kwargs['config']), {'userDict': [], 'projection': 'surface'})
                parent.assertTrue(Path(kwargs['dict']).is_absolute())
            def create(self, **kwargs):
                parent.assertEqual(kwargs, {'mode': 'C', 'projection': 'surface'})
                return Tokenizer()
            def close(self): pass
        module = types.ModuleType('sudachipy')
        module.Dictionary, module.Tokenizer = Dictionary, Tokenizer
        module.__file__ = str(r.site_path(self.tmp) / 'sudachipy' / '__init__.py')
        return module

    def parser_patches(self, fake):
        stack = contextlib.ExitStack()
        snapshot = {'files': {}, 'dictionary': {'bytes': r.DICT_SIZE, 'sha256': r.DICT_SHA}}
        r.write_json(self.tmp / 'installed.json', snapshot)
        stack.enter_context(patch.object(r, 'installed_snapshot', return_value=snapshot))
        stack.enter_context(patch.object(r.resource, 'setrlimit'))
        stack.enter_context(patch.object(sys, 'prefix', str(self.tmp / 'venv')))
        stack.enter_context(patch.dict(sys.modules, sudachipy=fake))
        distributions = [types.SimpleNamespace(metadata={'Name': name}, version=version) for name, version in
                         [('pip', '25.0'), ('SudachiPy', '0.6.11'), ('SudachiDict-core', '20260723')]]
        stack.enter_context(patch('importlib.metadata.distributions', return_value=distributions))
        return stack

    def test_fixed_batch_exactly_48_no_expected_labels(self):
        fake = self.fake_parser()
        with self.parser_patches(fake), patch.object(r, 'read_json', wraps=r.read_json) as reads:
            r.parse_batch(self.tmp, 'a' * 64)
        self.assertEqual(fake.Tokenizer.calls, [row['source'] for row in r.batch_sources()])
        self.assertFalse(any('expected' in str(c.args[0]) for c in reads.call_args_list))
        output = r.read_json(self.tmp / 'parser.json')
        self.assertEqual(output['parser_calls'], 48)
        self.assertTrue(output['complete'])
        r.assess(self.tmp, 'a' * 64)
        assessment = r.read_json(self.tmp / 'assessment.json')
        self.assertFalse(assessment['lexical_gate_passed'])
        self.assertEqual(len(assessment['seen_regressions']), 32)

    def test_bad_raw_surface_stops_no_retry(self):
        fake = self.fake_parser(fail=True)
        with self.parser_patches(fake), self.assertRaisesRegex(ValueError, 'surface mismatch'):
            r.parse_batch(self.tmp, 'a' * 64)
        self.assertEqual(len(fake.Tokenizer.calls), 1)
        self.assertFalse((self.tmp / 'parser.json').exists())

    def test_incomplete_batch_never_reads_labels(self):
        r.write_json(self.tmp / 'parser.json', {'complete': False})
        with patch.object(r, 'read_json', wraps=r.read_json) as reads, self.assertRaises(RuntimeError):
            r.assess(self.tmp, 'a' * 64)
        self.assertEqual(len(reads.call_args_list), 1)

    def test_prior_output_tampering_is_terminal(self):
        with patch.object(r, 'ROOT', self.tmp), patch.object(r, 'verify_manifest'), patch.object(r, 'host_check'), \
                patch.object(r, 'package_pins'), patch.object(r, 'batch_sources'):
            lock, state = r.claim_run('a' * 64, 'download')
            lock.close()
            path = self.tmp / 'run' / 'parser.json'
            r.write_json(path, {'original': True})
            state.update(state='parse_done', phases={'parse': {'artifacts': {'parser.json': r.digest_file(path)}}})
            r.save_state(state)
            r.write_json(path, {'tampered': True})
            with patch.object(r, 'owned_process') as launch, self.assertRaisesRegex(RuntimeError, 'integrity mismatch'):
                r.control('assess', 'a' * 64)
            launch.assert_not_called()
            self.assertEqual(r.read_json(self.tmp / 'RUN_CLAIM.json')['state'], 'terminal_failure')

    def test_spawn_timeout_keeps_owned_pid_for_cleanup(self):
        class FakePopen:
            def __init__(self, *args, **kwargs):
                self.pid, self.returncode = 12345, None
                raise r.PhaseTimeout('fake blocked spawn')
            def wait(self, timeout): self.returncode = -15
        with patch.object(r.subprocess, 'Popen', FakePopen), patch.object(r.signal, 'setitimer'), \
                patch.object(r, 'process_group_exists', return_value=False), \
                patch.object(r.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, '"timed_out": true'):
                r.owned_process(['fake'], self.tmp, {}, self.tmp / 'fake.log', 60)
        kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_spawn_before_setsid_signals_only_owned_child(self):
        process = types.SimpleNamespace(pid=12345, returncode=None)
        with patch.object(r.os, 'killpg', side_effect=ProcessLookupError), patch.object(r.os, 'kill') as kill:
            r.signal_owned(process, signal.SIGTERM)
        kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_failure_cleanup_is_terminal_even_success_exit(self):
        class FakePopen:
            def __init__(self, *args, **kwargs): self.pid, self.returncode = 12345, 0
            def wait(self, timeout): pass
        ticks = iter([0, 0, 0, 0, 60, 60, 60, 60, 60])
        with patch.object(r.subprocess, 'Popen', FakePopen), patch.object(r.signal, 'setitimer'), \
                patch.object(r.time, 'monotonic', side_effect=lambda: next(ticks, 60)), \
                patch.object(r, 'process_group_exists', return_value=True), patch.object(r.os, 'killpg'):
            with self.assertRaisesRegex(RuntimeError, '"cleanup_confirmed": false'):
                r.owned_process(['fake'], self.tmp, {}, self.tmp / 'fake.log', 60)


if __name__ == '__main__':
    unittest.main()
