"""Public source snapshot of a one-shot cloud lexical probe. NOT EXECUTED.

Only `freeze` and fake tests are preparation commands. Public manifest names and
hashes are distinct; real execution requires a new review. See README.md.
"""
import argparse
import base64
import csv
import email.parser
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import signal
import stat
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
PREPARATION_SHA = "2e91dbaa43b627df1b15f03e4f81b998dd34f62a308df49d2ab88e5af0990ab9"
MIB = 1024 * 1024
DICT_SIZE = 217466039
DICT_SHA = "53fa281d11eef3769712fe1c3c892117338f9892bee6daf4dad51daa5281bb6f"
LICENSE_FILES = ("license_sources/SudachiPy-0.6.11-LICENSE", "license_sources/SudachiDict-20260723-LICENSE-2.0.txt",
                 "license_sources/SudachiDict-20260723-LEGAL")
CODE_FILES = ("pilot_runner.py", "test_pilot_runner.py", "RUNNER.md", "API_NOTES.md", *LICENSE_FILES)
PHASES = ("download", "setup", "parse", "assess")
LIMITS = {"download": 240, "setup": 60, "parse": 60, "assess": 60}
STATES = {"download": "claimed", "setup": "download_done", "parse": "setup_done", "assess": "parse_done"}
ARTIFACTS = {"download": ("download.json",), "setup": ("setup.json", "installed.json", "venv/bin/python", "venv/pyvenv.cfg"),
             "parse": ("parser.json",), "assess": ("assessment.json",)}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest_file(path):
    h = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(MIB), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def read_json(path):
    require(Path(path).stat().st_size <= 4 * MIB, "JSON exceeds output bound")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value, exclusive=False):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    require(len(data) <= 4 * MIB, "JSON output exceeds bound")
    with Path(path).open("xb" if exclusive else "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def verify_file(path, pin):
    require(Path(path).is_file() and not Path(path).is_symlink(), "missing/symlink file: " + str(path))
    require(digest_file(path) == pin, "integrity mismatch: " + str(path))


def prepared_files():
    preparation = ROOT / "PUBLIC_PREPARATION_MANIFEST.json"
    require(digest_file(preparation)["sha256"] == PREPARATION_SHA, "preparation manifest changed")
    pins = read_json(preparation)["files"]
    for name, pin in pins.items():
        require(Path(name).name == name, "nonlocal preparation entry")
        verify_file(ROOT / name, pin)
    return dict(pins, **{"PUBLIC_PREPARATION_MANIFEST.json": digest_file(preparation)})


def freeze():
    pins = prepared_files()
    for name, pin in zip(LICENSE_FILES, read_json(ROOT / "PYPI_PINS.json")["license_sources"], strict=True):
        verify_file(ROOT / name, {"bytes": pin["size_bytes"], "sha256": pin["sha256"]})
    for name in CODE_FILES:
        pins[name] = digest_file(ROOT / name)
    path = ROOT / "PUBLIC_EXECUTION_MANIFEST.json"
    write_json(path, {"schema": 1, "files": pins, "planned_calls": 48,
                      "scope": "synthetic lexical-only; no semantic improvement claim"}, exclusive=True)
    print(digest_file(path)["sha256"])


def verify_manifest(sha):
    require(bool(re.fullmatch("[a-f0-9]{64}", sha)), "reviewed manifest SHA required")
    path = ROOT / "PUBLIC_EXECUTION_MANIFEST.json"
    require(digest_file(path)["sha256"] == sha, "manifest SHA mismatch")
    manifest = read_json(path)
    expected = set(prepared_files()) | set(CODE_FILES)
    require(manifest["schema"] == 1 and set(manifest["files"]) == expected and manifest["planned_calls"] == 48,
            "manifest schema/file inventory mismatch")
    for name, pin in manifest["files"].items():
        verify_file(ROOT / name, pin)
    return manifest


def host_check():
    require(platform.python_implementation() == "CPython" and platform.python_version() == "3.12.14",
            "requires reviewed CPython 3.12.14")
    require(platform.system() == "Linux" and platform.machine() == "x86_64", "host OS/architecture mismatch")
    libc, version = platform.libc_ver()
    require(libc == "glibc" and tuple(map(int, version.split(".")[:2])) >= (2, 17), "glibc incompatible")


def package_pins():
    value = read_json(ROOT / "PYPI_PINS.json")
    pins = value["packages"]
    require([(p["name"], p["version"]) for p in pins] == [("SudachiPy", "0.6.11"), ("SudachiDict-core", "20260723")],
            "unexpected packages")
    total = sum(p["size_bytes"] for p in pins)
    require(total == value["combined_compressed_size_bytes"] and total <= 100 * MIB, "compressed limit")
    for p in pins:
        require(p["url"].startswith("https://files.pythonhosted.org/packages/") and p["url"].endswith("/" + p["filename"])
                and p["filename"].endswith(".whl") and not p["yanked"], "URL/wheel pin invalid")
    return pins


def batch_sources():
    diagnostics = read_json(ROOT / "diagnostics.sources.json")
    seen = read_json(ROOT / "seen.sources.json")
    require(len(diagnostics) == 16 and len(seen) == 32, "fixed population changed")
    batch = []
    for records, maxlen in ((diagnostics, 160), (seen, 200)):
        for row in records:
            require(isinstance(row["source"], str) and 0 < len(row["source"]) <= maxlen
                    and not any(c in row["source"] for c in "\r\n"), "source schema")
            # The parser only receives source and identity, never semantic labels.
            batch.append({"id": row["id"], "source": row["source"]})
    require(len({r["id"] for r in batch}) == 48, "duplicate source ID")
    return batch


def block_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("Python socket operation forbidden in offline phase")


def clean_environment(run):
    return {"PATH": "/usr/bin:/bin", "HOME": str(run / "home"), "XDG_CONFIG_HOME": str(run / "home"),
            "TMPDIR": str(run / "tmp"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": "",
            "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


def claim_run(sha, phase):
    claim = ROOT / "RUN_CLAIM.json"
    lock_path = ROOT / "RUN_LOCK"
    lock = lock_path.open("a+b")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not claim.exists():
            require(phase in ("download", "all"), "download must claim attempt first")
            state = {"schema": 1, "attempt": uuid.uuid4().hex, "manifest_sha256": sha,
                     "state": "claimed", "phases": {}, "created_utc": time.time()}
            write_json(claim, state, exclusive=True)
            (ROOT / "run").mkdir(mode=0o700)
            for name in ("home", "tmp", "wheels"):
                (ROOT / "run" / name).mkdir(mode=0o700)
        state = read_json(claim)
        require(state["manifest_sha256"] == sha, "attempt bound to different manifest")
        require(state["state"] in STATES.values() or state["state"] == "assess_done", "terminal/stale claim; do not delete or retry")
        return lock, state
    except BaseException:
        lock.close()
        raise


def save_state(state):
    tmp = ROOT / "RUN_CLAIM.next"
    write_json(tmp, state, exclusive=True)
    os.replace(tmp, ROOT / "RUN_CLAIM.json")


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


def owned_process(command, cwd, env, logfile, seconds):
    """Own one process group, including spawn and seven-second cleanup reserve.

    SIGALRM covers blocking Popen initialization (whose pid becomes available on
    the allocated object), log open, native work and writes. Like any userspace
    watchdog this relies on the OS delivering signals and scheduling the parent.
    """
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "active parent alarm")
    started, process, output = time.monotonic(), None, None
    deadline = started + seconds
    timed_out, cleanup_ok, failure = False, False, None
    old_handler = signal.getsignal(signal.SIGALRM)
    def alarm(signum, frame):
        raise PhaseTimeout("owned lifecycle deadline")
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, seconds - 7))
    try:
        try:
            output = Path(logfile).open("xb")
            # Allocate before __init__: a blocked exec error-pipe read may occur
            # after fork and pid assignment but before Popen normally returns.
            process = subprocess.Popen.__new__(subprocess.Popen)
            subprocess.Popen.__init__(process, command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                      stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            process.wait(timeout=max(0, deadline - 7 - time.monotonic()))
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
              "failure": None if failure is None else type(failure).__name__ + ": " + str(failure)}
    require(cleanup_ok and not result["timed_out"] and result["exit_code"] == 0 and failure is None,
            "owned child failed: " + json.dumps(result))
    return result


