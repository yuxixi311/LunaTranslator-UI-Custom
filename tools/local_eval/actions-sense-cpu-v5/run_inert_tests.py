"""Only source tests; native child/socket/thread starts are forbidden."""
import sys
from pathlib import Path
import socket
import subprocess
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))

def forbidden(*args,**kwargs):raise AssertionError('native effect forbidden in source-only suite')
def audit(event,args):
    if event in ('subprocess.Popen','socket.__new__','os.system','os.posix_spawn'):forbidden()
    if event=='open' and args and isinstance(args[0],str) and (args[0].startswith('/proc/') or args[0].startswith('/sys/')):forbidden()

if __name__=='__main__':
    sys.addaudithook(audit)
    with patch.object(threading.Thread,'start',forbidden),patch.object(socket,'socket',forbidden),patch.object(subprocess,'Popen',forbidden):
        names=['test_cpu_harness','test_review_regressions','test_guarded_adapters','test_output_binding',
               'test_acquisition_source','test_final_kit','test_actions_wrapper','test_activation_scope','test_diagnostics']
        result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        if not result.wasSuccessful():raise SystemExit(1)
