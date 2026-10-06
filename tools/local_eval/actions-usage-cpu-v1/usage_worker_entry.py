"""Isolated worker derivative: pinned bootstrap and direct owned-parent admission.

Importing this module never admits native operations. The literal bootstrap
verifies entry bytes, then native_main verifies the immutable parent claim and
complete source closure before loading any policy. Preparation tests are fake.
"""
from hashlib import sha256
import json
import re

POLICY_PIN = "f94a9af78a2c1694f432c4a12850fd0e27e0c6d067180810e1dc87064d650df9"
GUARD_FILE_PIN = "bbbecdb62ff12030428d5da662beb537d7fe6aba49357d641f78d3e84e6554a7"
BANK_PIN = "9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a"
WORKER_PIN = "0d073fff625b8c3c8a5275905a499811409faa1adafe95513cca998f5ca63c73"
SOURCE_NAMES = ("_integrity_guard.py", "usage_example_policy.py", "usage_policy_worker.py", "runtime_bank.frozen.json")
STATE_NAME = "luna-usage-cpu-20261006-v1"
STDLIB_ROOTS = frozenset(("dataclasses", "hashlib", "json", "re", "typing"))


class EntryError(RuntimeError):
    pass


def need(ok):
    if not ok:
        raise EntryError("BINDING")


def require_native_release():
    import sys
    need(__name__ == "verified_usage_entry" and sys.flags.isolated and
         sys.flags.no_site and sys.flags.dont_write_bytecode and len(sys.argv) == 9 and
         globals().get("_ENTRY_BOOTSTRAP_VERIFIED") == tuple(sys.argv[1:3]))


def require_child_admission():
    require_native_release()
    need(globals().get("_CHILD_ADMITTED") is True)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out)
        out[key] = value
    return out


def strict_json(raw, cap=32768):
    try:
        need(type(raw) is bytes and 0 < len(raw) <= cap)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EntryError("BINDING")))
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except BaseException:
        raise EntryError("BINDING") from None


def verify_closure(manifest_bytes, manifest_sha, payloads):
    """No file reads or imports; all closure members verified before ANY exec."""
    need(type(manifest_sha) is str and re.fullmatch("[0-9a-f]{64}", manifest_sha) is not None and
         sha256(manifest_bytes).hexdigest() == manifest_sha)
    manifest = strict_json(manifest_bytes)
    need(type(manifest) is dict and set(manifest) == {"schema", "files"} and type(manifest["schema"]) is int and manifest["schema"] == 1)
    entries = manifest["files"]
    need(type(entries) is list and len(entries) == len(SOURCE_NAMES) and type(payloads) is dict and set(payloads) == set(SOURCE_NAMES))
    pinned = {}
    for entry in entries:
        need(type(entry) is dict and set(entry) == {"file", "path", "bytes", "sha256"} and
             entry["file"] in SOURCE_NAMES and entry["file"] not in pinned and
             type(entry["path"]) is str and entry["path"].startswith("/") and
             ".." not in entry["path"].split("/") and entry["path"].endswith("/"+entry["file"]))
        name, raw = entry["file"], payloads[entry["file"]]
        need(type(raw) is bytes and type(entry["bytes"]) is int and 0 < len(raw) == entry["bytes"] <=
             (16384 if name.endswith(".json") else 65536) and sha256(raw).hexdigest() == entry["sha256"])
        pinned[name] = raw
    for name, expected in (("usage_example_policy.py", POLICY_PIN), ("_integrity_guard.py", GUARD_FILE_PIN),
                           ("runtime_bank.frozen.json", BANK_PIN), ("usage_policy_worker.py", WORKER_PIN)):
        need(sha256(pinned[name]).hexdigest() == expected)
    return pinned


