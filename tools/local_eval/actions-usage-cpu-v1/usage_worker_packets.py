"""Concrete one-shot packet factory for the reviewed owned usage worker.

Pure byte assembly is separately testable. The production factory reads pinned
source and the existing immutable claim, creates exactly two exclusive private
evidence files, and seals their descriptors before returning a launch spec.
It performs no child launch, policy execution, network request or model work.
"""
from hashlib import sha256
import json

import usage_worker_entry as entry
import usage_helper_bridge as bridge

PACKET_NAMES = ("helper_closure.json", "helper_binding.json")
SOURCE_NAMES = (*entry.SOURCE_NAMES, "usage_worker_entry.py")
PACKET_CAP = 32768


def require_native_release():
    import activation_scope
    grant = activation_scope.require_role("actions")
    activation_scope.require(globals().get("_VERIFIED_BOOTSTRAP_SHA") == grant["manifest_sha"],
                             "verified usage packet source required")
    return grant


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def assemble_packets(payloads, source_paths, source_pins, binding_fields):
    """Full exact packet bytes from bounded supplied observations, without I/O."""
    entry.need(type(payloads) is dict and type(source_paths) is dict and type(source_pins) is dict and
               set(payloads) == set(source_paths) == set(source_pins) == set(SOURCE_NAMES))
    for name in SOURCE_NAMES:
        raw, pin, path = payloads[name], source_pins[name], source_paths[name]
        entry.need(type(raw) is bytes and type(pin) is dict and set(pin) == {"sha256", "bytes"} and
                   type(pin["bytes"]) is int and 0 < len(raw) == pin["bytes"] <=
                   (16384 if name.endswith(".json") else 65536) and
                   sha256(raw).hexdigest() == pin["sha256"] and
                   type(path) is str and path.startswith("/") and ".." not in path.split("/") and
                   path.endswith("/"+name))
    entry.need(source_pins["usage_worker_entry.py"]["sha256"] == bridge.ENTRY_SOURCE_SHA256 and
               sha256(entry.ENTRY_BOOTSTRAP.encode()).hexdigest() == bridge.ENTRY_BOOTSTRAP_SHA256)
    closure = canonical(dict(schema=1, files=[dict(file=name, path=source_paths[name],
        bytes=source_pins[name]["bytes"], sha256=source_pins[name]["sha256"]) for name in entry.SOURCE_NAMES]))
    closure_sha = sha256(closure).hexdigest()
    entry.verify_closure(closure, closure_sha, {name: payloads[name] for name in entry.SOURCE_NAMES})
    binding = {**binding_fields, "closure_sha256": closure_sha}
    entry.validate_binding(binding, parent_pid=binding["parent_pid"], parent_argv=binding["parent_argv"],
        python=binding["python"], cwd=binding["cwd"], now_ns=binding["launch_ns"])
    binding_raw = canonical(binding)
    entry.need(len(closure) <= PACKET_CAP and len(binding_raw) <= PACKET_CAP)
    spec = entry.build_spec(python=binding["python"], cwd=binding["cwd"],
        entry_path=source_paths["usage_worker_entry.py"], entry_sha=bridge.ENTRY_SOURCE_SHA256,
        closure_path=binding["cwd"]+"/"+PACKET_NAMES[0], closure_sha=closure_sha,
        binding_path=binding["cwd"]+"/"+PACKET_NAMES[1], binding_sha=sha256(binding_raw).hexdigest(),
        launch_ns=binding["launch_ns"], cleanup_end_ns=binding["cleanup_end_ns"])
    return spec, closure, binding_raw


def _seal_packet(runtime, evidence, name):
    """Seal exactly this writer's exclusive descriptor, retaining byte accounting."""
    require_native_release()
    import os
    with evidence.lock:
        fd = evidence.files[name]
        runtime.persistence_checkpoint()
        os.fsync(fd)
        runtime.persistence_checkpoint()
        del evidence.files[name]
        # close() may have released the fd even if it raises. Transfer ownership
        # before the single close attempt; inherited cleanup must not retry it.
        os.close(fd)
        runtime.persistence_checkpoint()


