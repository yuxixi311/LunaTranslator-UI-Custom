"""Package-specific, byte-pinned notice provenance and retention.

This supplements upstream distribution files. It does not certify legal
compliance or completeness of licenses for every transitive native dependency.
No network, installation, package import, or extraction occurs on import.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

import pilot_runner as base

SCHEMA = 1
POLICY_ID = 'luna-pinned-notice-policy-v3'
PACKAGES = ('SudachiPy', 'SudachiDict-core')
NOTICE_PREFIXES = ('LICENSE', 'LEGAL', 'NOTICE', 'COPYING', 'COPYRIGHT', 'AUTHORS')
NOTICE_DIRECTORIES = frozenset(('LICENSE', 'LICENSES', 'LEGAL', 'NOTICE', 'NOTICES', 'COPYING', 'COPYRIGHT', 'COPYRIGHTS'))
MAX_NOTICE_FILES = 32
MAX_NOTICE_BYTES = base.MIB
PACKAGE_PROVENANCE = {
    'SudachiPy': {'version': '0.6.11', 'tag': 'v0.6.11',
        'commit': '90fd6068c80c2fc3b63e0dbab0e341475bad4d8f',
        'repository': 'WorksApplications/sudachi.rs',
        'source_ids': ('sudachipy_0_6_11_license',)},
    'SudachiDict-core': {'version': '20260723', 'tag': 'v20260723',
        'commit': '4813c1cddda74f98a416f92b26d961424ecf8767',
        'repository': 'WorksApplications/SudachiDict',
        'source_ids': ('sudachidict_20260723_license', 'sudachidict_20260723_legal')},
}
SOURCES = (
    {'id': 'sudachipy_0_6_11_license', 'package': 'SudachiPy', 'version': '0.6.11',
     'commit': '90fd6068c80c2fc3b63e0dbab0e341475bad4d8f', 'upstream_file': 'LICENSE',
     'git_blob': '261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64',
     'file': 'license_sources/SudachiPy-0.6.11-LICENSE',
     'url': 'https://raw.githubusercontent.com/WorksApplications/sudachi.rs/v0.6.11/LICENSE',
     'bytes': 11357, 'sha256': 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'},
    {'id': 'sudachidict_20260723_license', 'package': 'SudachiDict-core', 'version': '20260723',
     'commit': '4813c1cddda74f98a416f92b26d961424ecf8767', 'upstream_file': 'LICENSE-2.0.txt',
     'git_blob': 'd645695673349e3947e8e5ae42332d0ac3164cd7',
     'file': 'license_sources/SudachiDict-20260723-LICENSE-2.0.txt',
     'url': 'https://raw.githubusercontent.com/WorksApplications/SudachiDict/v20260723/LICENSE-2.0.txt',
     'bytes': 11358, 'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'},
    {'id': 'sudachidict_20260723_legal', 'package': 'SudachiDict-core', 'version': '20260723',
     'commit': '4813c1cddda74f98a416f92b26d961424ecf8767', 'upstream_file': 'LEGAL',
     'git_blob': 'a406b9d21f88788dbbba19c213e2e7c63ebd65db',
     'file': 'license_sources/SudachiDict-20260723-LEGAL',
     'url': 'https://raw.githubusercontent.com/WorksApplications/SudachiDict/v20260723/LEGAL',
     'bytes': 6037, 'sha256': '725a8776b38e058b185e905594bc9a2437dbf3787df022fffeefedb9a84e4665'},
)


class LicenseRejected(RuntimeError):
    pass


def require(value):
    if not value:
        raise LicenseRejected('fixed notice-policy rejection')


def pin_digest(value):
    return {key: value[key] for key in ('bytes', 'sha256')}


def package_pin(package):
    require(package in PACKAGES)
    return next(value for value in base.package_pins() if value['name'] == package)


def checked_sources(root=base.ROOT):
    """All three reviewed, versioned source notices are mandatory on every setup."""
    published = base.read_json(Path(root) / 'PYPI_PINS.json')
    require(len(published['license_sources']) == len(SOURCES))
    for expected, supplied in zip(SOURCES, published['license_sources'], strict=True):
        provenance = PACKAGE_PROVENANCE[expected['package']]
        require(expected['version'] == provenance['version'] and expected['commit'] == provenance['commit']
                and expected['id'] in provenance['source_ids'])
        require(expected['url'] == 'https://raw.githubusercontent.com/' + provenance['repository']
                + '/' + provenance['tag'] + '/' + expected['upstream_file'])
        require(supplied['url'] == expected['url'] and supplied['size_bytes'] == expected['bytes']
                and supplied['sha256'] == expected['sha256'])
        target = Path(root) / expected['file']
        require(target.resolve() == target and target.is_file() and not target.is_symlink())
        require(target.stat().st_size == expected['bytes'])
        with target.open('rb') as stream:
            payload = stream.read(expected['bytes'] + 1)
        require({'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()} == pin_digest(expected))
        require(hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest() == expected['git_blob'])
    return [{'id': row['id'], 'package': row['package'], 'version': row['version'],
             'commit': row['commit'], 'git_blob': row['git_blob'], **pin_digest(row)} for row in SOURCES]


def safe_member(name):
    return (isinstance(name, str) and name and not name.startswith('/') and '\\' not in name and ':' not in name
            and all(part not in ('', '.', '..') for part in name.split('/')))


def inspect(pin, metadata, hashes, prefix, root=base.ROOT):
    """Return the complete supplied notice set, under the exact package policy.

    Caller has already verified every wheel member and the pinned core metadata.
    This function never uses absence of generic filenames as a license proof.
    """
    package = pin['name']
    expected = package_pin(package)
    keys = ('name', 'version', 'filename', 'sha256', 'size_bytes', 'wheel_core_metadata_sha256', 'wheel_core_metadata_size_bytes')
    require(all(pin[key] == expected[key] for key in keys))
    require(pin['version'] == PACKAGE_PROVENANCE[package]['version'])
    # The caller verifies the exact immutable metadata digest. Public pins carry
    # a declared license, but no raw-header observation authorizes imposing a
    # particular License/License-Expression representation here.
    declared = metadata.get_all('License-File', [])
    require(len(declared) <= MAX_NOTICE_FILES and all(safe_member(value) for value in declared))
    sources = checked_sources(root)
    require(any(row['package'] == package and row['version'] == pin['version'] for row in sources))
    notices = {name for name in hashes if PurePosixPath(name).name.upper().startswith(NOTICE_PREFIXES)
               or any(part.upper() in NOTICE_DIRECTORIES for part in PurePosixPath(name).parts[:-1])}
    for value in declared:
        # Only actual RECORD-verified members can satisfy a declared wheel file.
        # Search actual members; do not assume a package-root versus dist-info
        # license layout. Preserve every supplied match, including duplicates.
        matches = {name for name in hashes if name == value or name.endswith('/' + value)}
        require(matches)
        notices.update(matches)
    require(len(notices) <= MAX_NOTICE_FILES and sum(hashes[name]['bytes'] for name in notices) <= MAX_NOTICE_BYTES)
    if package == 'SudachiPy':
        # Exact 0.6.11 wheel and metadata identity are mandatory above. Its
        # observed missing packaged notice is supplied by the pinned source
        # LICENSE, never by accepting an arbitrary empty notice set.
        require([row['id'] for row in sources if row['package'] == package]
                == list(PACKAGE_PROVENANCE[package]['source_ids']))
    else:
        # Preserve the prior dictionary LICENSE-2.0.txt presence requirement.
        # Packaged and upstream texts are distinct authenticated byte streams;
        # packaging may legitimately change newlines. Never invent equality.
        required = [name for name in notices if PurePosixPath(name).name == 'LICENSE-2.0.txt']
        require(required)
    return {'package': package, 'version': pin['version'],
            'supplied': {name: hashes[name] for name in sorted(notices)},
            'external': [row for row in sources if row['package'] == package]}


def write_bytes_exclusive(path, payload, expected):
    require(len(payload) <= MAX_NOTICE_BYTES)
    require({'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()} == expected)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(path.resolve() == path and not path.is_symlink())
    with path.open('xb') as stream:
        stream.write(payload)
    require(base.digest_file(path) == expected)


def retain_bundle(run, wheels, reports, root=base.ROOT):
    """After all archives pass, retain every reviewed/supplied notice unchanged."""
    require(len(wheels) == len(reports) == 2)
    sources = checked_sources(root)
    bundle = Path(run) / 'notice-bundle'
    bundle.mkdir(mode=0o700)  # Exclusive; never reset or overwrite an earlier bundle.
    entries = {}
    for source in SOURCES:
        relative = 'upstream/' + source['id'] + '.txt'
        source_path = Path(root) / source['file']
        with source_path.open('rb') as stream:
            payload = stream.read(MAX_NOTICE_BYTES + 1)
        write_bytes_exclusive(bundle / relative, payload, pin_digest(source))
        entries[relative] = pin_digest(source)
    for index, (wheel, report) in enumerate(zip(wheels, reports, strict=True)):
        notice = report['license_evidence']
        require(notice['package'] == PACKAGES[index])
        with zipfile.ZipFile(wheel) as archive:
            for name, expected in notice['supplied'].items():
                require(safe_member(name))
                relative = 'wheel/' + str(index) + '/' + name
                with archive.open(name) as stream:
                    payload = stream.read(MAX_NOTICE_BYTES + 1)
                write_bytes_exclusive(bundle / relative, payload, expected)
                entries[relative] = expected
    require(len(entries) <= len(SOURCES) + 2 * MAX_NOTICE_FILES)
    require(sum(value['bytes'] for value in entries.values()) <= 2 * MAX_NOTICE_BYTES + sum(v['bytes'] for v in SOURCES))
    manifest = {'schema': SCHEMA, 'policy': POLICY_ID, 'files': entries, 'sources': sources}
    base.write_json(bundle / 'MANIFEST.json', manifest, exclusive=True)
    return manifest


def verify_retention(run, archives, bundle):
    """Require installed supplied notices and the external bundle to survive."""
    root = Path(run) / 'notice-bundle'
    require(base.read_json(root / 'MANIFEST.json') == bundle)
    actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
    require(actual == set(bundle['files']) | {'MANIFEST.json'})
    for relative, expected in bundle['files'].items():
        require(safe_member(relative))
        target = root / relative
        require(target.resolve() == target and not target.is_symlink())
        require(base.digest_file(target) == expected)
    for report in archives:
        for name, expected in report['license_evidence']['supplied'].items():
            require(safe_member(name))
            target = base.site_path(run) / name
            require(target.resolve() == target and target.is_file() and not target.is_symlink())
            require(base.digest_file(target) == expected)
    return {'policy': POLICY_ID, 'bundle_manifest': base.digest_file(root / 'MANIFEST.json'),
            'external_files': len(SOURCES),
            'supplied_files': sum(len(row['license_evidence']['supplied']) for row in archives),
            'retained_bytes': sum(value['bytes'] for value in bundle['files'].values())}


def public_retention(value):
    """Validate the fixed-size public receipt; no filenames or text are forwarded."""
    require(isinstance(value, dict) and set(value) == {'policy', 'bundle_manifest', 'external_files', 'supplied_files', 'retained_bytes'})
    require(value['policy'] == POLICY_ID and value['external_files'] == len(SOURCES))
    require(type(value['supplied_files']) is int and 0 <= value['supplied_files'] <= 2 * MAX_NOTICE_FILES)
    require(type(value['retained_bytes']) is int and sum(row['bytes'] for row in SOURCES) <= value['retained_bytes']
            <= 2 * MAX_NOTICE_BYTES + sum(row['bytes'] for row in SOURCES))
    digest = value['bundle_manifest']
    require(isinstance(digest, dict) and set(digest) == {'bytes', 'sha256'} and type(digest['bytes']) is int
            and 0 <= digest['bytes'] <= 4 * base.MIB and isinstance(digest['sha256'], str)
            and len(digest['sha256']) == 64 and all(ch in '0123456789abcdef' for ch in digest['sha256']))
    return value
