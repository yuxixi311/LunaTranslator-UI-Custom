"""Source-only, stdlib-only metadata inventory. This is NOT an install lockfile."""
import argparse
import hashlib
import http.client
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

INDEX = "https://download.pytorch.org/whl/cu128/torch/"
PACKAGES = {"transformers": "5.6.0", "peft": "0.21.2", "accelerate": "1.15.0", "safetensors": "0.8.0"}
FILENAMES = {
    "transformers": "transformers-5.6.0-py3-none-any.whl",
    "peft": "peft-0.21.2-py3-none-any.whl",
    "accelerate": "accelerate-1.15.0-py3-none-any.whl",
    "safetensors": "safetensors-0.8.0-cp310-abi3-win_amd64.whl",
}
TORCH_FILENAME = "torch-2.10.0+cu128-cp312-cp312-win_amd64.whl"
ALLOWED_REQUESTS = {INDEX} | {f"https://pypi.org/pypi/{p}/{v}/json" for p, v in PACKAGES.items()}
MAX_REQUESTS, MAX_RESPONSE, MAX_TOTAL = 5, 1024 * 1024, 8 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")


PUBLIC_ERROR_CODES = frozenset({
    "INVALID_URL", "URL_NOT_ALLOWED", "REQUEST_NOT_ALLOWED", "DEADLINE_REACHED",
    "REQUEST_LIMIT", "HTTP_FAILURE", "ENCODING_REJECTED", "MEDIA_TYPE_REJECTED",
    "CONTENT_LENGTH_REJECTED", "BYTE_LIMIT", "TRUNCATED_RESPONSE", "TORCH_HASH_INVALID",
    "TORCH_YANKED", "TORCH_ENTRY_AMBIGUOUS", "RELEASE_MISMATCH", "WHEEL_ENTRY_AMBIGUOUS",
    "WHEEL_URL_MISMATCH", "WHEEL_REJECTED", "WHEEL_DIGEST_SIZE_INVALID", "DEPENDENCY_SCHEMA_INVALID",
    "JSON_SCHEMA_INVALID", "UNEXPECTED_ERROR",
})


class Stop(Exception):
    def __init__(self, code):
        self.code = code if type(code) is str and code in PUBLIC_ERROR_CODES else "UNEXPECTED_ERROR"
        super().__init__(self.code)


def checked_url(url, hosts):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url):
        raise Stop("INVALID_URL")
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise Stop("URL_NOT_ALLOWED")
    return p


def validate_request(url):
    checked_url(url, {"download.pytorch.org", "pypi.org"})
    if url not in ALLOWED_REQUESTS:
        raise Stop("REQUEST_NOT_ALLOWED")


class Connection:
    def __init__(self, url, timeout):
        p = checked_url(url, {"download.pytorch.org", "pypi.org"})
        self.conn = http.client.HTTPSConnection(p.hostname, timeout=timeout, context=ssl.create_default_context())
        self.path = p.path

    def __enter__(self):
        self.conn.request("GET", self.path, headers={
            "User-Agent": "HyMT-Metadata-Inventory/1.0 (Python-stdlib; metadata-only)",
            "Accept": "application/json, text/html", "Accept-Encoding": "identity",
        })
        return self.conn.getresponse()

    def __exit__(self, *args):
        self.conn.close()


class Client:
    def __init__(self, transport=Connection, clock=time.monotonic, seconds=110):
        self.transport, self.clock = transport, clock
        self.deadline = clock() + seconds
        self.requests = self.total = 0
        self.sources = []

    def remaining(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise Stop("DEADLINE_REACHED")
        return remaining

    def get(self, url, content_type):
        validate_request(url)
        self.remaining()
        if self.requests >= MAX_REQUESTS:
            raise Stop("REQUEST_LIMIT")
        self.requests += 1
        with self.transport(url, min(10, self.remaining())) as response:
            if response.status != 200:
                raise Stop("HTTP_FAILURE")
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise Stop("ENCODING_REJECTED")
            if response.getheader("Content-Type", "").split(";")[0].strip().lower() != content_type:
                raise Stop("MEDIA_TYPE_REJECTED")
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE):
                raise Stop("CONTENT_LENGTH_REJECTED")
            chunks, count = [], 0
            while True:
                self.remaining()
                # Conservatively reject a response reaching the cap, without reading a sentinel byte.
                allowance = min(16384, MAX_RESPONSE - count, MAX_TOTAL - self.total)
                if allowance <= 0:
                    raise Stop("BYTE_LIMIT")
                data = response.read(allowance)
                self.total += len(data)
                count += len(data)
                if count > MAX_RESPONSE or self.total > MAX_TOTAL:
                    raise Stop("BYTE_LIMIT")
                if not data:
                    break
                chunks.append(data)
            self.remaining()
            if length is not None and count != int(length):
                raise Stop("TRUNCATED_RESPONSE")
        body = b"".join(chunks)
        self.sources.append({"url": url, "bytes": len(body), "sha256_of_metadata": hashlib.sha256(body).hexdigest()})
        return body


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.matches = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href")
        if not href:
            return
        url = urljoin(INDEX, href)
        if unquote(urlsplit(url).path.rsplit("/", 1)[-1]) != TORCH_FILENAME:
            return
        p = checked_url(url, {"download.pytorch.org", "download-r2.pytorch.org"})
        if p.query or not p.path.endswith(".whl") or not p.fragment.startswith("sha256=") or not SHA.fullmatch(p.fragment[7:]):
            raise Stop("TORCH_HASH_INVALID")
        if "data-yanked" in attrs:
            raise Stop("TORCH_YANKED")
        self.matches.append({"name": "torch", "version": "2.10.0+cu128", "filename": TORCH_FILENAME,
            "wheel_url_record_only": url.split("#", 1)[0], "sha256": p.fragment[7:],
            "size_bytes": None, "requires_dist": None, "requires_python": attrs.get("data-requires-python"),
            "license": None, "source": INDEX, "wheel_contacted": False})


