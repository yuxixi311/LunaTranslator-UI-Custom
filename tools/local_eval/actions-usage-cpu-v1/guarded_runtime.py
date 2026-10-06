"""CPU runtime adapters denied until verified Actions/owned-worker admission.

Native calls require the process-bound role installed by the reviewed bootstrap.
The source-read gate alone grants no runtime permission. Generic claim/CLI entry
points remain disabled. Lifecycle, request, resource and deadline controls remain
active after admission. This preparation has run only inert synthetic tests.
"""
from dataclasses import dataclass
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from types import ModuleType

import activation_scope
import cpu_harness as core
import frozen_renderer as renderer


HERE = Path(__file__).resolve().parent
ROOT = HERE
CLAIM_ROOT = HERE / '__UNBOUND_ACTIONS_STATE__'
BOUND_ROOTS = None
AUDITED = HERE / 'audited'
PERSISTENCE_CHECKPOINT = None
COORDINATOR_CANCEL_EVENT = None


def bind_actions_roots(roots):
    global ROOT,CLAIM_ROOT,BOUND_ROOTS
    require_activation()
    import actions_policy
    parsed=actions_policy.validate_roots(roots)
    core.require(parsed['source']==HERE and (BOUND_ROOTS is None or BOUND_ROOTS==roots),'source location/rebinding')
    ROOT=parsed['source'];CLAIM_ROOT=parsed['state'];BOUND_ROOTS=dict(roots)
    core.OUTPUT_POLICY['fixed_root']=str(CLAIM_ROOT)


def persistence_checkpoint():
    if PERSISTENCE_CHECKPOINT is not None:PERSISTENCE_CHECKPOINT()


class WireCapture:
    """Per-response temporary bounded wire buffer; persisted outside arm time."""
    def __init__(self):
        self.raw=bytearray()
    def retain(self,data):
        core.require(len(self.raw)+len(data)<=98304,'temporary wire cap')
        self.raw.extend(data)


def require_activation():
    try:return activation_scope.require_role('actions','acquire','validate')
    except activation_scope.Denied as exc:raise core.Disabled(str(exc)) from None



def bounded_file(path, cap):
    """Local byte reader; never silently accepts a truncated file."""
    require_activation()
    with open(path, 'rb') as stream:
        raw = stream.read(cap + 1)
    core.require(len(raw) <= cap, 'local file cap')
    return raw


def pinned_file(path, pin, cap):
    raw = bounded_file(path, cap)
    core.require(core.digest(raw) == pin, 'local frozen hash mismatch')
    return raw


def load_audited_components():
    require_activation()
    verified={}
    for path, pin in (('resources.py', 'resources'), ('myutils/local_translation.py', 'integrity_dependency'),
                      ('myutils/local_translation_integrity.py', 'integrity')):
        verified[path]=pinned_file(AUDITED/path, core.PINS[pin], 65536)
    core.require(bounded_file(AUDITED/'myutils/__init__.py',1)==b'','package init must be verified empty bytes')
    core.require(not any(name in sys.modules for name in ('resources','myutils','myutils.local_translation',
                  'myutils.local_translation_integrity')), 'ambiguous preloaded dependency')
    package=ModuleType('myutils');package.__path__=[]
    sys.modules['myutils']=package
    loaded={}
    try:
        for name,path in (('resources','resources.py'),('myutils.local_translation','myutils/local_translation.py'),
                          ('myutils.local_translation_integrity','myutils/local_translation_integrity.py')):
            module=ModuleType(name);module.__file__=str(AUDITED/path)
            module.__package__=name.rpartition('.')[0]
            sys.modules[name]=module
            exec(compile(verified[path],module.__file__,'exec'),module.__dict__)
            loaded[name]=module
    except BaseException:
        for name in ('resources','myutils.local_translation','myutils.local_translation_integrity','myutils'):
            sys.modules.pop(name,None)
        raise
    resources=loaded['resources'];dependency=loaded['myutils.local_translation'];integrity=loaded['myutils.local_translation_integrity']
    return resources, dependency.LocalTranslationError, integrity.validate_integrity


def persistent_write(fd, data):
    require_activation()
    while data:
        persistence_checkpoint()
        n = os.write(fd, data)
        core.require(n > 0, 'persistent short write')
        data = data[n:]
    persistence_checkpoint();os.fsync(fd);persistence_checkpoint()


