"""Finite setup diagnostics. No exception text, local names, or arbitrary values.

The archived validators remain unchanged. Only the filename-based license gate
is replaced by the reviewed exact-package provenance and notice-retention policy.
"""
import base64
import contextlib
import csv
import email.parser
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import zipfile

import pilot_runner as base
import license_policy as licensing

SCHEMA = 1
PROCESSES = ('preflight', 'setup', '_ensurepip', '_install')
PACKAGES = ('SudachiPy', 'SudachiDict-core')
STEPS = frozenset('''parent_identity offline_audit resource_limits preflight_resources control_lock exclusive_claim source_inventory
host_runtime runtime_cache event_binding claim_read claim_identity process_group
prior_receipts package_pins wheel_paths archive_digest archive_open archive_inventory
archive_member_paths archive_member_types archive_startup_hooks archive_payload
record_location record_size record_decode record_inventory record_self record_format
record_members metadata_read metadata_digest metadata_parse metadata_identity
metadata_dependencies wheel_tags license_provenance license_notices notice_bundle notice_retention dictionary_identity dictionary_license
venv_module venv_create installer_environment ensurepip_child install_child
venv_isolation venv_interpreter snapshot_dictionary snapshot_inventory snapshot_payload
snapshot_write setup_host source_notices setup_write phase_receipt
ensurepip_venv ensurepip_module ensurepip_hook ensurepip_bootstrap ensurepip_pip_child
install_venv install_pins install_arguments install_module install_exit'''.split())
STATUSES = ('started', 'passed', 'rejected', 'operation_failed')
SLOTS = ('wheel', 'metadata', 'dependencies', 'tags', 'dictionary')
EVENT_LIMITS = {'preflight': 9, 'setup': 80, '_ensurepip': 18, '_install': 18}
BYTE_LIMITS = {'preflight': 4096, 'setup': 24576, '_ensurepip': 8192, '_install': 8192}
MAX_BYTES = 512 * base.MIB


class Rejected(RuntimeError):
    """No caller-supplied information is carried by this exception."""


def require(value):
    if not value:
        raise Rejected('fixed diagnostic rejection')


def digest_bytes(value):
    return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}


def digest_values(value):
    return digest_bytes(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode())


def valid_digest(value):
    return (isinstance(value, dict) and set(value) == {'bytes', 'sha256'}
            and type(value['bytes']) is int and 0 <= value['bytes'] <= MAX_BYTES
            and isinstance(value['sha256'], str) and re.fullmatch('[a-f0-9]{64}', value['sha256']))


def public_expected(package, slot):
    """Only pinned public dependencies can be a source of comparison evidence."""
    require(package in PACKAGES and slot in SLOTS)
    require(slot != 'dictionary' or package == 'SudachiDict-core')
    pin = next(value for value in base.package_pins() if value['name'] == package)
    if slot == 'wheel':
        return {'bytes': pin['size_bytes'], 'sha256': pin['sha256']}
    if slot == 'metadata':
        return {'bytes': pin['wheel_core_metadata_size_bytes'], 'sha256': pin['wheel_core_metadata_sha256']}
    if slot == 'dependencies':
        return digest_values(pin['requires_dist'])
    if slot == 'tags':
        tags = ['cp312-cp312-manylinux2014_x86_64', 'cp312-cp312-manylinux_2_17_x86_64'] if package == 'SudachiPy' else ['py3-none-any']
        return digest_values(sorted(tags))
    return {'bytes': base.DICT_SIZE, 'sha256': base.DICT_SHA}


def validate(document, process):
    require(process in PROCESSES and isinstance(document, dict)
            and set(document) == {'schema', 'process', 'events', 'comparisons'}
            and type(document['schema']) is int and document['schema'] == SCHEMA and document['process'] == process)
    events, comparisons = document['events'], document['comparisons']
    require(isinstance(events, list) and len(events) <= EVENT_LIMITS[process])
    for event in events:
        require(isinstance(event, dict) and set(event) == {'step', 'package', 'status', 'seconds'}
                and event['step'] in STEPS and event['package'] in (None, *PACKAGES)
                and event['status'] in STATUSES and type(event['seconds']) in (float, int)
                and math.isfinite(event['seconds']) and 0 <= event['seconds'] <= 60)
    require(isinstance(comparisons, list) and len(comparisons) <= (9 if process == 'setup' else 0))
    require(len({(v['package'], v['slot']) for v in comparisons}) == len(comparisons))
    for value in comparisons:
        require(isinstance(value, dict) and set(value) == {'package', 'slot', 'expected', 'observed', 'matched'}
                and value['package'] in PACKAGES and value['slot'] in SLOTS
                and (value['slot'] != 'dictionary' or value['package'] == 'SudachiDict-core')
                and valid_digest(value['expected']) and valid_digest(value['observed'])
                and value['expected'] == public_expected(value['package'], value['slot'])
                and type(value['matched']) is bool and value['matched'] == (value['expected'] == value['observed']))
    require(len(json.dumps(document, allow_nan=False, indent=2).encode()) <= BYTE_LIMITS[process])
    return document


