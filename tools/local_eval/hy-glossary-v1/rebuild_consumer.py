"""Rebuild the frozen Hy glossary consumer from public Git and existing local pins.

Read-only Git plumbing; no network, model, DLL, configuration or credential use.
Fetch the exact approved public project commit separately before this command.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PREFIX = 'tools/local_eval/hy-glossary-v1/consumer/'
BASE = 'luna-threeway-repair-zip-verification/'
OLD_MANIFEST_SHA = '7cde10016e9203a7619e6bb957b767f0f29e1078c5cfb583c5397f117d9fbc88'
HY_MANIFEST_SHA = 'b534c2cc8a6d1cfb714b86c8a8c660bdad995c1621453778e50e596983c51ad6'
CONSUMER_SHA = 'c8a9bd050103331e9cc4ba411a9e73b8b10bd4e393df345d77603ebacd803509'
PRIVATE_PINS = 'luna-hy-glossary-design/RUNTIME_PINS.private.json'
PRIVATE_SHA = 'fe89be67d740dbfaf22f870d77d63782ce283f9a91fbc3addd2d4c9f4b0ed649'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def safe_file(root, relative):
    path = root / relative
    need(not Path(relative).is_absolute() and '..' not in Path(relative).parts and '\\' not in relative, 'Unsafe relative path')
    need(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'Unsafe local source path')
    return path


def rebuild(old_kit, hy_evidence, destination, read_public):
    need(not destination.exists(), 'Use a new isolated output directory')
    old_raw = (old_kit / 'SOURCE_KIT_MANIFEST.json').read_bytes()
    need(digest(old_raw) == OLD_MANIFEST_SHA, 'Original3b kit manifest mismatch')
    old = json.loads(old_raw)
    need(len(old['files']) == 81, 'Original3b kit payload count mismatch')
    old_payloads = {'SOURCE_KIT_MANIFEST.json': old_raw}
    for name, expected in old['files'].items():
        data = safe_file(old_kit, name).read_bytes()
        need(digest(data) == expected, 'Original3b payload mismatch')
        old_payloads[name] = data
    # Only existing private metadata is needed; never read or publish its outputs.
    hy_raw = (hy_evidence / 'manifest.json').read_bytes()
    need(digest(hy_raw) == HY_MANIFEST_SHA, 'Pinned Hy evidence manifest mismatch')
    hy_manifest = json.loads(hy_raw)
    metadata_raw = safe_file(hy_evidence, 'metadata.json').read_bytes()
    need(digest(metadata_raw) == hy_manifest['metadata.json'], 'Hy metadata hash mismatch')
    metadata = json.loads(metadata_raw)
    pins = {key: metadata[key] for key in ('runtime_version', 'runtime_files_sha256', 'server_sha256', 'nvidia_smi_sha256')}
    pins['provenance'] = 'Previously verified Windows Hy run from frozen3b7 experiment'
    pins['source_metadata_sha256'] = digest(metadata_raw)
    private_raw = (json.dumps(pins, indent=2) + '\n').encode('utf-8')
    need(digest(private_raw) == PRIVATE_SHA, 'Reconstructed private runtime pins mismatch')
    manifest_raw = read_public('CONSUMER_MANIFEST.json')
    need(digest(manifest_raw) == CONSUMER_SHA, 'Frozen consumer manifest mismatch')
    manifest = json.loads(manifest_raw)
    need(len(manifest['files']) == 101, 'Consumer payload count mismatch')
    payloads = {}
    for name, expected in manifest['files'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name, 'Unsafe consumer path')
        need('criteria' not in name.lower(), 'Private criteria must not be delivered')
        if name.startswith(BASE):
            data = old_payloads[name[len(BASE):]]
        elif name == PRIVATE_PINS:
            data = private_raw
        else:
            data = read_public(name)
        need(digest(data) == expected, 'Consumer source/hash mismatch: ' + name)
        payloads[name] = data
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)  # Preserve LF and UTF-8 bytes on Windows.
        need(digest(path.read_bytes()) == manifest['files'][name], 'Written payload mismatch')
    (destination / 'CONSUMER_MANIFEST.json').write_bytes(manifest_raw)
    return {'verified_payloads': len(payloads), 'consumer_manifest_sha256': CONSUMER_SHA,
            'private_runtime_pins_reconstructed_locally': True, 'private_criteria_included': False,
            'weights_included': False, 'model_executed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('old-kit', 'hy-evidence', 'out', 'repo'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    need(re.fullmatch('[0-9a-f]{40}', args.commit) is not None, 'Exact full commit required')
    environment = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
                       GIT_ASKPASS='', SSH_ASKPASS='')
    prefix = ['git', '-c', 'credential.helper=', '-c', 'core.askPass=', '-C', str(args.repo)]
    def git(*command):
        return subprocess.run(prefix + list(command), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                              timeout=30, env=environment).stdout
    # Reject partial/promisor configuration even on Git versions that predate
    # GIT_NO_LAZY_FETCH. This builder consumes a separately approved full fetch.
    configured = subprocess.run(prefix + ['config', '--get-regexp',
                                r'^(extensions\.partialclone|remote\..*\.promisor)$'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, env=environment)
    need(configured.returncode in (0, 1) and not configured.stdout.strip(),
         'Use a fully fetched non-promisor Git repository')
    need(git('rev-parse', args.commit + '^{commit}').decode().strip() == args.commit, 'Commit identity mismatch')
    result = rebuild(args.old_kit, args.hy_evidence, args.out,
                     lambda name: git('show', args.commit + ':' + PREFIX + name))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