def preflight_resources():
    disk = os.statvfs(ROOT)
    require(disk.f_bavail * disk.f_frsize >= 2 * 1024 * MIB, "less than 2 GiB free disk")
    available = re.search(r"^MemAvailable:\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.M)
    require(available and int(available.group(1)) * 1024 >= 2 * 1024 * MIB, "less than 2 GiB MemAvailable")


def download(run):
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError("redirect forbidden")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    total = 0
    reports = []
    for pin in package_pins():
        target = run / "wheels" / pin["filename"]
        request = urllib.request.Request(pin["url"], headers={"Accept-Encoding": "identity"})
        with opener.open(request, timeout=230) as response, target.open("xb") as output:
            require(response.status == 200 and response.url == pin["url"], "unexpected HTTP response")
            require(response.headers.get("Content-Encoding", "identity") == "identity", "encoded response")
            require(response.headers.get("Content-Length") == str(pin["size_bytes"]), "HTTP size mismatch")
            count = 0
            for block in iter(lambda: response.read(MIB), b""):
                count += len(block)
                total += len(block)
                require(count <= pin["size_bytes"] and total <= 100 * MIB, "download limit exceeded")
                output.write(block)
        verify_file(target, {"bytes": pin["size_bytes"], "sha256": pin["sha256"]})
        reports.append({"url": pin["url"], **digest_file(target)})
    write_json(run / "download.json", {"artifacts": reports, "compressed_bytes": total}, exclusive=True)


def inspect_wheels(wheels, pins):
    """No extraction until ALL members and RECORD hashes have been verified."""
    total = 0
    reports = []
    for wheel, pin in zip(wheels, pins, strict=True):
        verify_file(wheel, {"bytes": pin["size_bytes"], "sha256": pin["sha256"]})
        with zipfile.ZipFile(wheel) as archive:
            members = archive.infolist()
            names = [m.filename for m in members]
            require(len(names) == len(set(names)), "duplicate archive member")
            for member in members:
                name = member.filename
                path = PurePosixPath(name)
                mode = member.external_attr >> 16
                require(name and not name.startswith("/") and "\\" not in name and ":" not in name
                        and all(p not in ("", ".", "..") for p in name.rstrip("/").split("/"))
                        and not member.flag_bits & 1, "unsafe/encrypted wheel member")
                require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), "link/special wheel member")
                require(not name.endswith((".pth", ".egg-link")) and not any(p.endswith(".data") for p in path.parts),
                        "wheel startup hook/data relocation forbidden")
                total += member.file_size
                require(total <= 512 * MIB, "uncompressed payload limit")
            files = {m.filename for m in members if not m.is_dir()}
            record_paths = [n for n in files if n.endswith(".dist-info/RECORD")]
            require(len(record_paths) == 1, "wheel RECORD missing/ambiguous")
            record_name = record_paths[0]
            require(archive.getinfo(record_name).file_size <= MIB, "oversize RECORD")
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            require(all(len(r) == 3 for r in rows) and len(rows) == len({r[0] for r in rows})
                    and {r[0] for r in rows} == files, "RECORD inventory mismatch")
            hashes = {}
            for name, encoded, length in rows:
                if name == record_name:
                    require(encoded == length == "", "RECORD self hash forbidden")
                    continue
                require(encoded.startswith("sha256=") and length.isdecimal(), "unsupported RECORD digest/size")
                h, size = hashlib.sha256(), 0
                with archive.open(name) as stream:
                    for block in iter(lambda: stream.read(MIB), b""):
                        size += len(block)
                        require(size <= archive.getinfo(name).file_size, "member expands beyond declared size")
                        h.update(block)
                actual = base64.urlsafe_b64encode(h.digest()).decode().rstrip("=")
                require(str(size) == length and actual == encoded[7:], "RECORD hash/size mismatch")
                hashes[name] = {"bytes": size, "sha256": h.hexdigest()}
            prefix = record_name.rsplit("/", 1)[0]
            metadata = archive.read(prefix + "/METADATA")
            require(len(metadata) == pin["wheel_core_metadata_size_bytes"] and
                    hashlib.sha256(metadata).hexdigest() == pin["wheel_core_metadata_sha256"], "core metadata changed")
            parsed = email.parser.BytesParser().parsebytes(metadata)
            require(parsed["Name"].lower().replace("_", "-") == pin["name"].lower().replace("_", "-")
                    and parsed["Version"] == pin["version"] and parsed.get_all("Requires-Dist", []) == pin["requires_dist"],
                    "metadata identity/dependency mismatch")
            tags = email.parser.BytesParser().parsebytes(archive.read(prefix + "/WHEEL")).get_all("Tag", [])
            expected_tags = {"cp312-cp312-manylinux2014_x86_64", "cp312-cp312-manylinux_2_17_x86_64"} if pin["name"] == "SudachiPy" else {"py3-none-any"}
            require(set(tags) == expected_tags, "wheel tag mismatch")
            notices = [n for n in files if PurePosixPath(n).name.upper().startswith(("LICENSE", "LEGAL", "NOTICE"))]
            require(notices, "license files missing")
            if pin["name"] == "SudachiDict-core":
                require(hashes.get("sudachidict_core/resources/system.dic") == {"bytes": DICT_SIZE, "sha256": DICT_SHA},
                        "dictionary identity mismatch")
                require(any(PurePosixPath(n).name == "LICENSE-2.0.txt" for n in notices), "declared dictionary license missing")
            reports.append({"wheel": wheel.name, "members": len(files), "notices": notices,
                            "uncompressed_bytes": sum(m.file_size for m in members), "record_verified": True})
    return {"wheels": reports, "total_uncompressed_bytes": total}


