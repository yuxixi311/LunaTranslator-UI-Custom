"""SOURCE-ONLY REVIEW TEMPLATE. No NER, installation, or binary acquisition.

The entry point is intentionally disabled. A separate owner-approved release
must change SOURCE_ONLY after reviewing this file's exact hash. Importing this
module defines standard-library-only metadata helpers and performs no I/O.
"""

import hashlib
import json
import os
import re
import signal
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


SOURCE_ONLY = True
MAX_GETS = 49
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
ACTIVE_SECONDS = 50.0
REPORT_DEADLINE_SECONDS = 55.0
HARD_DEADLINE_SECONDS = 60.0
MAX_READ_CHUNK = 64 * 1024

PIN_TEXT = """annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.14.2
blis==1.3.3
catalogue==2.0.10
certifi==2026.7.22
charset-normalizer==3.5.1
click==8.4.2
cloudpathlib==0.24.0
confection==1.3.3
cymem==2.0.13
ginza==5.2.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.19
ja-ginza==5.2.0
jinja2==3.1.6
markdown-it-py==4.2.0
markupsafe==3.0.3
mdurl==0.1.2
murmurhash==1.0.15
numpy==2.5.2
packaging==26.3
plac==1.4.6
preshed==3.0.13
pydantic==2.13.4
pydantic-core==2.46.4
pygments==2.21.0
requests==2.34.2
rich==15.0.0
setuptools==84.0.0
shellingham==1.5.4
smart-open==8.0.1
spacy==3.8.15
spacy-legacy==3.0.12
spacy-loggers==1.0.5
srsly==2.5.3
sudachidict-core==20260723
sudachipy==0.6.11
thinc==8.3.13
tqdm==4.70.0
typer==0.27.1
typing-extensions==4.16.0
typing-inspection==0.4.4
urllib3==2.7.0
wasabi==1.1.3
weasel==1.0.0
wrapt==2.3.0
"""
PINS = dict(line.split("==") for line in PIN_TEXT.splitlines())
ERROR_CODES = frozenset({
    "source_only_disabled", "environment_mismatch", "invalid_allowlist",
    "deadline", "get_limit", "transport_failure", "http_status",
    "redirect_rejected", "non_json", "response_too_large",
    "aggregate_too_large", "invalid_json", "invalid_metadata",
    "version_mismatch",
    "output_limit", "internal_failure", "cancelled",
})


class Stop(Exception):
    """Only finite, reviewed codes may leave the collector."""

    def __init__(self, code):
        self.code = code if code in ERROR_CODES else "internal_failure"
        super().__init__(self.code)


def normal_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise Stop("invalid_metadata")
    return re.sub(r"[-_.]+", "-", value).lower()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def wheel_tags(filename):
    if not isinstance(filename, str) or len(filename) > 300 or not filename.endswith(".whl"):
        return None
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6):
        return None
    distribution, version = parts[:2]
    py, abi, platforms = parts[-3:]
    return distribution, version, py.split("."), abi.split("."), platforms.split(".")


def strict_wheel_match(filename, name, version):
    tags = wheel_tags(filename)
    if tags is None:
        return False
    distribution, wheel_version, py, abi, platforms = tags
    if normal_name(distribution) != name or wheel_version != version:
        return False
    universal = "py3" in py and set(py) <= {"py2", "py3"} and abi == ["none"] and platforms == ["any"]
    allowed_platforms = {"manylinux_2_17_x86_64", "manylinux_2_28_x86_64"}
    native = py == ["cp312"] and abi == ["cp312"] and bool(set(platforms) & allowed_platforms)
    return universal or native


def nearby_wheel(filename, name, version):
    """For review only; this function never selects a wheel."""
    tags = wheel_tags(filename)
    if tags is None:
        return False
    distribution, wheel_version, py, abi, platforms = tags
    if normal_name(distribution) != name or wheel_version != version:
        return False
    universal = platforms == ["any"] and "py3" in py
    linux_x86 = any(p.endswith("_x86_64") and (p.startswith("manylinux") or p.startswith("musllinux") or p.startswith("linux")) for p in platforms)
    return universal or (linux_x86 and ("cp312" in py or "abi3" in abi))