class Trace:
    def __init__(self, run, process):
        require(process in PROCESSES)
        self.path = Path(run) / (process.lstrip('_') + '.diagnostic.json')
        self.document = {'schema': SCHEMA, 'process': process, 'events': [], 'comparisons': []}
        # Exclusive identity: a second writer cannot reset an earlier receipt.
        self.write(exclusive=True)

    def write(self, exclusive=False):
        validate(self.document, self.document['process'])
        if exclusive:
            base.write_json(self.path, self.document, exclusive=True)
        else:
            temporary = self.path.with_suffix('.next')
            base.write_json(temporary, self.document, exclusive=True)
            os.replace(temporary, self.path)

    @contextlib.contextmanager
    def step(self, step, package=None):
        require(step in STEPS and package in (None, *PACKAGES))
        event = {'step': step, 'package': package, 'status': 'started', 'seconds': 0.0}
        self.document['events'].append(event)
        self.write()
        started = time.monotonic()
        try:
            yield
        except BaseException as exc:
            event['status'] = 'rejected' if isinstance(exc, (Rejected, licensing.LicenseRejected)) else 'operation_failed'
            raise
        else:
            event['status'] = 'passed'
        finally:
            # The enclosing owned 60s lifecycle remains the authority for timeout.
            event['seconds'] = min(60.0, max(0.0, round(time.monotonic() - started, 6)))
            self.write()

    def call(self, step, function, *args, **kwargs):
        with self.step(step):
            return function(*args, **kwargs)

    def compare(self, package, slot, expected, observed):
        require(package in PACKAGES and slot in SLOTS and valid_digest(expected) and valid_digest(observed))
        self.document['comparisons'].append({'package': package, 'slot': slot,
            'expected': expected, 'observed': observed, 'matched': expected == observed})
        self.write()


def collect(run):
    """Re-validate every byte before public output, including a failed child."""
    result = {}
    for process in PROCESSES:
        path = Path(run) / (process.lstrip('_') + '.diagnostic.json')
        if not path.exists():
            result[process] = {'status': 'not_recorded'}
            continue
        try:
            require(not path.is_symlink() and path.stat().st_size <= BYTE_LIMITS[process])
            with path.open('rb') as stream:
                payload = stream.read(BYTE_LIMITS[process] + 1)
            require(len(payload) <= BYTE_LIMITS[process])
            result[process] = validate(json.loads(payload.decode('utf-8')), process)
        except BaseException:
            result[process] = {'status': 'invalid_receipt'}
    return result


