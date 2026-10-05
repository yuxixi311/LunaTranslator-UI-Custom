"""Synthetic archives and injected boundaries only. Never install or import pip/native code."""
import base64
import builtins
import contextlib
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import warnings
import zipfile

import actions_runner as r
import setup_diagnostics as d

SECRET = 'NEVER_RETAIN_EXCEPTION_ENV_PATH_HEADER'
FAKE_DICT = b'synthetic dictionary bytes; never a parser input'


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.counter = 0
        self.synthetic_expected = {}
        self.real_public_expected = d.public_expected
        replacing = patch.object(d, 'public_expected', side_effect=lambda package, slot:
            self.synthetic_expected.get((package, slot), self.real_public_expected(package, slot)))
        replacing.start()
        self.addCleanup(replacing.stop)

    def trace(self, process='setup'):
        self.counter += 1
        run = self.tmp / str(self.counter)
        run.mkdir()
        return d.Trace(run, process)

    def assert_failure(self, trace, step, function, status=None):
        with self.assertRaises(BaseException):
            function()
        receipt = d.collect(trace.path.parent)[trace.document['process']]
        failed = [event for event in receipt['events'] if event['status'] in ('rejected', 'operation_failed')]
        self.assertTrue(any(event['step'] == step for event in failed), (step, failed))
        if status:
            self.assertEqual(next(event['status'] for event in failed if event['step'] == step), status)
        self.assertNotIn(SECRET, json.dumps(receipt))
        self.assertNotIn(str(self.tmp), json.dumps(receipt))

    def wheel(self, variant='good', dictionary=False):
        self.counter += 1
        package = 'SudachiDict-core' if dictionary else 'SudachiPy'
        version = '20260723' if dictionary else '0.6.11'
        prefix = ('sudachidict_core-' if dictionary else 'sudachipy-') + version + '.dist-info/'
        metadata = ('Name: ' + package + '\nVersion: ' + version + '\n\n').encode()
        if variant == 'name': metadata = b'Name: Wrong\nVersion: 0.6.11\n\n'
        if variant == 'name_missing': metadata = b'Version: 0.6.11\n\n'
        if variant == 'dependencies': metadata = metadata[:-1] + b'Requires-Dist: fake-dependency\n\n'
        tags = b'Tag: py3-none-any\n' if dictionary else b'Tag: cp312-cp312-manylinux2014_x86_64\nTag: cp312-cp312-manylinux_2_17_x86_64\n'
        files = {prefix + 'METADATA': metadata, prefix + 'WHEEL': tags,
                 prefix + ('LICENSE-2.0.txt' if dictionary else 'LICENSE'): b'fake notice'}
        if dictionary: files['sudachidict_core/resources/system.dic'] = FAKE_DICT
        else: files['sudachipy/__init__.py'] = b'# not imported\n'
        if variant == 'path': files['../' + SECRET] = b'x'
        if variant == 'hook': files['fake.pth'] = b'x'
        if variant == 'data': files['package.data/scripts/x'] = b'x'
        if variant == 'symlink': files['link'] = b'x'
        if variant == 'metadata_missing': del files[prefix + 'METADATA']
        if variant == 'tags': files[prefix + 'WHEEL'] = b'Tag: wrong\n'
        if variant == 'tags_missing': del files[prefix + 'WHEEL']
        if variant == 'license': del files[prefix + ('LICENSE-2.0.txt' if dictionary else 'LICENSE')]
        if variant == 'dictionary_missing': del files['sudachidict_core/resources/system.dic']
        if variant == 'dictionary_bad': files['sudachidict_core/resources/system.dic'] = b'wrong'
        if variant == 'dictionary_license':
            del files[prefix + 'LICENSE-2.0.txt']; files[prefix + 'LEGAL'] = b'fake legal'
        record = prefix + 'RECORD'
        rows = [[name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data))]
                for name, data in files.items()]
        rows.append([record, '', ''])
        if variant == 'record_inventory': rows.pop(0)
        if variant == 'record_columns': rows[0].append('extra')
        if variant == 'record_duplicate': rows.append(rows[0])
        if variant == 'record_self': rows[-1][1] = 'sha256=bad'
        if variant == 'record_format': rows[0][1] = 'md5=bad'
        if variant == 'record_size_format': rows[0][2] = 'invalid'
        if variant == 'record_digest': rows[0][1] = 'sha256=' + '0' * 43
        if variant == 'record_length': rows[0][2] = '0'
        stream = io.StringIO(); csv.writer(stream).writerows(rows)
        files[record] = stream.getvalue().encode()
        if variant == 'record_decode': files[record] = b'\xff'
        if variant == 'record_missing': del files[record]
        if variant == 'record_ambiguous': files['second.dist-info/RECORD'] = b''
        path = self.tmp / (str(self.counter) + '.whl')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, value in files.items():
                member = zipfile.ZipInfo(name)
                if variant == 'symlink' and name == 'link': member.external_attr = 0o120777 << 16
                archive.writestr(member, value)
            if variant == 'duplicate':
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr(prefix + 'METADATA', metadata)
        if variant == 'zip': path.write_bytes(b'not a zip')
        pin = {'name': package, 'version': version, 'filename': path.name,
               'size_bytes': path.stat().st_size, 'sha256': r.digest_file(path)['sha256'], 'requires_dist': [],
               'wheel_core_metadata_size_bytes': len(metadata), 'wheel_core_metadata_sha256': hashlib.sha256(metadata).hexdigest()}
        if variant == 'digest': pin['sha256'] = '0' * 64
        if variant == 'metadata_digest': pin['wheel_core_metadata_sha256'] = '0' * 64
        self.synthetic_expected.update({
            (package, 'wheel'): {'bytes': pin['size_bytes'], 'sha256': pin['sha256']},
            (package, 'metadata'): {'bytes': pin['wheel_core_metadata_size_bytes'], 'sha256': pin['wheel_core_metadata_sha256']},
            (package, 'dependencies'): d.digest_values(pin['requires_dist'])})
        if dictionary:
            self.synthetic_expected[(package, 'dictionary')] = {'bytes': r.base.DICT_SIZE, 'sha256': r.base.DICT_SHA}
        return path, pin

    def test_real_validator_rejections_match_archived_baseline_and_expose_fixed_steps(self):
        cases = {'digest': 'archive_digest', 'zip': 'archive_open', 'duplicate': 'archive_inventory',
            'path': 'archive_member_paths', 'symlink': 'archive_member_types', 'hook': 'archive_startup_hooks',
            'data': 'archive_startup_hooks', 'record_missing': 'record_location', 'record_ambiguous': 'record_location',
            'record_decode': 'record_decode', 'record_inventory': 'record_inventory', 'record_columns': 'record_inventory',
            'record_duplicate': 'record_inventory', 'record_self': 'record_self', 'record_format': 'record_format',
            'record_size_format': 'record_format', 'record_digest': 'record_members', 'record_length': 'record_members',
            'metadata_missing': 'metadata_read', 'metadata_digest': 'metadata_digest', 'name': 'metadata_identity',
            'name_missing': 'metadata_identity', 'dependencies': 'metadata_dependencies', 'tags': 'wheel_tags',
            'tags_missing': 'wheel_tags', 'license': 'license_notices'}
        for variant, step in cases.items():
            with self.subTest(variant=variant):
                wheel, pin = self.wheel(variant)
                with self.assertRaises(BaseException): r.base.inspect_wheels([wheel], [pin])
                trace = self.trace()
                self.assert_failure(trace, step, lambda: d.inspect_wheels([wheel], [pin], trace))

    def test_dictionary_checks_and_success_match_archived_baseline(self):
        with patch.object(r.base, 'DICT_SIZE', len(FAKE_DICT)), patch.object(r.base, 'DICT_SHA', hashlib.sha256(FAKE_DICT).hexdigest()):
            for variant, step in (('dictionary_missing', 'dictionary_identity'), ('dictionary_bad', 'dictionary_identity'),
                                  ('dictionary_license', 'dictionary_license')):
                with self.subTest(variant=variant):
                    wheel, pin = self.wheel(variant, dictionary=True)
                    with self.assertRaises(BaseException): r.base.inspect_wheels([wheel], [pin])
                    trace = self.trace()
                    self.assert_failure(trace, step, lambda: d.inspect_wheels([wheel], [pin], trace))
            first, a = self.wheel(); second, b = self.wheel(dictionary=True)
            trace = self.trace()
            self.assertEqual(d.inspect_wheels([first, second], [a, b], trace), r.base.inspect_wheels([first, second], [a, b]))
            self.assertEqual(len(trace.document['comparisons']), 9)
            self.assertTrue(all(item['matched'] for item in trace.document['comparisons']))

    def test_archive_missing_and_symlink_files_fail_before_open(self):
        wheel, pin = self.wheel(); wheel.unlink()
        for linked in (False, True):
            if linked: wheel.symlink_to(self.tmp)
            trace = self.trace()
            with patch.object(d.zipfile, 'ZipFile') as opening:
                self.assert_failure(trace, 'archive_digest', lambda: d.inspect_wheels([wheel], [pin], trace), 'rejected')
                opening.assert_not_called()

    def test_declared_archive_sizes_encryption_read_and_parse_faults(self):
        wheel, pin = self.wheel()
        original = zipfile.ZipFile.infolist
        def infos(archive, mode):
            values = original(archive)
            if mode == 'payload': values[0].file_size = 513 * r.base.MIB
            if mode == 'encrypted': values[0].flag_bits |= 1
            if mode == 'record_size': next(v for v in values if v.filename.endswith('/RECORD')).file_size = r.base.MIB + 1
            return values
        for mode, step in (('payload', 'archive_payload'), ('encrypted', 'archive_member_paths'), ('record_size', 'record_size')):
            with self.subTest(mode=mode), patch.object(zipfile.ZipFile, 'infolist', lambda archive: infos(archive, mode)):
                trace = self.trace()
                self.assert_failure(trace, step, lambda: d.inspect_wheels([wheel], [pin], trace), 'rejected')
                with self.assertRaises(BaseException): r.base.inspect_wheels([wheel], [pin])
        with patch.object(d.email.parser.BytesParser, 'parsebytes', side_effect=OSError(SECRET)):
            trace = self.trace()
            self.assert_failure(trace, 'metadata_parse', lambda: d.inspect_wheels([wheel], [pin], trace), 'operation_failed')
        with patch.object(zipfile.ZipFile, 'infolist', side_effect=OSError(SECRET)):
            trace = self.trace()
            self.assert_failure(trace, 'archive_inventory', lambda: d.inspect_wheels([wheel], [pin], trace), 'operation_failed')

    def test_public_comparisons_never_forward_metadata_or_dependency_strings(self):
        wheel, pin = self.wheel('dependencies')
        trace = self.trace()
        self.assert_failure(trace, 'metadata_dependencies', lambda: d.inspect_wheels([wheel], [pin], trace))
        data = json.dumps(d.collect(trace.path.parent))
        self.assertNotIn('fake-dependency', data)
        comparison = next(item for item in trace.document['comparisons'] if item['slot'] == 'dependencies')
        self.assertFalse(comparison['matched'])
        self.assertEqual(set(comparison['observed']), {'bytes', 'sha256'})

    def test_receipt_validation_blocks_unbounded_or_unapproved_fields(self):
        trace = self.trace()
        with trace.step('archive_digest', 'SudachiPy'): pass
        original = copy.deepcopy(trace.document)
        mutations = [lambda x: x.update(message=SECRET), lambda x: x['events'][0].update(step=SECRET),
            lambda x: x['events'][0].update(package=SECRET), lambda x: x['events'][0].update(status=SECRET),
            lambda x: x['events'][0].update(seconds=float('nan')),
            lambda x: x['events'][0].update(seconds=61), lambda x: x['events'].extend([x['events'][0]] * 100),
            lambda x: x['comparisons'].append({'package': 'SudachiPy', 'slot': 'wheel', 'observed': SECRET})]
        for mutate in mutations:
            value = copy.deepcopy(original); mutate(value)
            trace.path.write_text(json.dumps(value))
            self.assertEqual(d.collect(trace.path.parent)['setup'], {'status': 'invalid_receipt'})
        trace.path.write_bytes(b'x' * (d.BYTE_LIMITS['setup'] + 1))
        self.assertEqual(d.collect(trace.path.parent)['setup'], {'status': 'invalid_receipt'})

    def test_comparisons_bind_expected_values_to_public_pins_and_valid_pairs(self):
        for package in d.PACKAGES:
            for slot in d.SLOTS:
                if package == 'SudachiPy' and slot == 'dictionary':
                    with self.assertRaises(d.Rejected): self.real_public_expected(package, slot)
                    continue
                trace = self.trace()
                expected = self.real_public_expected(package, slot)
                trace.compare(package, slot, expected, expected)
                original = copy.deepcopy(trace.document)
                for field in ('expected', 'observed'):
                    value = copy.deepcopy(original)
                    value['comparisons'][0][field]['sha256'] = '0' * 64
                    trace.path.write_text(json.dumps(value))
                    self.assertEqual(d.collect(trace.path.parent)['setup'], {'status': 'invalid_receipt'})
        trace = self.trace()
        forged = {'package': 'SudachiPy', 'slot': 'dictionary',
                  'expected': {'bytes': r.base.DICT_SIZE, 'sha256': r.base.DICT_SHA},
                  'observed': {'bytes': r.base.DICT_SIZE, 'sha256': r.base.DICT_SHA}, 'matched': True}
        trace.document['comparisons'].append(forged)
        trace.path.write_text(json.dumps(trace.document))
        self.assertEqual(d.collect(trace.path.parent)['setup'], {'status': 'invalid_receipt'})
        trace.path.unlink(); trace.path.symlink_to(self.tmp)
        self.assertEqual(d.collect(trace.path.parent)['setup'], {'status': 'invalid_receipt'})

    def test_started_receipt_survives_interruption_and_cannot_reset(self):
        trace = self.trace()
        trace.document['events'].append({'step': 'archive_open', 'package': 'SudachiPy', 'status': 'started', 'seconds': 0.0})
        trace.write()
        self.assertEqual(d.collect(trace.path.parent)['setup']['events'][0]['status'], 'started')
        with self.assertRaises(FileExistsError): d.Trace(trace.path.parent, 'setup')

    @contextlib.contextmanager
    def fake_setup(self, trace):
        run = trace.path.parent
        (run / 'venv/bin').mkdir(parents=True)
        (run / 'venv/pyvenv.cfg').write_text('include-system-site-packages = false\n')
        with contextlib.ExitStack() as stack:
            values = {'work': stack.enter_context(patch.object(r, 'work', return_value=run)),
                'pins': stack.enter_context(patch.object(r.base, 'package_pins', return_value=[{'filename': 'a.whl'}, {'filename': 'b.whl'}])),
                'inspect': stack.enter_context(patch.object(d, 'inspect_wheels', return_value={})),
                'venv': stack.enter_context(patch('venv.EnvBuilder.create')),
                'env': stack.enter_context(patch.object(r, 'child_environment', return_value={})),
                'subprocess': stack.enter_context(patch.object(r.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0))),
                'digest': stack.enter_context(patch.object(r, 'digest_file', return_value={'bytes': 1, 'sha256': 'a' * 64})),
                'snapshot': stack.enter_context(patch.object(d, 'installed_snapshot', return_value={})),
                'host': stack.enter_context(patch.object(r, 'host_identity', return_value={}))}
            yield values

    def test_setup_operations_localize_failures_without_retrying_children(self):
        cases = [('pins', 'package_pins'), ('venv', 'venv_create'), ('env', 'installer_environment'),
                 ('subprocess', 'ensurepip_child'), ('digest', 'venv_interpreter'), ('host', 'setup_host')]
        for target, step in cases:
            with self.subTest(target=target):
                trace = self.trace()
                with self.fake_setup(trace) as mocks:
                    mocks[target].side_effect = OSError(SECRET)
                    self.assert_failure(trace, step, lambda: r.setup_offline('a' * 64, trace), 'operation_failed')
                    self.assertLessEqual(mocks['subprocess'].call_count, 2)
        trace = self.trace()
        with self.fake_setup(trace) as mocks:
            mocks['subprocess'].side_effect = [types.SimpleNamespace(returncode=0), OSError(SECRET)]
            self.assert_failure(trace, 'install_child', lambda: r.setup_offline('a' * 64, trace))
            self.assertEqual(mocks['subprocess'].call_count, 2)
        trace = self.trace()
        with self.fake_setup(trace):
            (trace.path.parent / 'venv/pyvenv.cfg').write_text('include-system-site-packages = true')
            self.assert_failure(trace, 'venv_isolation', lambda: r.setup_offline('a' * 64, trace), 'rejected')

    def test_setup_write_and_notice_failures_are_distinct(self):
        for step, name in (('snapshot_write', 'installed.json'), ('setup_write', 'setup.json')):
            trace = self.trace()
            original = r.write_json
            def writer(path, *args, **kwargs):
                if path.name == name: raise OSError(SECRET)
                return original(path, *args, **kwargs)
            with self.fake_setup(trace), patch.object(r, 'write_json', side_effect=writer):
                self.assert_failure(trace, step, lambda: r.setup_offline('a' * 64, trace))
        trace = self.trace()
        with self.fake_setup(trace) as mocks:
            mocks['digest'].side_effect = [{'bytes': 1, 'sha256': 'a' * 64}] * 2 + [OSError(SECRET)]
            self.assert_failure(trace, 'source_notices', lambda: r.setup_offline('a' * 64, trace))

    def test_venv_constructor_failure_is_inside_venv_step(self):
        trace = self.trace()
        with self.fake_setup(trace), patch('venv.EnvBuilder', side_effect=OSError(SECRET)):
            self.assert_failure(trace, 'venv_create', lambda: r.setup_offline('a' * 64, trace))

    def test_final_snapshot_dictionary_read_has_fixed_step(self):
        trace = self.trace(); run = trace.path.parent
        dictionary = r.base.site_path(run) / 'sudachidict_core/resources/system.dic'
        dictionary.parent.mkdir(parents=True); dictionary.write_bytes(FAKE_DICT)
        digest = d.digest_bytes(FAKE_DICT)
        with patch.object(r.base, 'DICT_SIZE', digest['bytes']), patch.object(r.base, 'DICT_SHA', digest['sha256']), \
             patch.object(r.base, 'digest_file', side_effect=[digest, digest, OSError(SECRET)]):
            self.assert_failure(trace, 'snapshot_payload', lambda: d.installed_snapshot(run, trace))

    def test_installed_snapshot_parity_and_every_rejection(self):
        for variant, step in (('missing', 'snapshot_dictionary'), ('symlink', 'snapshot_inventory'),
                              ('hook', 'snapshot_inventory'), ('payload', 'snapshot_payload'), ('good', None)):
            trace = self.trace(); run = trace.path.parent
            site = r.base.site_path(run); dictionary = site / 'sudachidict_core/resources/system.dic'
            dictionary.parent.mkdir(parents=True); dictionary.write_bytes(FAKE_DICT)
            if variant == 'missing': dictionary.unlink()
            if variant == 'symlink': (site / 'link').symlink_to(dictionary)
            if variant == 'hook': (site / 'startup.pth').write_text('x')
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(r.base, 'DICT_SIZE', len(FAKE_DICT)))
                stack.enter_context(patch.object(r.base, 'DICT_SHA', hashlib.sha256(FAKE_DICT).hexdigest()))
                if variant == 'payload':
                    # A synthetic large installed entry; dictionary verification remains real.
                    (site / 'other').write_bytes(b'x')
                    original = r.base.digest_file
                    stack.enter_context(patch.object(r.base, 'digest_file', side_effect=lambda path:
                        {'bytes': 513 * r.base.MIB, 'sha256': 'b' * 64} if Path(path).name == 'other' else original(path)))
                if step:
                    self.assert_failure(trace, step, lambda: d.installed_snapshot(run, trace))
                    with self.assertRaises(BaseException): r.base.installed_snapshot(run)
                else:
                    self.assertEqual(d.installed_snapshot(run, trace), r.base.installed_snapshot(run))

    def test_ensurepip_hook_executes_nested_socket_guard_and_retains_nested_failure(self):
        import ensurepip
        for fail in (False, True):
            trace = self.trace('_ensurepip'); run = trace.path.parent
            original = ensurepip._run_pip
            captured = []
            def bootstrap(**kwargs):
                self.assertEqual(kwargs, {'default_pip': True})
                return ensurepip._run_pip(['install', '--no-index'], ['/fake/public/bundled-pip.whl'])
            def fake_run(command, **kwargs):
                captured.append(command)
                self.assertEqual(command[:4], [sys.executable, '-I', '-B', '-c'])
                self.assertEqual(kwargs, {'check': True})
                hooks = []
                with patch.object(sys, 'addaudithook', side_effect=hooks.append), patch.object(runpy, 'run_module') as pip, \
                     patch.object(sys, 'path', list(sys.path)), patch.object(sys, 'argv', list(sys.argv)):
                    exec(compile(command[4], '<fake bundled bootstrap>', 'exec'), {})
                pip.assert_called_once_with('pip', run_name='__main__')
                self.assertEqual(len(hooks), 1)
                with self.assertRaises(RuntimeError): hooks[0]('socket.connect', ())
                hooks[0]('open', ())
                if fail: raise OSError(SECRET)
                return types.SimpleNamespace(returncode=0)
            with patch.object(r, 'work', return_value=run), patch.object(sys, 'prefix', str(run / 'venv')), \
                 patch.object(ensurepip, 'bootstrap', side_effect=bootstrap), patch.object(r.subprocess, 'run', side_effect=fake_run):
                if fail:
                    self.assert_failure(trace, 'ensurepip_pip_child', lambda: r.ensurepip_offline(trace))
                    self.assertTrue(any(e['step'] == 'ensurepip_bootstrap' and e['status'] == 'operation_failed' for e in trace.document['events']))
                else: r.ensurepip_offline(trace)
            self.assertIs(ensurepip._run_pip, original)
            self.assertEqual(len(captured), 1)

    def test_install_module_exit_status_argv_and_fixed_offline_flags(self):
        for failure, step in ((OSError(SECRET), 'install_module'), (SystemExit(2), 'install_exit'), (SystemExit(0), None)):
            trace = self.trace('_install'); run = trace.path.parent; original = sys.argv
            def pip(name, **kwargs):
                self.assertEqual(name, 'pip')
                self.assertEqual(kwargs, {'run_name': '__main__'})
                self.assertEqual(sys.argv[:9], ['pip', '--isolated', '--disable-pip-version-check', '--no-cache-dir',
                    'install', '--no-index', '--no-deps', '--no-compile', '--only-binary=:all:'])
                self.assertEqual(len(sys.argv), 11)
                raise failure
            with patch.object(r, 'work', return_value=run), patch.object(sys, 'prefix', str(run / 'venv')), \
                 patch.object(runpy, 'run_module', side_effect=pip):
                if step: self.assert_failure(trace, step, lambda: r.install_local(trace))
                else: r.install_local(trace)
            self.assertIs(sys.argv, original)

    def test_nested_venv_identity_and_pin_failures(self):
        for process, function, step in (('_ensurepip', r.ensurepip_offline, 'ensurepip_venv'),
                                        ('_install', r.install_local, 'install_venv')):
            trace = self.trace(process)
            with patch.object(r, 'work', return_value=trace.path.parent), patch.object(sys, 'prefix', sys.base_prefix):
                self.assert_failure(trace, step, lambda: function(trace), 'rejected')
        trace = self.trace('_install')
        with patch.object(r, 'work', return_value=trace.path.parent), patch.object(sys, 'prefix', str(trace.path.parent / 'venv')), \
             patch.object(r.base, 'package_pins', side_effect=OSError(SECRET)):
            self.assert_failure(trace, 'install_pins', lambda: r.install_local(trace))

    @contextlib.contextmanager
    def fake_child(self, trace):
        sha, run = 'a' * 64, trace.path.parent
        binding = {'protocol': r.PROTOCOL, 'source_manifest_sha256': sha, 'run_attempt': 1}
        state = {'binding': binding, 'source_manifest_sha256': sha, 'state': 'setup_running',
                 'host': {}, 'controller_pid': 123, 'phases': {}}
        original_read = r.read_json
        def reader(path):
            if Path(path).name == 'EVENT_BINDING.json': return binding
            if Path(path).name == 'RUN_CLAIM.json': return state
            return original_read(path)
        with contextlib.ExitStack() as stack:
            mocks = {}
            targets = [
                (r, 'work', {'return_value': run}), (d, 'Trace', {'return_value': trace}),
                (r.os, 'getppid', {'return_value': 123}), (r.os, 'getpid', {'return_value': 456}),
                (r.os, 'getpgrp', {'return_value': 456 if trace.document['process'] == 'setup' else 123}),
                (r.sys, 'addaudithook', {}), (r.resource, 'setrlimit', {}),
                (r.guard, 'verify_sources', {}), (r.base, 'host_check', {}),
                (r, 'validated_runtime', {}), (r, 'read_json', {'side_effect': reader}),
                (r, 'host_identity', {'return_value': {}}), (r, 'validate_completed', {}),
                (r, 'setup_offline', {}), (r, 'ensurepip_offline', {}), (r, 'install_local', {}),
                (r, 'phase_receipt', {})]
            for target, name, kwargs in targets:
                mocks[name] = stack.enter_context(patch.object(target, name, **kwargs))
            yield mocks, state, binding

    def test_child_boundary_faults_have_fixed_receipts_and_no_later_operation(self):
        targets = [('getppid', 'parent_identity'), ('addaudithook', 'offline_audit'),
            ('setrlimit', 'resource_limits'), ('verify_sources', 'source_inventory'), ('host_check', 'host_runtime'),
            ('validated_runtime', 'runtime_cache'), ('host_identity', 'claim_identity'), ('getpgrp', 'process_group'),
            ('validate_completed', 'prior_receipts'), ('phase_receipt', 'phase_receipt')]
        for target, step in targets:
            with self.subTest(target=target):
                trace = self.trace()
                with self.fake_child(trace) as (mocks, state, binding):
                    mocks[target].side_effect = OSError(SECRET)
                    self.assert_failure(trace, step, lambda: r.child('setup', 'a' * 64, 123))
                    if step != 'phase_receipt': mocks['setup_offline'].assert_not_called()
                error = json.loads((trace.path.parent / 'setup.error.json').read_text())
                self.assertEqual(error, {'stage': 'setup', 'category': 'operation_failed'})
        for filename, step in (('EVENT_BINDING.json', 'event_binding'), ('RUN_CLAIM.json', 'claim_read')):
            trace = self.trace()
            with self.fake_child(trace) as (mocks, state, binding):
                original = mocks['read_json'].side_effect
                def reader(path):
                    if Path(path).name == filename: raise OSError(SECRET)
                    return original(path)
                mocks['read_json'].side_effect = reader
                self.assert_failure(trace, step, lambda: r.child('setup', 'a' * 64, 123))

    def test_child_rejects_wrong_identity_binding_claim_and_process_group(self):
        for kind, step in (('parent', 'parent_identity'), ('binding', 'event_binding'),
                           ('claim', 'claim_identity'), ('group', 'process_group')):
            trace = self.trace()
            with self.fake_child(trace) as (mocks, state, binding):
                if kind == 'parent': mocks['getppid'].return_value = 999
                if kind == 'binding': binding['run_attempt'] = 2
                if kind == 'claim': state['state'] = 'download_running'
                if kind == 'group': mocks['getpgrp'].return_value = 999
                self.assert_failure(trace, step, lambda: r.child('setup', 'a' * 64, 123), 'rejected')
                mocks['setup_offline'].assert_not_called()
        for process in ('_ensurepip', '_install'):
            trace = self.trace(process)
            with self.fake_child(trace) as (mocks, state, binding):
                mocks['getpgrp'].return_value = 999
                self.assert_failure(trace, 'process_group', lambda: r.child(process, 'a' * 64, 123), 'rejected')

    def test_preflight_failures_do_not_claim_or_launch(self):
        for target, step in (('preflight_resources', 'preflight_resources'), ('flock', 'control_lock'), ('claim', 'exclusive_claim')):
            trace = self.trace('preflight')
            with patch.object(r, 'work', return_value=trace.path.parent), patch.object(d, 'Trace', return_value=trace), \
                 patch.object(r, 'verify', return_value={}), patch.object(r.base, 'preflight_resources') as resources, \
                 patch.object(r.fcntl, 'flock') as flock, patch.object(r, 'claim') as claim, patch.object(r, 'run_phase') as phase:
                {'preflight_resources': resources, 'flock': flock, 'claim': claim}[target].side_effect = OSError(SECRET)
                self.assert_failure(trace, step, lambda: r.control('a' * 64))
                phase.assert_not_called()
                if target != 'claim': claim.assert_not_called()

    def test_import_argument_and_bootstrap_boundaries(self):
        original_import = builtins.__import__
        def reject_import(name, *args, **kwargs):
            if name == denied: raise ImportError(SECRET)
            return original_import(name, *args, **kwargs)
        for denied, process, step, function in (('venv', 'setup', 'venv_module', lambda t: r.setup_offline('a' * 64, t)),
                ('ensurepip', '_ensurepip', 'ensurepip_module', r.ensurepip_offline)):
            trace = self.trace(process)
            with self.fake_setup(trace), patch.object(sys, 'prefix', str(trace.path.parent / 'venv')), \
                 patch('builtins.__import__', side_effect=reject_import):
                self.assert_failure(trace, step, lambda: function(trace))
        trace = self.trace('_ensurepip')
        with patch.object(r, 'work', return_value=trace.path.parent), patch.object(sys, 'prefix', str(trace.path.parent / 'venv')), \
             patch('ensurepip.bootstrap', side_effect=OSError(SECRET)):
            self.assert_failure(trace, 'ensurepip_bootstrap', lambda: r.ensurepip_offline(trace))
        trace = self.trace('_install')
        with patch.object(r, 'work', return_value=trace.path.parent), patch.object(sys, 'prefix', str(trace.path.parent / 'venv')), \
             patch.object(r.base, 'package_pins', return_value=[{}]):
            self.assert_failure(trace, 'install_arguments', lambda: r.install_local(trace))
        trace = self.trace()
        with self.fake_setup(trace) as mocks:
            mocks['pins'].return_value = [{'filename': '../' + SECRET}, {'filename': 'b.whl'}]
            self.assert_failure(trace, 'wheel_paths', lambda: r.setup_offline('a' * 64, trace), 'rejected')

    def test_ensurepip_hook_assignment_failure_is_localized(self):
        class RejectHook:
            _run_pip = None
            def __setattr__(self, name, value): raise OSError(SECRET)
        trace = self.trace('_ensurepip')
        with patch.object(r, 'work', return_value=trace.path.parent), patch.object(sys, 'prefix', str(trace.path.parent / 'venv')), \
             patch.dict(sys.modules, {'ensurepip': RejectHook()}):
            self.assert_failure(trace, 'ensurepip_hook', lambda: r.ensurepip_offline(trace))

    def test_maximum_diagnostics_fit_existing_public_summary_limit(self):
        for process in d.PROCESSES:
            trace = d.Trace(self.tmp, process)
            trace.document['events'] = [{'step': 'archive_startup_hooks', 'package': 'SudachiDict-core',
                'status': 'operation_failed', 'seconds': 59.999999} for _ in range(d.EVENT_LIMITS[process])]
            if process == 'setup':
                for package in d.PACKAGES:
                    for slot in d.SLOTS:
                        if package == 'SudachiPy' and slot == 'dictionary': continue
                        expected = self.real_public_expected(package, slot)
                        trace.document['comparisons'].append({'package': package, 'slot': slot, 'expected': expected,
                            'observed': expected, 'matched': True})
            trace.write()
        with patch.object(r, 'work', return_value=self.tmp):
            state = r.claim('a' * 64, {})
            state.update(state='terminal_failure', error={'phase': 'setup', 'category': 'operation_failed'})
            data = r.sanitized_summary(state)
        self.assertLessEqual(len(data.encode()), 32768)
        self.assertNotIn('invalid_receipt', data)
        self.assertNotIn(str(self.tmp), data)


if __name__ == '__main__':
    unittest.main()
