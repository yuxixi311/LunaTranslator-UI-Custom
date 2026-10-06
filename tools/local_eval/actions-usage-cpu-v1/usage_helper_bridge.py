"""Bounded persistent helper bridge for the separately reviewed enabled derivative.

The protocol is injected by the hash-verifying assembler. No workspace imports.
Fake backends exercise the exact bridge without processes, pipes, or probes.
Native calls require the existing verified, process-bound Actions admission.
Writing enabled source is not authorization to execute it during preparation.
"""
from hashlib import sha256
import threading

MIB = 1024 ** 2
ACTIVE_NS = 15_000_000_000
ENTRY_SOURCE_SHA256 = "1c9a1f8a6bfdc648155c72b388f05d02b34f616d4137731640108535d50910f4"
ENTRY_BOOTSTRAP_SHA256 = "88f97cf6121ea4d5c8c2a8a34622907c34d6a458a57b345df0c43a77d469ec79"
ERROR_CODES = frozenset(("STATE", "FRAME", "BUDGET", "IDENTITY", "RESOURCE",
                         "IO", "VALIDATION", "CANCELLED", "CLEANUP", "SPAWN", "PROTOCOL"))


class BridgeError(RuntimeError):
    def __init__(self, code):
        super().__init__(code if code in ERROR_CODES else "PROTOCOL")


def need(ok, code):
    if not ok:
        raise BridgeError(code)


def require_native_release():
    import activation_scope
    try:
        grant = activation_scope.require_role("actions")
        need(globals().get("_VERIFIED_BOOTSTRAP_SHA") == grant["manifest_sha"], "IDENTITY")
        return grant
    except activation_scope.Denied:
        raise BridgeError("IDENTITY") from None