def validate_binding(binding, *, parent_pid, parent_argv, python, cwd, now_ns):
    keys = {"schema", "parent_pid", "parent_argv", "python", "cwd", "launch_ns", "work_end_ns",
            "postready_end_ns", "cleanup_end_ns", "phase_end_ns", "row_ids", "eligible_ids", "source_hashes", "closure_sha256",
            "source_root", "source_manifest_sha256", "claim_path", "claim_sha256"}
    need(type(binding) is dict and set(binding) == keys and type(binding["schema"]) is int and binding["schema"] == 1)
    need(type(parent_pid) is int and parent_pid > 1 and binding["parent_pid"] == parent_pid and
         type(parent_argv) is list and parent_argv == binding["parent_argv"] and
         all(type(s) is str and 0 < len(s) <= 16384 for s in parent_argv) and
         binding["python"] == python and binding["cwd"] == cwd)
    root = binding["source_root"]
    need(type(root) is str and root.startswith("/") and ".." not in root.split("/") and not root.endswith("/"))
    need(len(parent_argv) == 8 and parent_argv[:3] == ["/usr/bin/python3", "-I", "-B"] and
         parent_argv[3:5] == [root+"/verified_bootstrap.py", root+"/KIT_MANIFEST.json"] and
         parent_argv[5:] == [binding["source_manifest_sha256"], "actions", "unused"])
    need(type(binding["claim_path"]) is str and binding["claim_path"].endswith("/ONE_SHOT_CPU_ATTEMPT.json") and
         binding["claim_path"].rsplit("/", 1)[0]+"/attempt" == cwd and
         binding["claim_path"].rsplit("/", 2)[-2] == STATE_NAME)
    for key in ("launch_ns", "work_end_ns", "postready_end_ns", "cleanup_end_ns", "phase_end_ns"):
        need(type(binding[key]) is int and binding[key] >= 0)
    need(type(now_ns) is int and binding["launch_ns"] <= now_ns < min(binding["launch_ns"]+15_000_000_000,
         binding["work_end_ns"], binding["postready_end_ns"], binding["cleanup_end_ns"], binding["phase_end_ns"]))
    rows, eligible, hashes = binding["row_ids"], binding["eligible_ids"], binding["source_hashes"]
    expected = ["R%03d" % n for n in range(1, 41)] + ["S%03d" % n for n in range(1, 16)] + ["N%03d" % n for n in range(1, 33)]
    need(rows == expected and type(eligible) is list and len(eligible) == 24 and
         eligible == [row for row in rows if row in eligible] and type(hashes) is dict and set(hashes) == set(rows))
    need(all(type(v) is str and re.fullmatch("[0-9a-f]{64}", v) is not None for v in
             [*hashes.values(), binding["closure_sha256"], binding["source_manifest_sha256"], binding["claim_sha256"]]))
    return binding