def file_record(file):
    filename = file.get("filename")
    url = file.get("url")
    if not isinstance(url, str) or len(url) > 1024:
        raise Stop("invalid_metadata")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org" or
            not parsed.path.startswith("/packages/") or parsed.path.rsplit("/", 1)[-1] != filename or
            parsed.query or parsed.fragment):
        raise Stop("invalid_metadata")
    size = file.get("size")
    digest = file.get("digests", {}).get("sha256")
    if type(size) is not int or not 0 < size < 2**63 or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise Stop("invalid_metadata")
    yanked = file.get("yanked")
    if type(yanked) is not bool:
        raise Stop("invalid_metadata")
    core = file.get("core-metadata", False)
    core_hash = core.get("sha256") if isinstance(core, dict) else None
    if core_hash is not None and (not isinstance(core_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", core_hash)):
        raise Stop("invalid_metadata")
    requires_python = file.get("requires_python")
    if requires_python is not None and not isinstance(requires_python, str):
        raise Stop("invalid_metadata")
    return {"filename": filename, "url": url, "bytes": size, "sha256": digest,
            "requires_python": requires_python, "core_metadata_sha256": core_hash,
            "yanked": yanked}


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Stop("invalid_json")
        result[key] = value
    return result


def reject_json_constant(unused):
    raise Stop("invalid_json")


def bounded_public_text(value, preview_characters=256):
    if value is None or len(value) <= preview_characters:
        return value
    encoded = value.encode("utf-8")
    return {"preview": value[:preview_characters], "characters_total": len(value),
            "utf8_bytes_total": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(),
            "truncated": True}


def bounded_requirements(values):
    if values is None or len(json_bytes(values)) <= 8192:
        return values
    encoded = json_bytes(values)
    preview = []
    for value in values:
        if len(json_bytes(preview + [value])) > 2048:
            break
        preview.append(value)
    return {"preview": preview, "count_total": len(values), "count_returned": len(preview),
            "serialized_bytes_total": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(),
            "truncated": True}


def parse_release(body, name, version, url):
    """Record public facts; do not resolve dependencies or infer compatibility."""
    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_json,
                          parse_constant=reject_json_constant)
    except (ValueError, UnicodeError):
        raise Stop("invalid_json") from None
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict) or not isinstance(data.get("urls"), list):
        raise Stop("invalid_metadata")
    info, files = data["info"], data["urls"]
    if normal_name(info.get("name")) != name or info.get("version") != version:
        raise Stop("version_mismatch")
    # Keep the exact registry fields; their semantics are reviewed afterward.
    requires = info.get("requires_dist")
    if requires is not None and (not isinstance(requires, list) or not all(isinstance(x, str) for x in requires)):
        raise Stop("invalid_metadata")
    classifiers = info.get("classifiers")
    if classifiers is None:
        classifiers = []
    if not isinstance(classifiers, list) or not all(isinstance(x, str) for x in classifiers):
        raise Stop("invalid_metadata")
    for field in ("requires_python", "license_expression", "license"):
        if info.get(field) is not None and not isinstance(info[field], str):
            raise Stop("invalid_metadata")
    licence = {"expression": bounded_public_text(info.get("license_expression")),
               "legacy": bounded_public_text(info.get("license")),
               "classifiers": [x for x in classifiers if isinstance(x, str) and x.startswith("License ::")]}
    candidates, nearby = [], []
    for file in files:
        if not isinstance(file, dict):
            raise Stop("invalid_metadata")
        if file.get("packagetype") != "bdist_wheel":
            continue
        filename = file.get("filename")
        if strict_wheel_match(filename, name, version):
            candidates.append(file_record(file))
        elif nearby_wheel(filename, name, version):
            nearby.append(file_record(file))
    selected = candidates[0] if len(candidates) == 1 and not candidates[0]["yanked"] else None
    if selected is not None:
        selection_status = "single_file_under_limited_policy_not_runtime_verified"
    elif len(candidates) > 1:
        selection_status = "ambiguous_source_review_required"
    elif candidates:
        selection_status = "yanked_source_review_required"
    else:
        selection_status = "not_selected_by_limited_policy_not_incompatible"
    returned_requirements = bounded_requirements(requires)
    return {"name": name, "version": version,
            "release_json_sha256": hashlib.sha256(body).hexdigest(),
            "requires_python": info.get("requires_python"), "requires_dist": returned_requirements,
            "requires_dist_complete": not isinstance(returned_requirements, dict),
            "licence_declared_by_registry": licence,
            "selection_status": selection_status, "selected": selected,
            "candidate_files_for_review": [] if selected is not None else candidates + nearby,
            "other_candidate_filenames": [f["filename"] for f in nearby] if selected is not None else []}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if fp is not None:
            try:
                fp.close()
            except Exception:
                pass
        raise Stop("redirect_rejected")


