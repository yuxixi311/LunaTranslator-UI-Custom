"""Adapted from the reviewed runner: configurable reserve and structured failure only."""
import os
from pathlib import Path
import signal
import subprocess
import time

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

class OwnedFailure(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__("owned child failed")

def process_group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def signal_owned(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        # Interrupted spawn may precede setsid; this is still our direct child.
        if process.returncode is None:
            try:
                os.kill(process.pid, signum)
            except ProcessLookupError:
                pass


class PhaseTimeout(TimeoutError):
    pass


def owned_process(command, cwd, env, logfile, seconds, cleanup_reserve=7):
    """Own one process group, including spawn and configurable cleanup reserve.

    SIGALRM covers blocking Popen initialization (whose pid becomes available on
    the allocated object), log open, native work and writes. Like any userspace
    watchdog this relies on the OS delivering signals and scheduling the parent.
    """
    require(0 < cleanup_reserve < seconds, "invalid cleanup reserve")
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "active parent alarm")
    started, process, output = time.monotonic(), None, None
    deadline = started + seconds
    timed_out, cleanup_ok, failure = False, False, None
    old_handler = signal.getsignal(signal.SIGALRM)
    def alarm(signum, frame):
        raise PhaseTimeout("owned lifecycle deadline")
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, seconds - cleanup_reserve))
    try:
        try:
            output = Path(logfile).open("xb")
            # Allocate before __init__: a blocked exec error-pipe read may occur
            # after fork and pid assignment but before Popen normally returns.
            process = subprocess.Popen.__new__(subprocess.Popen)
            subprocess.Popen.__init__(process, command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                      stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            process.wait(timeout=max(0, deadline - cleanup_reserve - time.monotonic()))
        except (subprocess.TimeoutExpired, PhaseTimeout):
            timed_out = True
        except BaseException as exc:
            failure = exc
        finally:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - time.monotonic()))
            try:
                pid = getattr(process, "pid", None)
                if pid is not None:
                    if process.returncode is None or process_group_exists(pid):
                        signal_owned(process, signal.SIGTERM)
                        try:
                            process.wait(timeout=max(0, min(2, deadline - time.monotonic())))
                        except subprocess.TimeoutExpired:
                            pass
                    if process.returncode is None or process_group_exists(pid):
                        signal_owned(process, signal.SIGKILL)
                    try:
                        process.wait(timeout=max(0, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        pass
                    while process_group_exists(pid) and time.monotonic() < deadline:
                        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
                    cleanup_ok = process.returncode is not None and not process_group_exists(pid)
                else:
                    cleanup_ok = True
                if output is not None:
                    output.close()
            except PhaseTimeout:
                timed_out, cleanup_ok = True, False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    elapsed = time.monotonic() - started
    result = {"exit_code": getattr(process, "returncode", None),
              "elapsed_seconds": elapsed, "deadline_seconds": seconds,
              "timed_out": timed_out or elapsed > seconds, "cleanup_confirmed": cleanup_ok,
              "failure": None if failure is None else type(failure).__name__}
    if not (cleanup_ok and not result["timed_out"] and result["exit_code"] == 0 and failure is None):
        raise OwnedFailure(result)
    return result

