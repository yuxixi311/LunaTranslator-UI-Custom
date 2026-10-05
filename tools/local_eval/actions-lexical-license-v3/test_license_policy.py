"""No real wheel inputs: source notice files plus explicitly synthetic archives."""
import base64
import contextlib
import copy
import csv
import email.parser
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import actions_runner as r
import license_policy as lp
import setup_diagnostics as d
import test_setup_diagnostics as fixtures


class NoticePolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DiagnosticsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tmp = self.fixture.tmp

    def sources_copy(self):
        root = self.tmp / ('sources-' + str(len(list(self.tmp.iterdir()))))
        root.mkdir()
        shutil.copyfile(r.BASELINE / 'PYPI_PINS.json', root / 'PYPI_PINS.json')
        for source in lp.SOURCES:
            target = root / source['file']; target.parent.mkdir(exist_ok=True)
            shutil.copyfile(r.BASELINE / source['file'], target)
        return root

    def rewrite(self, wheel, pin, additions=None, removals=()):
        with zipfile.ZipFile(wheel) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        record = next(name for name in files if name.endswith('.dist-info/RECORD'))
        files.pop(record)
        files.update(additions or {})
        for name in removals: files.pop(name)
        rows = [[name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data))]
                for name, data in files.items()]
        rows.append([record, '', ''])
        value = io.StringIO(); csv.writer(value).writerows(rows); files[record] = value.getvalue().encode()
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, value in files.items(): archive.writestr(name, value)
        metadata = files[record.rsplit('/', 1)[0] + '/METADATA']
        pin.update(size_bytes=wheel.stat().st_size, sha256=r.digest_file(wheel)['sha256'],
            wheel_core_metadata_size_bytes=len(metadata), wheel_core_metadata_sha256=hashlib.sha256(metadata).hexdigest())
        package = pin['name']
        self.fixture.synthetic_pins[package] = dict(pin)
        self.fixture.synthetic_expected[(package, 'wheel')] = {'bytes': pin['size_bytes'], 'sha256': pin['sha256']}
        self.fixture.synthetic_expected[(package, 'metadata')] = {'bytes': len(metadata), 'sha256': hashlib.sha256(metadata).hexdigest()}

    def inspected(self, variant='license', dictionary=False):
        wheel, pin = self.fixture.wheel(variant, dictionary=dictionary)
        trace = self.fixture.trace()
        report = d.inspect_wheels([wheel], [pin], trace)['wheels'][0]
        return wheel, pin, report, trace

    def test_observed_no_legacy_notice_shape_requires_pinned_external_license(self):
        # This models only the observed absence of legacy notice basenames.
        # It is not a reconstruction of the unavailable complete wheel listing.
        wheel, pin = self.fixture.wheel('license')
        with self.assertRaises(RuntimeError): r.base.inspect_wheels([wheel], [pin])
        trace = self.fixture.trace()
        report = d.inspect_wheels([wheel], [pin], trace)['wheels'][0]
        self.assertEqual(report['notices'], [])
        self.assertEqual(report['license_evidence']['supplied'], {})
        self.assertEqual(report['license_evidence']['external'][0]['id'], 'sudachipy_0_6_11_license')
        self.assertEqual(report['license_evidence']['external'][0]['commit'], lp.PACKAGE_PROVENANCE['SudachiPy']['commit'])
        self.assertTrue(any(event['step'] == 'license_provenance' and event['status'] == 'passed' for event in trace.document['events']))

    def test_real_public_artifact_identity_rejects_every_wrong_tuple_field(self):
        original_pin = self.fixture.real_package_pin('SudachiPy')
        metadata = email.parser.BytesParser().parsebytes(b'License: Apache-2.0\n\n')
        with patch.object(lp, 'package_pin', side_effect=self.fixture.real_package_pin):
            self.assertEqual(lp.inspect(original_pin, metadata, {}, 'fake.dist-info')['supplied'], {})
            for key, wrong in (('name', 'other'), ('version', '0.6.10'), ('filename', 'different.whl'),
                    ('sha256', '0' * 64), ('size_bytes', 1), ('wheel_core_metadata_sha256', '0' * 64),
                    ('wheel_core_metadata_size_bytes', 1)):
                with self.subTest(key=key):
                    value = dict(original_pin); value[key] = wrong
                    with self.assertRaises(lp.LicenseRejected): lp.inspect(value, metadata, {}, 'fake.dist-info')

    def test_missing_declared_notice_and_unsafe_declaration_rejected(self):
        for header in ('License: Apache-2.0\nLicense-File: missing.txt\n',
                       'License: Apache-2.0\nLicense-File: ../unsafe\n'):
            wheel, pin = self.fixture.wheel('license')
            self.rewrite(wheel, pin, {'sudachipy-0.6.11.dist-info/METADATA':
                ('Name: SudachiPy\nVersion: 0.6.11\n' + header + '\n').encode()})
            trace = self.fixture.trace()
            self.fixture.assert_failure(trace, 'license_notices', lambda: d.inspect_wheels([wheel], [pin], trace), 'rejected')

    def test_verified_metadata_identity_does_not_assume_license_header_presentation(self):
        for header in ('License: Apache Software License\n', 'License-Expression: Apache-2.0\n', ''):
            wheel, pin = self.fixture.wheel('license')
            self.rewrite(wheel, pin, {'sudachipy-0.6.11.dist-info/METADATA':
                ('Name: SudachiPy\nVersion: 0.6.11\n' + header + '\n').encode()})
            trace = self.fixture.trace()
            # Synthetic expected metadata bytes are explicitly substituted;
            # production still requires the original exact public metadata pin.
            report = d.inspect_wheels([wheel], [pin], trace)
            self.assertEqual(report['wheels'][0]['license_evidence']['external'][0]['id'], 'sudachipy_0_6_11_license')

    def test_missing_tampered_symlink_source_notice_never_uses_absence_exception(self):
        for source in lp.SOURCES:
            for variant in ('missing', 'tampered', 'symlink'):
                with self.subTest(source=source['id'], variant=variant):
                    root = self.sources_copy(); target = root / source['file']
                    if variant == 'missing': target.unlink()
                    if variant == 'tampered': target.write_bytes(b'x' * source['bytes'])
                    if variant == 'symlink': target.unlink(); target.symlink_to(r.BASELINE / source['file'])
                    with self.assertRaises(lp.LicenseRejected): lp.checked_sources(root)

    def test_source_version_commit_tag_and_blob_provenance_cannot_be_relabelled(self):
        # Apache text can be identical between releases: version/commit binding
        # must fail even while all original notice bytes and SHA-256 values remain.
        for key, wrong in (('version', '0.6.10'), ('commit', '0' * 40),
                            ('git_blob', '0' * 40), ('url', lp.SOURCES[0]['url'].replace('v0.6.11', 'v0.6.10'))):
            changed = copy.deepcopy(lp.SOURCES)
            changed[0][key] = wrong
            with self.subTest(key=key), patch.object(lp, 'SOURCES', changed):
                with self.assertRaises(lp.LicenseRejected): lp.checked_sources()
        root = self.sources_copy()
        pins = r.read_json(root / 'PYPI_PINS.json')
        pins['license_sources'][0]['url'] = pins['license_sources'][0]['url'].replace('v0.6.11', 'v0.6.10')
        r.write_json(root / 'PYPI_PINS.json', pins)
        with self.assertRaises(lp.LicenseRejected): lp.checked_sources(root)

    def test_every_supplied_and_declared_notice_is_retained_even_with_nonstandard_name(self):
        wheel, pin = self.fixture.wheel('license')
        prefix = 'sudachipy-0.6.11.dist-info/'
        metadata = b'Name: SudachiPy\nVersion: 0.6.11\nLicense: Apache-2.0\nLicense-File: attribution.txt\n\n'
        additions = {prefix + 'METADATA': metadata, prefix + 'COPYING.extra': b'copying text',
            prefix + 'licenses/attribution.txt': b'declared attribution', 'pkg/attribution.txt': b'package-root attribution',
            prefix + 'licenses/Apache-2.0.txt': b'alternate basename in license directory',
            'pkg/NOTICE.vendor': b'vendor notice'}
        self.rewrite(wheel, pin, additions)
        trace = self.fixture.trace()
        report = d.inspect_wheels([wheel], [pin], trace)['wheels'][0]
        self.assertEqual(set(report['notices']), set(additions) - {prefix + 'METADATA'})
        self.assertEqual(set(report['license_evidence']['supplied']), set(report['notices']))

    def test_dictionary_license_presence_requirement_remains(self):
        wheel, pin = self.fixture.wheel(dictionary=True)
        self.rewrite(wheel, pin, removals=('sudachidict_core-20260723.dist-info/LICENSE-2.0.txt',))
        trace = self.fixture.trace()
        with patch.object(r.base, 'DICT_SIZE', len(fixtures.FAKE_DICT)), \
             patch.object(r.base, 'DICT_SHA', hashlib.sha256(fixtures.FAKE_DICT).hexdigest()):
            self.fixture.assert_failure(trace, 'license_notices', lambda: d.inspect_wheels([wheel], [pin], trace), 'rejected')

    def bundle_fixture(self, newline_variation=False):
        engine, a = self.fixture.wheel('license')
        dictionary, b = self.fixture.wheel(dictionary=True)
        additions = {'sudachidict_core/LEGAL': (r.BASELINE / lp.SOURCES[2]['file']).read_bytes()}
        if newline_variation:
            additions['sudachidict_core-20260723.dist-info/LICENSE-2.0.txt'] = (r.BASELINE / lp.SOURCES[1]['file']).read_bytes().replace(b'\n', b'\r\n')
        self.rewrite(dictionary, b, additions)
        self.fixture.synthetic_expected[('SudachiDict-core', 'dictionary')] = d.digest_bytes(fixtures.FAKE_DICT)
        trace = self.fixture.trace()
        with patch.object(r.base, 'DICT_SIZE', len(fixtures.FAKE_DICT)), \
             patch.object(r.base, 'DICT_SHA', hashlib.sha256(fixtures.FAKE_DICT).hexdigest()):
            report = d.inspect_wheels([engine, dictionary], [a, b], trace)['wheels']
        run = trace.path.parent
        bundle = lp.retain_bundle(run, [engine, dictionary], report)
        for row, wheel in zip(report, (engine, dictionary), strict=True):
            with zipfile.ZipFile(wheel) as archive:
                for name in row['license_evidence']['supplied']:
                    path = r.base.site_path(run) / name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(name))
        return run, report, bundle

    def test_packaged_newline_variation_preserves_distinct_upstream_and_wheel_bytes(self):
        run, report, bundle = self.bundle_fixture(newline_variation=True)
        lp.verify_retention(run, report, bundle)
        relative = 'sudachidict_core-20260723.dist-info/LICENSE-2.0.txt'
        upstream = (run / 'notice-bundle/upstream/sudachidict_20260723_license.txt').read_bytes()
        supplied = (run / ('notice-bundle/wheel/1/' + relative)).read_bytes()
        self.assertNotEqual(upstream, supplied)
        self.assertEqual(supplied, upstream.replace(b'\n', b'\r\n'))
        self.assertEqual((r.base.site_path(run) / relative).read_bytes(), supplied)

    def test_bundle_preserves_full_source_and_supplied_notice_bytes_exclusively(self):
        run, report, bundle = self.bundle_fixture()
        value = lp.verify_retention(run, report, bundle)
        self.assertEqual(value['external_files'], 3)
        self.assertEqual(value['supplied_files'], 2)
        self.assertEqual(lp.public_retention(value), value)
        self.assertEqual((run / 'notice-bundle/upstream/sudachidict_20260723_legal.txt').read_bytes(),
                         (r.BASELINE / lp.SOURCES[2]['file']).read_bytes())
        with self.assertRaises(FileExistsError): lp.retain_bundle(run, [None, None], report)
        self.assertFalse(any(source['file'] in json.dumps(value) for source in lp.SOURCES))

    def test_bundle_and_installed_notice_deletion_tampering_or_extra_file_are_rejected(self):
        for variant in ('bundle_missing', 'bundle_tampered', 'bundle_extra', 'installed_missing', 'installed_tampered'):
            run, report, bundle = self.bundle_fixture()
            target = run / 'notice-bundle/upstream/sudachipy_0_6_11_license.txt'
            if variant.startswith('installed'):
                target = r.base.site_path(run) / next(iter(report[1]['license_evidence']['supplied']))
            if variant.endswith('missing'): target.unlink()
            if variant.endswith('tampered'): target.write_bytes(b'wrong')
            if variant == 'bundle_extra': (run / 'notice-bundle/unreviewed.txt').write_text('extra')
            with self.subTest(variant=variant), self.assertRaises((lp.LicenseRejected, FileNotFoundError)):
                lp.verify_retention(run, report, bundle)

    def test_new_setup_boundaries_are_fixed_and_stop_on_failure(self):
        for target, step in (('bundle', 'notice_bundle'), ('retention', 'notice_retention')):
            trace = self.fixture.trace()
            with self.fixture.fake_setup(trace) as mocks:
                mocks[target].side_effect = OSError(fixtures.SECRET)
                self.fixture.assert_failure(trace, step, lambda: r.setup_offline('a' * 64, trace), 'operation_failed')
        wheel, pin = self.fixture.wheel('license'); trace = self.fixture.trace()
        with patch.object(lp, 'checked_sources', side_effect=lp.LicenseRejected('fixed')):
            self.fixture.assert_failure(trace, 'license_provenance', lambda: d.inspect_wheels([wheel], [pin], trace), 'rejected')

    def test_public_notice_receipt_rejects_paths_text_and_misleading_counts(self):
        run, report, bundle = self.bundle_fixture()
        original = lp.verify_retention(run, report, bundle)
        for field, value in (('extra', fixtures.SECRET), ('external_files', 0), ('supplied_files', 65),
                             ('retained_bytes', 1), ('policy', 'arbitrary'), ('bundle_manifest', {'path': fixtures.SECRET})):
            changed = dict(original); changed[field] = value
            with self.subTest(field=field), self.assertRaises(lp.LicenseRejected): lp.public_retention(changed)

    def test_full_success_summary_with_maximum_diagnostics_and_notice_receipt_stays_bounded(self):
        for process in d.PROCESSES:
            trace = d.Trace(self.tmp, process)
            trace.document['events'] = [{'step': 'archive_startup_hooks', 'package': 'SudachiDict-core',
                'status': 'operation_failed', 'seconds': 59.999999} for _ in range(d.EVENT_LIMITS[process])]
            if process == 'setup':
                for package in d.PACKAGES:
                    for slot in d.SLOTS:
                        if package == 'SudachiPy' and slot == 'dictionary': continue
                        expected = self.fixture.real_public_expected(package, slot)
                        trace.document['comparisons'].append({'package': package, 'slot': slot, 'expected': expected,
                            'observed': expected, 'matched': True})
            trace.write()
        batch = r.base.batch_sources()
        parsed = {'complete': True, 'parser_calls': 48, 'records': [{'id': row['id'], 'tokens': []} for row in batch],
            'cold_initialization_seconds': 0.1, 'peak_rss_kib': 100, 'cpu_seconds': 0.1, 'elapsed_before_output_seconds': 0.2}
        decisions = [{'id': row['id'], 'admitted': [], 'occurrences': [], 'match': True} for row in batch]
        retained = {'policy': lp.POLICY_ID, 'bundle_manifest': {'bytes': 99999, 'sha256': 'a' * 64},
            'external_files': 3, 'supplied_files': 64, 'retained_bytes': 2 * lp.MAX_NOTICE_BYTES + sum(row['bytes'] for row in lp.SOURCES)}
        for name, value in [('parser.json', parsed), ('assessment.json', {'lexical_gate_passed': True,
                'diagnostics': decisions[:16], 'seen_regressions': decisions[16:]}), ('installed.json', {}),
                ('notice-retention.json', retained)]:
            r.write_json(self.tmp / name, value)
        life = {'exit_code': 0, 'elapsed_seconds': 0.2, 'deadline_seconds': 60, 'timed_out': False, 'cleanup_confirmed': True}
        state = {'state': 'complete', 'binding': {}, 'host': {}, 'phases': {'setup': {'lifecycle': life}, 'parse': {'lifecycle': life}}}
        with patch.object(r, 'work', return_value=self.tmp), patch.object(r, 'validate_completed'):
            data = r.sanitized_summary(state)
        self.assertLessEqual(len(data.encode()), 32768)
        self.assertEqual(json.loads(data)['notice_retention'], retained)
        self.assertEqual(len(json.loads(data)['cases']), 48)
        self.assertNotIn('invalid_receipt', data)


if __name__ == '__main__':
    unittest.main()