class MetadataTransport:
    """Only the 49 exact PyPI JSON URLs are fetchable. No retries or proxies."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.received_bytes = 0
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=context))
        self.urls = {"https://pypi.org/pypi/" + n + "/" + v + "/json" for n, v in PINS.items()}

    def __call__(self, url, deadline, body_limit):
        if url not in self.urls:
            raise Stop("invalid_allowlist")
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise Stop("deadline")
        request = urllib.request.Request(url, headers={
            "Accept": "application/json", "Accept-Encoding": "identity",
            "User-Agent": "reviewed-public-metadata-only/1.0"})
        try:
            with self.opener.open(request, timeout=min(5.0, remaining)) as response:
                if response.status != 200:
                    raise Stop("http_status")
                if response.geturl() != url:
                    raise Stop("redirect_rejected")
                if response.headers.get_content_type() != "application/json":
                    raise Stop("non_json")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise Stop("non_json")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    if not re.fullmatch(r"[0-9]+", declared):
                        raise Stop("invalid_metadata")
                    if int(declared) > body_limit:
                        raise Stop("response_too_large")
                chunks, count = [], 0
                while True:
                    if self.clock() >= deadline:
                        raise Stop("deadline")
                    # Do not read an extra sentinel byte beyond either cap.
                    # An unknown-length response at the exact cap is rejected.
                    if count == body_limit:
                        if declared is not None and count == int(declared):
                            break
                        raise Stop("response_too_large")
                    chunk = response.read(min(MAX_READ_CHUNK, body_limit - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    self.received_bytes += len(chunk)
                    if count > body_limit:
                        raise Stop("response_too_large")
                    chunks.append(chunk)
                return b"".join(chunks)
        except Stop:
            raise
        except urllib.error.HTTPError as error:
            try:
                error.close()
            except Exception:
                pass
            raise Stop("http_status") from None
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            raise Stop("transport_failure") from None


def collect(fetch, clock=time.monotonic):
    """Injectable core for offline fake tests. Never resolves or executes packages."""
    start = clock()
    deadline = start + ACTIVE_SECONDS
    receipt = {"status": "blocked", "code": None,
               "target": "linux-x86_64-cpython-3.12.14-no-extras",
               "reader_python": ".".join(str(v) for v in sys.version_info[:3]),
               "reader_implementation": sys.implementation.name,
               "metadata_url_template": "https://pypi.org/pypi/{name}/{version}/json",
               "allowlist_sha256": hashlib.sha256(PIN_TEXT.encode("ascii")).hexdigest(),
               "attempted_gets": 0, "metadata_bytes": 0, "records": [],
               "aggregate_selected_wheel_bytes": None,
               "dependency_closure": "unresolved_pending_source_review",
               "per_wheel_metadata_consistency": "unverified_release_JSON_only",
               "licence_text_review": "pending_before_package_execution"}
    current = None
    try:
        if len(PINS) != MAX_GETS:
            raise Stop("invalid_allowlist")
        for name, version in PINS.items():
            current = name
            if clock() >= deadline:
                raise Stop("deadline")
            if receipt["attempted_gets"] >= MAX_GETS:
                raise Stop("get_limit")
            budget = min(MAX_RESPONSE_BYTES, MAX_TOTAL_BYTES - receipt["metadata_bytes"])
            if budget <= 0:
                raise Stop("aggregate_too_large")
            url = "https://pypi.org/pypi/" + name + "/" + version + "/json"
            receipt["attempted_gets"] += 1
            body = fetch(url, deadline, budget)
            if not isinstance(body, bytes):
                raise Stop("invalid_metadata")
            if len(body) > MAX_RESPONSE_BYTES:
                raise Stop("response_too_large")
            if receipt["metadata_bytes"] + len(body) > MAX_TOTAL_BYTES:
                raise Stop("aggregate_too_large")
            receipt["metadata_bytes"] += len(body)
            if clock() >= deadline:
                raise Stop("deadline")
            record = parse_release(body, name, version, url)
            receipt["records"].append(record)
            if len(json_bytes(receipt)) > MAX_OUTPUT_BYTES - 1024:
                receipt["records"].pop()
                raise Stop("output_limit")
            if clock() >= deadline:
                raise Stop("deadline")
        truncated = any(not r["requires_dist_complete"] or
                        any(isinstance(v, dict) and v.get("truncated") for v in r["licence_declared_by_registry"].values())
                        for r in receipt["records"])
        receipt["status"] = "metadata_reads_complete_with_truncated_fields" if truncated else "metadata_reads_complete"
        if all(r["selected"] is not None for r in receipt["records"]):
            receipt["aggregate_selected_wheel_bytes"] = sum(r["selected"]["bytes"] for r in receipt["records"])
    except Stop as error:
        receipt["code"] = error.code
        receipt["failed_pin"] = current
    except (KeyboardInterrupt, SystemExit):
        receipt["code"] = "cancelled"
        receipt["failed_pin"] = current
    except Exception:
        receipt["code"] = "internal_failure"
        receipt["failed_pin"] = current
    receipt["elapsed_ms"] = max(0, round((clock() - start) * 1000))
    receipt["body_bytes_received"] = getattr(fetch, "received_bytes", None)
    return receipt


def emit(receipt):
    encoded = json_bytes(receipt) + b"\n"
    if len(encoded) > MAX_OUTPUT_BYTES:
        encoded = b'{"status":"blocked","code":"output_limit"}\n'
    # No environment, exception messages, tokens, caches, or local paths logged.
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def environment_ok():
    # Reader runtime is distinct from target package runtime. No setup/install.
    return sys.version_info >= (3, 8) and sys.platform == "linux" and hasattr(signal, "setitimer")


def main():
    # SOURCE_ONLY must be changed only in a separately reviewed release.
    if SOURCE_ONLY:
        emit({"status": "blocked", "code": "source_only_disabled"})
        return 2
    if not environment_ok():
        emit({"status": "blocked", "code": "environment_mismatch"})
        return 2
    started = time.monotonic()

    def hard_stop(signum, frame):
        os._exit(124)

    def report_deadline(signum, frame):
        signal.signal(signal.SIGALRM, hard_stop)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, HARD_DEADLINE_SECONDS - (time.monotonic() - started)))
        raise Stop("deadline")

    signal.signal(signal.SIGALRM, report_deadline)
    signal.setitimer(signal.ITIMER_REAL, REPORT_DEADLINE_SECONDS)
    try:
        receipt = collect(MetadataTransport())
        emit(receipt)
        return 0 if receipt["status"] in ("metadata_reads_complete", "metadata_reads_complete_with_truncated_fields") else 2
    except Stop as error:
        emit({"status": "blocked", "code": error.code})
        return 2
    except (KeyboardInterrupt, SystemExit):
        emit({"status": "blocked", "code": "cancelled"})
        return 130
    except Exception:
        emit({"status": "blocked", "code": "internal_failure"})
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    sys.exit(main())
