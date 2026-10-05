"""One claimed Actions job: exact wheels, offline setup, then 48 lexical calls.

This controller is independent of historical attempts. Importing it performs no
network, package import, child spawn, claim creation or lexical operation.
"""
import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import platform
import resource
import socket
import subprocess
import sys
import urllib.error

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import event_guard as guard
from owned_lifecycle import owned_process, OwnedFailure
BASELINE = ROOT.parent / 'cloud-lexical-v1'
sys.path.insert(0, str(BASELINE))
import pilot_runner as base
import setup_diagnostics as diagnostic

PROTOCOL = guard.PROTOCOL
LIMITS = {'download': 240, 'setup': 60, 'parse': 60, 'assess': 60}
ARTIFACTS = base.ARTIFACTS
require, read_json, write_json, digest_file = base.require, base.read_json, base.write_json, base.digest_file


def work():
    path = Path(os.environ['RUNNER_TEMP']) / PROTOCOL
    require(path.is_absolute() and path.resolve() == path and path.is_dir(), 'invalid fixed job directory')
    return path


def at(trace, step):
    return trace.step(step) if trace is not None else contextlib.nullcontext()


def verify(sha, trace=None):
    with at(trace, 'source_inventory'):
        guard.verify_sources(sha)
    with at(trace, 'host_runtime'):
        base.host_check()
    with at(trace, 'runtime_cache'):
        validated_runtime()
    with at(trace, 'event_binding'):
        binding = read_json(work() / 'EVENT_BINDING.json')
        diagnostic.require(binding['protocol'] == PROTOCOL and binding['source_manifest_sha256'] == sha)
        diagnostic.require(binding['run_attempt'] == 1)
    return binding


def validated_runtime():
    cache = Path(os.environ['RUNNER_TOOL_CACHE'])
    root = cache / 'Python/3.12.14/x64'
    require(cache.is_absolute() and root.resolve() == root and root.is_dir(), 'official cache entry unavailable')
    require((root.parent / 'x64.complete').is_file(), 'official cache entry incomplete')
    require(Path(sys.base_prefix).resolve() == root, 'interpreter outside fixed official cache')
    return root


def host_identity():
    return {'implementation': platform.python_implementation(), 'version': platform.python_version(),
            'system': platform.system(), 'machine': platform.machine(),
            'interpreter': digest_file(Path(sys.executable).resolve())}


def save(state):
    tmp = work() / 'RUN_CLAIM.next'
    write_json(tmp, state, exclusive=True)
    os.replace(tmp, work() / 'RUN_CLAIM.json')


def claim(sha, binding):
    state = {'protocol': PROTOCOL, 'source_manifest_sha256': sha, 'binding': binding,
             'host': host_identity(), 'controller_pid': os.getpid(), 'state': 'claimed', 'phases': {}}
    write_json(work() / 'RUN_CLAIM.json', state, exclusive=True)
    for name in ('home', 'tmp', 'wheels'):
        (work() / name).mkdir(mode=0o700)
    return state


