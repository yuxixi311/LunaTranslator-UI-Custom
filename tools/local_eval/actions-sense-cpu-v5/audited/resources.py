"""Read-only resource probes. Unknown measurements stay unknown, never zero.

Windows uses native, non-privileged APIs; no packages, services or driver changes.
NVIDIA probes use only an explicitly supplied, independently verified driver tool.
"""
import csv
import ctypes
import io
from pathlib import Path
import subprocess
import sys
import threading

MIB = 1024 ** 2


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
        (n, ctypes.c_uint64) for n in ('total_phys', 'avail_phys', 'total_page',
                                     'avail_page', 'total_virtual', 'avail_virtual', 'avail_extended')]


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_uint32), ('page_faults', ctypes.c_uint32)] + [
        (n, ctypes.c_size_t) for n in ('peak_working_set', 'working_set', 'quota_peak_paged',
        'quota_paged', 'quota_peak_nonpaged', 'quota_nonpaged', 'pagefile', 'peak_pagefile')]


def windows_available(kernel=None):
    kernel = kernel or ctypes.WinDLL('kernel32', use_last_error=True)
    if hasattr(kernel.GlobalMemoryStatusEx, 'argtypes'):
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
        kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
    state = MemoryStatus()
    state.length = ctypes.sizeof(state)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError('GlobalMemoryStatusEx failed')
    return state.avail_phys


def windows_rss(proc, psapi=None):
    # Popen owns this handle. Never open an arbitrary PID or close Popen's handle.
    psapi = psapi or ctypes.WinDLL('psapi', use_last_error=True)
    if hasattr(psapi.GetProcessMemoryInfo, 'argtypes'):
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_uint32]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(ctypes.c_void_p(int(proc._handle)),
                                      ctypes.byref(counters), counters.cb):
        raise OSError('GetProcessMemoryInfo failed')
    return counters.working_set


def memory_available():
    if sys.platform == 'win32':
        return windows_available()
    if sys.platform.startswith('linux'):
        for line in Path('/proc/meminfo').read_text(encoding='ascii').splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024
    raise OSError('No available-physical-RAM probe for this platform')


def process_rss(proc):
    if sys.platform == 'win32':
        return windows_rss(proc)
    if sys.platform.startswith('linux'):
        for line in Path('/proc/%d/status' % proc.pid).read_text(encoding='ascii').splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    return None


def stop_owned(proc):
    """Only the supplied Popen child; no process names, groups or unrelated PIDs."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


class RamMonitor:
    def __init__(self, proc, available):
        self.proc = proc
        self.stop = threading.Event()
        self.samples = {'peak_process_rss_bytes': None, 'rss_sample_count': 0,
                        'minimum_available_ram_bytes': available,
                        'resource_guard_stopped_process': False, 'resource_guard_reason': None}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def sample(self):
        if self.proc.poll() is not None:
            return False
        try:
            current = memory_available()
            if not isinstance(current, int) or current < 0:
                raise OSError('Invalid available RAM')
            self.samples['minimum_available_ram_bytes'] = min(self.samples['minimum_available_ram_bytes'], current)
            reason = 'available RAM below 768 MiB' if current < 768 * MIB else None
        except (OSError, ValueError, TypeError) as exc:
            reason = 'available RAM probe failed: ' + str(exc)
        if reason:
            self.samples['resource_guard_stopped_process'] = True
            self.samples['resource_guard_reason'] = reason
            stop_owned(self.proc)
            return False
        try:
            rss = process_rss(self.proc)
            if rss is not None:
                self.samples['peak_process_rss_bytes'] = max(self.samples['peak_process_rss_bytes'] or 0, rss)
                self.samples['rss_sample_count'] += 1
        except (OSError, ValueError):
            pass  # RSS observation is optional; never skip the independent RAM guard.
        return True

    def run(self):
        while not self.stop.is_set() and self.sample():
            self.stop.wait(.05)


class NvidiaProbe:
    def __init__(self, executable, device):
        self.executable = str(Path(executable).resolve())
        self.device = device

    def query(self, kind, fields):
        text = subprocess.check_output([self.executable, '--query-' + kind + '=' + fields,
            '--format=csv,noheader,nounits'], timeout=3, encoding='utf-8', errors='strict')
        return list(csv.reader(io.StringIO(text), skipinitialspace=True))

    def gpu(self):
        rows = self.query('gpu', 'index,uuid,name,memory.total,memory.free,driver_version')
        for row in rows:
            if len(row) == 6 and row[0] == str(self.device):
                return {'index': int(row[0]), 'uuid': row[1], 'name': row[2],
                        'total_bytes': int(row[3]) * MIB, 'free_bytes': int(row[4]) * MIB,
                        'driver_version': row[5]}
        raise ValueError('Selected NVIDIA GPU is missing or has unavailable memory measurements')

    def process_vram(self, pid, uuid):
        # WDDM commonly reports N/A. Whole-device usage must NOT fill this gap.
        rows = self.query('compute-apps', 'pid,gpu_uuid,used_gpu_memory')
        values = []
        for row in rows:
            if len(row) == 3 and row[0] == str(pid) and row[1] == uuid:
                try:
                    values.append(int(row[2]) * MIB)
                except ValueError:
                    return None
        return sum(values) if values else None


class GpuMonitor:
    def __init__(self, proc, probe, uuid):
        self.proc, self.probe, self.uuid = proc, probe, uuid
        self.stop = threading.Event()
        self.samples = {'peak_process_vram_bytes': None, 'vram_sample_count': 0,
                        'vram_probe_errors': 0, 'vram_scope': 'owned server PID on selected GPU only'}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set() and self.proc.poll() is None:
            try:
                value = self.probe.process_vram(self.proc.pid, self.uuid)
                if value is not None:
                    self.samples['peak_process_vram_bytes'] = max(self.samples['peak_process_vram_bytes'] or 0, value)
                    self.samples['vram_sample_count'] += 1
            except (OSError, ValueError, subprocess.SubprocessError):
                self.samples['vram_probe_errors'] += 1
            self.stop.wait(1)
