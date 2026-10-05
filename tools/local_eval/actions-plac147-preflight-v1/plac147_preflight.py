"""Disabled, metadata-only admission stage. Never acquires or executes wheels."""

import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time

SOURCE_ONLY = False
ROOT = Path(__file__).resolve().parent
FRAMEWORK_SHA256 = "de59208f9428e5713bb6a878f11a780d04955d6be5082f69b7f9620c432de8a6"
BASE48_SHA256 = "5ac01b1ebf8f4ead351cbca6d071627376a9863f5c1cff364e1ab2c6e18d7ac4"
PREVIOUS_METADATA_SHA256 = "f4c97284225254d04d82efd4d60daa609c26755e302d335dabcb5d7346f3537e"
URL = "https://pypi.org/pypi/plac/1.4.7/json"
FILENAME = "plac-1.4.7-py2.py3-none-any.whl"
WHEEL_SHA256 = "8af4bcd5d52e06c31fab641bffb7040d0eb0e579e2f70a4d2e87af5eed0612ea"
BASE48_BYTES = 207384350
MAX_WHEEL_BYTES = 32768
MAX_AGGREGATE_WHEEL_BYTES = 250 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
ACTIVE_SECONDS = 20.0
REPORT_SECONDS = 25.0
ERRORS = frozenset({"source_only_disabled", "baseline_mismatch", "framework_mismatch",
                    "deadline", "cancelled", "invalid_json", "release_identity_mismatch",
                    "dependency_metadata_mismatch", "python_metadata_mismatch",
                    "licence_metadata_mismatch", "wheel_identity_mismatch", "yanked",
                    "wheel_size_mismatch", "ambiguous_selected_file", "json_size_limit",
                    "aggregate_cap", "output_limit", "unsupported_reader_host", "internal_failure"})


class PreflightError(Exception):
    def __init__(self, code):
        self.code = code if code in ERRORS else "internal_failure"
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise PreflightError(code)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def pinned_bytes(filename, wanted, limit):
    path = ROOT / filename
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, "baseline_mismatch")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == wanted, "baseline_mismatch")
    return data


def load_framework():
    data = pinned_bytes("reviewed_metadata_framework.py", FRAMEWORK_SHA256, 32768)
    require(hashlib.sha256(data).hexdigest() == FRAMEWORK_SHA256, "framework_mismatch")
    spec = importlib.util.spec_from_file_location("reviewed_public_metadata_framework", ROOT / "reviewed_metadata_framework.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load_framework()


class SingleURLTransport(F.MetadataTransport):
    def __init__(self, clock=time.monotonic):
        super().__init__(clock=clock)
        # No network occurs in the reviewed constructor. Replace its broad
        # research allowlist before any request with exactly the new fixed URL.
        self.urls = frozenset({URL})


def load_baseline():
    base = json.loads(pinned_bytes("BASE48.json", BASE48_SHA256, 128 * 1024))
    previous = json.loads(pinned_bytes("metadata-summary.json", PREVIOUS_METADATA_SHA256, 256 * 1024))
    require(base["source_metadata_sha256"] == PREVIOUS_METADATA_SHA256, "baseline_mismatch")
    original = {r["name"]: r for r in previous["records"]}
    files = base["files"]
    require(len(files) == 48 and len(original) == 49, "baseline_mismatch")
    require({r["name"] for r in files} == set(original) - {"plac"}, "baseline_mismatch")
    require(original["plac"]["version"] == "1.4.6", "baseline_mismatch")
    for row in files:
        evidence = original[row["name"]]
        candidates = evidence["candidate_files_for_review"] + ([evidence["selected"]] if evidence["selected"] else [])
        require(row["version"] == evidence["version"] and row["wheel"] in candidates, "baseline_mismatch")
        require(row["wheel"]["yanked"] is False, "baseline_mismatch")
        require(row["registry_licence_declarations"] == evidence["licence_declared_by_registry"], "baseline_mismatch")
    require(sum(r["wheel"]["bytes"] for r in files) == base["aggregate_bytes"] == BASE48_BYTES, "baseline_mismatch")
    return base


def verify_plac(body):
    require(isinstance(body, bytes) and len(body) <= MAX_JSON_BYTES, "json_size_limit")
    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=F.unique_json, parse_constant=F.reject_json_constant)
    except (ValueError, UnicodeError):
        raise PreflightError("invalid_json") from None
    require(isinstance(data, dict) and isinstance(data.get("info"), dict), "invalid_json")
    info = data["info"]
    require(info.get("name") == "plac" and info.get("version") == "1.4.7", "release_identity_mismatch")
    require("requires_dist" in info and info["requires_dist"] in (None, []), "dependency_metadata_mismatch")
    require("requires_python" in info and info["requires_python"] is None, "python_metadata_mismatch")
    require(info.get("license") == "BSD License" and "license_expression" in info and
            info["license_expression"] is None, "licence_metadata_mismatch")
    classifiers = info.get("classifiers")
    require(isinstance(classifiers, list) and all(isinstance(s, str) for s in classifiers), "licence_metadata_mismatch")
    licence_classifiers = [s for s in classifiers if s.startswith("License ::")]
    require(licence_classifiers == ["License :: OSI Approved :: BSD License"], "licence_metadata_mismatch")
    require(info.get("yanked") is False, "yanked")
    urls = data.get("urls")
    require(isinstance(urls, list) and all(isinstance(r, dict) for r in urls), "invalid_json")
    matches = [r for r in urls if r.get("filename") == FILENAME]
    require(len(matches) == 1, "ambiguous_selected_file")
    entry = matches[0]
    require(entry.get("packagetype") == "bdist_wheel", "wheel_identity_mismatch")
    require(entry.get("digests", {}).get("sha256") == WHEEL_SHA256, "wheel_identity_mismatch")
    require(entry.get("yanked") is False, "yanked")
    require("requires_python" in entry and entry["requires_python"] is None, "python_metadata_mismatch")
    size = entry.get("size")
    require(type(size) is int and 0 < size <= MAX_WHEEL_BYTES, "wheel_size_mismatch")
    # Reuses the reviewed official-host/path, SHA, and byte validation. It only
    # records this URL and never requests it.
    wheel = F.file_record(entry)
    return {"name": "plac", "version": "1.4.7", "wheel": wheel,
            "registry_licence_declarations": {"legacy": "BSD License", "expression": None,
                                               "classifiers": licence_classifiers}}