def claim_once(plan):
    """Source implementation of the single FIXED production claim location."""
    raise core.Disabled('Generic claim entry is disabled; reviewed coordinator only')
    core.validate_claim_plan(plan)
    data=core.canonical(plan)
    core.require(len(data)<=32768,'immutable claim cap')
    root_fd = os.open(CLAIM_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        claim_fd = os.open('ONE_SHOT_CPU_ATTEMPT.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=root_fd)
        try:
            persistent_write(claim_fd, data)
        finally:
            os.close(claim_fd)
        os.fsync(root_fd)
        # If this creation fails, the immutable claim remains consumed.
        event_fd = os.open('ONE_SHOT_CPU_EVENTS.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
        os.fsync(root_fd)
        return event_fd
    finally:
        os.close(root_fd)


class EvidenceFiles:
    """One synchronized 64 MiB budget for every retained evidence/log byte."""
    def __init__(self, output, *, initial_claim_size, initial_arm_key_size=0):
        self.output = Path(output)
        self.budget = core.EvidenceBudget()
        self.lock = threading.RLock()
        self.files = {}
        self.file_bytes={}
        core.require(type(initial_claim_size) is int and 0<initial_claim_size<=32768 and
                     type(initial_arm_key_size) is int and initial_arm_key_size==0,
                     'verified claim size; no runner arm key in public protocol')
        self.budget.retain(b'\0'*(initial_claim_size+initial_arm_key_size))

    @classmethod
    def from_claim(cls,plan):
        require_activation()
        core.validate_claim_plan(plan)
        claim=bounded_file(CLAIM_ROOT/'ONE_SHOT_CPU_ATTEMPT.json',32768)
        core.require(claim==core.canonical(plan),'immutable claim binding')
        return cls(plan['paths']['output'],initial_claim_size=len(claim))

    def create(self, name):
        require_activation()
        core.require(name not in self.files and '..' not in Path(name).parts and not Path(name).is_absolute(), 'evidence filename')
        core.require(name in core.OUTPUT_POLICY['output_files'],'unclaimed output filename')
        fd = os.open(self.output/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.files[name] = fd
        self.file_bytes[name]=0

    def append(self, name, data):
        require_activation()
        with self.lock:
            core.require(name in self.files and self.file_bytes[name]+len(data)<=
                         core.OUTPUT_POLICY['output_files'][name]['max_bytes'],'per-file output cap')
            self.budget.retain(data)  # Reserve before retaining/writing.
            self.file_bytes[name]+=len(data)
            persistent_write(self.files[name], data)

    def json(self, name, value):
        self.append(name, core.canonical(value) + b'\n')

    def close(self):
        require_activation()
        errors=[]
        with self.lock:
            for fd in self.files.values():
                try:persistence_checkpoint();os.fsync(fd)
                except BaseException as exc:errors.append('fsync: '+type(exc).__name__)
                try:os.close(fd)
                except BaseException as exc:errors.append('close: '+type(exc).__name__)
            self.files.clear()
        core.require(not errors,'evidence descriptors unconfirmed: '+str(errors))


@dataclass
class Intent:
    name: str
    spec: dict
    deadline: float
    pending: bool = True
    process: object = None
    exit_confirmed: bool = False


class OwnedSupervisor:
    """Native source adaptation of audited owned-child/deadline lifecycle."""
    def __init__(self, claimed_at, journal, evidence, resources, staging, *, full_cgroup_ancestry_verified=False):
        self.outer_end = claimed_at + 1475
        self.lifecycle_end = None
        self.work_end = None
        self.postready_end = None
        self.phase_end = self.outer_end
        self.journal, self.evidence, self.resources = journal, evidence, resources
        self.staging = Path(staging)
        self.full_cgroup_ancestry_verified=full_cgroup_ancestry_verified
        self.lock = threading.RLock()
        self.intents, self.connections, self.readers = {}, set(), []
        self.failure, self.failure_at = None, None
        self.stop_event = threading.Event()
        self.monitor = None
        self.deadline_monitor = None
        self.cleanup_errors = []
        self.loaded = threading.Event()
        self.peak_server_rss, self.peak_runner_rss = 0, 0
        self.security_warning = False
        self.diagnostic=None

    def record(self, event):
        require_activation()
        # A stalled write must never hold the ownership lock used by fail().
        with self.evidence.lock:
            data = core.canonical(event) + b'\n'
            self.evidence.budget.retain(data)
            persistent_write(self.journal, data)

    def arm(self):
        require_activation()
        core.require(self.monitor is None, 'one supervisor monitor')
        self.deadline_monitor=threading.Thread(target=self._watch_deadlines,name='owned-absolute-watchdog',daemon=True)
        self.deadline_monitor.start()
        self.monitor = threading.Thread(target=self._watch, name='owned-resource-watchdog', daemon=True)
        self.monitor.start()

    def check(self):
        require_activation()
        core.require(COORDINATOR_CANCEL_EVENT is None or not COORDINATOR_CANCEL_EVENT.is_set(),
                     'independent coordinator cancellation')
        core.require(self.failure is None, 'attempt failed: ' + str(self.failure))
        now = time.monotonic()
        bounds = [self.outer_end, self.phase_end]
        if self.work_end is not None:
            bounds.append(self.work_end)
        if self.postready_end is not None:
            bounds.append(self.postready_end)
        core.require(now < min(bounds), 'phase/global deadline')
        core.require(not self.security_warning, 'runtime security warning')

    def set_phase(self, name, seconds):
        require_activation()
        if self.diagnostic:self.diagnostic.enter(name)
        self.check()
        self.phase_end = min(time.monotonic() + seconds, self.outer_end,
                             self.work_end or self.outer_end, self.postready_end or self.outer_end)
        self.record(dict(event='phase', name=name, deadline=self.phase_end))

    def launch(self, name, spec, seconds, log_name):
        require_activation()
        self.check()
        with self.lock:
            core.require(self.monitor is not None and self.monitor.is_alive() and
                         self.deadline_monitor is not None and self.deadline_monitor.is_alive(), 'watchdog not armed')
            core.require(name not in self.intents, 'launch already consumed')
            before = time.monotonic()
            if name == 'server':
                core.require(self.lifecycle_end is None, 'second server forbidden')
                self.lifecycle_end = min(before + 800, self.outer_end)
                self.work_end = min(before + 780, self.outer_end)
            deadline = min(before + seconds, self.phase_end, self.outer_end, self.work_end or self.outer_end,
                           self.postready_end or self.outer_end)
            intent = Intent(name, spec, deadline)
            self.intents[name] = intent
            if self.diagnostic:self.diagnostic.child(name,launch='INTENT')
            self.phase_end = deadline
        try:
            self.record(dict(event='launch_intent', name=name, spec=spec, deadline=deadline,
                             pending_handle=True, watchdog_armed=True, stdout=log_name))
            self.check()  # A watchdog may have fired while the journal blocked.
        except BaseException:
            self.fail('launch intent journal failed or expired: '+name)
            raise
        # No lock spans Popen: the independent watchdog can observe pending state.
        try:
            if self.diagnostic:self.diagnostic.child(name,launch='PENDING')
            proc = subprocess.Popen(spec['argv'], executable=spec['executable'], cwd=spec['cwd'],
                env=spec['env'], shell=False, close_fds=True, pass_fds=(), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except BaseException as exc:
            if self.diagnostic:
                self.diagnostic.child(name,launch='ERROR_UNCONFIRMED');self.diagnostic.fail(exc,code='CHILD_SETUP_FAILURE')
            self.fail('launch outcome unknown: ' + name)
            raise
        with self.lock:
            intent.process, intent.pending = proc, False
            if self.diagnostic:self.diagnostic.child(name,launch='RETURNED',adopted=True,exit='RUNNING')
            late = self.failure is not None or time.monotonic() >= deadline
        if late:
            self.fail('late Popen return: ' + name)
            self._stop(intent)
            raise core.TerminalFailure('late child adopted and stopped')
        try:
            reader = threading.Thread(target=self._read_log, args=(intent, log_name),
                                      name='owned-log-' + name, daemon=True)
            self.readers.append(reader)
            reader.start()
            self.record(dict(event='child_adopted', name=name, pid=proc.pid))
        except BaseException as exc:
            if self.diagnostic:self.diagnostic.fail(exc,code='CHILD_SETUP_FAILURE')
            self.fail('post-adoption setup failed: '+name)
            raise
        return proc

    def _read_log(self, intent, name):
        require_activation()
        carry, retained = b'', 0
        cap = 65536 if intent.name in ('version', 'validation','helper') else 64*core.MIB
        try:
            while True:
                data = os.read(intent.process.stdout.fileno(), 8192)
                if not data:
                    return
                core.require(retained + len(data) <= cap, 'child diagnostic/log cap')
                retained += len(data)
                self.evidence.append(name, data)
                text = (carry + data).decode('utf-8', errors='replace')
                if re.search(r'(?im)^.*\bsecurity\s*:', text):
                    self.security_warning = True
                    self.fail('runtime security warning')
                    return
                if intent.name == 'server' and 'model loaded' in text:
                    self.loaded.set()
                carry = (carry + data)[-4096:]
        except BaseException as exc:
            self.fail('log reader: ' + type(exc).__name__)

    def _watch(self):
        require_activation()
        while not self.stop_event.wait(.05):
            try:
                self.check()
                host = self.resources.memory_available()
                runner_rss=self.resources.process_rss(SimpleNamespace(pid=os.getpid()))
                core.require(type(runner_rss) is int,'runner RSS unknown')
                self.peak_runner_rss=max(self.peak_runner_rss,runner_rss)
                effective = cgroup_headroom(host,hierarchy_root_verified=self.full_cgroup_ancestry_verified)
                rss = 0
                server = self.intents.get('server')
                if server and server.process is not None:
                    core.require(server.process.poll() is None, 'owned server exited')
                    rss = self.resources.process_rss(server.process)
                    core.require(type(rss) is int, 'owned server RSS unknown')
                    self.peak_server_rss = max(self.peak_server_rss, rss)
                free = shutil.disk_usage(self.staging).free
                # Growth measurement below is bounded by known owned files only.
                growth = owned_growth(self.staging)
                core.resource_gate(host, effective, rss=rss, free_disk=free, growth=growth)
                for intent in tuple(self.intents.values()):
                    if intent.pending and time.monotonic() >= intent.deadline:
                        raise core.TerminalFailure('pending launch deadline')
            except BaseException as exc:
                if self.diagnostic:self.diagnostic.fail(exc,code='RESOURCE_GUARD_FAILED')
                self.fail(type(exc).__name__ + ': ' + str(exc))
                return

    def _watch_deadlines(self):
        require_activation()
        # No resource probes, file writes, Popen or socket reads on this thread.
        # It remains available while those independent operations are blocked.
        while not self.stop_event.wait(.01):
            try:
                self.check()
                for intent in tuple(self.intents.values()):
                    core.require(not intent.pending or time.monotonic()<intent.deadline,'pending Popen deadline')
            except BaseException as exc:
                if self.diagnostic:self.diagnostic.fail(exc)
                self.fail('absolute watchdog: '+type(exc).__name__)
                return

    def _stop(self, intent):
        require_activation()
        proc = intent.process
        if self.diagnostic:self.diagnostic.child(intent.name,cleanup='REQUESTED')
        if proc is None:
            return
        cleanup_end = min((self.failure_at if self.failure_at is not None else time.monotonic()) + 20, self.outer_end,
                          self.lifecycle_end or self.outer_end)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=max(.001, min(3, cleanup_end-time.monotonic())))
            except subprocess.TimeoutExpired:
                if self.diagnostic:self.diagnostic.child(intent.name,timeout=True)
                proc.kill()
                proc.wait(timeout=max(.001, min(3, cleanup_end-time.monotonic())))
        exit_code=proc.poll();intent.exit_confirmed = exit_code is not None
        if self.diagnostic:self.diagnostic.child(intent.name,exit='EXITED' if intent.exit_confirmed else 'UNKNOWN',
            exit_code=exit_code,cleanup='CONFIRMED' if intent.exit_confirmed else 'UNCONFIRMED')

    def fail(self, cause):
        require_activation()
        with self.lock:
            if self.failure is None:
                if self.diagnostic:self.diagnostic.fail(code='OWNER_FAILURE')
                self.failure, self.failure_at = cause, time.monotonic()
            connections, intents = tuple(self.connections), tuple(self.intents.values())
        # Close connections before process waits so a blocked read wakes promptly.
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:connection.close()
            except BaseException as exc:self.cleanup_errors.append('socket close: '+type(exc).__name__)
        for intent in intents:
            try:
                self._stop(intent)
            except BaseException as exc:
                self.cleanup_errors.append('owned stop: '+type(exc).__name__)

    def finalize(self):
        require_activation()
        start = self.failure_at if self.failure_at is not None else time.monotonic()
        end = min(start+20, self.outer_end, self.lifecycle_end or self.outer_end)
        self.stop_event.set()
        unresolved = list(self.cleanup_errors)
        for intent in self.intents.values():
            try:
                self._stop(intent)
            except BaseException:
                pass
            if intent.pending or not intent.exit_confirmed:
                if self.diagnostic:
                    self.diagnostic.cleanup_issue('PENDING_LAUNCH' if intent.pending else 'CHILD_EXIT_UNCONFIRMED')
                    self.diagnostic.child(intent.name,cleanup='UNCONFIRMED')
                unresolved.append(intent.name + ':unknown OS outcome')
        for thread in [*self.readers, self.monitor,self.deadline_monitor]:
            if thread is None or thread is threading.current_thread():
                continue
            try:
                thread.join(timeout=max(0, end-time.monotonic()))
                if thread.is_alive():
                    if self.diagnostic:self.diagnostic.cleanup_issue('THREAD_JOIN_UNCONFIRMED')
                    unresolved.append(thread.name + ':join incomplete')
            except BaseException as exc:
                if self.diagnostic:self.diagnostic.cleanup_issue('THREAD_JOIN_UNCONFIRMED')
                unresolved.append(thread.name + ':join raised '+type(exc).__name__)
        for intent in self.intents.values():
            if intent.process and intent.process.stdout:
                try:intent.process.stdout.close()
                except BaseException as exc:
                    if self.diagnostic:self.diagnostic.cleanup_issue('PIPE_CLOSE_FAILED')
                    unresolved.append('pipe close: '+type(exc).__name__)
        for connection in tuple(self.connections):
            try:connection.close()
            except BaseException as exc:
                if self.diagnostic:self.diagnostic.cleanup_issue('SOCKET_CLOSE_FAILED')
                unresolved.append('socket close: '+type(exc).__name__)
        if time.monotonic() >= end:
            if self.diagnostic:self.diagnostic.cleanup_issue('DEADLINE_EXPIRED')
            unresolved.append('cleanup deadline')
        status = dict(status='incomplete' if self.failure or unresolved else 'operationally_complete',
                      cause=self.failure, unresolved=unresolved, cleanup_confirmed=not unresolved)
        try:
            self.record(dict(event='terminal', **status))
            self.evidence.json('metadata.json', status)
            core.require(time.monotonic() < end, 'finalization late')
        except BaseException:
            status.update(status='incomplete', cleanup_confirmed=False)
            status['unresolved'].append('evidence finalization incomplete')
            if self.diagnostic:self.diagnostic.cleanup_issue('EVIDENCE_FINALIZE_FAILED')
        try:self.evidence.close()
        except BaseException:
            status.update(status='incomplete',cleanup_confirmed=False)
            status['unresolved'].append('evidence close incomplete')
            if self.diagnostic:self.diagnostic.cleanup_issue('EVIDENCE_CLOSE_FAILED')
        return status


def cgroup_headroom(host_available, *, hierarchy_root_verified=False):
    """Known cgroup-v2 ancestry only; unsupported/ambiguous layouts fail closed."""
    require_activation()
    core.require(hierarchy_root_verified is True,'full cgroup hierarchy/namespace visibility unverified')
    entries = bounded_file('/proc/self/cgroup', 16384).decode('ascii').splitlines()
    core.require(len(entries) == 1 and entries[0].startswith('0::/'), 'unsupported cgroup layout')
    relative = entries[0][3:]
    core.require('..' not in Path(relative).parts, 'cgroup traversal')
    mounts = bounded_file('/proc/self/mountinfo', 131072).decode('ascii').splitlines()
    candidates = []
    for line in mounts:
        left, separator, right = line.partition(' - ')
        if separator and right.split()[0] == 'cgroup2':
            fields = left.split()
            core.require(len(fields) >= 5 and '\\' not in fields[3]+fields[4], 'encoded cgroup mount')
            candidates.append((fields[3], fields[4]))
    core.require(len(candidates) == 1, 'ambiguous cgroup mount')
    mount_root, mount_point = map(Path, candidates[0])
    core.require(mount_root==Path('/'),'incomplete cgroup ancestry is unknown')
    try:
        local = Path(relative).relative_to(mount_root)
    except ValueError as exc:
        raise core.TerminalFailure('cgroup path outside mounted root') from exc
    current, root = mount_point/local, mount_point
    headrooms = [host_available]
    for _ in range(128):
        if current==root:
            return min(headrooms)  # True hierarchy root has no memory.max/current.
        maximum = bounded_file(current/'memory.max', 128).strip()
        usage = bounded_file(current/'memory.current', 128).strip()
        core.require(re.fullmatch(rb'[0-9]+', usage), 'cgroup usage unknown')
        if maximum != b'max':
            core.require(re.fullmatch(rb'[0-9]+', maximum), 'cgroup limit unknown')
            headrooms.append(max(0, int(maximum)-int(usage)))
        current = current.parent
    raise core.TerminalFailure('cgroup ancestry cap')


def owned_growth(root):
    require_activation()
    total, count = 0, 0
    def scan_error(exc):raise exc
    for current, dirs, files in os.walk(root, followlinks=False,onerror=scan_error):
        count += len(dirs) + len(files)
        core.require(count <= 2048, 'owned staging file-count cap')
        for name in files:
            path = Path(current)/name
            if not path.is_symlink():
                total += path.stat().st_size
                core.require(total <= 2*core.GIB, 'owned disk growth cap')
    return total


class RequestWatchdog:
    def __init__(self, supervisor, deadline):
        self.supervisor, self.deadline = supervisor, deadline
        self.event = threading.Event()
        self.thread = None

    def start(self):
        require_activation()
        self.thread = threading.Thread(target=self.run, name='owned-request-watchdog', daemon=True)
        self.thread.start()

    def run(self):
        require_activation()
        if not self.event.wait(max(0, self.deadline.end-time.monotonic())):
            self.supervisor.fail('absolute request deadline')

    def cancel(self):
        require_activation()
        self.event.set()

    def join(self, timeout=7):
        require_activation()
        if self.thread:
            self.thread.join(timeout=max(0,min(7,timeout)))

    def is_alive(self):
        return bool(self.thread and self.thread.is_alive())


class OwnedSocketReader:
    def __init__(self, connection, supervisor):
        self.connection, self.supervisor = connection, supervisor

    def read(self, n, remaining):
        require_activation()
        self.supervisor.check()
        self.connection.settimeout(remaining)
        return self.connection.recv(min(n, 8192))

    def close(self):
        require_activation()
        self.connection.close()
        with self.supervisor.lock:
            self.supervisor.connections.discard(self.connection)


class LoopbackTransport:
    """Direct AF_INET socket, exact owned port; no proxy or redirect machinery."""
    def __init__(self, supervisor, port):
        core.require(type(port) is int and 1024 <= port <= 65535, 'owned loopback port')
        self.supervisor, self.port, self.deadline = supervisor, port, None
        self.watchdogs = []

    def arm_watchdog(self, deadline):
        require_activation()
        self.deadline = deadline
        self.request_started=time.monotonic()
        guard = RequestWatchdog(self.supervisor, deadline)
        self.watchdogs.append(guard)
        guard.start()
        return guard

    def send(self, method, endpoint, body, remaining, *, proxy, redirects, request_header_cap):
        require_activation()
        core.require(proxy is False and redirects is False and request_header_cap == 8192,
                     'loopback transport policy')
        core.require((method,endpoint) in {(v[0],v[1]) for v in core.ENDPOINTS.values()}, 'endpoint forbidden')
        self.supervisor.check()
        headers = f'{method} {endpoint} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nConnection: close\r\nAccept-Encoding: identity\r\n'
        if body is not None:
            core.require(type(body) is bytes and len(body) <= 32768, 'body cap')
            headers += f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n'
        raw_headers = (headers+'\r\n').encode('ascii')
        core.require(len(raw_headers) <= 8192, 'request header cap')
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self.supervisor.lock:
            self.supervisor.connections.add(connection)
        try:
            connection.settimeout(self.deadline.remaining())
            connection.connect(('127.0.0.1',self.port))
            for payload in (raw_headers,body or b''):
                view = memoryview(payload)
                while view:
                    connection.settimeout(self.deadline.remaining())
                    n = connection.send(view[:8192])
                    core.require(n > 0, 'socket send failed')
                    view = view[n:]
            self.deadline.remaining()
            return OwnedSocketReader(connection,self.supervisor)
        except BaseException:
            connection.close()
            with self.supervisor.lock:
                self.supervisor.connections.discard(connection)
            raise


def load_source_only_rows():
    raise core.Disabled('Superseded 88-row study path; use the reviewed usage adapter')
    require_activation()
    fresh = core.strict_json(pinned_file(ROOT/'inputs/SOURCES48.json',
                                        core.PINS['fresh_sources'], 65536))
    legacy = core.strict_json(pinned_file(ROOT/'inputs/PUBLIC_REGRESSION40_REFERENCE.json',
                                         core.PINS['legacy_sources'], 65536))
    core.require(set(fresh) == {'schema','rows'} and len(fresh['rows']) == 48, 'fresh source schema')
    core.require([r['id'] for r in fresh['rows']] == [f'N{i:03d}' for i in range(1,49)] and
                 all(set(r)=={'id','source'} for r in fresh['rows']), 'fresh source-only identities')
    core.require(len(legacy['cases']) == 40, 'legacy count')
    rows = {r['id']:r['source'] for r in fresh['rows']}
    for index, case in enumerate(legacy['cases'],1):
        core.require(not case.get('context') and not case.get('glossary'), 'legacy context/glossary')
        rows[f'R{index:03d}'] = case['source']
    core.require(set(rows)==set(core.ROW_IDS) and all(type(s) is str and 0<len(s)<=4096 for s in rows.values()),
                 'source row identities/types')
    # References/facts from the public legacy fixture are deliberately discarded.
    return rows


def execute_generation_stage(supervisor, transport, alias, lexicon, sources, integrity, expected_error,
                             evidence, ledger):
    """Source wiring of exactly one preflight and fixed measured schedule.

    Called only after the (still absent) acquisition/validation/version/claim
    coordinator. Setup and helper measurement stay outside per-arm intervals.
    """
    raise core.Disabled('Superseded 88-row study path; use the reviewed usage adapter')
    require_activation()
    def exchange(kind, row, arm, prepare, validate):
        supervisor.check()
        bounds = [supervisor.outer_end,supervisor.phase_end,supervisor.work_end,supervisor.postready_end]
        pending=[]
        try:return recorded_exchange(ledger,kind,row,arm,prepare,transport,bounds,validate,pending)[0]
        finally:
            for record in pending:evidence.json('wire.jsonl',record)

    # Marker readiness is local log only; exactly two HTTP readiness calls.
    while not supervisor.loaded.is_set():
        supervisor.check()
        supervisor.loaded.wait(.05)
    exchange('health',None,None,lambda:None,lambda raw:core.readiness_response('health',raw,alias))
    exchange('models',None,None,lambda:None,lambda raw:core.readiness_response('models',raw,alias))
    supervisor.postready_end=min(time.monotonic()+600,supervisor.work_end,supervisor.outer_end)
    supervisor.set_phase('preflight',60)
    plans = []
    for row in core.ROW_IDS:
        sides=iter(('baseline','second'))
        def count(body):
            return exchange('preflight',row,next(sides),lambda:body,core.token_response)
        plans.append(core.preflight_pair(row,sources[row],alias,lexicon,core.PINS['lexicon'],renderer,count))
    ledger.seal_preflight(plans)
    plan_by_id={p.row_id:p for p in plans}
    evidence.json('metadata.json',dict(event='token_coverage_preflight',rows=[dict(row=p.row_id,
        active=p.active,eligible=p.eligible,reason=p.reason,baseline=p.baseline.binding,
        provisional=p.provisional.binding,candidate=p.candidate.binding) for p in plans]))

    supervisor.set_phase('helper',15)
    measure_helper_source(supervisor,alias,lexicon,sources,plans,evidence)
    supervisor.phase_end=supervisor.postready_end
    if getattr(supervisor,'diagnostic',None):supervisor.diagnostic.enter('generation')
    return measured_schedule_source(supervisor,transport,alias,lexicon,sources,plan_by_id,
                                    integrity,expected_error,evidence,ledger)


def measure_helper_source(supervisor,alias,lexicon,sources,plans,evidence):
    """One isolated Python worker, fixed 88+880 renders, no HTTP/model access."""
    raise core.Disabled('Superseded 88-row study path; use the reviewed usage adapter')
    require_activation()
    from isolated_helper import validate_helper_result
    receipts={}
    for plan in plans:
        for receipt in (plan.baseline,plan.provisional):
            key=core.digest(receipt.body)
            core.require(key not in receipts or receipts[key]==receipt.count,'helper duplicate count conflict')
            receipts[key]=receipt.count
    payload=core.canonical(dict(alias=alias,lexicon_hex=lexicon.hex(),lexicon_sha256=core.PINS['lexicon'],
        rows=[dict(id=p.row_id,source=sources[p.row_id],active=p.active,reason=p.reason) for p in plans],
        receipts=receipts))
    core.require(len(payload)<=1024*1024,'helper input bound')
    evidence.create('helper_input.json');evidence.append('helper_input.json',payload)
    evidence.create('helper.log')
    spec=core.child_spec(str(Path(sys.executable).resolve()),['-I','-B',str(HERE/'isolated_helper.py'),
        '--input',str(evidence.output/'helper_input.json')],str(evidence.output))
    proc=supervisor.launch('helper',spec,15,'helper.log')
    while proc.poll() is None:
        supervisor.check()
        supervisor.stop_event.wait(.05)
    core.require(proc.returncode==0,'helper exited unsuccessfully')
    remaining=max(0,supervisor.phase_end-time.monotonic())
    supervisor.readers[-1].join(timeout=remaining)
    core.require(not supervisor.readers[-1].is_alive(),'helper result reader unfinished')
    result=core.strict_json(bounded_file(evidence.output/'helper.log',65536))
    core.require(result.get('input_sha256')==core.digest(payload),'helper input binding')
    validate_helper_result(result,time.get_clock_info('perf_counter').resolution)
    supervisor.public_helper_metrics=dict(helper_peak_rss_bytes=result['peak_rss_bytes'],
        helper_render_p95_ns=result['render_ns']['p95'])
    evidence.json('metadata.json',dict(event='helper_measurement',result=result))


def recorded_exchange(ledger,kind,row,arm,prepare,transport,bounds,validate,pending):
    """Retain bounded attempt/wire evidence even when send/read/validation fails."""
    require_activation()
    before=time.perf_counter_ns();began=time.monotonic();consumed=ledger.total
    capture=WireCapture();body_holder=[];stamps={};failure=None
    def prepared():
        body=prepare();body_holder.append(body);return body
    def validated(raw):
        result=validate(raw);stamps['validated_end']=time.monotonic();return result
    try:
        result=core.checked_exchange(ledger,kind,row,arm,prepared,transport,time.monotonic,
                                     [b for b in bounds if b is not None],validated,capture)
        return result,time.perf_counter_ns()-before
    except BaseException as exc:
        failure=type(exc).__name__
        raise
    finally:
        body=body_holder[0] if body_holder else None;wire=bytes(capture.raw)
        pending.append(dict(kind=kind,row=row,arm=arm,request_hex=body.hex() if body is not None else None,
            response_wire_hex=wire.hex(),request_sha256=core.digest(body) if body is not None else None,
            response_sha256=core.digest(wire),start=getattr(transport,'request_started',began),
            validated_end=stamps.get('validated_end'),deadline=getattr(getattr(transport,'deadline',None),'end',None),
            request_number=ledger.total if ledger.total>consumed else None,
            attempted=ledger.total>consumed,status='failed' if failure else 'validated',failure=failure))


def measured_schedule_source(supervisor, transport, alias, lexicon, sources, plans, integrity,
                             expected_error, evidence, ledger):
    """Uncalled source implementation; requires completed helper integration."""
    raise core.Disabled('Superseded 88-row study path; use the reviewed usage adapter')
    require_activation()
    observations = {}
    totals = dict(prompt=0,completion=0,count_requests=0,count_input_tokens=0)
    try:
        for row,arm in core.SCHEDULE:
            supervisor.check()
            plan=plans[row]
            started=time.perf_counter_ns()
            arm_started=time.monotonic()
            components=dict(token_counter_ns=[],renderer_ns=0,construction_ns=0,completion_ns=0,integrity_ns=0)
            pending_wire=[]
            def exchange(kind, side, body, validator):
                return recorded_exchange(ledger,kind,row,side,lambda:body,transport,
                    [supervisor.outer_end,supervisor.work_end,supervisor.postready_end],validator,pending_wire)
            try:
                if arm=='baseline':
                    before=time.perf_counter_ns()
                    body=core.serialize_request(renderer.baseline_messages(sources[row]),alias)
                    core.require(body==plan.baseline.body,'baseline serialization drift')
                    components['construction_ns']=time.perf_counter_ns()-before;receipt=plan.baseline
                else:
                    sides=iter(('baseline','provisional'))
                    def count(body):
                        value,elapsed=exchange('recurring',next(sides),body,core.token_response)
                        components['token_counter_ns'].append(elapsed)
                        totals['count_requests']+=1;totals['count_input_tokens']+=value
                        return value
                    before=time.perf_counter_ns()
                    body=core.measured_candidate(plan,sources[row],alias,lexicon,core.PINS['lexicon'],renderer,count)
                    components['renderer_ns']=time.perf_counter_ns()-before;receipt=plan.candidate
                def validate(raw):
                    def timed_integrity(source,text):
                        before=time.perf_counter_ns()
                        try:return integrity(source,text)
                        finally:components['integrity_ns']=time.perf_counter_ns()-before
                    return core.completion_response(raw,alias,receipt,sources[row],timed_integrity,expected_error)
                result,elapsed=exchange('completion',arm,body,validate)
                components['completion_ns']=elapsed-components['integrity_ns']
                finished=time.perf_counter_ns();arm_finished=time.monotonic()
                result.pop('raw_response')
                record=dict(row=row,arm=arm,total_ns=finished-started,perf_start_ns=started,perf_end_ns=finished,
                    components=components,start=arm_started,end=arm_finished,request_sha256=core.digest(body),
                    preflight=receipt.binding,**result)
                observations[(row,arm)]=dict(status='observed',**record)
                totals['prompt']+=result['usage']['prompt_tokens'];totals['completion']+=result['usage']['completion_tokens']
                core.require(totals['prompt']<=67584 and totals['completion']<=90112 and
                             totals['prompt']+totals['completion']<=157696,'aggregate generation token caps')
            except BaseException as exc:
                # Stop timing before any partial-evidence persistence/cleanup.
                finished=time.perf_counter_ns();arm_finished=time.monotonic()
                failure_record=dict(row=row,arm=arm,status='operational_failure',failure=type(exc).__name__,
                    total_ns=finished-started,perf_start_ns=started,perf_end_ns=finished,
                    start=arm_started,end=arm_finished,timing_scoreable=False)
                observations[(row,arm)]=failure_record
                supervisor.fail('measured arm failed: '+type(exc).__name__)
                for wire in pending_wire:evidence.json('wire.jsonl',wire)
                evidence.json('results.jsonl',failure_record)
                raise
            else:
                # Successful and partial request bytes share the same retention path.
                for wire in pending_wire:evidence.json('wire.jsonl',wire)
                evidence.json('results.jsonl',record)
        ledger.assert_complete()
        return observations,totals
    finally:
        evidence.json('all_rows.json',core.all_row_accounting(observations))


def reconcile_completed_evidence(evidence,plans,sources,alias,lexicon,integrity,expected_error):
    """Reconcile persisted private protocol evidence before any completion claim."""
    raise core.Disabled('Superseded 88-row study path; use the reviewed usage adapter')
    require_activation()
    from evidence_validation import validate_final_evidence
    wires=bounded_file(evidence.output/'wire.jsonl',64*core.MIB)
    results=bounded_file(evidence.output/'results.jsonl',64*core.MIB)
    core.require(len(wires)+len(results)<=64*core.MIB,'persisted evidence cap')
    transcripts=[];intervals=[]
    wire_lines=wires.splitlines();result_lines=results.splitlines()
    core.require(len(wire_lines)==442 and len(result_lines)==176,'persisted record count')
    for line in wire_lines:
        core.require(len(line)<=262144,'wire record line cap')
        item=core.strict_json(line)
        item['request_body']=bytes.fromhex(item.pop('request_hex')) if item['request_hex'] is not None else None
        item.pop('request_hex',None)
        item['response_wire']=bytes.fromhex(item.pop('response_wire_hex'))
        transcripts.append(item)
    for line in result_lines:
        core.require(len(line)<=262144,'result record line cap')
        item=core.strict_json(line)
        intervals.append({key:item[key] for key in ('row','arm','start','end','perf_start_ns','perf_end_ns','total_ns')})
    result=validate_final_evidence(plans,sources,alias,lexicon,core.PINS['lexicon'],renderer,
        transcripts,intervals,time.get_clock_info('perf_counter').resolution,integrity,expected_error)
    # Cost cannot advance without a separate review of real AB/BA/noise evidence.
    if result['cost']['status']=='pass':
        result['cost']['status']='inconclusive_pending_order_and_noise_review'
    evidence.create('protocol_reconciliation.json');evidence.json('protocol_reconciliation.json',result)
    return result


def main():
    raise core.Disabled('Generic runtime entry is disabled; reviewed Actions bootstrap only')


if __name__=='__main__':
    main()