def error_category(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return 'http_failure'
    if isinstance(exc, urllib.error.URLError):
        exc = exc.reason
    if isinstance(exc, socket.gaierror):
        return 'dns_failure'
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return 'timeout'
    if isinstance(exc, PermissionError):
        return 'permission_rejected'
    if isinstance(exc, OwnedFailure):
        return 'owned_phase_failed'
    return 'operation_failed'


def phase_receipt(stage, sha):
    write_json(work() / (stage + '.receipt.json'), {'stage': stage, 'source_manifest_sha256': sha,
        'artifacts': {name: digest_file(work() / name) for name in ARTIFACTS[stage]}}, exclusive=True)


def validate_completed(state):
    expected = list(LIMITS)[:len(state['phases'])]
    require(list(state['phases']) == expected, 'phase order changed')
    for stage, saved in state['phases'].items():
        life = saved['lifecycle']
        require(life['exit_code'] == 0 and life['cleanup_confirmed'] is True and life['timed_out'] is False
                and life['failure'] is None and life['deadline_seconds'] == LIMITS[stage]
                and 0 <= life['elapsed_seconds'] <= LIMITS[stage], 'incomplete phase lifecycle')
        target = work() / (stage + '.receipt.json')
        require(digest_file(target) == saved['receipt'], 'phase receipt changed')
        receipt = read_json(target)
        require(receipt['stage'] == stage and receipt['source_manifest_sha256'] == state['source_manifest_sha256']
                and set(receipt['artifacts']) == set(ARTIFACTS[stage]), 'phase receipt mismatch')
        for name, pin in receipt['artifacts'].items():
            require(digest_file(work() / name) == pin, 'phase artifact changed')


def setup_offline(sha, trace):
    with trace.step('package_pins'):
        pins, run = base.package_pins(), work()
    with trace.step('wheel_paths'):
        wheels = [run / 'wheels' / pin['filename'] for pin in pins]
        diagnostic.require(len(wheels) == 2 and all(path.resolve() == path for path in wheels))
    report = diagnostic.inspect_wheels(wheels, pins, trace)
    with trace.step('venv_module'):
        import venv
    with trace.step('venv_create'):
        venv.EnvBuilder(with_pip=False, symlinks=False).create(run / 'venv')
    python = run / 'venv/bin/python'
    with trace.step('installer_environment'):
        environment = child_environment()
    for internal, step in (('_ensurepip', 'ensurepip_child'), ('_install', 'install_child')):
        trace.call(step, subprocess.run,
            [str(python), '-I', '-B', str(ROOT / 'actions_runner.py'), internal,
             '--manifest-sha256', sha, '--parent-pid', str(os.getpid())], check=True,
            env=environment, cwd=run)
    with trace.step('venv_isolation'):
        diagnostic.require('include-system-site-packages = false' in (run / 'venv/pyvenv.cfg').read_text())
    with trace.step('venv_interpreter'):
        diagnostic.require(digest_file(python) == digest_file(Path(sys.executable).resolve()))
    snapshot = diagnostic.installed_snapshot(run, trace)
    trace.call('snapshot_write', write_json, run / 'installed.json', snapshot, exclusive=True)
    host = trace.call('setup_host', host_identity)
    with trace.step('source_notices'):
        notices = {name: digest_file(BASELINE / name) for name in base.LICENSE_FILES}
    trace.call('setup_write', write_json, run / 'setup.json', {'archives': report, 'host': host,
        'retained_source_notices': notices,
        'network_boundary': 'Python socket audit restriction; native code assumed network-free; not an OS sandbox'},
        exclusive=True)


def ensurepip_offline(trace):
    with trace.step('ensurepip_venv'):
        diagnostic.require(Path(sys.prefix).resolve() == (work() / 'venv').resolve() and sys.prefix != sys.base_prefix)
    with trace.step('ensurepip_module'):
        import ensurepip
    def offline_pip(args, additional_paths=None):
        bootstrap = ('import sys,runpy; '
            'sys.addaudithook(lambda event,args: (_ for _ in ()).throw(RuntimeError("socket forbidden")) '
            'if event.startswith("socket.") else None); '
            'sys.path[:0]=' + repr(additional_paths or []) + '; '
            'sys.argv=' + repr(['pip', *args]) + '; runpy.run_module("pip",run_name="__main__")')
        return trace.call('ensurepip_pip_child', subprocess.run,
            [sys.executable, '-I', '-B', '-c', bootstrap], check=True).returncode
    with trace.step('ensurepip_hook'):
        original = ensurepip._run_pip
        ensurepip._run_pip = offline_pip
    try:
        trace.call('ensurepip_bootstrap', ensurepip.bootstrap, default_pip=True)
    finally:
        ensurepip._run_pip = original


def install_local(trace):
    with trace.step('install_venv'):
        diagnostic.require(Path(sys.prefix).resolve() == (work() / 'venv').resolve() and sys.prefix != sys.base_prefix)
    with trace.step('install_pins'):
        pins = base.package_pins()
    with trace.step('install_arguments'):
        arguments = ['pip', '--isolated', '--disable-pip-version-check', '--no-cache-dir', 'install', '--no-index',
            '--no-deps', '--no-compile', '--only-binary=:all:'] + [str(work() / 'wheels' / p['filename']) for p in pins]
        original = sys.argv
        sys.argv = arguments
    try:
        code = None
        with trace.step('install_module'):
            import runpy
            try:
                runpy.run_module('pip', run_name='__main__')
            except SystemExit as exc:
                code = exc.code
        with trace.step('install_exit'):
            diagnostic.require(code in (None, 0))
    finally:
        sys.argv = original


def child_environment():
    # No GitHub token, event payload, user config or proxy is passed to package code.
    root = validated_runtime()
    return {**base.clean_environment(work()), 'RUNNER_TEMP': str(work().parent),
            'RUNNER_TOOL_CACHE': str(root.parents[2]), 'LD_LIBRARY_PATH': str(root / 'lib')}


def child(stage, sha, parent_pid):
    trace = None
    try:
        if stage in diagnostic.PROCESSES:
            trace = diagnostic.Trace(work(), stage)
        with at(trace, 'parent_identity'):
            diagnostic.require(parent_pid > 1 and os.getppid() == parent_pid)
        with at(trace, 'offline_audit'):
            if stage != 'download':
                sys.addaudithook(base.block_network)
        with at(trace, 'resource_limits'):
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, ((100 if stage == 'download' else
                512 if stage in ('setup', '_ensurepip', '_install') else 4) * base.MIB,) * 2)
            if stage == 'parse':
                resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
                resource.setrlimit(resource.RLIMIT_AS, (1024 * base.MIB, 1024 * base.MIB))
        binding = verify(sha, trace)
        with at(trace, 'claim_read'):
            state = read_json(work() / 'RUN_CLAIM.json')
        active = 'setup' if stage in ('_ensurepip', '_install') else stage
        with at(trace, 'claim_identity'):
            diagnostic.require(state['binding'] == binding and state['source_manifest_sha256'] == sha and
                state['state'] == active + '_running' and state['host'] == host_identity())
        with at(trace, 'process_group'):
            if stage not in ('_ensurepip', '_install'):
                diagnostic.require(state['controller_pid'] == parent_pid and os.getpgrp() == os.getpid())
            else:
                diagnostic.require(os.getpgrp() == parent_pid)
        with at(trace, 'prior_receipts'):
            validate_completed(state)
        if stage == 'download': base.download(work())
        elif stage == 'setup': setup_offline(sha, trace)
        elif stage == 'parse': base.parse_batch(work(), sha)
        elif stage == 'assess': base.assess(work(), sha)
        elif stage == '_ensurepip': ensurepip_offline(trace)
        elif stage == '_install': install_local(trace)
        else: raise RuntimeError('unknown stage')
        if stage in LIMITS:
            with at(trace, 'phase_receipt'):
                phase_receipt(stage, sha)
    except BaseException as exc:
        write_json(work() / (stage.lstrip('_') + '.error.json'),
                   {'stage': stage, 'category': error_category(exc)}, exclusive=True)
        raise RuntimeError('phase failed') from None