class BoundedBridge:
    """One child; one command in flight; validation belongs to active wall time.

    backend implements spawn/read_frame/write_frame/snapshot/close/reap/stop.
    It must independently supervise deadline()/cleanup_deadline(), including
    while the coordinator is blocked or the worker is idle. Fake implementations
    are test seams; NativeBackend is the reviewed Actions runtime adapter.
    """
    def __init__(self, protocol, backend, *, now_ns, phase_deadline_ns,
                 work_end_ns, postready_end_ns, cleanup_end_ns, expected_commands=224,
                 launch_ns=None, parent_setup_ns=0, parent_setup_cpu_ns=0):
        need(type(expected_commands) is int and expected_commands == 224, "STATE")
        self.p, self.backend = protocol, backend
        need(getattr(backend, "native_clock", now_ns) is now_ns, "BUDGET")
        self.now, self.phase_deadline = now_ns, phase_deadline_ns
        need(launch_ns is None or (type(launch_ns) is int and 0 <= launch_ns <= now_ns()), "BUDGET")
        need(all(type(v) is int and v >= 0 for v in (parent_setup_ns, parent_setup_cpu_ns)) and
             (launch_ns is not None or (parent_setup_ns == parent_setup_cpu_ns == 0)), "BUDGET")
        need(getattr(backend, "launch_ns", launch_ns) == launch_ns, "IDENTITY")
        self.launch_ns, self.parent_setup_ns, self.parent_setup_cpu_ns = launch_ns, parent_setup_ns, parent_setup_cpu_ns
        self.bounds = (work_end_ns, postready_end_ns, cleanup_end_ns)
        self.expected_commands = expected_commands
        self.state, self.commands = "new", 0
        self.budget = None
        self.lock = threading.Lock()
        self.owner_identity = None
        self.peak_rss, self.cpu_ns, self.cold_start_ns = 0, 0, 0
        self.finish_ns, self.closed_ns = 0, None
        self.cleanup_result = None

    def deadline(self):
        need(self.budget is not None, "STATE")
        end = min(self.budget.work_end, self.phase_deadline())
        if self.budget.active_start is not None:
            end = min(end, self.budget.deadline)
        return end

    def cleanup_deadline(self):
        need(self.budget is not None, "STATE")
        return self.budget.cleanup_end

    def _snapshot(self, *, allow_exit=False):
        snap = self.backend.snapshot(allow_exit=allow_exit)
        need(type(snap) is dict and set(snap) == {"identity", "peak_rss_bytes", "cpu_ns", "exited"}, "RESOURCE")
        need(snap["identity"] == self.owner_identity, "IDENTITY")
        rss, cpu = snap["peak_rss_bytes"], snap["cpu_ns"]
        need(type(rss) is int and 0 < rss <= 32*MIB and type(cpu) is int and 0 <= cpu <= ACTIVE_NS, "RESOURCE")
        need(type(snap["exited"]) is bool and (allow_exit or not snap["exited"]), "RESOURCE")
        self.peak_rss, self.cpu_ns = max(self.peak_rss, rss), max(self.cpu_ns, cpu)

    def check(self):
        need(self.state in ("starting", "ready", "finishing"), "STATE")
        self.backend.check()
        need(self.now() < self.deadline(), "BUDGET")
        if self.owner_identity is not None:
            self._snapshot(allow_exit=self.state == "finishing")

    def _ready(self, value):
        fields = {"op", "policy_sha256", "bank_sha256", "guard_excerpt_sha256", "expected_commands"}
        envelope = {"worker_identity", "closure_sha256", "peak_rss_bytes", "cpu_ns"}
        need(type(value) is dict and set(value) == fields | envelope, "PROTOCOL")
        need(value["op"] == "READY" and value["policy_sha256"] == self.p.POLICY_SHA256 and
             value["bank_sha256"] == self.p.BANK_SHA256 and
             value["guard_excerpt_sha256"] == self.p.GUARD_SHA256 and
             type(value["expected_commands"]) is int and value["expected_commands"] == self.expected_commands, "IDENTITY")
        need(value["worker_identity"] == self.owner_identity and
             value["closure_sha256"] == self.backend.closure_sha256, "IDENTITY")
        need(type(value["peak_rss_bytes"]) is int and 0 < value["peak_rss_bytes"] <= 32*MIB and
             type(value["cpu_ns"]) is int and 0 <= value["cpu_ns"] <= ACTIVE_NS, "RESOURCE")
        self.peak_rss = max(self.peak_rss, value["peak_rss_bytes"])
        self.cpu_ns = max(self.cpu_ns, value["cpu_ns"])
        return {key: value[key] for key in fields}

    def start(self):
        need(self.lock.acquire(False), "STATE")
        try:
            need(self.state == "new", "STATE")
            self.state = "starting"
            launched = self.now() if self.launch_ns is None else self.launch_ns
            need(self.parent_setup_ns <= self.now()-launched, "BUDGET")
            self.budget = self.p.ActiveBudget(launched, *self.bounds)
            self.budget.deadline = min(self.budget.deadline, self.phase_deadline())
            need(self.now() < self.deadline(), "BUDGET")
            self.owner_identity = self.backend.spawn(self.deadline, self.cleanup_deadline)
            self.check()
            result = self._ready(self.p.decode_frame(self.backend.read_frame(self.deadline())))
            self.check()
            ended = self.now()
            self.budget.finish_roundtrip(ended)
            self.cold_start_ns = ended - launched
            need(self.cold_start_ns > 0, "BUDGET")
            self.state = "ready"
            return result
        except BaseException as exc:
            self.abort()
            raise BridgeError(str(exc) if isinstance(exc, BridgeError) else "PROTOCOL") from None
        finally:
            self.lock.release()

    def request(self, message, validate):
        if not self.lock.acquire(False):
            self.abort()
            raise BridgeError("STATE")
        try:
            need(self.state == "ready" and callable(validate) and self.commands < self.expected_commands, "STATE")
            self.budget.begin_roundtrip(self.now(), self.phase_deadline())
            self.check()
            frame = self.p.encode_frame(message)  # Encoding/UTF-8 checks are charged.
            need(type(message) is dict and message.get("op") in ("PREPARE", "GATE", "SEAL", "FINISH"), "PROTOCOL")
            finishing = message["op"] == "FINISH"
            need(finishing == (self.commands == self.expected_commands - 1), "STATE")
            self.commands += 1  # A failed write consumes the command; never retry.
            self.backend.write_frame(frame, self.deadline())
            if finishing:
                self.state = "finishing"
            response = self.p.decode_frame(self.backend.read_frame(self.deadline()))
            result = validate(response)
            self.check()  # Includes caller's strict response validation.
            if finishing:
                need(response == {"op": "FINISHED", "commands": self.expected_commands}, "PROTOCOL")
                self.finish_ns = self.budget.active_start
            else:
                self.budget.finish_roundtrip(self.now())
            return result
        except BaseException as exc:
            self.abort()
            raise BridgeError(str(exc) if isinstance(exc, BridgeError) else "VALIDATION") from None
        finally:
            self.lock.release()

    def close(self):
        need(self.lock.acquire(False), "STATE")
        try:
            if self.state == "closed":
                return self.cleanup_result
            need(self.state == "finishing" and self.commands == self.expected_commands, "STATE")
            # FINISH remains active until EOF, exact successful exit and reap.
            self.backend.close_input()
            need(self.backend.reap(self.deadline(), expected_exit=0), "CLEANUP")
            self._snapshot(allow_exit=True)
            self.check()
            self.backend.close()
            ended = self.now()
            self.budget.finish_roundtrip(ended)
            self.finish_ns = ended - self.finish_ns
            self.closed_ns, self.state = ended, "closed"
            self.cleanup_result = dict(cleanup_confirmed=True, reaped=True, protocol_complete=True)
            return self.cleanup_result
        except BaseException:
            self.abort()
            raise BridgeError("CLEANUP") from None
        finally:
            self.lock.release()

    def abort(self):
        if self.state in ("failed", "closed"):
            return self.cleanup_result
        self.state = "failed"
        confirmed = False
        try:
            if self.budget is not None:
                deadline = self.budget.emergency_deadline(self.now())
                confirmed = self.backend.stop(deadline) is True
                self.backend.close()
                confirmed = confirmed and self.now() < deadline
        except BaseException:
            confirmed = False
        self.cleanup_result = dict(cleanup_confirmed=confirmed, reaped=confirmed, protocol_complete=False)
        return self.cleanup_result

    def metrics(self):
        need(self.cold_start_ns > 0 and self.owner_identity is not None, "STATE")
        if self.state in ("ready", "finishing"):
            self.check()
        need(self.state != "failed", "STATE")
        return dict(owner_identity=dict(self.owner_identity), policy_in_owner_process=True,
                    peak_rss_bytes=self.peak_rss, cold_start_ns=self.cold_start_ns)

    def timing_metrics(self):
        need(self.state == "closed", "STATE")
        return dict(active_work_ns=ACTIVE_NS-self.budget.remaining, worker_cpu_ns=self.cpu_ns,
                    lifetime_ns=self.closed_ns-self.budget.launch, startup_ns=self.cold_start_ns,
                    finish_ns=self.finish_ns, commands=self.commands,
                    parent_setup_ns=self.parent_setup_ns, parent_setup_cpu_ns=self.parent_setup_cpu_ns)