def site_path(run):
    return run / "venv" / "lib" / "python3.12" / "site-packages"


def installed_snapshot(run):
    site = site_path(run)
    dictionary = site / "sudachidict_core" / "resources" / "system.dic"
    verify_file(dictionary, {"bytes": DICT_SIZE, "sha256": DICT_SHA})
    entries = {}
    for path in sorted(site.rglob("*")):
        require(not path.is_symlink(), "installed symlink")
        if path.is_file():
            require(path.suffix not in (".pth", ".egg-link"), "installed startup hook")
            entries[str(path.relative_to(site))] = digest_file(path)
    require(sum(x["bytes"] for x in entries.values()) <= 512 * MIB, "installed payload limit")
    return {"files": entries, "total_installed_bytes": sum(x["bytes"] for x in entries.values()),
            "dictionary": digest_file(dictionary)}


def setup(run, sha):
    import venv
    pins = package_pins()
    wheels = [run / "wheels" / p["filename"] for p in pins]
    archive_report = inspect_wheels(wheels, pins)
    venv.EnvBuilder(with_pip=False, symlinks=False).create(run / "venv")
    python = run / "venv" / "bin" / "python"
    # ensurepip is the CPython bundled offline installer, never a network fetch.
    subprocess.run([str(python), "-I", "-B", "-m", "ensurepip", "--default-pip"], check=True, env=clean_environment(run), cwd=run)
    subprocess.run([str(python), "-I", "-B", str(ROOT / "pilot_runner.py"), "_install", "--manifest-sha256", sha,
                    "--parent-pid", str(os.getpid())],
                   check=True, env=clean_environment(run), cwd=run)
    require("include-system-site-packages = false" in (run / "venv" / "pyvenv.cfg").read_text(), "venv not isolated")
    require(digest_file(python) == digest_file(Path(sys.executable).resolve()), "venv interpreter differs from host")
    write_json(run / "installed.json", installed_snapshot(run), exclusive=True)
    write_json(run / "setup.json", {"archives": archive_report, "installer": "stdlib ensurepip + isolated offline pip",
               "host_python": {"path": str(Path(sys.executable).resolve()), "version": platform.python_version(), **digest_file(Path(sys.executable).resolve())},
               "venv_python": {"path": str(python), **digest_file(python)},
               "retained_source_notices": {name: digest_file(ROOT / name) for name in LICENSE_FILES},
               "network_boundary": "Python socket audit hook; native extension no-network assumption, not an OS sandbox"}, exclusive=True)