def parse_torch(body):
    parser = IndexParser()
    parser.feed(body.decode("utf-8", errors="strict"))
    if len(parser.matches) != 1:
        raise Stop("TORCH_ENTRY_AMBIGUOUS")
    return parser.matches[0]


def parse_pypi(name, body):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Stop("JSON_SCHEMA_INVALID")
            result[key] = value
        return result

    def reject_constant(value):
        raise Stop("JSON_SCHEMA_INVALID")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise Stop("JSON_SCHEMA_INVALID")
        return number

    obj = json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant, parse_float=finite_float)
    info = obj["info"]
    for field in ("requires_python", "license", "license_expression"):
        if info.get(field) is not None and type(info[field]) is not str:
            raise Stop("JSON_SCHEMA_INVALID")
    if info["name"].lower().replace("_", "-") != name or info["version"] != PACKAGES[name]:
        raise Stop("RELEASE_MISMATCH")
    choices = [x for x in obj["urls"] if x.get("filename") == FILENAMES[name]]
    if len(choices) != 1:
        raise Stop("WHEEL_ENTRY_AMBIGUOUS")
    wheel = choices[0]
    p = checked_url(wheel["url"], {"files.pythonhosted.org"})
    if p.query or p.fragment or unquote(p.path.rsplit("/", 1)[-1]) != FILENAMES[name]:
        raise Stop("WHEEL_URL_MISMATCH")
    if wheel.get("packagetype") != "bdist_wheel" or wheel.get("yanked") is not False:
        raise Stop("WHEEL_REJECTED")
    size, sha = wheel["size"], wheel["digests"]["sha256"]
    if type(size) is not int or size <= 0 or not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise Stop("WHEEL_DIGEST_SIZE_INVALID")
    dependencies = info.get("requires_dist")
    if dependencies is not None and (not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies)):
        raise Stop("DEPENDENCY_SCHEMA_INVALID")
    return {"name": name, "version": PACKAGES[name], "filename": FILENAMES[name],
        "wheel_url_record_only": wheel["url"], "sha256": sha, "size_bytes": size,
        "requires_dist": dependencies, "requires_python": info.get("requires_python"),
        "license": info.get("license_expression") or info.get("license"),
        "source": f"https://pypi.org/pypi/{name}/{PACKAGES[name]}/json", "wheel_contacted": False,
        "metadata_scope": "PyPI release JSON; not verified against wheel-specific METADATA"}


def collect(client):
    result = {"schema_version": 1, "kind": "top_level_metadata_inventory", "install_ready": False,
        "target": "CPython 3.12 / Windows x86-64", "packages": [], "status": "incomplete",
        "unknown_blockers": ["Torch wheel byte size", "Torch Requires-Dist and license",
            "All transitive version selections, hashes, sizes and licenses", "Marker/extras and full compatibility resolution",
            "Wheel-specific metadata verification", "Complete download total"],
        "limits": {"requests": MAX_REQUESTS, "response_bytes": MAX_RESPONSE, "total_bytes": MAX_TOTAL,
            "request_timeout_seconds": 10, "worker_seconds": 110, "supervisor_budget_seconds": 120}}
    try:
        result["packages"].append(parse_torch(client.get(INDEX, "text/html")))
        for name, version in PACKAGES.items():
            result["packages"].append(parse_pypi(name, client.get(f"https://pypi.org/pypi/{name}/{version}/json", "application/json")))
        result["status"] = "top_level_metadata_collected_not_install_ready"
    except Exception as exc:
        result["status"] = "stopped_on_first_failure"
        result["error_code"] = exc.code if type(exc) is Stop and exc.code in PUBLIC_ERROR_CODES else "UNEXPECTED_ERROR"
    result["sources"] = client.sources
    result["requests_attempted"] = client.requests
    result["metadata_bytes_read"] = client.total
    result["known_top_level_bytes_excluding_torch"] = sum(p["size_bytes"] or 0 for p in result["packages"])
    return result


def worker(destination):
    report = collect(Client())
    temporary = Path(destination) / "inventory.partial.json"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(Path(destination) / "inventory.json")
    if report["status"] == "stopped_on_first_failure":
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory, which must not already exist")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This handoff is scoped to native Windows")
    import sys
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the existing Python 3.12 interpreter")
    destination = Path(args.output).resolve()
    destination.mkdir(parents=False, exist_ok=False)
    process = multiprocessing.get_context("spawn").Process(target=worker, args=(str(destination),))
    started = time.monotonic()
    process.start()
    process.join(max(0, 110 - (time.monotonic() - started)))
    if process.is_alive():
        process.terminate()
        process.join(max(0, 115 - (time.monotonic() - started)))
    if process.is_alive():
        process.kill()
        process.join(max(0, 120 - (time.monotonic() - started)))
    receipt = {"elapsed_seconds": time.monotonic() - started, "worker_exitcode": process.exitcode,
        "worker_exit_confirmed": not process.is_alive(), "inventory_present": (destination / "inventory.json").is_file()}
    (destination / "supervisor.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt))
    if process.is_alive():
        print("STOP: worker exit not confirmed. Do not retry; report the blocker.", flush=True)
        os._exit(2)  # Avoid multiprocessing's automatic unbounded join on shutdown.
    if process.exitcode != 0 or not receipt["inventory_present"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
