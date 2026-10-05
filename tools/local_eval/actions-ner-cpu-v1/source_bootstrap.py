"""Stdlib-only, hash-bound source launcher for isolated Python children.

The source root is this launcher's directory, never the process cwd. The
controller supplies the independently reviewed inventory digest. Every listed
file and this launcher are verified before sibling imports are enabled from
those exact verified bytes, without consulting source-directory bytecode. Only inventoried activation entrypoints can be dispatched.
"""
import argparse
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_SOURCE_FILE_BYTES = 4 * 1024 * 1024
MAX_INVENTORY_BYTES = 256 * 1024
ALLOWED_ENTRYPOINTS = frozenset({"actions_runner.py", "offline_setup.py"})


def require(condition):
    if not condition:
        raise ValueError("source binding failed")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def bounded_regular_file(path, cap):
    require(path.resolve(strict=True) == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 <= info.st_size <= cap)
        data = stream.read(cap + 1)
        require(len(data) == info.st_size)
    return data


def verify_sources(root, expected_inventory_sha256, entrypoint):
    require(type(expected_inventory_sha256) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected_inventory_sha256) is not None)
    require(entrypoint in ALLOWED_ENTRYPOINTS)
    root = Path(root)
    require(root.is_absolute() and root.resolve(strict=True) == root)
    data = bounded_regular_file(root / "PREPARATION_INVENTORY.json", MAX_INVENTORY_BYTES)
    require(hashlib.sha256(data).hexdigest() == expected_inventory_sha256)
    inventory = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
    require(type(inventory) is dict and type(inventory.get("files")) is dict
            and 1 <= len(inventory["files"]) <= 64)
    require({"source_bootstrap.py", entrypoint} <= set(inventory["files"]))
    # This reviewed source bundle is flat. Refuse unlisted importable siblings
    # and package directories that could shadow verified modules or stdlib.
    for child in root.iterdir():
        if child.name == "__pycache__":
            require(child.is_dir() and not child.is_symlink())
        else:
            require(child.is_file() and not child.is_symlink()
                    and child.name in set(inventory["files"]) | {"PREPARATION_INVENTORY.json"})
    verified, total = {}, 0
    for name, pin in inventory["files"].items():
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is not None
                and name not in (".", "..") and type(pin) is dict and set(pin) == {"bytes", "sha256"}
                and type(pin["bytes"]) is int and 0 <= pin["bytes"] <= MAX_SOURCE_FILE_BYTES
                and type(pin["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is not None)
        content = bounded_regular_file(root / name, MAX_SOURCE_FILE_BYTES)
        total += len(content)
        require(total <= 16 * 1024 * 1024 and len(content) == pin["bytes"]
                and hashlib.sha256(content).hexdigest() == pin["sha256"])
        verified[name] = content
    return verified


class VerifiedSourceLoader(importlib.abc.Loader):
    def __init__(self, path, content):
        self.path, self.content = path, content

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = str(self.path)
        module.__cached__ = None
        exec(compile(self.content, str(self.path), "exec"), module.__dict__)


class VerifiedSourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root, verified):
        self.root, self.verified = root, verified

    def find_spec(self, fullname, path=None, target=None):
        filename = fullname + ".py"
        if "." not in fullname and filename in self.verified:
            loader = VerifiedSourceLoader(self.root / filename, self.verified[filename])
            return importlib.util.spec_from_loader(fullname, loader, origin=str(self.root / filename))
        return None


def dispatch(root, inventory_sha256, entrypoint, child_arguments):
    verified = verify_sources(root, inventory_sha256, entrypoint)
    # -I omits both cwd and script directory. Load approved sibling modules from
    # the checked bytes themselves, leaving sys.path unchanged and ignoring pyc.
    sys.meta_path.insert(0, VerifiedSourceFinder(root, verified))
    target = str(root / entrypoint)
    sys.argv = [target, *child_arguments]
    namespace = {"__name__": "__main__", "__file__": target, "__package__": None, "__cached__": None}
    # Execute the exact entrypoint bytes already checked, without reopening it.
    exec(compile(verified[entrypoint], target, "exec"), namespace)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--entrypoint", choices=sorted(ALLOWED_ENTRYPOINTS), required=True)
    parser.add_argument("child_arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.child_arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    try:
        dispatch(Path(__file__).resolve(strict=True).parent, args.inventory_sha256, args.entrypoint, arguments)
        return 0
    except Exception:
        print('{"status":"stopped","reason":"approved_source_binding_or_dispatch_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
