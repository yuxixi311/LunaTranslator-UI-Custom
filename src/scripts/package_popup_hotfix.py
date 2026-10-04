"""Build the complete v1.0.1 portable hotfix from the verified v1.0.0 ZIP.

No native binary is executed, no dependency is downloaded, and no model branch
is used. Run with CPython 3.10+; the only inputs are the old published archive
and this release's corresponding source checkout.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from refresh_custom_launcher import find_digest_slot, parse_pe_layout, refresh_launcher


BASE_SHA256 = "aafdbcadee8f75054ea3aa6783f6efb18b5cc0697690cdf9311a311f4115d19a"
BASE_BYTES = 251214174
BASE_COMMIT = "87d125adc2cc528b5781d87d5610c2615f68efe2"
RELEASE_TAG = "v1.0.1"
RUNTIME_PATHS = (
    "LunaTranslator/LunaTranslator.py",
    "LunaTranslator/gui/flowsearchword.py",
    "LunaTranslator/gui/rendertext/textbrowser.py",
    "LunaTranslator/gui/rendertext/tooltipswidget.py",
    "LunaTranslator/gui/rendertext/webview.py",
    "LunaTranslator/gui/showword.py",
    "LunaTranslator/htmlcode/uiwebview/mainui.html",
)
LAUNCHERS = ("LunaTranslator.exe", "LunaTranslator_admin.exe")
NOTICES = {
    "README.txt": "release/README.txt",
    "MODIFICATIONS.md": "MODIFICATIONS.md",
    "THIRD_PARTY_SOURCE.md": "THIRD_PARTY_SOURCE.md",
    "RELEASE_NOTES.md": "RELEASE_NOTES.md",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect_base(archive):
    data = archive.read_bytes()
    if len(data) != BASE_BYTES or sha(data) != BASE_SHA256:
        raise ValueError("Base archive does not match the published v1.0.0 artifact")
    with ZipFile(archive) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != 4921 or len(set(n.casefold() for n in names)) != len(names):
            raise ValueError("Unexpected or duplicate base archive entries")
        if sum(i.file_size for i in infos) > 1024**3:
            raise ValueError("Unexpected base uncompressed size")
        for info in infos:
            p = PurePosixPath(info.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in info.filename or ":" in info.filename:
                raise ValueError("Unsafe archive path")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlink is not allowed")
            if p.parts[0] in ("cache", "userconfig", "docs") or "__pycache__" in p.parts:
                raise ValueError("Private/generated directory in archive")
            if p.suffix in (".pyc", ".gguf") or "local_hymt" in info.filename or "local_translation" in info.filename:
                raise ValueError("Generated or unfinished translation-model content")
        if z.testzip() is not None:
            raise ValueError("Base archive CRC failure")
    return names


def build(archive, source, output, report):
    if output.exists() or report.exists():
        raise FileExistsError("Refusing to overwrite a package or verification report")
    base_names = inspect_base(archive)
    with tempfile.TemporaryDirectory(prefix="luna-popup-hotfix-") as tmp:
        root = Path(tmp)
        with ZipFile(archive) as z:
            z.extractall(root)  # Every member was checked above and the ZIP is pinned.
            base_hashes = {name: sha(z.read(name)) for name in base_names}
        for name in RUNTIME_PATHS:
            (root / name).write_bytes((source / "src" / name).read_bytes())
        for archive_name, source_name in NOTICES.items():
            (root / archive_name).write_bytes((source / source_name).read_bytes())

        launcher_checks = {}
        for name in LAUNCHERS:
            exe = root / name
            before = exe.read_bytes()
            layout = parse_pe_layout(before)
            slots = {}
            for path in RUNTIME_PATHS:
                if not path.endswith(".py"):
                    continue
                slot = find_digest_slot(before, layout, path)
                if slot is None:
                    raise ValueError("Modified Python file has no embedded launcher digest: " + path)
                slots[path] = slot
            refreshed = refresh_launcher(exe, root / "LunaTranslator")
            if set(refreshed["refreshed"]) != set(slots):
                raise ValueError("Launcher refresh changed an unexpected Python digest")
            second = refresh_launcher(exe, root / "LunaTranslator", dry_run=True)
            if second["refreshed"]:
                raise ValueError("Launcher still contains stale Python digests")
            after = exe.read_bytes()
            permitted = set()
            for offset in slots.values():
                permitted.update(range(offset, offset + 32))
            permitted.update(range(layout.security_directory_offset, layout.security_directory_offset + 8))
            permitted.update(range(layout.checksum_offset, layout.checksum_offset + 4))
            if len(before) != len(after) or any(a != b and i not in permitted for i, (a, b) in enumerate(zip(before, after))):
                raise ValueError("Unexpected launcher byte modification")
            for path, slot in slots.items():
                if after[slot:slot + 32] != hashlib.sha256((root / path).read_bytes()).digest():
                    raise ValueError("Launcher digest does not match packaged source")
            if struct.unpack_from("<II", after, layout.security_directory_offset) != (0, 0):
                raise ValueError("Custom launcher falsely retains a signing directory")
            launcher_checks[name] = {
                "sha256": sha(after), "updated_python_digests": sorted(slots),
                "stale_digests_after_refresh": 0, "unsigned_custom_launcher": True,
                "unchanged_nonembedded_file_count": len(second["not_embedded"]),
            }

        allowed_changed = set(RUNTIME_PATHS) | set(LAUNCHERS) | set(NOTICES)
        names = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        hashes = {name: sha((root / name).read_bytes()) for name in names}
        changed = sorted(n for n in base_names if hashes[n] != base_hashes[n])
        added = sorted(set(names) - set(base_names))
        if set(changed) - allowed_changed or set(added) != {"RELEASE_NOTES.md"}:
            raise ValueError("Package changes exceed popup sources, launcher digests and release notices")
        if set(base_names) - set(names):
            raise ValueError("A previously released runtime file was removed")
        manifest = {
            "release": RELEASE_TAG, "source_tag": RELEASE_TAG,
            "source_repository": "https://github.com/yuxixi311/LunaTranslator-UI-Custom",
            "baseline_commit": BASE_COMMIT, "baseline_archive_sha256": BASE_SHA256,
            "baseline_archive_bytes": BASE_BYTES,
            "runtime_strategy": "Retain v1.0.0 runtime; replace only seven popup source files and refresh their existing launcher digests",
            "native_windows_gui_test": "NOT RUN; headless method/bridge and package integrity checks only",
            "unfinished_translation_model_work_included": False,
            "base_entries": len(base_names), "unchanged_base_entries": len(base_names) - len(changed),
            "changed_entries": {n: hashes[n] for n in changed},
            "added_entries": {n: hashes[n] for n in added},
            "launcher_checks": launcher_checks,
        }
        (root / "BUILD_INFO.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        names.append("BUILD_INFO.json")
        with ZipFile(output, "x", compression=ZIP_DEFLATED, compresslevel=9) as z:
            for name in sorted(names):
                info = ZipInfo(name, date_time=(2026, 10, 4, 0, 0, 0))
                info.create_system = 0
                info.external_attr = 0x20
                info.compress_type = ZIP_DEFLATED
                z.writestr(info, (root / name).read_bytes(), compresslevel=9)
        with ZipFile(output) as z:
            if z.testzip() is not None or len(z.namelist()) != len(names):
                raise ValueError("Final archive CRC/inventory failure")
            for name in names:
                if z.read(name) != (root / name).read_bytes():
                    raise ValueError("Final archive content mismatch")
        manifest["artifact"] = {"filename": output.name, "bytes": output.stat().st_size, "sha256": sha(output.read_bytes()), "entries": len(names)}
        report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-archive", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base_archive, args.source, args.output, args.report)["artifact"], indent=2))


if __name__ == "__main__":
    main()
