"""Prospective offline setup; CLI stopped, no installation during preparation.

Uses the previously reviewed stdlib-venv/ensurepip pattern, with the new complete
49-wheel validator. These functions are not evidence of a successful install.
"""
import argparse
import csv
import hashlib
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from ner_adapter import ProbeFailure, require
from runner_control import INSTALLED_CAP, deny_network, file_pin, exclusive_json

SUPPLEMENTS = {
    "SudachiDict-20260723-LEGAL": {"bytes": 6037, "sha256": "725a8776b38e058b185e905594bc9a2437dbf3787df022fffeefedb9a84e4665"},
    "SudachiDict-20260723-LICENSE-2.0.txt": {"bytes": 11358, "sha256": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"},
    "SudachiPy-0.6.11-LICENSE": {"bytes": 11357, "sha256": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"},
}


def snapshot_tree(root):
    """Bound total installed regular-file bytes; refuse links and special files."""
    root = Path(root)
    require(root.resolve(strict=True) == root, "unsafe_install_root")
    inventory, total = {}, 0
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(parent) / name
            if path.is_symlink():
                # Standard Linux stdlib venv layout, even with symlinks=False.
                require(path == root / "lib64" and os.readlink(path) == "lib"
                        and path.resolve(strict=True) == root / "lib", "installed_symlink")
        for name in files:
            path = Path(parent) / name
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "installed_special_file")
            total += info.st_size
            require(total <= INSTALLED_CAP, "installed_size_exceeded")
            inventory[str(path.relative_to(root))] = file_pin(path)
    return {"bytes": total, "files": inventory}


def verify_installed_members(site_packages, report):
    """Every original payload byte, including notices, must still be present.

    RECORD is the wheel-specified exception: pip rewrites it for relocation and
    generated script records. Its original remains in the retained pinned wheel.
    The installed RECORD must still include each original non-RECORD member.
    """
    site_packages = Path(site_packages)
    retained = []
    for wheel in report.wheels:
        expected_record = None
        regular = []
        for member in wheel.members:
            if member.directory:
                continue
            path = site_packages / member.destination
            require(path.resolve(strict=True) == path, "installed_path_escape")
            if member.archive_path.endswith(".dist-info/RECORD"):
                expected_record = path
                continue
            require(file_pin(path) == {"bytes": member.size, "sha256": member.sha256}, "installed_payload_changed")
            regular.append(member.destination)
        require(expected_record is not None and expected_record.stat().st_size <= 16 * 1024 * 1024,
                "invalid_installed_record")
        with expected_record.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        require(all(len(row) == 3 for row in rows), "invalid_installed_record")
        names = [row[0] for row in rows]
        require(len(names) == len(set(names)) and set(regular) <= set(names), "installed_record_incomplete")
        retained.append({"name": wheel.name, "version": wheel.version,
                         "original_member_count_retained": len(regular),
                         "installed_record": file_pin(expected_record), "wheel_sha256": wheel.sha256})
    return retained


def retain_supplements(source, destination):
    source, destination = Path(source), Path(destination)
    destination.mkdir(mode=0o700)
    for name, pin in SUPPLEMENTS.items():
        require(file_pin(source / name) == pin, "supplement_hash_mismatch")
        with (source / name).open("rb") as original, (destination / name).open("xb") as output:
            shutil.copyfileobj(original, output, length=1024 * 1024)
        require(file_pin(destination / name) == pin, "supplement_copy_mismatch")
    return {"files": SUPPLEMENTS, "meaning": "notice retention only; no legal clearance claim"}


def verify_model_inventory(site_packages, model_inventory):
    for name, pin in model_inventory["files"].items():
        path = Path(site_packages) / name
        require(path.resolve(strict=True) == path and file_pin(path) == pin, "model_inventory_mismatch")
    return {"model": "ja_ginza", "version": "5.2.0", "bytes": model_inventory["total_bytes"],
            "file_count": len(model_inventory["files"])}


def ensurepip_offline(venv_root):
    """Runs only within the future owned setup group, never in preparation tests."""
    require(Path(sys.prefix).resolve() == Path(venv_root).resolve() and sys.prefix != sys.base_prefix,
            "installer_venv_mismatch")
    import ensurepip
    def offline_pip(args, additional_paths=None):
        bootstrap = (
            "import sys,runpy; "
            "sys.addaudithook(lambda event,args: (_ for _ in ()).throw(RuntimeError('socket forbidden')) "
            "if event.startswith('socket.') else None); "
            "sys.path[:0]=" + repr(additional_paths or []) + "; "
            "sys.argv=" + repr(["pip", *args]) + "; runpy.run_module('pip',run_name='__main__')")
        # Inherit the outer setup process group so its deadline owns descendants.
        return subprocess.run([sys.executable, "-I", "-B", "-c", bootstrap], check=True).returncode
    original = ensurepip._run_pip
    ensurepip._run_pip = offline_pip
    try:
        ensurepip.bootstrap(default_pip=True)
    finally:
        ensurepip._run_pip = original


def install_local_wheels(venv_root, wheels):
    require(Path(sys.prefix).resolve() == Path(venv_root).resolve() and sys.prefix != sys.base_prefix,
            "installer_venv_mismatch")
    require(type(wheels) is list and len(wheels) == 49
            and all(Path(path).is_absolute() and Path(path).suffix == ".whl" for path in wheels),
            "invalid_install_wheels")
    sys.addaudithook(deny_network)
    import runpy
    original = sys.argv
    sys.argv = ["pip", "--isolated", "--disable-pip-version-check", "--no-cache-dir", "install", "--no-index",
                "--no-deps", "--no-compile", "--only-binary=:all:", *map(str, wheels)]
    try:
        code = None
        try:
            runpy.run_module("pip", run_name="__main__")
        except SystemExit as exc:
            code = exc.code
        require(code in (None, 0), "offline_install_failed")
    finally:
        sys.argv = original


def installer_command(python, source_root, source_inventory_sha256, command, venv_root, parent_pid, wheels):
    """Bind isolated installer dispatch to the parent-reviewed source inventory."""
    require(command in ("_ensurepip", "_install"), "invalid_installer_command")
    require(type(source_inventory_sha256) is str and len(source_inventory_sha256) == 64
            and all(char in "0123456789abcdef" for char in source_inventory_sha256), "invalid_source_inventory_hash")
    return [str(python), "-I", "-B", str(Path(source_root) / "source_bootstrap.py"),
            "--inventory-sha256", source_inventory_sha256, "--entrypoint", "offline_setup.py", "--",
            command, str(venv_root), str(parent_pid), *map(str, wheels)]


def prepare_offline_setup(work, manifest_bytes, marker_environment, supported_tags, environment,
                          supplements, model_inventory, *, source_inventory_sha256, progress=None):
    """Future 60s-owned-phase body. Calls remain unreachable from current CLI."""
    mark = progress if progress is not None else lambda step, package=None: None
    from finalized_manifest import read_finalized_manifest
    read_finalized_manifest(manifest_bytes)
    mark("packaging_bootstrap", "packaging")
    # This function belongs in a fresh isolated setup child. No packaging module
    # may preexist; bootstrap imports only the already-downloaded fixed wheel.
    from validator_bootstrap import bootstrap_packaging, PACKAGING_PIN
    bootstrap_report = bootstrap_packaging(Path(work) / "wheels" / PACKAGING_PIN["filename"])
    # Compute host markers/tags only after the exact packaging-wheel bootstrap.
    if marker_environment is None and supported_tags is None:
        from packaging.markers import default_environment
        from packaging.tags import sys_tags
        marker_environment, supported_tags = default_environment(), tuple(sys_tags())
    require(marker_environment is not None and supported_tags is not None, "missing_runtime_tags")
    from wheel_validation import validate_finalized_manifest, validate_wheelhouse
    import venv
    work = Path(work)
    records = validate_finalized_manifest(manifest_bytes)
    wheels = [work / "wheels" / record["wheel"]["filename"] for record in records.values()]
    mark("wheel_validation")
    # Observe the already-reviewed validator's fixed package identity without
    # changing its inputs, outputs, order, archive rules or exceptions.
    import wheel_validation
    original_validate = wheel_validation._validate_wheel
    def observed_validate(path, record, *args, **kwargs):
        mark("wheel_validation", record["name"])
        return original_validate(path, record, *args, **kwargs)
    wheel_validation._validate_wheel = observed_validate
    try:
        report = validate_wheelhouse(wheels, {'records': list(records.values())}, marker_environment, supported_tags)
    finally:
        wheel_validation._validate_wheel = original_validate
    require(report.total_uncompressed_bytes <= INSTALLED_CAP, "installed_size_exceeded")
    # Preserve and hash archive inventory before any package execution.
    exclusive_json(work / "wheel-validation.json", report.to_dict())
    mark("notice_retention")
    retained_notices = retain_supplements(supplements, work / "notice-supplements")
    venv_root = work / "venv"
    mark("venv_create")
    venv.EnvBuilder(with_pip=False, symlinks=False).create(venv_root)
    mark("venv_identity")
    python = venv_root / "bin/python"
    require(file_pin(python) == file_pin(Path(sys.executable).resolve()), "venv_interpreter_mismatch")
    require("include-system-site-packages = false" in (venv_root / "pyvenv.cfg").read_text(), "venv_not_isolated")
    source_root = Path(__file__).resolve().parent
    for command in ("_ensurepip", "_install"):
        mark(command.lstrip("_"))
        arguments = installer_command(python, source_root, source_inventory_sha256,
                                      command, venv_root, os.getpid(), wheels)
        subprocess.run(arguments, env=environment,
                       cwd=work, stdin=subprocess.DEVNULL, check=True)
    site_packages = venv_root / "lib/python3.12/site-packages"
    mark("payload_retention")
    retained = verify_installed_members(site_packages, report)
    mark("model_inventory", "ja-ginza")
    model = verify_model_inventory(site_packages, model_inventory)
    mark("installed_snapshot")
    snapshot = snapshot_tree(venv_root)
    exclusive_json(work / "installed.json", snapshot)
    result = {"installed_bytes": snapshot["bytes"], "wheel_payload_retention": retained,
              "validator_bootstrap": bootstrap_report,
              "source_notice_supplements": retained_notices, "model": model,
              "network_boundary": "Python socket audit and offline pip from trusted official-cache stdlib ensurepip; "
                                  "ensurepip/pip payload not independently pinned; not an OS network sandbox"}
    mark("setup_output")
    exclusive_json(work / "setup.json", result)
    return result


def main():
    # It accepts only descendants of the owned setup process group.
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("_ensurepip", "_install"))
    parser.add_argument("venv_root")
    parser.add_argument("parent_pid", type=int)
    parser.add_argument("wheels", nargs=49)
    args = parser.parse_args()
    require(args.parent_pid > 1 and os.getppid() == args.parent_pid and os.getpgrp() == args.parent_pid,
            "installer_parent_mismatch")
    sys.addaudithook(deny_network)
    if args.command == "_ensurepip":
        ensurepip_offline(Path(args.venv_root))
    else:
        install_local_wheels(Path(args.venv_root), args.wheels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
