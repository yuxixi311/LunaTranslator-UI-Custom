"""Exercise both CLI dispatchers with no real guard, controller, or child calls."""
import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import actions_runner as r
import event_guard as g


class ActivationTests(unittest.TestCase):
    def runner(self, args):
        with patch.object(sys, 'argv', ['actions_runner.py', *args]):
            return r.main()

    def test_runner_dispatches_controller_success_and_failure(self):
        for success in (True, False):
            with self.subTest(success=success), patch.object(r, 'control', return_value=success) as control, \
                 patch.object(r, 'child') as child:
                self.assertEqual(self.runner(['run', '--manifest-sha256', 'a' * 64]), 0 if success else 1)
                control.assert_called_once_with('a' * 64)
                child.assert_not_called()

    def test_runner_dispatches_every_child_command_with_mocked_boundary(self):
        cases = [(['_child', stage], stage) for stage in r.LIMITS]
        cases += [([command], command) for command in ('_ensurepip', '_install')]
        for arguments, stage in cases:
            with self.subTest(stage=stage), patch.object(r, 'child') as child, \
                 patch.object(r, 'control') as control:
                self.assertEqual(self.runner([*arguments, '--manifest-sha256', 'b' * 64,
                    '--parent-pid', '123']), 0)
                child.assert_called_once_with(stage, 'b' * 64, 123)
                control.assert_not_called()

    def test_runner_rejects_missing_or_unknown_arguments_before_dispatch(self):
        for arguments in ([], ['retry'], ['run'], ['_child', 'retry', '--manifest-sha256', 'c' * 64]):
            with self.subTest(arguments=arguments), patch.object(r, 'child') as child, \
                 patch.object(r, 'control') as control, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    self.runner(arguments)
                self.assertEqual(stopped.exception.code, 2)
                child.assert_not_called()
                control.assert_not_called()

    def test_runner_cli_failure_output_is_bounded_and_sanitized(self):
        private = 'NEVER_DISCLOSE_RAW_CLI_FAILURE'
        with tempfile.TemporaryDirectory() as directory, patch.object(r, 'work', return_value=Path(directory)), \
             patch.object(r, 'control', side_effect=OSError(private)) as control, \
             patch.object(r, 'child') as child, patch.object(r.diagnostic, 'collect', return_value={}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.runner(['run', '--manifest-sha256', 'd' * 64]), 1)
            self.assertEqual(json.loads(output.getvalue()), {'state': 'stopped', 'setup_diagnostics': {}})
            self.assertNotIn(private, output.getvalue())
            self.assertLessEqual(len(output.getvalue().encode()), 32768)
            control.assert_called_once()
            child.assert_not_called()

    def test_event_guard_cli_dispatches_once_with_mocked_guard(self):
        with patch.object(g, 'guard') as guard, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(g.main(), 0)
        guard.assert_called_once_with()
        self.assertEqual(output.getvalue(), 'Luna diagnostic source/event binding verified\n')

    def test_event_guard_cli_failure_discloses_no_exception(self):
        with patch.object(g, 'guard', side_effect=OSError('NEVER_DISCLOSE_GUARD_FAILURE')) as guard, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(g.main(), 1)
        guard.assert_called_once_with()
        self.assertNotIn('NEVER_DISCLOSE_GUARD_FAILURE', output.getvalue())
        self.assertEqual(output.getvalue(),
            'Luna diagnostic source/event binding rejected; no dependency preparation authorized\n')

    def test_both_script_entrypoints_only_dispatch_main(self):
        for module in (r, g):
            tree = ast.parse(Path(module.__file__).read_text())
            trailer = ast.Module(body=[tree.body[-1]], type_ignores=[])
            for status in (0, 1):
                with self.subTest(module=module.__name__, status=status):
                    main = Mock(return_value=status)
                    with self.assertRaises(SystemExit) as stopped:
                        exec(compile(trailer, module.__file__, 'exec'), {'__name__': '__main__', 'main': main})
                    self.assertEqual(stopped.exception.code, status)
                    main.assert_called_once_with()

    def test_v2_identity_is_distinct_on_owner_approved_branch(self):
        self.assertEqual(g.BRANCH, 'experiment/luna-actions-lexical-20261005')
        self.assertEqual(g.WORKFLOW, '.github/workflows/luna-lexical-diagnostic-v2.yml')
        self.assertEqual(g.PROTOCOL, 'luna-actions-lexical-diagnostic-20261005-v2')
        self.assertNotEqual(g.PROTOCOL, 'luna-actions-lexical-20261005-v1')
        self.assertEqual(r.LIMITS, {'download': 240, 'setup': 60, 'parse': 60, 'assess': 60})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / g.PROTOCOL
            target.mkdir()
            with patch.dict(r.os.environ, {'RUNNER_TEMP': directory}):
                self.assertEqual(r.work(), target)


if __name__ == '__main__':
    unittest.main()
