"""One event-bound CPU attempt: exact download, offline setup, 73 NER calls.

Importing is inert. Execution is exclusively through the reviewed source
bootstrap, exact K/L push guard and new fixed claim. No reset, retry, private
semantic grading, alternative model, translation call or GPU continuation.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import event_guard as guard
import safe_diagnostics as diagnostics
from source_bootstrap import verify_sources
from ner_adapter import ProbeFailure, require, canonical_json, MAX_EVIDENCE_BYTES, POLICY_SHA256
from finalized_manifest import read_finalized_manifest, FINAL_MANIFEST_SHA256, FINAL_AGGREGATE_BYTES
from evidence_io import decode_json, read_pinned_file, load_frozen_population, validate_evidence, FIXTURE_HASHES
from runner_control import (file_pin, exclusive_json, exclusive_claim, host_preflight, child_environment,
    set_child_limits, deny_network, download_pinned_wheels, run_one_stage, seal_stage_receipt, STAGES)

ROOT = Path(__file__).resolve(strict=True).parent
INTERPRETER_PIN = {'bytes': 17752, 'sha256': 'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0'}
ARTIFACTS = {'download': ('download.json',),
             'setup': ('wheel-validation.json', 'installed.json', 'setup.json'),
             'parse': ('ner-evidence.json',)}
STAGE_NAMES = tuple(name for name, _ in STAGES)


def read_json(path):
    return decode_json(guard.read_bytes(Path(path)), MAX_EVIDENCE_BYTES)


def source_inputs(sha):
    verify_sources(ROOT, sha, 'actions_runner.py')
    require(file_pin(ROOT / 'ner_entry_policy.py')['sha256'] == POLICY_SHA256, 'policy_hash_mismatch')
    manifest = read_finalized_manifest((ROOT / 'WHEELS49.frozen.json').read_bytes())
    metadata = read_json(ROOT / 'PLAC_PREFLIGHT_RECEIPT.json')
    require(metadata['status'] == 'metadata_verified_manifest_frozen' and metadata['attempted_gets'] == 1
            and metadata['frozen_manifest_sha256'] == FINAL_MANIFEST_SHA256
            and canonical_json(metadata['frozen_manifest']) == canonical_json(manifest), 'metadata_receipt_mismatch')
    inputs = read_json(ROOT / 'INPUT_MANIFEST.json')
    require(set(inputs) == set(FIXTURE_HASHES), 'fixture_roles_mismatch')
    for name, expected in FIXTURE_HASHES.items():
        require(inputs[name]['sha256'] == expected, 'fixture_freeze_mismatch')
        read_pinned_file(ROOT, inputs[name])
    return inputs


def runtime_identity(runtime, work):
    runtime = Path(runtime)
    host = host_preflight(runtime, work)
    require(file_pin(Path(sys.executable).resolve(strict=True)) == INTERPRETER_PIN, 'interpreter_hash_mismatch')
    return {**host, 'interpreter': INTERPRETER_PIN, 'runtime_path': str(runtime)}


def checked_work(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and path.is_dir()
            and path.name == guard.CLAIM_NAME, 'unsafe_work_directory')
    return path


def verify_wheels(work):
    manifest = read_finalized_manifest((ROOT / 'WHEELS49.frozen.json').read_bytes())
    expected = {r['wheel']['filename']: {'bytes': r['wheel']['bytes'], 'sha256': r['wheel']['sha256']}
                for r in manifest['files']}
    wheelhouse = Path(work) / 'wheels'
    require(wheelhouse.resolve(strict=True) == wheelhouse
            and {p.name for p in wheelhouse.iterdir()} == set(expected), 'wheelhouse_inventory_mismatch')
    require(all(file_pin(wheelhouse / name) == pin for name, pin in expected.items()), 'wheel_hash_mismatch')
    return expected


def verify_receipts(work, binding, receipts, next_stage):
    require(type(receipts) is dict and list(receipts) == list(STAGE_NAMES[:STAGE_NAMES.index(next_stage)]),
            'phase_order_mismatch')
    for stage, pin in receipts.items():
        target = work / (stage + '.receipt.json')
        require(file_pin(target) == pin, 'receipt_changed')
        record = read_json(target)
        require(set(record) == {'stage', 'bindings', 'lifecycle', 'artifacts'}
                and record['stage'] == stage and record['bindings'] == binding
                and set(record['artifacts']) == set(ARTIFACTS[stage]), 'receipt_binding_mismatch')
        life = record['lifecycle']
        require(life['exit_code'] == 0 and life['cleanup_confirmed'] is True and life['timed_out'] is False
                and life['failure'] is None and life['deadline_seconds'] == dict(STAGES)[stage]
                and 0 <= life['elapsed_seconds'] <= dict(STAGES)[stage], 'invalid_lifecycle')
        require(all(file_pin(work / name) == artifact for name, artifact in record['artifacts'].items()),
                'artifact_changed')


def verify_setup(work):
    # Full installed tree/model/notice verification executes within the owned
    # parse lifecycle before the factory import, including its CPU/RSS budgets.
    from offline_setup import snapshot_tree, verify_model_inventory, SUPPLEMENTS
    require(snapshot_tree(work / 'venv') == read_json(work / 'installed.json'), 'installed_inventory_changed')
    require(file_pin(work / 'venv/bin/python') == INTERPRETER_PIN, 'venv_interpreter_mismatch')
    require('include-system-site-packages = false' in (work / 'venv/pyvenv.cfg').read_text(), 'venv_not_isolated')
    verify_model_inventory(work / 'venv/lib/python3.12/site-packages', read_json(ROOT / 'MODEL_INVENTORY.json'))
    require({p.name for p in (work / 'notice-supplements').iterdir()} == set(SUPPLEMENTS), 'notice_inventory_changed')
    for name, pin in SUPPLEMENTS.items():
        require(file_pin(work / 'notice-supplements' / name) == pin, 'notice_inventory_changed')
    setup = read_json(work / 'setup.json')
    require(setup['installed_bytes'] == read_json(work / 'installed.json')['bytes'], 'installed_size_mismatch')


def evidence_bindings(work, binding):
    return {'protocol': guard.PROTOCOL, 'attempt_id': 'actions-' + binding['event']['run_id'] + '-attempt-1',
            'source_inventory_sha256': binding['source_inventory_sha256'],
            'dependency_manifest_sha256': FINAL_MANIFEST_SHA256,
            'installed_inventory_sha256': file_pin(work / 'installed.json')['sha256'],
            'model_inventory_sha256': file_pin(ROOT / 'MODEL_INVENTORY.json')['sha256'],
            'input_manifest_sha256': file_pin(ROOT / 'INPUT_MANIFEST.json')['sha256']}


def child_command(stage, work, runtime, sha, claim_sha, context_sha, parent_pid):
    require(stage in STAGE_NAMES, 'invalid_stage')
    python = work / 'venv/bin/python' if stage == 'parse' else runtime / 'bin/python'
    return [str(python), '-I', '-B', str(ROOT / 'source_bootstrap.py'), '--inventory-sha256', sha,
            '--entrypoint', 'actions_runner.py', '--', '_child', stage, '--inventory-sha256', sha,
            '--work', str(work), '--runtime', str(runtime), '--claim-sha256', claim_sha,
            '--context-sha256', context_sha, '--parent-pid', str(parent_pid)]


def child(stage, work, runtime, sha, claim_sha, context_sha, parent_pid):
    require(stage in STAGE_NAMES and parent_pid > 1 and os.getppid() == parent_pid
            and os.getpgrp() == os.getpid(), 'child_parent_mismatch')
    work = checked_work(work)
    set_child_limits(stage)
    if stage != 'download':
        sys.addaudithook(deny_network)
    claim_file = work / 'RUN_CLAIM.json'
    context_file = work / (stage + '.context.json')
    require(file_pin(claim_file)['sha256'] == claim_sha and file_pin(context_file)['sha256'] == context_sha,
            'child_context_changed')
    claim, context = read_json(claim_file), read_json(context_file)
    binding = claim['bindings']
    require(claim['pid'] == parent_pid and claim['state'] == 'claimed'
            and context['stage'] == stage and context['bindings'] == binding
            and binding['source_inventory_sha256'] == sha,
            'child_binding_mismatch')
    require(read_json(work / 'EVENT_BINDING.json') == binding['event'], 'event_binding_changed')
    require(read_json(work / (stage + '.started.json')) == {'stage': stage, 'bindings': binding},
            'stage_start_mismatch')
    require(not (work / 'TERMINAL_FAILURE.json').exists(), 'terminal_attempt')
    trace = diagnostics.Diagnostics(work, stage, sha, claim_sha, context_sha)
    try:
        trace.mark('source_binding')
        inputs = source_inputs(sha)
        trace.mark('host_binding')
        require(binding['host'] == runtime_identity(runtime, work), 'host_identity_changed')
        trace.mark('prerequisite_receipts')
        verify_receipts(work, binding, context['receipts'], stage)
        if stage == 'download':
            trace.mark('download')
            result = download_pinned_wheels((ROOT / 'WHEELS49.frozen.json').read_bytes(), work / 'wheels',
                                             progress=trace.mark)
            require(result == {'wheel_count': 49, 'compressed_bytes': FINAL_AGGREGATE_BYTES}, 'download_count_mismatch')
            trace.mark('wheel_inventory')
            exclusive_json(work / 'download.json', {**result, 'files': verify_wheels(work)})
        elif stage == 'setup':
            trace.mark('wheel_inventory')
            require(read_json(work / 'download.json')['files'] == verify_wheels(work), 'download_inventory_changed')
            from offline_setup import prepare_offline_setup
            prepare_offline_setup(work, (ROOT / 'WHEELS49.frozen.json').read_bytes(), None, None,
                child_environment(work, runtime), ROOT, read_json(ROOT / 'MODEL_INVENTORY.json'),
                source_inventory_sha256=sha, progress=trace.mark)
        else:
            trace.mark('installed_verification')
            verify_setup(work)
            trace.mark('ner_pipeline', 'ja-ginza')
            from parser_child import parser_body
            parser_body(work, ROOT, ROOT, inputs, evidence_bindings(work, binding), parent_pid)
        return 0
    except BaseException as exc:
        trace.fail(exc)
        raise


def review_stage(stage, work, binding, inputs):
    # Only bounded JSON and source checks in the controller; large tree/archive
    # hashing stays inside the owned setup/parse lifecycle.
    if stage == 'download':
        value = read_json(work / 'download.json')
        manifest = read_finalized_manifest((ROOT / 'WHEELS49.frozen.json').read_bytes())
        expected = {r['wheel']['filename']: {'bytes': r['wheel']['bytes'], 'sha256': r['wheel']['sha256']}
                    for r in manifest['files']}
        require(value == {'wheel_count': 49, 'compressed_bytes': FINAL_AGGREGATE_BYTES, 'files': expected},
                'download_receipt_mismatch')
    elif stage == 'setup':
        setup, installed = read_json(work / 'setup.json'), read_json(work / 'installed.json')
        require(0 < installed['bytes'] <= 1024 * 1024 * 1024 and installed['bytes'] == setup['installed_bytes']
                and len(setup['wheel_payload_retention']) == 49
                and setup['model'] == {'model': 'ja_ginza', 'version': '5.2.0', 'bytes': 79000185, 'file_count': 23},
                'setup_receipt_mismatch')
    else:
        value = validate_evidence(guard.read_bytes(work / 'ner-evidence.json'), load_frozen_population(ROOT, inputs),
                                  evidence_bindings(work, binding))
        require(value['resource_gates_passed'] is True, 'warm_p95_gate_failed')


def public_lifecycle(life):
    names = ('exit_code', 'elapsed_seconds', 'deadline_seconds', 'timed_out', 'cleanup_confirmed')
    value = {name: life.get(name) for name in names}
    require(value['exit_code'] is None or type(value['exit_code']) is int, 'invalid_lifecycle')
    for name in ('elapsed_seconds', 'deadline_seconds'):
        require(value[name] is None or (type(value[name]) in (float, int) and math.isfinite(value[name])
                                       and value[name] >= 0), 'invalid_lifecycle')
    require(all(value[name] is None or type(value[name]) is bool for name in ('timed_out', 'cleanup_confirmed')),
            'invalid_lifecycle')
    return value


def public_diagnostic(work, stage, binding, suffix, claim_sha, context_sha):
    target = work / (stage + '.' + suffix + '.json')
    if not target.exists():
        return {'status': 'not_recorded'}
    try:
        data = decode_json(guard.read_bytes(target, 4096), 4096)
        identity = {'stage': stage, 'source_inventory_sha256': binding['source_inventory_sha256'],
                    'claim_sha256': claim_sha, 'context_sha256': context_sha}
        require(file_pin(work / 'RUN_CLAIM.json')['sha256'] == claim_sha
                and file_pin(work / (stage + '.context.json'))['sha256'] == context_sha, 'diagnostic_binding_changed')
        extras = {'code', 'step', 'package'} if suffix == 'error' else {'step', 'package', 'sequence'}
        require(set(data) == set(identity) | extras and all(data[key] == value for key, value in identity.items()),
                'diagnostic_binding_changed')
        require(data['step'] in diagnostics.STEPS and (data['package'] is None or data['package'] in diagnostics.PACKAGES),
                'invalid_diagnostic_state')
        result = {'status': 'recorded', 'step': data['step'], 'package': data['package'], 'receipt': file_pin(target)}
        if suffix == 'error':
            require(data['code'] in diagnostics.PROBE_CODES | diagnostics.GENERIC_CODES, 'invalid_diagnostic_state')
            result['code'] = data['code']
        else:
            require(type(data['sequence']) is int and 1 <= data['sequence'] <= 128, 'invalid_diagnostic_state')
            result['sequence'] = data['sequence']
        return result
    except Exception:
        return {'status': 'rejected'}


def publish_result(work, binding, receipts, success, failed_stage, inputs, claim_sha, contexts):
    # Only explicit public host fields; private runtime/work paths stay internal.
    host_fields = ('implementation', 'python', 'system', 'machine', 'interpreter_sha256', 'glibc', 'interpreter')
    summary = {'protocol': guard.PROTOCOL, 'event': binding['event'],
        'host': {name: binding['host'][name] for name in host_fields},
        'state': 'complete' if success else 'terminal_failure', 'failed_stage': failed_stage,
        'phases': {}, 'planned_pipeline_calls': 73, 'confirmed_pipeline_calls': None,
        'calls_on_incomplete_failure': 'unknown', 'gpu_used': False, 'translation_model_calls': 0,
        'semantic_grading': 'not_performed_private_offline_grading_required', 'limits_seconds': dict(STAGES)}
    for stage, pin in receipts.items():
        target = work / (stage + '.receipt.json')
        require(file_pin(target) == pin, 'receipt_changed')
        record = read_json(target)
        require(record['bindings'] == binding and record['stage'] == stage, 'receipt_binding_mismatch')
        summary['phases'][stage] = {**public_lifecycle(record['lifecycle']), 'receipt': pin}
    evidence = None
    if (work / 'ner-evidence.json').exists():
        # Warm-gate failure may preserve all records, but never becomes success.
        evidence = validate_evidence(guard.read_bytes(work / 'ner-evidence.json'), load_frozen_population(ROOT, inputs),
                                     evidence_bindings(work, binding))
        summary['confirmed_pipeline_calls'] = 73
        summary['evidence_sha256'] = file_pin(work / 'ner-evidence.json')['sha256']
    if failed_stage is not None:
        failure = read_json(work / 'TERMINAL_FAILURE.json')
        require(failure['bindings'] == binding and failure['stage'] == failed_stage
                and failure['status'] == 'terminal_failure'
                and failure['category'] in {'owned_phase_failed', 'phase_failed', 'phase_validation_failed'},
                'failure_binding_mismatch')
        summary['failure'] = {'stage': failed_stage, 'category': failure['category'],
            'lifecycle': public_lifecycle(failure.get('lifecycle', {})),
            'child_error': public_diagnostic(work, failed_stage, binding, 'error', claim_sha, contexts.get(failed_stage)),
            'last_child_step': public_diagnostic(work, failed_stage, binding, 'progress', claim_sha, contexts.get(failed_stage))}
    value = {'summary': summary, 'evidence': evidence}
    encoded = canonical_json(value)
    require(len(encoded) <= MAX_EVIDENCE_BYTES, 'output_size_exceeded')
    exclusive_json(work / 'PUBLIC_RESULT.json', value)
    # Emit bounded chunks to avoid a single oversized Actions log line. Decoding
    # concatenated chunks yields exact PUBLIC_RESULT bytes, with no row filtering.
    payload = base64.b64encode(encoded).decode('ascii')
    chunks = [payload[i:i + 12000] for i in range(0, len(payload), 12000)]
    lines = ['LUNA_NER_RESULT_BEGIN ' + json.dumps({'bytes': len(encoded),
             'sha256': hashlib.sha256(encoded).hexdigest(), 'chunks': len(chunks)}, sort_keys=True)]
    lines.extend('LUNA_NER_RESULT_CHUNK ' + str(index) + ' ' + text for index, text in enumerate(chunks))
    lines.append('LUNA_NER_RESULT_END')
    require(sum(len(line.encode('ascii')) + 1 for line in lines) <= MAX_EVIDENCE_BYTES, 'output_size_exceeded')
    for line in lines:
        print(line, flush=True)
    return value


def control(sha):
    inputs = source_inputs(sha)
    event = guard.inspect_event(os.environ)
    require(event['source_inventory_sha256'] == sha, 'source_inventory_mismatch')
    work = checked_work(Path(os.environ['RUNNER_TEMP']) / guard.CLAIM_NAME)
    require(read_json(work / 'EVENT_BINDING.json') == event, 'event_binding_changed')
    require({p.name for p in work.iterdir()} == {'EVENT_BINDING.json'}, 'attempt_already_exists')
    runtime = Path(os.environ['RUNNER_TOOL_CACHE']) / 'Python/3.12.14/x64'
    host = runtime_identity(runtime, work)
    binding = {'event': event, 'host': host, 'source_inventory_sha256': sha,
               'input_manifest': file_pin(ROOT / 'INPUT_MANIFEST.json'),
               'dependency_manifest': file_pin(ROOT / 'WHEELS49.frozen.json'),
               'model_inventory': file_pin(ROOT / 'MODEL_INVENTORY.json')}
    receipts, contexts, success, failed_stage = {}, {}, False, None
    with exclusive_claim(work, binding):
        claim_sha = file_pin(work / 'RUN_CLAIM.json')['sha256']
        for stage in STAGE_NAMES:
            life = None
            try:
                source_inputs(sha)
                require(runtime_identity(runtime, work) == host, 'host_identity_changed')
                verify_receipts(work, binding, receipts, stage)
                context_path = work / (stage + '.context.json')
                exclusive_json(context_path, {'stage': stage, 'bindings': binding, 'receipts': receipts})
                contexts[stage] = file_pin(context_path)['sha256']
                command = child_command(stage, work, runtime, sha, claim_sha, contexts[stage], os.getpid())
                life = run_one_stage(stage, command, work, child_environment(work, runtime), binding, receipts)
                require(not (work / (stage + '.error.json')).exists(), 'unexpected_child_error_receipt')
                source_inputs(sha)
                review_stage(stage, work, binding, inputs)
                receipts[stage] = seal_stage_receipt(work, stage, binding, life, ARTIFACTS[stage])
            except BaseException:
                failed_stage = stage
                if not (work / 'TERMINAL_FAILURE.json').exists():
                    exclusive_json(work / 'TERMINAL_FAILURE.json', {'stage': stage, 'bindings': binding,
                                   'status': 'terminal_failure', 'category': 'phase_validation_failed',
                                   **({'lifecycle': life} if life is not None else {})})
                break
        else:
            success = True
        publish_result(work, binding, receipts, success, failed_stage, inputs, claim_sha, contexts)
    return success


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', '_child'))
    parser.add_argument('stage', nargs='?', choices=STAGE_NAMES)
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--claim-sha256')
    parser.add_argument('--context-sha256')
    parser.add_argument('--parent-pid', type=int)
    try:
        args = parser.parse_args(argv)
        if args.command == 'run':
            require(args.stage is None and all(getattr(args, key) is None for key in
                    ('work', 'runtime', 'claim_sha256', 'context_sha256', 'parent_pid')), 'invalid_run_arguments')
            return 0 if control(args.inventory_sha256) else 1
        require(args.stage in STAGE_NAMES and all(getattr(args, key) is not None for key in
                ('work', 'runtime', 'claim_sha256', 'context_sha256', 'parent_pid')), 'invalid_child_arguments')
        return child(args.stage, args.work, args.runtime, args.inventory_sha256, args.claim_sha256,
                     args.context_sha256, args.parent_pid)
    except BaseException:
        print('{"state":"stopped","reason":"cpu_attempt_failed_no_retry"}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
