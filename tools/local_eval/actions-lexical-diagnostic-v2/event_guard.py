"""Verify the immutable source/event binding before any dependency preparation."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
REPOSITORY = 'yuxixi311/LunaTranslator-UI-Custom'
BRANCH = 'experiment/luna-actions-lexical-20261005'
WORKFLOW = '.github/workflows/luna-lexical-diagnostic-v2.yml'
SOURCE_DIR = 'tools/local_eval/actions-lexical-diagnostic-v2'
BASELINE_DIR = 'tools/local_eval/cloud-lexical-v1'
PROTOCOL = 'luna-actions-lexical-diagnostic-20261005-v2'
PUBLIC_BASE = 'd452ac242211991ddd3439cd451c39e5d988c249'


def require(value):
    if not value:
        raise RuntimeError('binding verification failed')


def digest(path):
    h, count = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            count += len(block)
            h.update(block)
    return {'bytes': count, 'sha256': h.hexdigest()}


def read_json(path):
    require(Path(path).stat().st_size <= 4 * 1024 * 1024)
    return json.loads(Path(path).read_text())


def write_exclusive(path, data):
    with Path(path).open('x', encoding='utf-8') as out:
        json.dump(data, out, sort_keys=True, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def verify_sources(expected_sha, repo=REPO_ROOT):
    require(re.fullmatch('[0-9a-f]{64}', expected_sha or ''))
    path = repo / SOURCE_DIR / 'SOURCE_MANIFEST.json'
    require(not path.is_symlink() and digest(path)['sha256'] == expected_sha)
    manifest = read_json(path)
    require(manifest['protocol'] == PROTOCOL and manifest['public_base'] == PUBLIC_BASE)
    for name, pin in manifest['files'].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name)
        require(name.startswith(SOURCE_DIR + '/') or name.startswith(BASELINE_DIR + '/'))
        target = repo / name
        require(target.resolve() == target and target.is_file() and digest(target) == pin)
    return manifest


def validate_event(event, env):
    before, after = env['LUNA_SOURCE_COMMIT'], env['GITHUB_SHA']
    require(re.fullmatch('[0-9a-f]{40}', before or '') and before != '0' * 40)
    require(re.fullmatch('[0-9a-f]{40}', after or '') and after != before)
    require(env['GITHUB_ACTIONS'] == 'true' and env['GITHUB_EVENT_NAME'] == 'push')
    require(env['GITHUB_REPOSITORY'] == REPOSITORY and env['GITHUB_REF'] == 'refs/heads/' + BRANCH)
    require(env['GITHUB_RUN_ATTEMPT'] == '1' and env['RUNNER_ENVIRONMENT'] == 'github-hosted')
    require(env['RUNNER_OS'] == 'Linux' and env['RUNNER_ARCH'] == 'X64')
    require(env['GITHUB_RUN_ID'].isdecimal())
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
            'source_commit': before, 'trigger_commit': after, 'run_id': env['GITHUB_RUN_ID'],
            'run_attempt': 1, 'workflow': WORKFLOW, 'source_manifest_sha256': env['LUNA_MANIFEST_SHA'],
            'runner_image': image}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def guard(env=os.environ):
    event = read_json(env['GITHUB_EVENT_PATH'])
    binding = validate_event(event, env)
    require(git('rev-parse', 'HEAD') == binding['trigger_commit'])
    # Exactly one parent, equal to reviewed source commit C; D changes only this workflow.
    require(git('show', '-s', '--format=%P', 'HEAD').split() == [binding['source_commit']])
    require(git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD') == WORKFLOW)
    require(git('status', '--porcelain', '--untracked-files=all') == '')
    manifest = verify_sources(binding['source_manifest_sha256'])
    actual = set(git('ls-tree', '-r', '--name-only', 'HEAD', '--', SOURCE_DIR, BASELINE_DIR).splitlines())
    require(actual == set(manifest['files']) | {SOURCE_DIR + '/SOURCE_MANIFEST.json'})
    temporary = Path(env['RUNNER_TEMP'])
    require(temporary.is_absolute() and temporary.resolve() == temporary and temporary.is_dir())
    work = temporary / PROTOCOL
    work.mkdir(mode=0o700)  # Exclusive job-local identity; never reset or choose another path.
    write_exclusive(work / 'EVENT_BINDING.json', binding)
    return binding


def main():
    try:
        guard()
    except BaseException:
        print('Luna diagnostic source/event binding rejected; no dependency preparation authorized')
        return 1
    print('Luna diagnostic source/event binding verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
