"""Prospective owned CPU child body. CLI remains unconditionally stopped."""
import os
from pathlib import Path
import resource
import sys

from ner_adapter import (POLICY_SHA256, ProbeFailure, check_resources, execute_batch,
                         load_spacy_pipeline_after_release, require, canonical_json, MAX_EVIDENCE_BYTES)
from evidence_io import load_frozen_population, validate_evidence
from runner_control import deny_network, exclusive_json, file_pin, set_child_limits
from finalized_manifest import FINAL_MANIFEST_SHA256


def process_cpu_seconds():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def peak_rss_kib():
    # Linux-only preflight is mandatory; ru_maxrss has different units on macOS.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def parser_body(work, source_root, fixture_root, file_pins, bindings, expected_parent_pid):
    """Body for a future released single owned child, not called in preparation.

    Controller must first verify event/run identity, complete source inventory,
    finalized dependencies, setup/model/notice receipts and exact venv snapshot.
    """
    work, source_root = Path(work), Path(source_root)
    require(os.getpgrp() == os.getpid() and expected_parent_pid > 1 and os.getppid() == expected_parent_pid,
            "parser_parent_mismatch")
    require(Path(sys.prefix).resolve() == (work / "venv").resolve() and sys.prefix != sys.base_prefix,
            "parser_venv_mismatch")
    require(file_pin(source_root / "ner_entry_policy.py")["sha256"] == POLICY_SHA256, "policy_hash_mismatch")
    require(bindings.get('dependency_manifest_sha256') == FINAL_MANIFEST_SHA256, "dependency_manifest_mismatch")
    set_child_limits("parse")
    sys.addaudithook(deny_network)
    population = load_frozen_population(fixture_root, file_pins)
    result = execute_batch(load_spacy_pipeline_after_release, population, bindings,
                           cpu_seconds=process_cpu_seconds, peak_rss_kib=peak_rss_kib)
    encoded = canonical_json(result)
    # Replay every decision before sealing, still within the owned 60s lifecycle.
    validate_evidence(encoded, population, bindings)
    check_resources(process_cpu_seconds(), peak_rss_kib())
    result["metrics"]["cpu_seconds"] = process_cpu_seconds()
    result["metrics"]["peak_rss_kib"] = peak_rss_kib()
    require(len(canonical_json(result)) <= MAX_EVIDENCE_BYTES, "output_size_exceeded")
    exclusive_json(work / "ner-evidence.json", result)
    check_resources(process_cpu_seconds(), peak_rss_kib())
    # A warm failure keeps all73 complete records for audit but terminates the
    # candidate. It can never release private grading/GPU or a subsequent stage.
    require(result["resource_gates_passed"], "warm_p95_gate_failed")
    return result


def main():
    print('{"status":"stopped","reason":"source_preparation_only_not_released"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
