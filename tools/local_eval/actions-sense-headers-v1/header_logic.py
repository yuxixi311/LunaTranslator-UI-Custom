"""Pure, bounded HTTP header parsing and finite redirect observations.

This module has no transport, file, subprocess, model, or activation operations.
Location values exist only transiently and are never returned or logged.
"""
import math
import re
from urllib.parse import unquote, urljoin, urlsplit


INITIAL_URL = (
    "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/"
    "b27182d810fa3ceb6ed04e7c324c54e35c0d209c/Hy-MT2-1.8B-Q4_K_M.gguf"
)
EXPECTED_BRIDGE = "cas-bridge.xethub.hf.co"
LINE_LIMIT = 2048
HEADER_BLOCK_LIMIT = 16384
HEADER_FIELDS_LIMIT = 64
LOCATION_LIMIT = 2048

# These are observation labels, never a destination allowlist.
EXACT_HOST_CLASSES = {
    "cdn-lfs.hf.co": "HF_META_CDN_LFS_HF_CO",
    "cdn-lfs-us-1.hf.co": "HF_META_CDN_LFS_US_1_HF_CO",
    "cdn-lfs-eu-1.hf.co": "HF_META_CDN_LFS_EU_1_HF_CO",
    "transfer.xethub.hf.co": "HF_META_TRANSFER_XETHUB_HF_CO",
    "transfer.xethub-eu.hf.co": "HF_META_TRANSFER_XETHUB_EU_HF_CO",
    "aws.cdn.hf.co": "HF_META_AWS_CDN_HF_CO",
    "us.aws.cdn.hf.co": "HF_META_US_AWS_CDN_HF_CO",
    "us-east-1.aws.cdn.hf.co": "HF_META_US_EAST_1_AWS_CDN_HF_CO",
    "us-west-2.aws.cdn.hf.co": "HF_META_US_WEST_2_AWS_CDN_HF_CO",
    "eu-west-3.aws.cdn.hf.co": "HF_META_EU_WEST_3_AWS_CDN_HF_CO",
    "ap-southeast-1.aws.cdn.hf.co": "HF_META_AP_SOUTHEAST_1_AWS_CDN_HF_CO",
    "us.gcp.cdn.hf.co": "HF_META_US_GCP_CDN_HF_CO",
    "us-east1.us.gcp.cdn.hf.co": "HF_META_US_EAST1_US_GCP_CDN_HF_CO",
    "us-central1.us.gcp.cdn.hf.co": "HF_META_US_CENTRAL1_US_GCP_CDN_HF_CO",
    "us-west4.us.gcp.cdn.hf.co": "HF_META_US_WEST4_US_GCP_CDN_HF_CO",
    "europe-west4.us.gcp.cdn.hf.co": "HF_META_EUROPE_WEST4_US_GCP_CDN_HF_CO",
    "asia-southeast1.us.gcp.cdn.hf.co": "HF_META_ASIA_SOUTHEAST1_US_GCP_CDN_HF_CO",
    "huggingface.co": "HF_META_HUGGINGFACE_CO",
    "hf.co": "HF_META_HF_CO",
    "huggingface.com": "HF_META_HUGGINGFACE_COM",
    "huggingface.cn": "HF_META_HUGGINGFACE_CN",
    EXPECTED_BRIDGE: "EXISTING_EXPECTED_BRIDGE",
}
_FROZEN_HOST_ITEMS = frozenset(EXACT_HOST_CLASSES.items())

