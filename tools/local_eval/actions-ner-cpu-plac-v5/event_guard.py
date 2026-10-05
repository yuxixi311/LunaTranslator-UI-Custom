"""Exact source U / workflow V push guard, before any CPU attempt claim."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
REPOSITORY = 'yuxixi311/LunaTranslator-UI-Custom'
BRANCH = 'experiment/luna-actions-lexical-20261005'
WORKFLOW = '.github/workflows/luna-ner-cpu-plac-v5.yml'
SOURCE_DIR = 'tools/local_eval/actions-ner-cpu-plac-v5'
PROTOCOL = 'luna-ner-cpu-plac-v5'
CLAIM_NAME = 'luna-actions-ner-cpu-plac-20261005-v5'
SOURCE_PARENT = 'e8713691d8c8814fc407eaa014252d331e640535'


def require(value):
    if not value:
        raise ValueError('source_event_binding_rejected')


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def read_bytes(path, cap=4 * 1024 * 1024):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= cap)
        data = stream.read(cap + 1)
    require(len(data) == info.st_size)
    return data


def digest(path):
    data = read_bytes(path)
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read_json(path):
    return json.loads(read_bytes(path), object_pairs_hook=no_duplicates)


def write_exclusive(path, data):
    with Path(path).open('x', encoding='utf-8') as out:
        json.dump(data, out, sort_keys=True, separators=(',', ':'), allow_nan=False)
        out.flush()
        os.fsync(out.fileno())


def verify_sources(expected_sha, root=ROOT):
    require(re.fullmatch('[0-9a-f]{64}', expected_sha or ''))
    raw = read_bytes(root / 'PREPARATION_INVENTORY.json', 256 * 1024)
    require(hashlib.sha256(raw).hexdigest() == expected_sha)
    manifest = json.loads(raw, object_pairs_hook=no_duplicates)
    require(set(manifest) == {'protocol', 'source_parent', 'files'}
            and manifest['protocol'] == PROTOCOL and manifest['source_parent'] == SOURCE_PARENT)
    require(type(manifest['files']) is dict and 1 <= len(manifest['files']) <= 64)
    require({p.name for p in root.iterdir()} == set(manifest['files']) | {'PREPARATION_INVENTORY.json'})
    for name, pin in manifest['files'].items():
        require(type(name) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name))
        require(type(pin) is dict and set(pin) == {'bytes', 'sha256'} and digest(root / name) == pin)
    return manifest


def validate_event(event, env):
    before, after = env['LUNA_SOURCE_COMMIT'], env['GITHUB_SHA']
    require(re.fullmatch('[0-9a-f]{40}', before or '') and before != '0' * 40)
    require(re.fullmatch('[0-9a-f]{40}', after or '') and after not in (before, '0' * 40))
    require(env['GITHUB_ACTIONS'] == 'true' and env['GITHUB_EVENT_NAME'] == 'push')
    require(env['GITHUB_REPOSITORY'] == REPOSITORY and env['GITHUB_REF'] == 'refs/heads/' + BRANCH)
    require(env['GITHUB_RUN_ATTEMPT'] == '1' and env['RUNNER_ENVIRONMENT'] == 'github-hosted')
    require(env['RUNNER_OS'] == 'Linux' and env['RUNNER_ARCH'] == 'X64')
    require(re.fullmatch('[1-9][0-9]{0,19}', env['GITHUB_RUN_ID']))
    require(env['GITHUB_WORKFLOW_REF'] == REPOSITORY + '/' + WORKFLOW + '@refs/heads/' + BRANCH)
    require(env['GITHUB_WORKFLOW_SHA'] == after)
    require(event['repository']['full_name'] == REPOSITORY and event['repository']['private'] is False)
    require(event['ref'] == env['GITHUB_REF'] and event['before'] == before and event['after'] == after)
    require(event.get('created') is False and event.get('deleted') is False and event.get('forced') is False)
    require(event['head_commit']['id'] == after)
    image = {key: env[key] for key in ('ImageOS', 'ImageVersion')}
    require(all(re.fullmatch('[a-zA-Z0-9_.-]{1,80}', value) for value in image.values()))
    require(image['ImageOS'] == 'ubuntu24')
    return {'protocol': PROTOCOL, 'repository': REPOSITORY, 'ref': env['GITHUB_REF'],
            'source_parent': SOURCE_PARENT, 'source_commit': before, 'trigger_commit': after,
            'run_id': env['GITHUB_RUN_ID'], 'run_attempt': 1, 'workflow': WORKFLOW,
            'source_inventory_sha256': env['LUNA_INVENTORY_SHA'], 'runner_image': image}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def inspect_event(env):
    binding = validate_event(read_json(Path(env['GITHUB_EVENT_PATH'])), env)
    require(git('rev-parse', 'HEAD') == binding['trigger_commit'])
    require(git('show', '-s', '--format=%P', 'HEAD').split() == [binding['source_commit']])
    require(git('show', '-s', '--format=%P', binding['source_commit']).split() == [SOURCE_PARENT])
    require(git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD') == WORKFLOW)
    require(git('status', '--porcelain', '--untracked-files=all') == '')
    manifest = verify_sources(binding['source_inventory_sha256'])
    expected = {SOURCE_DIR + '/' + name for name in manifest['files']} | {SOURCE_DIR + '/PREPARATION_INVENTORY.json'}
    require(set(git('ls-tree', '-r', '--name-only', 'HEAD', '--', SOURCE_DIR).splitlines()) == expected)
    require(set(git('diff-tree', '--no-commit-id', '--name-only', '-r', binding['source_commit']).splitlines()) == expected)
    template = read_bytes(ROOT / 'WORKFLOW_TEMPLATE.yml.in').decode('utf-8')
    for placeholder, value in {'__REVIEWED_SOURCE_COMMIT_U__': binding['source_commit'],
            '__SOURCE_INVENTORY_SHA256__': binding['source_inventory_sha256'],
            '__EVENT_GUARD_SHA256__': manifest['files']['event_guard.py']['sha256'],
            '__SOURCE_BOOTSTRAP_SHA256__': manifest['files']['source_bootstrap.py']['sha256']}.items():
        template = template.replace(placeholder, value)
    require(read_bytes(REPO_ROOT / WORKFLOW) == template.encode('utf-8'))
    return binding


def guard(env=os.environ):
    binding = inspect_event(env)
    temporary = Path(env['RUNNER_TEMP'])
    require(temporary.is_absolute() and temporary.resolve(strict=True) == temporary and temporary.is_dir())
    work = temporary / CLAIM_NAME
    work.mkdir(mode=0o700)
    write_exclusive(work / 'EVENT_BINDING.json', binding)
    return binding


def main():
    try:
        guard()
    except BaseException:
        print('Luna CPU NER source/event binding rejected; no attempt released')
        return 1
    print('Luna CPU NER source/event binding verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
