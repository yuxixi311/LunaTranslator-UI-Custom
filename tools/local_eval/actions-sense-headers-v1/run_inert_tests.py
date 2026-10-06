"""Fake-only verification: native process/socket/thread starts are forbidden."""
from pathlib import Path
import resource
import socket
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))

def forbidden(*args,**kwargs):raise AssertionError('native action forbidden in source-only tests')
def audit(event,args):
    if event in ('subprocess.Popen','socket.__new__','socket.getaddrinfo','os.system','os.posix_spawn','os.fork'):forbidden()
    if event=='open' and args and isinstance(args[0],str) and args[0].startswith(('/proc/','/sys/')):forbidden()

if __name__=='__main__':
    sys.addaudithook(audit)
    with patch.object(threading.Thread,'start',forbidden),patch.object(socket,'socket',forbidden),\
         patch.object(socket,'getaddrinfo',forbidden),patch.object(subprocess,'Popen',forbidden),\
         patch.object(resource,'setrlimit',forbidden):
        result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(['test_header_logic','test_probe_entry']))
        if not result.wasSuccessful():raise SystemExit(1)
