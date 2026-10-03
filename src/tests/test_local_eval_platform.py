"""Linux-hosted platform mocks. These are NOT a Windows/GPU runtime test."""
import base64
import ctypes
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[2] / 'tools/local_eval'
sys.path.insert(0, str(TOOLS))
import resources
import run
import blind_review


class PlatformTests(unittest.TestCase):
    def test_windows_available_uses_real_physical_field(self):
        def api(pointer):
            self.assertEqual(pointer._obj.length, ctypes.sizeof(resources.MemoryStatus))
            pointer._obj.avail_phys = 9 * 1024**3
            pointer._obj.avail_page = 999 * 1024**3
            return 1
        self.assertEqual(resources.windows_available(SimpleNamespace(GlobalMemoryStatusEx=api)), 9 * 1024**3)

    def test_windows_available_failure(self):
        with self.assertRaises(OSError):
            resources.windows_available(SimpleNamespace(GlobalMemoryStatusEx=lambda p: 0))

    def test_windows_rss_owned_pointer_width_handle(self):
        def api(handle, pointer, size):
            self.assertEqual(handle.value, 0x1FFFFFFFF)
            self.assertEqual(size, ctypes.sizeof(resources.ProcessMemoryCounters))
            pointer._obj.working_set = 123456
            return 1
        self.assertEqual(resources.windows_rss(SimpleNamespace(_handle=0x1FFFFFFFF),
                          SimpleNamespace(GetProcessMemoryInfo=api)), 123456)

    def test_windows_rss_failure(self):
        with self.assertRaises(OSError):
            resources.windows_rss(SimpleNamespace(_handle=1), SimpleNamespace(GetProcessMemoryInfo=lambda *a: 0))

    def test_platform_dispatch(self):
        with patch.object(resources.sys, 'platform', 'win32'), patch.object(resources, 'windows_available', return_value=123):
            self.assertEqual(resources.memory_available(), 123)
        with patch.object(resources.sys, 'platform', 'win32'), patch.object(resources, 'windows_rss', return_value=456):
            self.assertEqual(resources.process_rss(Mock()), 456)
        with patch.object(resources.sys, 'platform', 'unknown'), self.assertRaises(OSError):
            resources.memory_available()

    def test_low_ram_terminates_only_owned_child(self):
        child = Mock(); child.poll.return_value = None
        monitor = resources.RamMonitor(child, 1000 * resources.MIB)
        with patch.object(resources, 'memory_available', return_value=767 * resources.MIB):
            self.assertFalse(monitor.sample())
        child.terminate.assert_called_once(); child.wait.assert_called_once_with(timeout=3)
        child.kill.assert_not_called()
        self.assertTrue(monitor.samples['resource_guard_stopped_process'])

    def test_ram_measurement_failure_is_fail_closed(self):
        for value in (None, -1):
            child = Mock(); child.poll.return_value = None
            monitor = resources.RamMonitor(child, 9999999999)
            with patch.object(resources, 'memory_available', return_value=value):
                self.assertFalse(monitor.sample())
            child.terminate.assert_called_once()
        child = Mock(); child.poll.return_value = None
        with patch.object(resources, 'memory_available', side_effect=OSError('gone')):
            self.assertFalse(resources.RamMonitor(child, 9999999999).sample())
        child.terminate.assert_called_once()

    def test_rss_failure_does_not_disable_ram_guard(self):
        child = Mock(); child.poll.return_value = None
        monitor = resources.RamMonitor(child, 9999999999)
        with patch.object(resources, 'memory_available', return_value=9999999999), patch.object(resources, 'process_rss', side_effect=OSError()):
            self.assertTrue(monitor.sample())
        self.assertIsNone(monitor.samples['peak_process_rss_bytes'])
        child.terminate.assert_not_called()

    def test_ended_child_not_terminated(self):
        child = Mock(); child.poll.return_value = 0
        resources.stop_owned(child)
        child.terminate.assert_not_called()
        self.assertFalse(resources.RamMonitor(child, 1).sample())

    def test_cleanup_escalates_and_is_bounded(self):
        child = Mock(); child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('owned', 3), 0]
        resources.stop_owned(child)
        child.kill.assert_called_once()
        self.assertEqual([x.kwargs for x in child.wait.call_args_list], [{'timeout': 3}, {'timeout': 3}])

    def test_nvidia_measurements_keep_pid_gpu_scope(self):
        probe = resources.NvidiaProbe('/verified/nvidia-smi', 0)
        probe.query = Mock(return_value=[['11','GPU-one','123'], ['22','GPU-one','900'], ['11','GPU-two','999']])
        self.assertEqual(probe.process_vram(11, 'GPU-one'), 123 * resources.MIB)
        self.assertIsNone(probe.process_vram(33, 'GPU-one'))
        probe.query.return_value = [['11','GPU-one','[N/A]']]
        self.assertIsNone(probe.process_vram(11, 'GPU-one'))

    def test_gpu_free_is_distinct_from_process_memory(self):
        probe = resources.NvidiaProbe('/verified/nvidia-smi', 1)
        probe.query = Mock(return_value=[['0','GPU-a','other','100','90','500'], ['1','GPU-b','NVIDIA','12000','9000','600']])
        self.assertEqual(probe.gpu()['free_bytes'], 9000 * resources.MIB)
        probe.query.return_value = [['1','GPU-b','NVIDIA','12000','N/A','600']]
        with self.assertRaises(ValueError):
            probe.gpu()

    def test_probe_no_shell_explicit_path_timeout(self):
        probe = resources.NvidiaProbe('/verified path/驱动/nvidia-smi.exe', 0)
        with patch.object(resources.subprocess, 'check_output', return_value='0, GPU-x, NVIDIA, 12000, 9000, 600\n') as output:
            self.assertEqual(probe.gpu()['uuid'], 'GPU-x')
        self.assertEqual(output.call_args.args[0][0], probe.executable)
        self.assertEqual(output.call_args.kwargs['timeout'], 3)
        self.assertNotIn('shell', output.call_args.kwargs)

    def test_portable_manifest_and_wire_tamper_rejected(self):
        archive = TOOLS.parents[1] / 'docs/local-eval/20261003-1.8b'
        meta, rows = blind_review.load_run(archive)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            meta['schema_version'] = 2
            (folder/'metadata.json').write_text(json.dumps(meta), encoding='utf-8')
            (folder/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            wires = []
            for row in rows:
                wire = {}
                for kind in ('request','response'):
                    raw = json.dumps(row[kind], ensure_ascii=False).encode('utf-8')
                    wire[kind+'_base64'] = base64.b64encode(raw).decode('ascii')
                    wire[kind+'_sha256'] = hashlib.sha256(raw).hexdigest()
                wires.append(wire)
            (folder/'wire.jsonl').write_text('\n'.join(json.dumps(w) for w in wires), encoding='utf-8')
            (folder/'server.log').write_text('synthetic', encoding='utf-8')
            manifest = {f.name: run.digest(f) for f in folder.iterdir()}
            (folder/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(len(blind_review.load_run(folder)[1]), 40)
            original_wire = (folder/'wire.jsonl').read_text(encoding='utf-8')
            wires[0]['response_base64'] = base64.b64encode(b'{}').decode('ascii')
            wires[0]['response_sha256'] = hashlib.sha256(b'{}').hexdigest()
            (folder/'wire.jsonl').write_text('\n'.join(json.dumps(w) for w in wires), encoding='utf-8')
            manifest['wire.jsonl'] = run.digest(folder/'wire.jsonl')
            (folder/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'content mismatch'):
                blind_review.load_run(folder)
            (folder/'wire.jsonl').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                blind_review.load_run(folder)

    def test_pair_rejects_schema_backend_runtime_helper_and_gpu_mismatch(self):
        import copy
        folder = TOOLS.parents[1] / 'docs/local-eval/20261003-1.8b'
        left, rows = blind_review.load_run(folder)
        left.update(schema_version=2, backend='cuda', gpu_layers=99,
                    runtime_files_sha256={'a.dll':'123'}, resource_probe_sha256='123',
                    gpu={'uuid':'GPU-a', 'name':'mock','total_bytes':123,'driver_version':'500'})
        for field, value in [('schema_version',1), ('backend','cpu'), ('gpu_layers',0),
                             ('runtime_files_sha256',{}), ('resource_probe_sha256','different'),
                             ('gpu',{'uuid':'GPU-b'})]:
            right = copy.deepcopy(left)
            right['model_sha256'] = 'different-model'
            right[field] = value
            with self.subTest(field=field), patch.object(blind_review, 'load_run', side_effect=[(left, rows),(right, rows)]):
                with self.assertRaises(ValueError):
                    blind_review.make_sheet(folder, folder)

    def mocked_run(self, failure=None):
        with tempfile.TemporaryDirectory(prefix='luna 空格 ') as tmp:
            root = Path(tmp); gguf = root/'模型.gguf'; server = root/'runtime 空格'/'llama-server.exe'
            server.parent.mkdir(); server.write_bytes(b'fake'); (server.parent/'ggml-cuda.dll').write_bytes(b'fake dll')
            with gguf.open('wb') as f:
                f.truncate(run.MODELS['1.8b'][0])
            out = root/'输出'
            (root/'nvidia-smi.exe').write_bytes(b'mocked driver tool')
            real_digest = run.digest
            def digest(path):
                return run.MODELS['1.8b'][1] if Path(path) == gguf else real_digest(path)
            child = Mock(pid=123); child.poll.return_value = None
            child.terminate.side_effect = lambda: setattr(child.poll, 'return_value', 0)
            alias = []
            def popen(cmd, **kwargs):
                alias.append(cmd[cmd.index('--alias')+1])
                startup = ('load: using device CUDA0 (Mock GPU) (mock-id) - 100 MiB free\n'
                           'load_tensors: offloaded 25/25 layers to GPU\n'
                           'load_tensors:        CUDA0 model buffer size = 100.00 MiB\n')
                if failure == 'security':
                    startup += 'W srv llama_server: security: no API key is set and CORS allows all origins\n'
                elif failure == 'proof':
                    startup = 'model loaded, listening on loopback\n'
                kwargs['stdout'].write(startup); kwargs['stdout'].flush()
                return child
            def response(request, timeout):
                if request.full_url.endswith('health'):
                    data = {'status':'ok'}
                elif request.full_url.endswith('v1/models'):
                    data = {'data':[{'id':alias[0]}]}
                else:
                    if failure == 'late_security':
                        with (out/'server.log').open('a', encoding='utf-8') as log:
                            log.write('W srv security: synthetic later warning\n')
                    data = {'model':alias[0], 'choices':[{'finish_reason':'stop','message':{'content':'合成测试'}}]}
                return io.BytesIO(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            opener = Mock(); opener.open.side_effect = response
            gpu = {'uuid':'GPU-test', 'index':0, 'name':'Mock GPU', 'driver_version':'mock', 'total_bytes':20*1024**3, 'free_bytes':19*1024**3}
            monitor = resources.RamMonitor(child, 10*1024**3)
            if failure == 'startup':
                monitor.thread.start = Mock(side_effect=RuntimeError('start failed'))
            elif failure == 'guard':
                monitor.thread.start = Mock(side_effect=lambda: monitor.samples.update(resource_guard_stopped_process=True))
            stop = Mock(side_effect=RuntimeError('cleanup failed')) if failure == 'cleanup' else resources.stop_owned
            argv = ['run.py','--model','1.8b','--gguf',str(gguf),'--server',str(server),'--out',str(out), '--restrict-cors-to-loopback','--backend','cuda','--nvidia-smi',str(root/'nvidia-smi.exe')]
            with patch.object(sys,'argv',argv), patch.object(run,'digest',side_effect=digest), patch.object(run,'memory_available',return_value=10*1024**3), patch.object(resources,'memory_available',return_value=10*1024**3), patch.object(resources,'process_rss',return_value=1234), patch.object(run.NvidiaProbe,'gpu',return_value=gpu), patch.object(run.NvidiaProbe,'process_vram',return_value=None), patch.object(run.subprocess,'check_output',return_value='build 11349, commit fb4b2737a'), patch.object(run.subprocess,'Popen',side_effect=popen) as launch, patch.object(run.urllib.request,'build_opener',return_value=opener), patch('builtins.print'), patch.object(run, 'RamMonitor', return_value=monitor), patch.object(run, 'stop_owned', side_effect=stop):
                previous = run.os.environ.get('CUDA_VISIBLE_DEVICES')
                if failure:
                    with self.assertRaises(RuntimeError):
                        run.main()
                else:
                    run.main()
                self.assertEqual(run.os.environ.get('CUDA_VISIBLE_DEVICES'), previous)
            cmd = launch.call_args.args[0]
            self.assertEqual(cmd[cmd.index('-m')+1], str(gguf.resolve()))
            self.assertEqual(launch.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'], 'GPU-test')
            self.assertEqual(cmd[cmd.index('-ngl')+1], '99')
            self.assertLess(cmd.index('-lv'), cmd.index('--device'))
            self.assertEqual(cmd[cmd.index('-lv')+1], '4')
            self.assertIn('--no-warmup', cmd)
            self.assertEqual(cmd[cmd.index('--cors-origins')+1], 'http://127.0.0.1:' + cmd[cmd.index('--port')+1])
            if failure:
                meta = json.loads((out/'metadata.json').read_text(encoding='utf-8'))
                self.assertEqual(meta['status'], 'incomplete')
                if failure in ('startup', 'guard', 'security', 'proof'):
                    self.assertFalse((out/'results.jsonl').exists())
                    child.terminate.assert_called_once()
                    self.assertFalse(any(c.args[0].full_url.endswith('v1/chat/completions') for c in opener.open.call_args_list))
                elif failure == 'late_security':
                    child.terminate.assert_called_once()
                    self.assertEqual(sum(c.args[0].full_url.endswith('v1/chat/completions') for c in opener.open.call_args_list), 1)
                    self.assertIn('security warning', meta['failure'])
                else:
                    self.assertIn('cleanup failed', meta['cleanup_error'])
                return
            meta, rows = blind_review.load_run(out)
            self.assertEqual(meta['status'], 'complete'); self.assertEqual(len(rows),40)
            self.assertIsNone(meta['peak_process_vram_bytes'])
            self.assertIn('ggml-cuda.dll', meta['runtime_files_sha256'])
            self.assertEqual(meta['fixture_sha256'], run.FIXTURE_SHA)
            self.assertEqual(meta['startup_checks']['cuda_proof']['offloaded_layers'], 25)
            self.assertEqual(meta['startup_checks']['security_warning_gate'], 'passed')
            self.assertFalse(meta['runtime_warmup'])
            self.assertGreater(meta['timing_clock']['resolution'], 0)

    def test_full_mocked_cuda_run_unicode_paths_raw_bytes_and_child_env(self):
        self.mocked_run()

    def test_startup_security_warning_prevents_all_corpus_requests(self):
        self.mocked_run('security')

    def test_late_security_warning_stops_before_next_corpus_request(self):
        self.mocked_run('late_security')

    def test_missing_gpu_proof_prevents_all_corpus_requests(self):
        self.mocked_run('proof')

    def test_missing_cors_approval_stops_before_any_runtime_execution(self):
        argv = ['run.py', '--model', '1.8b', '--gguf', 'unused', '--server', 'unused', '--out', 'unused']
        with patch.object(sys, 'argv', argv), patch.object(run.subprocess, 'Popen') as launch, patch.object(run.subprocess, 'check_output') as probe, patch.object(sys, 'stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main()
        launch.assert_not_called(); probe.assert_not_called()

    def test_startup_proof_rejects_enumeration_host_buffers_and_zero_offload(self):
        good = ('using device CUDA0 (Mock) (id) - 100 MiB free\n'
                'offloaded 25/25 layers to GPU\n'
                'CUDA0 model buffer size = 100.00 MiB\n')
        bad = ['', good.replace('using device CUDA0', 'Found device CUDA0'),
               good.replace('25/25', '0/25'), good.replace('25/25', '26/25'),
               good.replace('CUDA0 model buffer', 'CUDA_Host model buffer'),
               good.replace('100.00', '0.00'), good + 'security: unexpected warning\n']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'server.log'
            for value in bad:
                path.write_text(value, encoding='utf-8')
                with self.subTest(value=value), self.assertRaises(RuntimeError):
                    run.check_startup_log(path, cuda=True, require_gpu=True)
            path.write_text(good, encoding='utf-8')
            self.assertEqual(run.check_startup_log(path, cuda=True, require_gpu=True)['offloaded_layers'], 25)

    def test_cleanup_failure_cannot_complete(self):
        self.mocked_run('cleanup')

    def test_monitor_startup_failure_cleans_owned_child(self):
        self.mocked_run('startup')

    def test_guard_stopped_run_makes_no_requests(self):
        self.mocked_run('guard')


if __name__ == '__main__':
    unittest.main()