class FrameIO:
    """Bounded partial I/O algorithm, independent of the OS transport.

    read_some/write_some/wait must be nonblocking and use the SAME absolute
    deadline. Tests exercise backpressure, truncation, and fragmented framing.
    """
    def __init__(self, protocol, transport, now_ns, checkpoint):
        self.p, self.io, self.now, self.checkpoint = protocol, transport, now_ns, checkpoint

    def _check(self, deadline):
        self.checkpoint()
        need(type(deadline) is int and self.now() < deadline, "BUDGET")

    def write(self, frame, deadline):
        self.p.decode_frame(frame)
        offset = 0
        while offset < len(frame):
            self._check(deadline)
            n = self.io.write_some(memoryview(frame)[offset:])
            need(n is None or (type(n) is int and 0 < n <= len(frame)-offset), "IO")
            if n is None:
                self.io.wait("write", deadline)
            else:
                offset += n
        self._check(deadline)

    def _read(self, size, deadline):
        buf = bytearray()
        while len(buf) < size:
            self._check(deadline)
            part = self.io.read_some(size-len(buf))
            need(part is None or (type(part) is bytes and 0 < len(part) <= size-len(buf)), "IO")
            if part is None:
                self.io.wait("read", deadline)
            else:
                buf.extend(part)
        return bytes(buf)

    def read(self, deadline):
        header = self._read(4, deadline)
        size = int.from_bytes(header, "big")
        need(0 < size <= self.p.FRAME_CAP, "FRAME")
        frame = header + self._read(size, deadline)
        self.p.decode_frame(frame)
        need(self.io.read_some(1) in (None, b""), "FRAME")
        self._check(deadline)
        return frame


