"""Prospective owned-process stages. All command-line entry points are stopped.

These routines are source for review, not an execution release. There is no
automatic stage loop, retry, new identity, model fallback, or GPU continuation.
The copied owned_lifecycle helper is byte-identical to its reviewed predecessor.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import stat
import sys
import time
import urllib.request

from ner_adapter import ProbeFailure, require, canonical_json, sha256_bytes, MAX_EVIDENCE_BYTES
from owned_lifecycle import owned_process, OwnedFailure

MIB = 1024 * 1024
DOWNLOAD_CAP = 250 * MIB
INSTALLED_CAP = 1024 * MIB
PROPOSED_PARSER_AS_CAP = 2 * 1024 * MIB
STAGES = (("download", 240), ("setup", 60), ("parse", 60))
CPU_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "BLIS_NUM_THREADS": "1",
    "OMP_DYNAMIC": "FALSE", "MKL_DYNAMIC": "FALSE", "CUDA_VISIBLE_DEVICES": "",
    "NVIDIA_VISIBLE_DEVICES": "none", "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1",
    "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_CACHE_DIR": "1",
    "PIP_CONFIG_FILE": "/dev/null", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
}


def child_environment(work, runtime):
    """Allowlist only. Never pass tokens, cloud credentials, proxy or user config."""
    work, runtime = Path(work), Path(runtime)
    require(work.is_absolute() and runtime.is_absolute(), "invalid_child_paths")
    return {**CPU_ENVIRONMENT, "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"),
            "PATH": str(runtime / "bin") + ":/usr/bin:/bin", "LD_LIBRARY_PATH": str(runtime / "lib")}


def deny_network(event, args):
    if event.startswith("socket."):
        raise ProbeFailure("offline_network_denied")


def set_child_limits(stage):
    """Run in the owned child before model-factory imports.

    Python startup may first execute the exact audited setuptools .pth/shim.
    This is an explicit trusted startup exception; the outer owned deadline
    already covers it. Whole-process CPU/RSS readings include that startup.

    Proposed CPU cap: 2GiB, without a runtime override or post-failure increase.
    This allows virtual mapping headroom for fixed single-thread NumPy/BLIS;
    compatibility is unmeasured and requires review before release. RSS remains
    measured eligibility, never described as RLIMIT_RSS enforcement.
    """
    require(stage in dict(STAGES), "invalid_stage")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output_limit = DOWNLOAD_CAP if stage == "download" else INSTALLED_CAP if stage == "setup" else MAX_EVIDENCE_BYTES
    resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))
    if stage == "parse":
        resource.setrlimit(resource.RLIMIT_AS, (PROPOSED_PARSER_AS_CAP, PROPOSED_PARSER_AS_CAP))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))


def host_preflight(runtime, work):
    """No package/native-model imports. Exact official cache identity required."""
    runtime, work = Path(runtime), Path(work)
    require(platform.python_implementation() == "CPython" and platform.python_version() == "3.12.14"
            and platform.system() == "Linux" and platform.machine() == "x86_64", "unsupported_host")
    require(runtime.is_absolute() and runtime.resolve(strict=True) == runtime
            and runtime.parts[-3:] == ("Python", "3.12.14", "x64")
            and (runtime.parent / "x64.complete").is_file()
            and Path(sys.base_prefix).resolve() == runtime, "runtime_cache_mismatch")
    libc, version = platform.libc_ver()
    require(libc == "glibc" and tuple(map(int, version.split(".")[:2])) >= (2, 28), "unsupported_libc")
    require(shutil.disk_usage(work).free >= 3 * 1024 * MIB, "insufficient_disk")
    memory = Path("/proc/meminfo").read_text(encoding="ascii")
    available = next((line.split()[1] for line in memory.splitlines() if line.startswith("MemAvailable:")), None)
    require(available is not None and int(available) >= 2 * 1024 * 1024, "insufficient_ram")
    return {"implementation": "CPython", "python": "3.12.14", "system": "Linux", "machine": "x86_64",
            "interpreter_sha256": file_pin(Path(sys.executable).resolve())["sha256"], "glibc": version}


def file_pin(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), "unsafe_artifact")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe_artifact")
        return {"bytes": info.st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}


def exclusive_json(path, data):
    encoded = canonical_json(data)
    require(len(encoded) <= MAX_EVIDENCE_BYTES, "output_size_exceeded")
    with Path(path).open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


@contextlib.contextmanager
def exclusive_claim(work, bindings):
    """One new identity. Existing claims are terminal, never reused or reset."""
    work = Path(work)
    require(work.resolve(strict=True) == work and work.is_dir(), "unsafe_work_directory")
    lock = (work / "CONTROL_LOCK").open("xb")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        exclusive_json(work / "RUN_CLAIM.json", {"bindings": bindings, "pid": os.getpid(), "state": "claimed"})
        for name in ("home", "tmp", "wheels"):
            (work / name).mkdir(mode=0o700)
        yield
    finally:
        lock.close()


def run_one_stage(stage, command, work, environment, bindings, prerequisite_receipts):
    """Only one named stage; earlier evidence must match its immutable receipt.

    A future released controller must bind the immutable event/run identity and
    complete reviewed source inventory before entering this routine. No such
    release/event guard is installed by source preparation.
    """
    work = Path(work)
    stage_names = [name for name, _ in STAGES]
    require(stage in stage_names, "invalid_stage")
    require(list(prerequisite_receipts) == stage_names[:stage_names.index(stage)], "phase_order_mismatch")
    require(not (work / "TERMINAL_FAILURE.json").exists(), "terminal_attempt")
    for earlier, expected in prerequisite_receipts.items():
        require(file_pin(work / (earlier + ".receipt.json")) == expected, "receipt_changed")
        receipt = json.loads((work / (earlier + ".receipt.json")).read_bytes())
        require(receipt["bindings"] == bindings and receipt["stage"] == earlier, "receipt_binding_mismatch")
        for filename, pin in receipt["artifacts"].items():
            require(Path(filename).name == filename and file_pin(work / filename) == pin, "artifact_changed")
    # Exclusive start marker prevents retry even after interruption before a receipt.
    exclusive_json(work / (stage + ".started.json"), {"stage": stage, "bindings": bindings})
    try:
        lifecycle = owned_process(command, work, environment, work / (stage + ".private.log"),
                                  dict(STAGES)[stage], cleanup_reserve=7)
        return lifecycle
    except BaseException as exc:
        record = {"stage": stage, "bindings": bindings, "status": "terminal_failure",
                  "category": "owned_phase_failed" if isinstance(exc, OwnedFailure) else "phase_failed"}
        if isinstance(exc, OwnedFailure):
            record["lifecycle"] = exc.result
        exclusive_json(work / "TERMINAL_FAILURE.json", record)
        raise ProbeFailure(record["category"]) from None


def seal_stage_receipt(work, stage, bindings, lifecycle, filenames):
    """Only seal after successful lifecycle and phase-specific evidence review."""
    require(stage in dict(STAGES) and type(filenames) is tuple and 0 < len(filenames) <= 16,
            "invalid_receipt")
    require(lifecycle["exit_code"] == 0 and lifecycle["cleanup_confirmed"] is True
            and lifecycle["timed_out"] is False and lifecycle["failure"] is None
            and lifecycle["deadline_seconds"] == dict(STAGES)[stage]
            and 0 <= lifecycle["elapsed_seconds"] <= dict(STAGES)[stage], "invalid_lifecycle")
    require(all(type(name) is str and Path(name).name == name for name in filenames), "unsafe_artifact")
    receipt = {"stage": stage, "bindings": bindings, "lifecycle": lifecycle,
               "artifacts": {name: file_pin(Path(work) / name) for name in filenames}}
    target = Path(work) / (stage + ".receipt.json")
    exclusive_json(target, receipt)
    return file_pin(target)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeFailure("redirect_forbidden")


def download_pinned_wheels(manifest_bytes, destination, *, progress=None):
    """Future phase code only. Finalized manifest must already have passed validation.

    Does not perform plac metadata refresh, resolution, retries or fallbacks.
    One official GET per fixed wheel, rejecting redirects and response encodings.
    An outer owned 240s phase includes cleanup; this inner budget reserves 7s.
    """
    from finalized_manifest import read_finalized_manifest
    records = {record['name']: record for record in read_finalized_manifest(manifest_bytes)['files']}
    destination = Path(destination)
    opener = urllib.request.build_opener(NoRedirect())
    deadline, total = time.monotonic() + 233, 0
    for pin in records.values():
        if progress is not None:
            progress("download", pin["name"])
        wheel = pin["wheel"]
        require(wheel["url"].startswith("https://files.pythonhosted.org/packages/")
                and Path(wheel["filename"]).name == wheel["filename"], "nonofficial_wheel_url")
        require(time.monotonic() < deadline and total + wheel["bytes"] <= DOWNLOAD_CAP, "download_budget_exceeded")
        request = urllib.request.Request(wheel["url"], headers={"Accept-Encoding": "identity"}, method="GET")
        with opener.open(request, timeout=max(.01, min(30, deadline - time.monotonic()))) as response:
            require(response.status == 200 and response.geturl() == wheel["url"]
                    and response.headers.get("Content-Encoding", "identity") == "identity", "invalid_wheel_response")
            expected_header = response.headers.get("Content-Length")
            require(expected_header is not None and expected_header == str(wheel["bytes"]), "wheel_size_mismatch")
            count, digest = 0, hashlib.sha256()
            with (destination / wheel["filename"]).open("xb") as output:
                while True:
                    require(time.monotonic() < deadline, "download_deadline")
                    block = response.read(min(1024 * 1024, wheel["bytes"] - count + 1))
                    if not block:
                        break
                    count += len(block)
                    total += len(block)
                    require(count <= wheel["bytes"] and total <= DOWNLOAD_CAP, "download_budget_exceeded")
                    digest.update(block)
                    output.write(block)
            require(count == wheel["bytes"] and digest.hexdigest() == wheel["sha256"], "wheel_hash_mismatch")
    return {"wheel_count": 49, "compressed_bytes": total}


def main():
    print('{"status":"stopped","reason":"source_preparation_only_not_released"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