def validate_parent_claim(binding, claim_bytes, source_manifest_bytes, closure_bytes, *, entry_sha, now_ns):
    """Pure cross-binding of actual parent identity to exact reviewed source."""
    need(sha256(claim_bytes).hexdigest() == binding["claim_sha256"] and
         sha256(source_manifest_bytes).hexdigest() == binding["source_manifest_sha256"])
    claim = strict_json(claim_bytes)
    need(json.dumps(claim, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8") == claim_bytes)
    need(claim.get("coordinator_pid") == binding["parent_pid"] and
         claim.get("coordinator_argv") == binding["parent_argv"] and
         claim.get("absolute_python") == binding["python"] and
         claim.get("component_manifest_sha256") == binding["source_manifest_sha256"] and
         claim.get("commitments", {}).get("harness_manifest") == binding["source_manifest_sha256"] and
         claim.get("roots", {}).get("source") == binding["source_root"] and
         claim.get("paths", {}).get("output") == binding["cwd"] and
         type(claim.get("roots", {}).get("state")) is str and
         claim.get("roots", {}).get("state")+"/ONE_SHOT_CPU_ATTEMPT.json" == binding["claim_path"])
    need(type(claim.get("claimed_monotonic")) in (int, float) and
         type(claim.get("outer_deadline_monotonic")) in (int, float) and
         claim["claimed_monotonic"] <= now_ns/1e9 < claim["outer_deadline_monotonic"])
    manifest = strict_json(source_manifest_bytes, 65536)
    need(type(manifest) is dict and type(manifest.get("files")) is list and len(manifest["files"]) <= 128)
    entries = manifest["files"]
    need(all(type(v) is dict and type(v.get("path")) is str for v in entries))
    pinned = {v["path"]: v for v in entries}
    need(len(pinned) == len(entries) and pinned.get("usage_worker_entry.py", {}).get("sha256") == entry_sha)
    closure = strict_json(closure_bytes)
    need(sha256(closure_bytes).hexdigest() == binding["closure_sha256"] and
         type(closure) is dict and type(closure.get("files")) is list)
    for member in closure["files"]:
        name = member["file"]
        relative = ("policy/" if name != "usage_policy_worker.py" else "")+name
        item = pinned.get(relative, {})
        need(member["path"] == binding["source_root"]+"/"+relative and
             item.get("bytes") == member["bytes"] and item.get("sha256") == member["sha256"])
    return True


def load_verified_modules(payloads):
    """Only previously verified closure bytes; import dependencies are explicit.

    Actual execution remains outside preparation's fake-test authorization.
    """
    require_child_admission()
    import builtins
    import sys
    from types import ModuleType
    modules = {}
    original_import = builtins.__import__
    def constrained_import(name, globals=None, locals=None, fromlist=(), level=0):
        need(level == 0)
        if name in modules:
            return modules[name]
        need(name.split(".", 1)[0] in STDLIB_ROOTS)
        return original_import(name, globals, locals, fromlist, level)
    for filename in SOURCE_NAMES[:-1]:
        name = filename[:-3]
        need(name not in sys.modules)
        module = ModuleType(name)
        module.__file__ = "<verified:" + filename + ">"
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": constrained_import}
        modules[name] = module
        sys.modules[name] = module  # dataclasses resolves its exact defining module.
        exec(compile(payloads[filename], module.__file__, "exec"), module.__dict__)
    return modules


def run_loop(worker, protocol, io, *, identity, closure_sha256, observe, checkpoint):
    """Same finite loop for native and fakes. Never emit an exception string.

    io.read/write are bounded frame operations. No error frame is emitted:
    failed/partial writes terminate and the parent treats EOF as terminal.
    """
    try:
        checkpoint()
        ready = worker.ready()
        metrics = observe()
        need(set(metrics) == {"peak_rss_bytes", "cpu_ns"} and
             type(metrics["peak_rss_bytes"]) is int and 0 < metrics["peak_rss_bytes"] <= 33554432 and
             type(metrics["cpu_ns"]) is int and 0 <= metrics["cpu_ns"] <= 15_000_000_000)
        io.write(protocol.encode_frame({**ready, "worker_identity": identity,
                 "closure_sha256": closure_sha256, **metrics}))
        for _ in range(worker.expected_commands):
            checkpoint()
            reply = worker.exchange_frame(io.read())
            checkpoint()
            io.write(reply)
            del reply  # Never hold a source-bearing response while waiting idle.
            if worker.phase == "finished":
                return 0
        raise EntryError("PROTOCOL")
    except BaseException:
        worker.phase, worker.pending = "failed", None
        return 1


def _read_file(path, cap, *, private=False):
    require_native_release()
    import os
    import stat
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= cap)
        if private:
            need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600)
        raw = os.read(fd, cap+1)
        need(len(raw) == info.st_size)
        return raw
    finally:
        os.close(fd)