def install_local(run):
    import runpy
    require(Path(sys.prefix).resolve() == (run / "venv").resolve() and sys.prefix != sys.base_prefix, "installer outside venv")
    sys.argv = ["pip", "--isolated", "--disable-pip-version-check", "--no-cache-dir", "install", "--no-index",
                "--no-deps", "--no-compile", "--only-binary=:all:"] + [str(run / "wheels" / p["filename"]) for p in package_pins()]
    try:
        runpy.run_module("pip", run_name="__main__")
    except SystemExit as exc:
        require(exc.code in (None, 0), "offline pip failed")


def parse_batch(run, sha):
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * MIB, 1024 * MIB))
    started = time.perf_counter()
    snapshot = installed_snapshot(run)
    require(snapshot == read_json(run / "installed.json"), "installed package bytes changed")
    require(Path(sys.prefix).resolve() == (run / "venv").resolve() and sys.prefix != sys.base_prefix, "parser outside venv")
    import importlib.metadata
    versions = {d.metadata["Name"].lower().replace("_", "-"): d.version for d in importlib.metadata.distributions()}
    require(versions.get("sudachipy") == "0.6.11" and versions.get("sudachidict-core") == "20260723"
            and set(versions) == {"pip", "sudachipy", "sudachidict-core"}, "installed package inventory mismatch")
    from sudachipy import Dictionary, Tokenizer
    import sudachipy
    require(Path(sudachipy.__file__).resolve().is_relative_to(site_path(run)), "unexpected engine import")
    dictionary = site_path(run) / "sudachidict_core" / "resources" / "system.dic"
    config = json.dumps({"userDict": [], "projection": "surface"})
    engine = Dictionary(dict=str(dictionary), config=config, resource_dir=str(site_path(run) / "sudachipy" / "resources"))
    tokenizer = engine.create(mode=Tokenizer.SplitMode.C, projection="surface")
    initialized = time.perf_counter()
    # -I intentionally removes script paths. Add ONLY the verified local helper directory.
    sys.path.insert(0, str(ROOT))
    from lexical_policy import validate_tokens
    records = []
    for row in batch_sources():
        one_started = time.perf_counter()
        morphs = tokenizer.tokenize(row["source"])
        tokens = [{"start": m.begin(), "end": m.end(), "raw_surface": m.raw_surface(),
                   "pos": list(m.part_of_speech()), "is_oov": m.is_oov(), "dictionary_id": m.dictionary_id()} for m in morphs]
        validate_tokens(row["source"], tokens)
        records.append({**row, "tokens": tokens, "latency_seconds": time.perf_counter() - one_started})
    engine.close()
    result = {"schema": 1, "manifest_sha256": sha, "complete": True, "parser_calls": len(records),
              "records": records, "package_versions": versions, "dictionary": snapshot["dictionary"],
              "cold_initialization_seconds": initialized - started,
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
              "elapsed_before_output_seconds": time.perf_counter() - started,
              "network_boundary": "Python socket audit denied; native extension assumed network-free; not an OS network sandbox",
              "configuration": {"split_mode": "C", "userDict": [], "projection": "surface", "dictionary_path": str(dictionary)}}
    write_json(run / "parser.json", result, exclusive=True)