def perform(fetch, clock=time.monotonic):
    start = clock()
    receipt = {"status": "blocked", "code": None, "attempted_gets": 0,
               "metadata_url": URL, "previous_metadata_sha256": PREVIOUS_METADATA_SHA256,
               "base48_sha256": BASE48_SHA256, "base48_bytes": BASE48_BYTES,
               "version_amendment": {"from": "plac==1.4.6", "to": "plac==1.4.7"},
               "acquisition_allowed": False, "installation_allowed": False,
               "ner_execution_allowed": False}
    try:
        base = load_baseline()
        deadline = start + ACTIVE_SECONDS
        require(clock() < deadline, "deadline")
        receipt["attempted_gets"] = 1
        body = fetch(URL, deadline, MAX_JSON_BYTES)
        require(clock() < deadline, "deadline")
        plac = verify_plac(body)
        require(clock() < deadline, "deadline")
        files = sorted(base["files"] + [plac], key=lambda r: r["name"])
        total = sum(r["wheel"]["bytes"] for r in files)
        require(len(files) == 49 and total <= MAX_AGGREGATE_WHEEL_BYTES, "aggregate_cap")
        manifest = {"kind": "EXACT_METADATA_SNAPSHOT_ONLY_NOT_EXECUTION_APPROVAL",
                    "previous_metadata_sha256": PREVIOUS_METADATA_SHA256,
                    "base48_sha256": BASE48_SHA256,
                    "plac147_metadata_sha256": hashlib.sha256(body).hexdigest(),
                    "version_amendment": receipt["version_amendment"],
                    "target": base["target"], "files": files, "aggregate_bytes": total,
                    "actual_host_compatibility": "unverified",
                    "embedded_wheel_metadata_record_and_notices": "unverified",
                    "next_action": "review_frozen_manifest_only"}
        receipt.update(status="metadata_verified_manifest_frozen", metadata_bytes=len(body),
                       frozen_manifest=manifest, frozen_manifest_sha256=hashlib.sha256(encoded(manifest)).hexdigest())
        require(len(encoded(receipt)) < MAX_OUTPUT_BYTES - 512, "output_limit")
        require(clock() < deadline, "deadline")
    except (PreflightError, F.Stop) as error:
        receipt.pop("frozen_manifest", None)
        receipt.pop("frozen_manifest_sha256", None)
        receipt["status"] = "blocked"
        receipt["code"] = error.code
    except (KeyboardInterrupt, SystemExit):
        receipt.pop("frozen_manifest", None)
        receipt.pop("frozen_manifest_sha256", None)
        receipt.update(status="blocked", code="cancelled")
    except Exception:
        receipt.pop("frozen_manifest", None)
        receipt.pop("frozen_manifest_sha256", None)
        receipt.update(status="blocked", code="internal_failure")
    receipt["elapsed_ms"] = max(0, round((clock() - start) * 1000))
    return receipt


def main():
    if SOURCE_ONLY:
        F.emit({"status": "blocked", "code": "source_only_disabled"})
        return 2
    if not F.environment_ok():
        F.emit({"status": "blocked", "code": "unsupported_reader_host"})
        return 2
    def interrupt(signum, frame):
        raise PreflightError("deadline")
    signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, REPORT_SECONDS)
    try:
        result = perform(SingleURLTransport())
        F.emit(result)
        return 0 if result["status"] == "metadata_verified_manifest_frozen" else 2
    except (PreflightError, F.Stop) as error:
        F.emit({"status": "blocked", "code": error.code})
        return 2
    except (KeyboardInterrupt, SystemExit):
        F.emit({"status": "blocked", "code": "cancelled"})
        return 130
    except Exception:
        F.emit({"status": "blocked", "code": "internal_failure"})
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    sys.exit(main())
