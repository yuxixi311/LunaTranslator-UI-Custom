"""Preparation-only tests; deny all real transport, child execution and native imports."""
import builtins
import contextlib
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'cloud-lexical-v1')]
original_import = builtins.__import__


def safe_import(name, *args, **kwargs):
    if name.split('.')[0] in {'sudachipy', 'sudachidict_core'} and name not in sys.modules:
        raise AssertionError('real package import forbidden in fake tests')
    return original_import(name, *args, **kwargs)


with contextlib.ExitStack() as guard:
    for target in ('socket.socket', 'socket.getaddrinfo', 'socket.create_connection',
                   'subprocess.Popen', 'venv.EnvBuilder.create', 'ensurepip.bootstrap', 'runpy.run_module', 'os.kill', 'os.killpg', 'urllib.request.OpenerDirector.open'):
        guard.enter_context(patch(target, side_effect=AssertionError('real network/process boundary forbidden')))
    guard.enter_context(patch('builtins.__import__', side_effect=safe_import))
    suite = unittest.TestSuite()
    for name in ('test_actions_runner', 'test_cli_activation', 'test_setup_diagnostics', 'test_license_policy', 'test_pilot_runner', 'test_lexical_policy', 'test_public_snapshot'):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