def occurrence_diagnostics(source, tokens, keys):
    spans = {(t["start"], t["end"]): t for t in tokens}
    return [{"key": key, "start": m.start(), "end": m.end(), "exact_token": spans.get((m.start(), m.end())),
             "overlapping_tokens": [t for t in tokens if t["start"] < m.end() and t["end"] > m.start()]}
            for key in keys for m in re.finditer(re.escape(key), source)]


def assess(run, sha):
    parsed = read_json(run / "parser.json")
    require(parsed["complete"] is True and parsed["parser_calls"] == 48 and parsed["manifest_sha256"] == sha
            and parsed["dictionary"] == {"bytes": DICT_SIZE, "sha256": DICT_SHA}, "incomplete technical evidence")
    batch = batch_sources()
    require(len(parsed["records"]) == 48 and [{"id": r["id"], "source": r["source"]} for r in parsed["records"]] == batch,
            "parser population/order mismatch")
    sys.path.insert(0, str(ROOT))
    from lexical_policy import admitted_entries
    keys = [r["src"] for r in read_json(ROOT / "canon.json")["entries"]]
    decisions = []
    for row in parsed["records"]:
        decisions.append({"id": row["id"], "admitted": admitted_entries(row["source"], row["tokens"], keys),
                          "occurrences": occurrence_diagnostics(row["source"], row["tokens"], keys)})
    # Expected labels are read only after all 48 outputs and source-only decisions validate.
    expected = read_json(ROOT / "diagnostics.expected.json")
    require([e["id"] for e in expected] == [r["id"] for r in batch[:16]], "expected fixture IDs mismatch")
    gates = [{**d, "category": e["category"], "expected": e["expected_admitted_canon_keys"],
              "match": set(d["admitted"]) == set(e["expected_admitted_canon_keys"])}
             for d, e in zip(decisions[:16], expected, strict=True)]
    categories = sorted({g["category"] for g in gates})
    passed = all(g["match"] for g in gates)
    write_json(run / "assessment.json", {"technical_complete": True, "lexical_gate_passed": passed,
               "diagnostics": gates, "per_stratum_failures": {c: [g["id"] for g in gates if g["category"] == c and not g["match"]] for c in categories},
               "seen_regressions": decisions[16:], "conclusion": "Lexical feasibility only; no semantic, translation-quality, Hy, or Windows performance claim",
               "candidate_decision": "consider separately frozen semantic experiment" if passed else "reject this fixed lexical mechanism; retain baseline"}, exclusive=True)