def run_phase(state, stage, sha):
    validate_completed(state)
    state['state'] = stage + '_running'
    save(state)
    python = work() / 'venv/bin/python' if stage == 'parse' else Path(sys.executable).resolve()
    command = [str(python), '-I', '-B', str(ROOT / 'actions_runner.py'), '_child', stage,
               '--manifest-sha256', sha, '--parent-pid', str(os.getpid())]
    life = owned_process(command, work(), child_environment(), work() / (stage + '.log'), LIMITS[stage])
    verify(sha)
    state['phases'][stage] = {'lifecycle': life, 'receipt': digest_file(work() / (stage + '.receipt.json'))}
    validate_completed(state)
    state['state'] = stage + '_done'
    save(state)


def sanitized_summary(state):
    summary = {'protocol': PROTOCOL, 'state': state['state'], 'binding': state['binding'],
        'runtime': state['host'], 'planned_parser_calls': 48, 'confirmed_parser_calls': None,
        'parser_calls_on_failure': 'unknown if parser phase started; never assume zero',
        'model_calls': 0, 'gpu_used': False, 'phases': {},
        'limits_seconds': LIMITS, 'compressed_wheel_bytes': 73904174,
        'wheels': [{k: p[k] for k in ('name', 'version', 'size_bytes', 'sha256')} for p in base.package_pins()],
        'required_dictionary': {'bytes': base.DICT_SIZE, 'sha256': base.DICT_SHA},
        'evidence_scope': 'Exposed lexical diagnostics and seen decisions only; no translation-quality inference',
        'setup_diagnostics': diagnostic.collect(work())}
    for stage, phase in state['phases'].items():
        life = phase['lifecycle']
        require(isinstance(life['elapsed_seconds'], (int, float)) and math.isfinite(life['elapsed_seconds']),
                'invalid phase timing')
        summary['phases'][stage] = {k: life[k] for k in
            ('exit_code', 'elapsed_seconds', 'deadline_seconds', 'timed_out', 'cleanup_confirmed')}
    if 'error' in state:
        summary['failure'] = state['error']
    if 'failed_lifecycle' in state:
        life = state['failed_lifecycle']
        require(isinstance(life['elapsed_seconds'], (int, float)) and math.isfinite(life['elapsed_seconds'])
                and life['elapsed_seconds'] >= 0, 'invalid failed-phase timing')
        summary['failed_phase_lifecycle'] = {k: life[k] for k in
            ('exit_code', 'elapsed_seconds', 'deadline_seconds', 'timed_out', 'cleanup_confirmed')}
    if 'parse' in state['phases']:
        parsed = read_json(work() / 'parser.json')
        require(parsed['complete'] is True and parsed['parser_calls'] == 48, 'incomplete parser evidence')
        summary['confirmed_parser_calls'] = 48
        summary['parser_output_sha256'] = digest_file(work() / 'parser.json')['sha256']
        for key in ('cold_initialization_seconds', 'peak_rss_kib', 'cpu_seconds', 'elapsed_before_output_seconds'):
            value = parsed[key]
            require(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0, 'invalid parser metric')
            summary[key] = value
    if state['state'] == 'complete':
        validate_completed(state)
        parsed, assessment = read_json(work() / 'parser.json'), read_json(work() / 'assessment.json')
        batch = base.batch_sources()
        require([r['id'] for r in parsed['records']] == [r['id'] for r in batch], 'summary population mismatch')
        canon = [r['src'] for r in read_json(BASELINE / 'canon.json')['entries']]
        expected = read_json(BASELINE / 'diagnostics.expected.json')
        decisions = assessment['diagnostics'] + assessment['seen_regressions']
        require([r['id'] for r in decisions] == [r['id'] for r in batch], 'summary decision mismatch')
        rows = []
        for i, (row, decision) in enumerate(zip(parsed['records'], decisions, strict=True)):
            entry = {'id': batch[i]['id'], 'kind': 'diagnostic' if i < 16 else 'seen',
                'token_count': len(row['tokens']), 'occurrence_count': len(decision['occurrences']),
                'admitted_canon_indexes': sorted(canon.index(key) for key in decision['admitted'])}
            if i < 16:
                require(isinstance(decision['match'], bool), 'invalid diagnostic flag')
                entry.update(stratum=expected[i]['category'], matched=decision['match'])
            rows.append(entry)
        summary.update(lexical_gate_passed=assessment['lexical_gate_passed'],
            diagnostic_matches=sum(row['matched'] for row in rows[:16]), diagnostics_total=16,
            seen_total=32, cases=rows, assessment_output_sha256=digest_file(work() / 'assessment.json')['sha256'],
            installed_inventory_sha256=digest_file(work() / 'installed.json')['sha256'])
    data = json.dumps(summary, ensure_ascii=True, sort_keys=True, allow_nan=False)
    require(len(data.encode()) <= 32768, 'summary too large')
    return data