def create_worker_packet_factory(core, inventory, runtime, owner, evidence, *, python, cwd,
                                 parent_argv, now_ns, source_paths=None, source_pins=None):
    """Return the concrete once-only factory used at post-ready helper start.

    Creation requires the existing Actions grant. A call permanently consumes
    this factory before any read/write and narrows the already independently
    supervised parent phase to the full 15-second setup/bootstrap budget. The
    bridge restores the captured inherited phase only after validated READY.
    """
    require_native_release()
    import os
    import time
    from pathlib import Path
    h = core.h
    h.require(now_ns is time.monotonic_ns, "one native helper clock")
    h.require((source_paths is None and source_pins is None) or
              (type(source_paths) is dict and type(source_pins) is dict and
               set(source_paths) == set(source_pins) == set(SOURCE_NAMES)), "complete helper source map")
    supplied_paths = None if source_paths is None else dict(source_paths)
    supplied_pins = None if source_pins is None else {key: dict(value) for key, value in source_pins.items()}
    argv = list(parent_argv)
    consumed = False

    def create():
        nonlocal consumed
        launch_ns, cpu_start = now_ns(), time.process_time_ns()
        grant = require_native_release()
        h.require(not consumed, "helper packet factory already consumed")
        consumed = True  # Failed persistence cannot be retried or spawn later.
        h.require(owner.evidence is evidence and str(evidence.output) == cwd and
                  owner.plan["absolute_python"] == python and owner.plan["coordinator_argv"] == argv and
                  owner.plan["coordinator_pid"] == os.getpid() == grant["owner_pid"] and
                  grant["manifest_sha"] == owner.plan["component_manifest_sha256"], "owned helper packet context")
        owner.check()
        original_phase_ns = int(owner.phase_end*1e9)
        owner.phase_end = min(original_phase_ns, launch_ns+15_000_000_000)/1e9
        runtime.persistence_checkpoint()
        root = grant["source_root"]
        h.require(root == owner.plan["roots"]["source"] and str(Path(sys_executable()).resolve()) == python,
                  "native helper source/Python binding")
        claim_path = owner.plan["roots"]["state"]+"/ONE_SHOT_CPU_ATTEMPT.json"
        claim_raw = runtime.bounded_file(Path(claim_path), PACKET_CAP)
        h.require(claim_raw == h.canonical(owner.plan), "unchanged immutable parent claim")
        source_manifest = runtime.pinned_file(Path(root)/"KIT_MANIFEST.json", grant["manifest_sha"], 65536)
        manifest = entry.strict_json(source_manifest, 65536)
        h.require(type(manifest) is dict and type(manifest.get("files")) is list and
                  len(manifest["files"]) <= 128 and all(type(v) is dict and type(v.get("path")) is str
                  for v in manifest["files"]), "bounded helper source inventory")
        inventory_pins = {v["path"]: v for v in manifest["files"]}
        h.require(len(inventory_pins) == len(manifest["files"]), "unique helper source inventory")
        paths, pins = {}, {}
        for name in SOURCE_NAMES:
            relative = ("policy/" if name in entry.SOURCE_NAMES and name != "usage_policy_worker.py" else "")+name
            h.require(relative in inventory_pins and set(inventory_pins[relative]) == {"path", "sha256", "bytes"},
                      "declared helper source inventory member")
            paths[name] = root+"/"+relative
            pins[name] = {key: inventory_pins[relative][key] for key in ("sha256", "bytes")}
        h.require(supplied_paths is None or (supplied_paths == paths and supplied_pins == pins),
                  "supplied source bindings equal exact manifest")
        payloads = {}
        for name in SOURCE_NAMES:
            owner.check()
            relative = ("policy/" if name in entry.SOURCE_NAMES and name != "usage_policy_worker.py" else "")+name
            h.require(paths[name] == root+"/"+relative, "exact helper source path")
            payloads[name] = runtime.pinned_file(Path(paths[name]), pins[name]["sha256"],
                16384 if name.endswith(".json") else 65536)
        rows = ["R%03d" % n for n in range(1, 41)]+["S%03d" % n for n in range(1, 16)]+["N%03d" % n for n in range(1, 33)]
        fields = dict(schema=1, parent_pid=os.getpid(), parent_argv=argv, python=python, cwd=cwd,
            launch_ns=launch_ns, work_end_ns=int(owner.work_end*1e9), postready_end_ns=int(owner.postready_end*1e9),
            cleanup_end_ns=min(int(owner.outer_end*1e9), int(owner.lifecycle_end*1e9), launch_ns+600_000_000_000),
            phase_end_ns=original_phase_ns, row_ids=rows, eligible_ids=list(inventory.eligible_ids),
            source_hashes={row: sha256(inventory.sources[row].encode("utf-8")).hexdigest() for row in rows},
            source_root=root, source_manifest_sha256=grant["manifest_sha"], claim_path=claim_path,
            claim_sha256=sha256(claim_raw).hexdigest())
        spec, closure_raw, binding_raw = assemble_packets(payloads, paths, pins, fields)
        entry.validate_parent_claim(entry.strict_json(binding_raw), claim_raw, source_manifest, closure_raw,
                                    entry_sha=bridge.ENTRY_SOURCE_SHA256, now_ns=now_ns())
        for name, raw in zip(PACKET_NAMES, (closure_raw, binding_raw)):
            owner.check()
            evidence.create(name)
            evidence.append(name, raw)  # Exact bytes, without a trailing newline.
            _seal_packet(runtime, evidence, name)
            h.require(evidence.file_bytes[name] == len(raw) and name not in evidence.files,
                      "sealed exact helper packet bytes")
        owner.check()
        ended, cpu_end = now_ns(), time.process_time_ns()
        h.require(launch_ns < ended < min(original_phase_ns, launch_ns+15_000_000_000) and cpu_end >= cpu_start,
                  "measured helper parent setup")
        return spec, sha256(closure_raw).hexdigest(), dict(launch_ns=launch_ns,
            parent_setup_ns=ended-launch_ns, parent_setup_cpu_ns=cpu_end-cpu_start,
            inherited_phase_end_ns=original_phase_ns)
    return create


def sys_executable():
    import sys
    return sys.executable