def child(phase, sha, parent_pid):
    run = ROOT / "run"
    require(os.getppid() == parent_pid and parent_pid > 1, "child must belong to controller")
    if phase == "parse":
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_AS, (1024 * MIB, 1024 * MIB))
    verify_manifest(sha)
    state = read_json(ROOT / "RUN_CLAIM.json")
    for completed in state["phases"].values():
        for name, pin in completed.get("artifacts", {}).items():
            verify_file(run / name, pin)
    if phase == "_install":
        require(state["state"] == "setup_running", "installer outside setup")
    else:
        require(state["state"] == phase + "_running", "child phase/state mismatch")
    resource.setrlimit(resource.RLIMIT_FSIZE, ((100 if phase == "download" else 512 if phase == "setup" or phase == "_install" else 4) * MIB,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if phase != "download":
        sys.addaudithook(block_network)
    try:
        if phase == "download":
            download(run)
        elif phase == "setup":
            setup(run, sha)
        elif phase == "parse":
            parse_batch(run, sha)
        elif phase == "assess":
            assess(run, sha)
        else:
            install_local(run)
    except BaseException as exc:
        try:
            write_json(run / (phase.strip("_") + ".error.json"), {"type": type(exc).__name__, "error": str(exc), "complete": False}, exclusive=True)
        finally:
            raise


def control(phase, sha):
    verify_manifest(sha)
    host_check()
    package_pins()
    batch_sources()
    lock, state = claim_run(sha, phase)
    run = ROOT / "run"
    try:
        phases = PHASES if phase == "all" else (phase,)
        for current in phases:
            require(state["state"] == STATES[current], "phase already consumed or out of order")
            state["state"] = current + "_running"
            save_state(state)
            try:
                verify_manifest(sha)
                for completed in state["phases"].values():
                    for name, pin in completed.get("artifacts", {}).items():
                        verify_file(run / name, pin)
                if current == "download":
                    preflight_resources()
                python = run / "venv" / "bin" / "python" if current == "parse" else Path(sys.executable)
                command = [str(python), "-I", "-B", str(ROOT / "pilot_runner.py"), "_child", current,
                           "--manifest-sha256", sha, "--parent-pid", str(os.getpid())]
                state["phases"][current] = owned_process(command, run, clean_environment(run), run / (current + ".log"), LIMITS[current])
                verify_manifest(sha)
                state["phases"][current]["artifacts"] = {name: digest_file(run / name) for name in ARTIFACTS[current]}
                state["state"] = current + "_done"
                save_state(state)
            except BaseException as exc:
                state["state"] = "terminal_failure"
                state["error"] = {"phase": current, "type": type(exc).__name__, "message": str(exc)}
                save_state(state)
                raise
    finally:
        lock.close()
    print(json.dumps({"state": state["state"], "attempt": state["attempt"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["freeze", "all", *PHASES, "_child", "_install"])
    parser.add_argument("child_phase", nargs="?", choices=PHASES)
    parser.add_argument("--manifest-sha256", default="")
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args()
    if args.phase == "freeze":
        freeze()
    elif args.phase in ("_child", "_install"):
        child(args.child_phase if args.phase == "_child" else "_install", args.manifest_sha256, args.parent_pid)
    else:
        control(args.phase, args.manifest_sha256)


if __name__ == "__main__":
    main()