def native_main():
    global _CHILD_ADMITTED
    require_native_release()
    import os
    import resource
    import select
    import stat
    import sys
    import time
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and len(sys.argv) == 9)
    # -c bootstrap argv: entry path, entry pin, closure path/pin, binding path/pin.
    closure_path, closure_sha, binding_path, binding_sha = sys.argv[3:7]
    raw_binding = _read_file(binding_path, 32768, private=True)
    need(sha256(raw_binding).hexdigest() == binding_sha)
    binding = strict_json(raw_binding)
    need(binding.get("launch_ns") == int(sys.argv[7]) and binding.get("cleanup_end_ns") == int(sys.argv[8]))
    parent = os.getppid()
    def proc_bytes(pid, leaf, cap):
        fd = os.open("/proc/%d/%s" % (pid, leaf), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            raw = os.read(fd, cap+1)
            need(len(raw) <= cap)
            return raw
        finally:
            os.close(fd)
    python = os.readlink("/proc/self/exe")
    need(os.readlink("/proc/%d/exe" % parent) == python)
    validate_binding(binding, parent_pid=parent,
        parent_argv=[x.decode("utf-8") for x in proc_bytes(parent, "cmdline", 16384).split(b"\0")[:-1]],
        python=python, cwd=os.getcwd(), now_ns=time.monotonic_ns())
    need(binding["closure_sha256"] == closure_sha)
    need(binding_path == binding["cwd"]+"/helper_binding.json" and
         closure_path == binding["cwd"]+"/helper_closure.json" and
         sys.argv[1] == binding["source_root"]+"/usage_worker_entry.py")
    for directory in (binding["claim_path"].rsplit("/", 1)[0], binding["cwd"]):
        info = os.lstat(directory)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700)
    # No children, threads, core dumps, bytecode writes, or unbounded CPU.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    prior_soft, prior_hard = resource.getrlimit(resource.RLIMIT_CPU)
    hard = 15 if prior_hard == resource.RLIM_INFINITY else min(15, prior_hard)
    soft = hard if prior_soft == resource.RLIM_INFINITY else min(hard, prior_soft)
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))
    raw_manifest = _read_file(closure_path, 32768, private=True)
    need(sha256(raw_manifest).hexdigest() == closure_sha)
    manifest = strict_json(raw_manifest)
    need(type(manifest) is dict and set(manifest) == {"schema", "files"} and
         type(manifest["files"]) is list and len(manifest["files"]) == 4)
    payloads = {}
    for entry in manifest["files"]:
        need(type(entry) is dict and set(entry) == {"file", "path", "bytes", "sha256"} and
             entry["file"] in SOURCE_NAMES and entry["file"] not in payloads and
             type(entry["path"]) is str and entry["path"].startswith("/") and ".." not in entry["path"].split("/"))
        payloads[entry["file"]] = _read_file(entry["path"], 16384 if entry["file"].endswith(".json") else 65536)
    verified = verify_closure(raw_manifest, closure_sha, payloads)
    validate_parent_claim(binding, _read_file(binding["claim_path"], 32768, private=True),
        _read_file(binding["source_root"]+"/KIT_MANIFEST.json", 65536), raw_manifest,
        entry_sha=sys.argv[2], now_ns=time.monotonic_ns())
    need(os.getppid() == parent)
    validate_binding(binding, parent_pid=parent,
        parent_argv=[x.decode("utf-8") for x in proc_bytes(parent, "cmdline", 16384).split(b"\0")[:-1]],
        python=python, cwd=os.getcwd(), now_ns=time.monotonic_ns())
    _CHILD_ADMITTED = True
    modules = load_verified_modules(verified)
    p = modules["usage_policy_worker"]
    worker = p.PolicyWorker(modules["usage_example_policy"], verified["runtime_bank.frozen.json"],
                            binding["row_ids"], binding["eligible_ids"], binding["source_hashes"])
    del payloads, verified, raw_manifest, manifest, modules
    launch = binding["launch_ns"]
    hard_end = min(launch+580_000_000_000, binding["work_end_ns"], binding["postready_end_ns"], binding["cleanup_end_ns"])
    fields = proc_bytes(os.getpid(), "stat", 8192).decode("ascii").rsplit(")", 1)[1].split()
    identity = dict(pid=os.getpid(), ppid=parent, start_ticks=int(fields[19]), executable=python, closure_sha256=closure_sha)
    def observe():
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return dict(peak_rss_bytes=usage.ru_maxrss*1024,
                    cpu_ns=int((usage.ru_utime+usage.ru_stime)*1_000_000_000))
    def checkpoint():
        need(os.getppid() == parent and time.monotonic_ns() < hard_end)
        metrics = observe()
        need(metrics["peak_rss_bytes"] <= 33554432 and metrics["cpu_ns"] <= 15_000_000_000)
    os.set_blocking(0, False)
    os.set_blocking(1, False)
    class NativeIO:
        def wait(self, writing=False):
            checkpoint()
            select.select([] if writing else [0], [1] if writing else [], [],
                          min(.005, max(0, (hard_end-time.monotonic_ns())/1e9)))
        def read_exact(self, size):
            buf = bytearray()
            while len(buf) < size:
                checkpoint()
                try:
                    part = os.read(0, size-len(buf))
                except BlockingIOError:
                    self.wait()
                    continue
                need(bool(part))
                buf.extend(part)
            return bytes(buf)
        def read(self):
            header = self.read_exact(4)
            size = int.from_bytes(header, "big")
            need(0 < size <= p.FRAME_CAP)
            frame = header+self.read_exact(size)
            p.decode_frame(frame)
            try:
                extra = os.read(0, 1)
            except BlockingIOError:
                extra = b""
            need(not extra)
            return frame
        def write(self, frame):
            p.decode_frame(frame)
            offset = 0
            while offset < len(frame):
                checkpoint()
                try:
                    count = os.write(1, memoryview(frame)[offset:])
                except BlockingIOError:
                    self.wait(True)
                    continue
                need(count > 0)
                offset += count
    return run_loop(worker, p, NativeIO(), identity=identity, closure_sha256=closure_sha,
                    observe=observe, checkpoint=checkpoint)