class OwnedProcess:
    """Injected wait4 adapter shared by the preserved supervisor and helper bridge.

    Fake kernel/clock adapters test this without any native operations.
    Only the gated NativeBackend supplies real OS functions.
    Captures final full-process HWM and CPU even if a guard or inherited owner
    reaps first. No PID search, process groups, blocking waitpid, or second child.
    """
    def __init__(self, process, os_api, clock, timeout_error):
        self.os, self.clock, self.timeout_error = os_api, clock, timeout_error
        self.raw = self.pid = self.stdin = self.stdout = None
        self.final_usage = self.returncode = None
        self.termination_requested = None
        self.lock = threading.Lock()
        if process is not None:
            self.adopt(process)

    def adopt(self, process):
        # The SAME wrapper is registered before spawn and remains the sole
        # reaper. No raw Popen is ever published to the inherited owner.
        with self.lock:
            need(self.raw is None and type(process.pid) is int and process.pid > 1, "STATE")
            self.raw, self.pid = process, process.pid
            self.stdin, self.stdout = process.stdin, process.stdout
            self.returncode = process.returncode
            if self.termination_requested is not None and self.returncode is None:
                try:
                    self.os.kill(self.pid, self.termination_requested)
                except ProcessLookupError:
                    pass

    def poll(self):
        if not self.lock.acquire(False):
            return self.returncode
        try:
            if self.returncode is None and self.pid is not None:
                pid, status, usage = self.os.wait4(self.pid, self.os.WNOHANG)
                if pid == self.pid:
                    self.final_usage = usage
                    self.returncode = self.os.waitstatus_to_exitcode(status)
                    self.raw.returncode = self.returncode
            return self.returncode
        finally:
            self.lock.release()

    def wait(self, timeout):
        need(type(timeout) in (int, float) and 0 <= timeout <= 20, "CLEANUP")
        end = self.clock.monotonic() + timeout
        while self.clock.monotonic() < end:
            code = self.poll()
            if code is not None:
                return code
            self.clock.sleep(min(.005, max(0, end-self.clock.monotonic())))
        raise self.timeout_error([] if self.raw is None else self.raw.args, timeout)

    def terminate(self):
        # Popen.send_signal internally polls/reaps, so never delegate to it.
        self._signal(15)

    def kill(self):
        self._signal(9)

    def _signal(self, signum):
        with self.lock:
            if self.returncode is None:
                self.termination_requested = 9 if signum == 9 or self.termination_requested == 9 else signum
                if self.pid is None:
                    return
                try:
                    self.os.kill(self.pid, self.termination_requested)
                except ProcessLookupError:
                    pass


def resource_tick(backend):
    """Do not expose half-published adoption to the independent resource thread."""
    if backend.proc is not None and backend.identity is not None and backend.last_snapshot is not None:
        backend.snapshot(allow_exit=backend.finish_expected)
        return True
    return False


def effective_cleanup_deadline(previous, *limits):
    need(all(type(value) is int and value >= 0 for value in limits), "CLEANUP")
    need(previous is None or (type(previous) is int and previous >= 0), "CLEANUP")
    return min((*limits, previous) if previous is not None else limits)


def handoff_terminal_failure(controller):
    """Cancel the same inherited attempt; never start a helper-only reserve."""
    controller.expired("helper terminal failure")