def control(sha):
    preflight = diagnostic.Trace(work(), 'preflight')
    binding = verify(sha, preflight)
    # Resources and host are checked before claim; no package/native import or DNS occurs here.
    preflight.call('preflight_resources', base.preflight_resources)
    with preflight.step('control_lock'):
        lock = (work() / 'CONTROL_LOCK').open('a+b')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        state = preflight.call('exclusive_claim', claim, sha, binding)
    except BaseException:
        lock.close()
        raise
    success = False
    try:
        for stage in LIMITS:
            try:
                run_phase(state, stage, sha)
            except BaseException as exc:
                state['state'] = 'terminal_failure'
                category = error_category(exc)
                fixed = work() / (stage + '.error.json')
                if fixed.exists():
                    category = read_json(fixed)['category']
                require(category in {'http_failure', 'dns_failure', 'timeout', 'permission_rejected',
                                     'owned_phase_failed', 'operation_failed'}, 'invalid error category')
                state['error'] = {'phase': stage, 'category': category}
                if isinstance(exc, OwnedFailure):
                    state['failed_lifecycle'] = exc.result
                save(state)
                break
        else:
            state['state'] = 'complete'
            save(state)
            success = True
        data = sanitized_summary(state)
        write_json(work() / 'SANITIZED_SUMMARY.json', json.loads(data), exclusive=True)
        print(data, flush=True)
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as out:
            out.write(summary_headline(json.loads(data)) + '\n\n' + data + '\n')
    finally:
        lock.close()
    return success


def summary_headline(summary):
    technical = summary['state']
    if technical == 'complete':
        outcome = 'PASSED' if summary['lexical_gate_passed'] else 'FAILED'
        mechanism = 'lexical gate ' + outcome + ' (' + str(summary['diagnostic_matches']) + '/16 matched)'
    else:
        mechanism = 'lexical gate NOT ASSESSED'
    return 'Luna lexical experiment: ' + mechanism + '; technical status ' + technical


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', '_child', '_ensurepip', '_install'))
    parser.add_argument('stage', nargs='?', choices=tuple(LIMITS))
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--parent-pid', type=int, default=0)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            return 0 if control(args.manifest_sha256) else 1
        child(args.stage if args.command == '_child' else args.command, args.manifest_sha256, args.parent_pid)
        return 0
    except BaseException:
        # Never emit exception text, raw frames, environment, source strings or local logs.
        try:
            report = {'state': 'stopped', 'setup_diagnostics': diagnostic.collect(work())}
            data = json.dumps(report, ensure_ascii=True, allow_nan=False)
            require(len(data.encode()) <= 32768, 'summary too large')
            print(data, flush=True)
        except BaseException:
            print('Luna lexical experiment stopped; no automatic retry', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