# Bootstrap itself is passed as literal reviewed source under -I -S -B. It
# verifies this entry's bytes before execution; no sys.path changes are made.
ENTRY_BOOTSTRAP_BODY = """import os,sys,time,signal
assert len(sys.argv)==9 and all(v.isdecimal() and len(v)<=20 for v in sys.argv[7:9])
l,c=map(int,sys.argv[7:9]);n=time.monotonic_ns();d=min(l+600000000000,c)
assert 0<=l<=n<d
signal.signal(signal.SIGALRM,signal.SIG_DFL)
signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})
n=time.monotonic_ns()
assert n<d
signal.setitimer(signal.ITIMER_REAL,(d-n)/1000000000)
assert time.monotonic_ns()<d
import resource
s,h=resource.getrlimit(resource.RLIMIT_CPU)
h=15 if h==resource.RLIM_INFINITY else min(15,h)
s=h if s==resource.RLIM_INFINITY else min(h,s)
resource.setrlimit(resource.RLIMIT_CPU,(s,h))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
os.set_blocking(0,False)
try:r=os.read(0,1)
except BlockingIOError:pass
else:os._exit(1)
import hashlib,stat
p,h=sys.argv[1:3]
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
try:
 s=os.fstat(f);b=os.read(f,65537)
 assert stat.S_ISREG(s.st_mode) and 0<len(b)==s.st_size<=65536 and hashlib.sha256(b).hexdigest()==h
finally:os.close(f)
n={'__name__':'verified_usage_entry','__file__':p,'_ENTRY_BOOTSTRAP_VERIFIED':(p,h)}
exec(compile(b,'<verified usage entry>','exec'),n)
try:r=n['native_main']()
except BaseException:r=1
os._exit(r)
"""


# This enabled derivative is reviewed separately from the frozen source-only kit.
ENTRY_BOOTSTRAP = ENTRY_BOOTSTRAP_BODY


def build_spec(*, python, cwd, entry_path, entry_sha, closure_path, closure_sha, binding_path, binding_sha,
               launch_ns, cleanup_end_ns):
    need(all(type(s) is str and s.startswith("/") and ".." not in s.split("/")
             for s in (python, cwd, entry_path, closure_path, binding_path)))
    need(all(type(s) is str and re.fullmatch("[0-9a-f]{64}", s) is not None
             for s in (entry_sha, closure_sha, binding_sha)))
    need(type(launch_ns) is int and type(cleanup_end_ns) is int and 0 <= launch_ns < cleanup_end_ns)
    return dict(executable=python, cwd=cwd, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                argv=[python, "-I", "-S", "-B", "-c", ENTRY_BOOTSTRAP,
                      entry_path, entry_sha, closure_path, closure_sha, binding_path, binding_sha,
                      str(launch_ns), str(cleanup_end_ns)])


def run_real(*args, **kwargs):
    return native_main()


if __name__ == "__main__":
    run_real()