def spawn_options(spec, *, pipe, devnull):
    """Pure Popen argument contract: direct child inherits the parent's group."""
    return dict(executable=spec["executable"], cwd=spec["cwd"], env=spec["env"],
        shell=False, close_fds=True, pass_fds=(), stdin=pipe, stdout=pipe,
        stderr=devnull, bufsize=0, start_new_session=False, process_group=None)


class NativeBackend:
    """Linux private pipes bound to the EXACT admitted owner/controller.

    Construction and every native method require process-bound Actions role.
    Preparation exercises only fake observations, never this native backend.
    """
    def __init__(self, protocol, runtime, owner, controller, spec, *, closure_sha256):
        require_native_release()
        import os
        import time
        self.os, self.time, self.p = os, time, protocol
        self.native_clock = time.monotonic_ns
        self.runtime, self.owner, self.controller, self.spec = runtime, owner, controller, spec
        need(controller.owner is owner and runtime.COORDINATOR_CANCEL_EVENT is controller.cancel, "IDENTITY")
        need(type(spec) is dict and set(spec) == {"executable", "cwd", "env", "argv"} and
             spec["env"] == {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"} and
             type(spec["argv"]) is list and len(spec["argv"]) == 14 and
             all(type(value) is str for value in spec["argv"]) and
             spec["argv"][:5] == [spec["executable"], "-I", "-S", "-B", "-c"] and
             sha256(spec["argv"][5].encode("utf-8")).hexdigest() == ENTRY_BOOTSTRAP_SHA256 and
             spec["argv"][7] == ENTRY_SOURCE_SHA256 and spec["argv"][9] == closure_sha256, "IDENTITY")
        self.closure_sha256 = closure_sha256
        need(all(v.isdecimal() and len(v) <= 20 for v in spec["argv"][12:14]), "IDENTITY")
        self.launch_ns = int(spec["argv"][12])
        self.proc = self.intent = None
        self.stop_event = threading.Event()
        self.threads, self.failure = [], None
        self.identity = self.last_snapshot = None
        self.finish_expected = self.stopping = False
        self.effective_cleanup_end = None
        self.io = FrameIO(protocol, self, time.monotonic_ns, self.check)

    def check(self):
        require_native_release()
        self.controller.checkpoint()
        self.owner.check()
        need(self.failure is None, "RESOURCE")
        need(self.time.monotonic_ns() < self.command_deadline(), "BUDGET")

    def spawn(self, command_deadline, cleanup_deadline):
        require_native_release()
        import subprocess
        self.command_deadline, self.cleanup_end = command_deadline, cleanup_deadline
        need(cleanup_deadline() == int(self.spec["argv"][13]) and
             self.launch_ns <= self.time.monotonic_ns() < command_deadline() <= self.launch_ns+ACTIVE_NS, "BUDGET")
        self.check()
        self.proc = OwnedProcess(None, self.os, self.time, subprocess.TimeoutExpired)
        with self.owner.lock:
            need("helper" not in self.owner.intents and self.owner.monitor.is_alive() and
                 self.owner.deadline_monitor.is_alive(), "STATE")
            self.intent = self.runtime.Intent("helper", self.spec, command_deadline()/1e9)
            self.intent.process = self.proc
            self.owner.intents["helper"] = self.intent
        self._arm()  # Independent watchdogs see pending spawn before Popen.
        try:
            # Preserve the owner's existing durable intent/diagnostic path;
            # this contains paths/hashes and bootstrap code, never row text.
            self.owner.record(dict(event="launch_intent", name="helper", spec=self.spec,
                deadline=command_deadline()/1e9, pending_handle=True, watchdog_armed=True,
                stdout="private_helper_pipe"))
            self.check()
            raw_process = subprocess.Popen(self.spec["argv"],
                **spawn_options(self.spec, pipe=subprocess.PIPE, devnull=subprocess.DEVNULL))
            # Preallocated handle receives ownership immediately. A cancellation
            # queued before Popen returned is applied by the same handle.
            self.proc.adopt(raw_process)
        except BaseException:
            self.failure = "SPAWN"
            self.controller.expired("helper spawn unconfirmed")
            raise BridgeError("SPAWN") from None
        with self.owner.lock:
            self.intent.process, self.intent.pending = self.proc, False
        if self.failure or self.time.monotonic_ns() >= command_deadline():
            self.stop(min(self.time.monotonic_ns()+20_000_000_000, cleanup_deadline()))
            raise BridgeError("SPAWN")
        self.os.set_blocking(self.proc.stdin.fileno(), False)
        self.os.set_blocking(self.proc.stdout.fileno(), False)
        self.identity = self._identity()
        self.last_snapshot = self._sample()
        return self.identity

    def _read_proc(self, leaf, cap):
        require_native_release()
        fd = self.os.open("/proc/%d/%s" % (self.proc.pid, leaf), self.os.O_RDONLY | self.os.O_NOFOLLOW)
        try:
            data = self.os.read(fd, cap+1)
            need(len(data) <= cap, "RESOURCE")
            return data
        finally:
            self.os.close(fd)

    def _identity(self):
        require_native_release()
        fields = self._read_proc("stat", 8192).decode("ascii").rsplit(")", 1)[1].split()
        need(int(fields[1]) == self.os.getpid() and self.os.readlink("/proc/%d/exe" % self.proc.pid) == self.spec["executable"], "IDENTITY")
        need(self._read_proc("cmdline", 16384).split(b"\0")[:-1] == [v.encode() for v in self.spec["argv"]], "IDENTITY")
        return dict(pid=self.proc.pid, ppid=self.os.getpid(), start_ticks=int(fields[19]),
                    executable=self.spec["executable"], closure_sha256=self.closure_sha256)

    def _sample(self):
        require_native_release()
        identity = self._identity()
        need(self.identity is None or identity == self.identity, "IDENTITY")
        stat = self._read_proc("stat", 8192).decode("ascii").rsplit(")", 1)[1].split()
        status = self._read_proc("status", 16384).decode("ascii")
        rows = {line.split(":", 1)[0]: line.split(":", 1)[1].strip().split() for line in status.splitlines() if ":" in line}
        need(rows["VmHWM"][1:] == ["kB"] and rows["Threads"] == ["1"], "RESOURCE")
        rss = int(rows["VmHWM"][0])*1024
        cpu = (int(stat[11])+int(stat[12]))*1_000_000_000//self.os.sysconf("SC_CLK_TCK")
        need(0 < rss <= 32*MIB and 0 <= cpu <= ACTIVE_NS, "RESOURCE")
        return dict(identity=identity, peak_rss_bytes=rss, cpu_ns=cpu, exited=False)

    def _arm(self):
        require_native_release()
        def deadline_watch():
            while not self.stop_event.wait(.005):
                try:
                    self.check()
                except BaseException:
                    self.failure = "BUDGET"
                    self.controller.expired("helper absolute deadline")
                    try:
                        self._signal_kill()
                    except BaseException:
                        self.failure = "CLEANUP"
                    return
        def resource_watch():
            while not self.stop_event.wait(.01):
                try:
                    resource_tick(self)
                except BaseException:
                    self.failure = "RESOURCE"
                    self.controller.expired("helper resource or identity gate")
                    try:
                        self._signal_kill()
                    except BaseException:
                        self.failure = "CLEANUP"
                    return
        for name, target in (("usage-deadline", deadline_watch), ("usage-resources", resource_watch)):
            thread = threading.Thread(target=target, name=name, daemon=True)
            self.owner.readers.append(thread)
            self.threads.append(thread)
            thread.start()

    def _signal_kill(self):
        require_native_release()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()  # Supplied direct child handle only; no group/name lookup.

    def snapshot(self, *, allow_exit=False):
        require_native_release()
        need(self.proc is not None and self.last_snapshot is not None, "RESOURCE")
        if self.proc.poll() is None:
            try:
                self.last_snapshot = self._sample()
                return dict(self.last_snapshot)
            except BaseException:
                # Exit may race /proc reads. Only an owned final wait4 result
                # can replace that observation, and only during normal FINISH.
                need(allow_exit and self.proc.poll() is not None, "RESOURCE")
        need(allow_exit, "RESOURCE")
        usage = self.proc.final_usage
        need(usage is not None, "RESOURCE")
        final = dict(identity=self.identity, exited=True,
            peak_rss_bytes=usage.ru_maxrss*1024,
            cpu_ns=int((usage.ru_utime+usage.ru_stime)*1_000_000_000))
        need(0 < final["peak_rss_bytes"] <= 32*MIB and 0 <= final["cpu_ns"] <= ACTIVE_NS, "RESOURCE")
        self.last_snapshot = final
        return dict(final)

    def read_some(self, size):
        require_native_release()
        try:
            return self.os.read(self.proc.stdout.fileno(), size)
        except BlockingIOError:
            return None

    def write_some(self, data):
        require_native_release()
        try:
            return self.os.write(self.proc.stdin.fileno(), data)
        except BlockingIOError:
            return None

    def wait(self, direction, deadline):
        require_native_release()
        import select
        self.check()
        remaining = (deadline-self.time.monotonic_ns())/1e9
        need(remaining > 0, "BUDGET")
        select.select([self.proc.stdout] if direction == "read" else [],
                      [self.proc.stdin] if direction == "write" else [], [], min(.005, remaining))

    def read_frame(self, deadline):
        require_native_release()
        return self.io.read(deadline)

    def write_frame(self, frame, deadline):
        require_native_release()
        if self.p.decode_frame(frame).get("op") == "FINISH":
            self.finish_expected = True
        return self.io.write(frame, deadline)

    def close_input(self):
        require_native_release()
        if self.proc is not None and self.proc.stdin is not None:
            self.proc.stdin.close()

    def reap(self, deadline, *, expected_exit=None):
        require_native_release()
        if self.proc is None:
            return False
        while self.time.monotonic_ns() < deadline:
            code = self.proc.poll()  # waitpid(WNOHANG); never a blocking wait.
            if code is not None:
                self.intent.exit_confirmed = True
                need(expected_exit is None or code == expected_exit, "CLEANUP")
                if expected_exit is not None:
                    need(self.read_some(1) == b"", "FRAME")
                return True
            self.stop_event.wait(min(.005, max(0, (deadline-self.time.monotonic_ns())/1e9)))
        return False

    def stop(self, deadline):
        require_native_release()
        self.stopping = True
        handoff_terminal_failure(self.controller)
        self.effective_cleanup_end = effective_cleanup_deadline(self.effective_cleanup_end,
            deadline, self.cleanup_end(), int(self.controller.cleanup_deadline()*1e9))
        self._signal_kill()
        return self.reap(self.effective_cleanup_end)

    def close(self):
        require_native_release()
        self.stop_event.set()
        end = effective_cleanup_deadline(self.effective_cleanup_end,
            self.cleanup_end(), int(self.controller.cleanup_deadline()*1e9))
        if not self.stopping:
            end = min(end, self.command_deadline())
        else:
            # Stop/reap/close/join all share the first failure's fixed deadline.
            self.effective_cleanup_end = end
        for stream in (() if self.proc is None else (self.proc.stdin, self.proc.stdout)):
            need(self.time.monotonic_ns() < end, "CLEANUP")
            if stream is not None:
                stream.close()
            need(self.time.monotonic_ns() < end, "CLEANUP")
        for thread in self.threads:
            need(self.time.monotonic_ns() < end, "CLEANUP")
            if thread is not threading.current_thread():
                thread.join(timeout=max(0, (end-self.time.monotonic_ns())/1e9))
        need(self.time.monotonic_ns() < end and all(not thread.is_alive() for thread in self.threads), "CLEANUP")
        if not self.stopping:
            self.check()


def run_real(*args, **kwargs):
    require_native_release()
    raise BridgeError("STATE")  # Only the admitted coordinator binds NativeBackend.
