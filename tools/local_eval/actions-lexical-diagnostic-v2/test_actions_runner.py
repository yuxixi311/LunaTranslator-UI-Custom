"""Fake-only checks of event binding, one claimed job, failure and disclosure bounds."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import actions_runner as r
import event_guard as g


class ActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.sha = 'a' * 64
        self.work_patch = patch.object(r, 'work', return_value=self.tmp)
        self.work_patch.start()
        self.addCleanup(self.work_patch.stop)
        self.env = {'LUNA_SOURCE_COMMIT': 'b' * 40, 'LUNA_MANIFEST_SHA': self.sha,
            'GITHUB_SHA': 'c' * 40, 'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push',
            'GITHUB_REPOSITORY': g.REPOSITORY, 'GITHUB_REF': 'refs/heads/' + g.BRANCH,
            'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_ENVIRONMENT': 'github-hosted',
            'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'GITHUB_RUN_ID': '1234',
            'GITHUB_WORKFLOW_REF': g.REPOSITORY + '/' + g.WORKFLOW + '@refs/heads/' + g.BRANCH,
            'GITHUB_WORKFLOW_SHA': 'c' * 40, 'ImageOS': 'ubuntu24', 'ImageVersion': '20260927.320.1'}
        self.event = {'before': 'b' * 40, 'after': 'c' * 40, 'ref': self.env['GITHUB_REF'],
            'repository': {'full_name': g.REPOSITORY, 'private': False}, 'created': False,
            'deleted': False, 'forced': False, 'head_commit': {'id': 'c' * 40}}
        self.binding = g.validate_event(self.event, self.env)

    def test_event_rejects_rerun_wrong_branch_repo_host_and_workflow(self):
        for field, bad in [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REF', 'refs/heads/main'),
                           ('GITHUB_REPOSITORY', 'someone/else'), ('RUNNER_ENVIRONMENT', 'self-hosted'),
                           ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_WORKFLOW_SHA', 'd' * 40),
                           ('GITHUB_WORKFLOW_REF', 'wrong'), ('RUNNER_ARCH', 'ARM64')]:
            with self.subTest(field=field):
                env = {**self.env, field: bad}
                with self.assertRaises(RuntimeError): g.validate_event(self.event, env)

    def test_event_rejects_creation_forcepushing_wrong_parent_private_and_missing_flags(self):
        for field, bad in [('created', True), ('deleted', True), ('forced', True),
                           ('before', 'd' * 40), ('after', 'd' * 40), ('ref', 'refs/heads/main')]:
            with self.subTest(field=field):
                event = {**self.event, field: bad}
                with self.assertRaises(RuntimeError): g.validate_event(event, self.env)
        event = copy.deepcopy(self.event); event['repository']['private'] = True
        with self.assertRaises(RuntimeError): g.validate_event(event, self.env)
        event = dict(self.event); del event['forced']
        with self.assertRaises(RuntimeError): g.validate_event(event, self.env)

    def test_guard_checks_exact_parent_single_workflow_change_and_claim_path(self):
        self.env.update(GITHUB_EVENT_PATH=str(self.tmp / 'event.json'), RUNNER_TEMP=str(self.tmp))
        (self.tmp / 'event.json').write_text(json.dumps(self.event))
        files = {g.SOURCE_DIR + '/actions_runner.py': {}}
        inventory = '\n'.join([*files, g.SOURCE_DIR + '/SOURCE_MANIFEST.json'])
        values = ['c' * 40, 'b' * 40, g.WORKFLOW, '', inventory]
        with patch.object(g, 'verify_sources', return_value={'files': files}), patch.object(g, 'git', side_effect=values):
            g.guard(self.env)
        self.assertTrue((self.tmp / g.PROTOCOL / 'EVENT_BINDING.json').exists())
        with patch.object(g, 'verify_sources', return_value={'files': files}), patch.object(g, 'git', side_effect=values):
            with self.assertRaises(FileExistsError): g.guard(self.env)
        for bad in ('b' * 40 + ' ' + 'd' * 40, 'd' * 40):
            with patch.object(g, 'git', side_effect=['c' * 40, bad]):
                with self.assertRaises(RuntimeError): g.guard(self.env)
        with patch.object(g, 'git', side_effect=['c' * 40, 'b' * 40, g.WORKFLOW + '\nsecret.txt']):
            with self.assertRaises(RuntimeError): g.guard(self.env)

    def test_exclusive_claim_survives_failure_and_refuses_second_attempt(self):
        state = r.claim(self.sha, self.binding)
        state['state'] = 'terminal_failure'; r.save(state)
        with self.assertRaises(FileExistsError): r.claim(self.sha, self.binding)
        self.assertEqual(r.read_json(self.tmp / 'RUN_CLAIM.json')['state'], 'terminal_failure')

    def test_child_environment_excludes_auth_proxy_and_private_values(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'private', 'HTTPS_PROXY': 'private', 'SECRET': 'private'}), \
             patch.object(r, 'validated_runtime', return_value=Path('/opt/hostedtoolcache/Python/3.12.14/x64')):
            env = r.child_environment()
        self.assertEqual(env['PIP_NO_INDEX'], '1')
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('HTTPS_PROXY', env)
        self.assertNotIn('private', json.dumps(env))
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(env['LD_LIBRARY_PATH'], '/opt/hostedtoolcache/Python/3.12.14/x64/lib')

    def test_missing_runtime_cache_has_no_fallback(self):
        with patch.dict(os.environ, {'RUNNER_TOOL_CACHE': str(self.tmp)}):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                r.validated_runtime()

    def test_failure_stops_following_phases_retains_claim_and_safe_log(self):
        launched = []
        def failed(state, phase, sha):
            launched.append(phase)
            raise RuntimeError('sensitive full source must never be logged')
        with patch.object(r, 'verify', return_value=self.binding), patch.object(r.base, 'preflight_resources'), \
             patch.object(r, 'run_phase', side_effect=failed), \
             patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(self.tmp / 'public-summary')}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(r.control(self.sha))
        self.assertEqual(launched, ['download'])
        self.assertNotIn('sensitive full source', output.getvalue())
        self.assertEqual(r.read_json(self.tmp / 'RUN_CLAIM.json')['state'], 'terminal_failure')
        summary = json.loads(output.getvalue())
        self.assertIsNone(summary['confirmed_parser_calls'])
        self.assertEqual(summary['failure'], {'phase': 'download', 'category': 'operation_failed'})

    def test_phase_order_integrity_and_lifecycle(self):
        state = {'phases': {}, 'source_manifest_sha256': self.sha}
        (self.tmp / 'download.json').write_text('{}')
        r.phase_receipt('download', self.sha)
        phase = {'lifecycle': {'exit_code': 0, 'elapsed_seconds': 0.1, 'deadline_seconds': 240,
                 'timed_out': False, 'cleanup_confirmed': True, 'failure': None},
                 'receipt': r.digest_file(self.tmp / 'download.receipt.json')}
        state['phases']['download'] = phase
        r.validate_completed(state)
        for key, value in [('timed_out', True), ('cleanup_confirmed', False), ('elapsed_seconds', 241), ('exit_code', 1)]:
            modified = copy.deepcopy(state); modified['phases']['download']['lifecycle'][key] = value
            with self.assertRaises(RuntimeError): r.validate_completed(modified)
        (self.tmp / 'download.json').write_text('{"changed":true}')
        with self.assertRaises(RuntimeError): r.validate_completed(state)

    def test_summary_records_only_ids_numeric_indexes_counts_and_pass_flags(self):
        state = r.claim(self.sha, self.binding)
        state.update(state='complete', phases={'parse': {'lifecycle': {'exit_code': 0,
            'elapsed_seconds': 0.2, 'deadline_seconds': 60, 'timed_out': False, 'cleanup_confirmed': True}}})
        batch = r.base.batch_sources()
        private = 'NEVER_PUBLISH_RAW_SOURCE_OR_TOKEN'
        rows = [{'id': b['id'], 'source': private, 'tokens': [{'raw_surface': private}]} for b in batch]
        parsed = {'complete': True, 'parser_calls': 48, 'records': rows, 'cold_initialization_seconds': 0.1,
            'peak_rss_kib': 100, 'cpu_seconds': 0.1, 'elapsed_before_output_seconds': 0.2}
        decisions = [{'id': b['id'], 'admitted': [], 'occurrences': [{'source': private}]} for b in batch]
        for row in decisions[:16]: row['match'] = True
        for name, payload in [('parser.json', parsed), ('assessment.json', {'lexical_gate_passed': True,
            'diagnostics': decisions[:16], 'seen_regressions': decisions[16:]}), ('installed.json', {})]:
            r.write_json(self.tmp / name, payload)
        with patch.object(r, 'validate_completed'):
            data = r.sanitized_summary(state)
        result = json.loads(data)
        self.assertNotIn(private, data)
        self.assertNotIn(str(self.tmp), data)
        self.assertEqual(result['confirmed_parser_calls'], 48)
        self.assertEqual(result['diagnostic_matches'], 16)
        self.assertEqual(len(result['cases']), 48)
        self.assertNotIn('matched', result['cases'][16])
        self.assertLessEqual(len(data.encode()), 32768)

    def test_source_manifest_catches_modified_file_and_symlink(self):
        root = self.tmp / 'repo'
        directory = root / g.SOURCE_DIR
        directory.mkdir(parents=True)
        target = directory / 'example.py'; target.write_text('example')
        manifest = {'protocol': g.PROTOCOL, 'public_base': g.PUBLIC_BASE,
            'files': {g.SOURCE_DIR + '/example.py': g.digest(target)}}
        path = directory / 'SOURCE_MANIFEST.json'; path.write_text(json.dumps(manifest))
        sha = g.digest(path)['sha256']
        g.verify_sources(sha, root)
        target.write_text('changed')
        with self.assertRaises(RuntimeError): g.verify_sources(sha, root)
        target.unlink(); target.symlink_to(path)
        with self.assertRaises(RuntimeError): g.verify_sources(sha, root)

    def test_summary_headline_separates_mechanism_failure_from_technical_completion(self):
        summary = {'state': 'complete', 'lexical_gate_passed': False, 'diagnostic_matches': 15}
        self.assertEqual(r.summary_headline(summary),
            'Luna lexical experiment: lexical gate FAILED (15/16 matched); technical status complete')
        summary.update(lexical_gate_passed=True, diagnostic_matches=16)
        self.assertIn('lexical gate PASSED (16/16 matched)', r.summary_headline(summary))
        self.assertIn('lexical gate NOT ASSESSED', r.summary_headline({'state': 'terminal_failure'}))


if __name__ == '__main__':
    unittest.main()
