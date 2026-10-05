"""Stdlib-only prospective bootstrap for the pinned pure-Python packaging wheel.

No wheel is acquired, read or imported on module import. The CLI always stops.
This avoids depending on an unpinned host packaging installation during setup.
"""
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

from ner_adapter import require
from runner_control import file_pin

PACKAGING_PIN = {
    "filename": "packaging-26.3-py3-none-any.whl", "bytes": 129956,
    "sha256": "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
    "core_metadata_sha256": "70fdb89fc4d4a9a043bf7372b8972bcc883fddff34ab55e9cf80d73875384763",
}


def audit_packaging_archive(data, pin):
    """Non-executing helper permits synthetic pin values in offline tests."""
    require(type(data) is bytes and len(data) == pin["bytes"] and len(data) <= 1024 * 1024
            and hashlib.sha256(data).hexdigest() == pin["sha256"], "bootstrap_archive_hash_mismatch")
    prefix = "packaging-26.3.dist-info/"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= 256, "bootstrap_member_count")
        require(len({member.filename for member in entries}) == len(entries), "bootstrap_duplicate_path")
        files, total = {}, 0
        for member in entries:
            name, mode = member.filename, member.external_attr >> 16
            path = PurePosixPath(name)
            require(not path.is_absolute() and "\\" not in name and "\x00" not in name
                    and all(part not in ("", ".", "..") for part in name.rstrip("/").split("/"))
                    and (name.startswith("packaging/") or name.startswith(prefix)), "bootstrap_unsafe_path")
            require(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR)
                    and not member.flag_bits & 1 and member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "bootstrap_unsafe_member")
            require(not name.endswith(".pth") and path.name not in ("sitecustomize.py", "usercustomize.py")
                    and not name.endswith((".so", ".pyd", ".dll")), "bootstrap_startup_or_native_code")
            if member.is_dir():
                require(member.file_size == 0, "bootstrap_directory_payload")
                continue
            total += member.file_size
            require(member.file_size <= 2 * 1024 * 1024 and total <= 8 * 1024 * 1024,
                    "bootstrap_uncompressed_budget")
            files[name] = archive.read(member)
        require({"packaging/__init__.py", prefix + "METADATA", prefix + "WHEEL", prefix + "RECORD"} <= set(files),
                "bootstrap_missing_metadata")
        metadata = files[prefix + "METADATA"]
        require(hashlib.sha256(metadata).hexdigest() == pin["core_metadata_sha256"], "bootstrap_metadata_hash")
        fields = BytesParser().parsebytes(metadata)
        require(fields.get_all("Name") == ["packaging"] and fields.get_all("Version") == ["26.3"]
                and fields.get_all("Requires-Python") == [">=3.9"] and not fields.get_all("Requires-Dist"),
                "bootstrap_metadata_mismatch")
        wheel = BytesParser().parsebytes(files[prefix + "WHEEL"])
        require(wheel.get_all("Wheel-Version") == ["1.0"] and wheel.get_all("Root-Is-Purelib") == ["true"]
                and wheel.get_all("Tag") == ["py3-none-any"], "bootstrap_wheel_tag")
        rows = list(csv.reader(io.StringIO(files[prefix + "RECORD"].decode("utf-8"))))
        require(all(len(row) == 3 for row in rows) and len({row[0] for row in rows}) == len(rows)
                and {row[0] for row in rows} == set(files), "bootstrap_record_inventory")
        for name, digest, size in rows:
            if name == prefix + "RECORD":
                require(digest == size == "", "bootstrap_record_self_hash")
            else:
                actual = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip("=")
                require(digest == "sha256=" + actual and size == str(len(files[name])), "bootstrap_record_hash")
    return {"bytes": len(data), "sha256": pin["sha256"], "uncompressed_bytes": total, "members": len(files)}


def bootstrap_packaging(wheel_path):
    """Future setup only, fixed identity; cannot load a different supplied pin."""
    wheel_path = Path(wheel_path)
    require(wheel_path.is_absolute() and wheel_path.name == PACKAGING_PIN["filename"], "bootstrap_path_mismatch")
    require(file_pin(wheel_path) == {k: PACKAGING_PIN[k] for k in ("bytes", "sha256")}, "bootstrap_archive_hash_mismatch")
    require(not any(name == "packaging" or name.startswith("packaging.") for name in sys.modules),
            "preexisting_packaging_forbidden")
    audit = audit_packaging_archive(wheel_path.read_bytes(), PACKAGING_PIN)
    sys.path.insert(0, str(wheel_path))
    import packaging
    require(packaging.__version__ == "26.3" and packaging.__file__.startswith(str(wheel_path) + "/packaging/"),
            "bootstrap_import_origin")
    return audit


def main():
    print('{"status":"stopped","reason":"source_preparation_only_not_released"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