FAILURE_CODES = frozenset({
    "NONE", "DNS_FAILURE", "CONNECT_FAILURE", "TLS_FAILURE", "SEND_FAILURE",
    "HTTP_LINE_LIMIT", "HTTP_HEADER_BLOCK_LIMIT", "HTTP_CRLF_REJECTED",
    "HTTP_EOF_OR_INVALID_READ", "ASSET_STATUS_LINE_REJECTED",
    "ASSET_HEADER_FIELDS_REJECTED", "ASSET_HEADER_SYNTAX_REJECTED",
    "RESOURCE_CAP", "DEADLINE_EXPIRED", "CLEANUP_UNCONFIRMED", "UNKNOWN_FAILURE",
})
STATUS_VALUES = frozenset({
    "UNOBSERVED", "HTTP_200", "HTTP_301", "HTTP_302", "HTTP_303",
    "HTTP_307", "HTTP_308", "OTHER_HTTP_STATUS",
})
LOCATION_FORM_VALUES = frozenset({
    "UNOBSERVED", "ABSENT", "RELATIVE", "ABSOLUTE", "NETWORK_PATH", "INVALID",
})
AUTHORITY_VALUES = frozenset({
    "UNOBSERVED", "IMPLICIT_SAME_ORIGIN", "CANONICAL_HTTPS_443",
    "NONCANONICAL_HTTPS_443", "REJECTED_AUTHORITY",
})
POLICY_VALUES = frozenset({
    "UNOBSERVED", "NOT_A_REDIRECT", "ACCEPTS_EXISTING_HOST_AND_AUTHORITY",
    "REJECTS_HOST", "REJECTS_AUTHORITY_SHAPE", "REJECTS_OTHER_EXISTING_URL_RULE",
})
HOST_CLASS_VALUES = frozenset(EXACT_HOST_CLASSES.values()) | {
    "NO_LOCATION", "UNPARSEABLE", "OTHER_UNREVIEWED_HOST",
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_STATUS_PATTERN = re.compile(rb"HTTP/1\.[01] [0-9]{3}(?: [\x20-\x7e]*)?")
_TOKEN_PATTERN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_VALUE_CONTROL_PATTERN = re.compile(rb"[\x00-\x08\x0a-\x1f\x7f]")
_URL_CONTROL_PATTERN = re.compile(r"[\x00-\x20\x7f\\]")


class ProbeFailure(Exception):
    """A failure whose arguments and text contain one fixed code only."""

    def __init__(self, code):
        self.code = code if type(code) is str and code in FAILURE_CODES else "UNKNOWN_FAILURE"
        super().__init__(self.code)


def _require(condition, code):
    if not condition:
        raise ProbeFailure(code)


def _remaining(deadline):
    failure = None
    try:
        remaining = deadline.remaining()
    except ProbeFailure as exc:
        failure = exc.code
    except TimeoutError:
        failure = "DEADLINE_EXPIRED"
    except Exception:
        failure = "UNKNOWN_FAILURE"
    if failure is not None:
        raise ProbeFailure(failure)
    _require(type(remaining) in (int, float) and math.isfinite(remaining), "UNKNOWN_FAILURE")
    _require(remaining > 0, "DEADLINE_EXPIRED")
    return remaining


class _HeaderWire:
    def __init__(self, reader, deadline):
        self.reader = reader
        self.deadline = deadline
        self.total = 0

    def _byte(self):
        remaining = _remaining(self.deadline)
        failure = None
        try:
            data = self.reader.read(1, remaining)
        except ProbeFailure as exc:
            failure = exc.code
        except TimeoutError:
            failure = "DEADLINE_EXPIRED"
        except Exception:
            failure = "UNKNOWN_FAILURE"
        if failure is not None:
            raise ProbeFailure(failure)
        _remaining(self.deadline)
        _require(type(data) is bytes and len(data) == 1, "HTTP_EOF_OR_INVALID_READ")
        return data

    def line(self):
        line = bytearray()
        while True:
            _require(len(line) < LINE_LIMIT, "HTTP_LINE_LIMIT")
            _require(self.total < HEADER_BLOCK_LIMIT, "HTTP_HEADER_BLOCK_LIMIT")
            byte = self._byte()
            self.total += 1
            if line and line[-1] == 13:
                _require(byte == b"\n", "HTTP_CRLF_REJECTED")
            line.extend(byte)
            if byte == b"\n":
                _require(len(line) >= 2 and line[-2] == 13, "HTTP_CRLF_REJECTED")
                return bytes(line[:-2])


def read_headers(reader, deadline):
    """Read exactly one status/header block, including its final CRLF.

    Every application read requests one byte. No code path reads past the first
    complete header block or begins a response body or another status block.
    """
    wire = _HeaderWire(reader, deadline)
    status = wire.line()
    _require(_STATUS_PATTERN.fullmatch(status) is not None, "ASSET_STATUS_LINE_REJECTED")
    headers = {}
    fields = 0
    while True:
        line = wire.line()
        if not line:
            break
        fields += 1
        _require(fields <= HEADER_FIELDS_LIMIT and b":" in line
                 and not line.startswith((b" ", b"\t")), "ASSET_HEADER_FIELDS_REJECTED")
        key, value = line.split(b":", 1)
        key = key.lower()
        _require(_TOKEN_PATTERN.fullmatch(key) is not None and key not in headers
                 and _VALUE_CONTROL_PATTERN.search(value) is None,
                 "ASSET_HEADER_SYNTAX_REJECTED")
        headers[key] = value.strip(b" \t")
    _remaining(deadline)
    return int(status[9:12]), headers


def _safe_path(path):
    """Preserve the historical four-pass encoded-path rejection semantics."""
    try:
        for _ in range(4):
            if (re.search(r"%2f|%5c", path, re.I) or "\\" in path
                    or any(part in (".", "..") for part in path.split("/"))):
                return False
            decoded = unquote(path, errors="strict")
            if decoded == path:
                return True
            path = decoded
    except (UnicodeError, ValueError):
        return False
    return False


def _observed_location(location, host_classes):
    invalid = ("INVALID", "UNPARSEABLE", "REJECTED_AUTHORITY",
               "REJECTS_OTHER_EXISTING_URL_RULE")
    if (type(location) is not bytes or not location or len(location) > LOCATION_LIMIT
            or not location.isascii()):
        return invalid
    text = location.decode("ascii")
    if _URL_CONTROL_PATTERN.search(text):
        return invalid
    try:
        raw = urlsplit(text)
        raw_port = raw.port
        if (raw.scheme not in ("", "https") or raw.username is not None
                or raw.password is not None or raw_port not in (None, 443)
                or "#" in text or raw.fragment):
            return invalid
        form = "NETWORK_PATH" if text.startswith("//") else (
            "ABSOLUTE" if raw.scheme else "RELATIVE")
        raw_path_valid = _safe_path(raw.path)
        resolved = urljoin(INITIAL_URL, text)
        # Preserve a provider's opaque query, including a bare trailing '?'.
        if "?" in text:
            resolved = resolved.split("?", 1)[0] + "?" + text.split("?", 1)[1]
        if (len(resolved) > LOCATION_LIMIT or not resolved.isascii()
                or _URL_CONTROL_PATTERN.search(resolved)):
            return invalid
        parsed = urlsplit(resolved)
        if (parsed.scheme != "https" or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None
                or "#" in resolved or parsed.fragment or not parsed.hostname):
            return invalid
        hostname = parsed.hostname
    except (UnicodeError, ValueError):
        return invalid

    host_class = host_classes.get(hostname, "OTHER_UNREVIEWED_HOST")
    canonical = parsed.netloc in (hostname, hostname + ":443")
    authority = ("IMPLICIT_SAME_ORIGIN" if not raw.netloc else
                 ("CANONICAL_HTTPS_443" if canonical else "NONCANONICAL_HTTPS_443"))
    # Historical redirect() checked the raw path before joining/validating its
    # host, then validate_url() checked host/authority before the resolved path.
    if not raw_path_valid:
        policy = "REJECTS_OTHER_EXISTING_URL_RULE"
    elif hostname != EXPECTED_BRIDGE:
        policy = "REJECTS_HOST"
    elif not canonical:
        policy = "REJECTS_AUTHORITY_SHAPE"
    elif not (parsed.path.startswith("/") and len(parsed.path) > 1
              and _safe_path(parsed.path)):
        policy = "REJECTS_OTHER_EXISTING_URL_RULE"
    else:
        policy = "ACCEPTS_EXISTING_HOST_AND_AUTHORITY"
    return form, host_class, authority, policy


def classify_response(status, headers, host_classes):
    """Project a parsed response into five closed, non-sensitive enum fields."""
    _require(type(status) is int and 0 <= status <= 999, "UNKNOWN_FAILURE")
    _require(type(headers) is dict and all(type(key) is bytes and type(value) is bytes
             for key, value in headers.items()), "UNKNOWN_FAILURE")
    _require(type(host_classes) is dict and all(type(key) is str and type(value) is str
             for key, value in host_classes.items()), "UNKNOWN_FAILURE")
    _require(frozenset(host_classes.items()) == _FROZEN_HOST_ITEMS, "UNKNOWN_FAILURE")
    status_class = "HTTP_" + str(status) if status in _REDIRECT_STATUSES | {200} else "OTHER_HTTP_STATUS"
    if b"location" not in headers:
        form, host, authority, policy = (
            "ABSENT", "NO_LOCATION", "UNOBSERVED", "REJECTS_OTHER_EXISTING_URL_RULE")
    else:
        form, host, authority, policy = _observed_location(headers[b"location"], host_classes)
    if status not in _REDIRECT_STATUSES:
        policy = "NOT_A_REDIRECT"
    return {
        "status": status_class,
        "location_form": form,
        "host_class": host,
        "authority": authority,
        "current_policy_outcome": policy,
    }
