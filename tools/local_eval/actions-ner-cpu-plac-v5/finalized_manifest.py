"""Exact-byte binding to the independently collected final plac1.4.7 manifest.

No registry request, package acquisition or package import occurs here. This
small stdlib reader is also usable before the packaging validator bootstrap.
"""
import hashlib
import json

FINAL_MANIFEST_BYTES = 30148
FINAL_MANIFEST_SHA256 = "c04f4e31641594e90b9a6436625ad20d0de550b5f8543d70d5d70f46458d3401"
FINAL_AGGREGATE_BYTES = 207406351


def read_finalized_manifest(data):
    if (type(data) is not bytes or len(data) != FINAL_MANIFEST_BYTES
            or hashlib.sha256(data).hexdigest() != FINAL_MANIFEST_SHA256):
        raise ValueError("Finalized dependency manifest byte identity mismatch")
    value = json.loads(data.decode("utf-8"))
    files = value["files"]
    if (type(files) is not list or len(files) != 49 or len({row["name"] for row in files}) != 49
            or sum(row["wheel"]["bytes"] for row in files) != FINAL_AGGREGATE_BYTES
            or value["aggregate_bytes"] != FINAL_AGGREGATE_BYTES):
        raise ValueError("Finalized dependency manifest population mismatch")
    return value