def inspect_wheels(wheels, pins, trace):
    """Unchanged integrity checks plus package-specific notice provenance."""
    total, reports = 0, []
    for wheel, pin in zip(wheels, pins, strict=True):
        package = pin['name']
        with trace.step('archive_digest', package):
            require(Path(wheel).is_file() and not Path(wheel).is_symlink())
            expected = {'bytes': pin['size_bytes'], 'sha256': pin['sha256']}
            observed = base.digest_file(wheel)
            trace.compare(package, 'wheel', expected, observed)
            require(observed == expected)
        with trace.step('archive_open', package):
            archive = zipfile.ZipFile(wheel)
        with archive:
            with trace.step('archive_inventory', package):
                members = archive.infolist()
                names = [m.filename for m in members]
                require(len(names) == len(set(names)))
            with trace.step('archive_member_paths', package):
                for member in members:
                    name = member.filename
                    require(name and not name.startswith('/') and '\\' not in name and ':' not in name
                            and all(p not in ('', '.', '..') for p in name.rstrip('/').split('/'))
                            and not member.flag_bits & 1)
            with trace.step('archive_member_types', package):
                require(all(stat.S_IFMT(m.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR) for m in members))
            with trace.step('archive_startup_hooks', package):
                require(all(not n.endswith(('.pth', '.egg-link'))
                            and not any(p.endswith('.data') for p in PurePosixPath(n).parts) for n in names))
            with trace.step('archive_payload', package):
                total += sum(m.file_size for m in members)
                require(total <= 512 * base.MIB)
            with trace.step('record_location', package):
                files = {m.filename for m in members if not m.is_dir()}
                paths = [n for n in files if n.endswith('.dist-info/RECORD')]
                require(len(paths) == 1)
                record_name = paths[0]
            with trace.step('record_size', package):
                require(archive.getinfo(record_name).file_size <= base.MIB)
            with trace.step('record_decode', package):
                rows = list(csv.reader(io.StringIO(archive.read(record_name).decode('utf-8'))))
            with trace.step('record_inventory', package):
                require(all(len(r) == 3 for r in rows) and len(rows) == len({r[0] for r in rows})
                        and {r[0] for r in rows} == files)
            with trace.step('record_self', package):
                require(all(encoded == length == '' for name, encoded, length in rows if name == record_name))
            with trace.step('record_format', package):
                require(all(encoded.startswith('sha256=') and length.isdecimal()
                            for name, encoded, length in rows if name != record_name))
            with trace.step('record_members', package):
                hashes = {}
                for name, encoded, length in rows:
                    if name == record_name:
                        continue
                    h, size = hashlib.sha256(), 0
                    with archive.open(name) as stream:
                        for block in iter(lambda: stream.read(base.MIB), b''):
                            size += len(block)
                            require(size <= archive.getinfo(name).file_size)
                            h.update(block)
                    actual = base64.urlsafe_b64encode(h.digest()).decode().rstrip('=')
                    require(str(size) == length and actual == encoded[7:])
                    hashes[name] = {'bytes': size, 'sha256': h.hexdigest()}
            prefix = record_name.rsplit('/', 1)[0]
            with trace.step('metadata_read', package):
                metadata = archive.read(prefix + '/METADATA')
            with trace.step('metadata_digest', package):
                expected = {'bytes': pin['wheel_core_metadata_size_bytes'], 'sha256': pin['wheel_core_metadata_sha256']}
                observed = digest_bytes(metadata)
                trace.compare(package, 'metadata', expected, observed)
                require(expected == observed)
            with trace.step('metadata_parse', package):
                parsed = email.parser.BytesParser().parsebytes(metadata)
            with trace.step('metadata_identity', package):
                require(parsed['Name'].lower().replace('_', '-') == package.lower().replace('_', '-')
                        and parsed['Version'] == pin['version'])
            with trace.step('metadata_dependencies', package):
                actual = parsed.get_all('Requires-Dist', [])
                trace.compare(package, 'dependencies', digest_values(pin['requires_dist']), digest_values(actual))
                require(actual == pin['requires_dist'])
            with trace.step('wheel_tags', package):
                tags = email.parser.BytesParser().parsebytes(archive.read(prefix + '/WHEEL')).get_all('Tag', [])
                expected_tags = {'cp312-cp312-manylinux2014_x86_64', 'cp312-cp312-manylinux_2_17_x86_64'} if package == 'SudachiPy' else {'py3-none-any'}
                trace.compare(package, 'tags', digest_values(sorted(expected_tags)), digest_values(sorted(set(tags))))
                require(set(tags) == expected_tags)
            with trace.step('license_provenance', package):
                licensing.checked_sources()
            with trace.step('license_notices', package):
                license_evidence = licensing.inspect(pin, parsed, hashes, prefix)
                notices = list(license_evidence['supplied'])
            if package == 'SudachiDict-core':
                with trace.step('dictionary_identity', package):
                    observed = hashes.get('sudachidict_core/resources/system.dic')
                    expected = {'bytes': base.DICT_SIZE, 'sha256': base.DICT_SHA}
                    if observed is not None:
                        trace.compare(package, 'dictionary', expected, observed)
                    require(observed == expected)
                with trace.step('dictionary_license', package):
                    require(any(PurePosixPath(n).name == 'LICENSE-2.0.txt' for n in notices))
            reports.append({'wheel': wheel.name, 'members': len(files), 'notices': notices,
                            'uncompressed_bytes': sum(m.file_size for m in members), 'record_verified': True,
                            'license_evidence': license_evidence})
    return {'wheels': reports, 'total_uncompressed_bytes': total}


def installed_snapshot(run, trace):
    site = base.site_path(run)
    dictionary = site / 'sudachidict_core/resources/system.dic'
    with trace.step('snapshot_dictionary'):
        base.verify_file(dictionary, {'bytes': base.DICT_SIZE, 'sha256': base.DICT_SHA})
    with trace.step('snapshot_inventory'):
        entries = {}
        for path in sorted(site.rglob('*')):
            require(not path.is_symlink())
            if path.is_file():
                require(path.suffix not in ('.pth', '.egg-link'))
                entries[str(path.relative_to(site))] = base.digest_file(path)
    with trace.step('snapshot_payload'):
        total = sum(x['bytes'] for x in entries.values())
        require(total <= 512 * base.MIB)
        result = {'files': entries, 'total_installed_bytes': total, 'dictionary': base.digest_file(dictionary)}
    return result
