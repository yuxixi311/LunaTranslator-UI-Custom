"""Validate actual nested helper samples; never run extra benchmarks.

The native isolated policy-worker lifecycle/IPC design is not yet released.
A larger runner process cannot stand in for the measured 32 MiB helper owner.
"""
import math
from usage_runner_core import ROW_IDS


def validate_owner_metrics(core, metrics, owner_identity):
    """Future bridge must bind this to the actual policy worker's RSS guard."""
    h = core.h
    keys = {"owner_identity", "policy_in_owner_process", "peak_rss_bytes", "cold_start_ns"}
    h.require(type(metrics) is dict and set(metrics) == keys and
              metrics["owner_identity"] == owner_identity and metrics["policy_in_owner_process"] is True,
              "actual policy interpreter owner binding")
    h.require(type(metrics["peak_rss_bytes"]) is int and 0 < metrics["peak_rss_bytes"] <= 32*h.MIB,
              "actual policy-process RSS including interpreter/imports/bank")
    h.require(type(metrics["cold_start_ns"]) is int and metrics["cold_start_ns"] > 0,
              "genuine separately observed cold start; no extra benchmark")
    return metrics


def validate_helper_result(core, samples, owner_metrics, clock_resolution_seconds):
    h = core.h
    h.require(type(samples) is list and len(samples) == 87 and
              [r.get("row") for r in samples] == list(ROW_IDS) and
              all(set(r) == {"row", "elapsed_ns"} for r in samples), "exactly 87 measured helper intervals")
    values = [r["elapsed_ns"] for r in samples]
    h.require(all(type(v) is int and v > 0 for v in values), "helper positive integer intervals")
    h.require(type(clock_resolution_seconds) in (int, float) and math.isfinite(clock_resolution_seconds) and
              clock_resolution_seconds > 0,
              "helper timer resolution")
    quantiles = h.quantiles(values)
    h.require(quantiles["p95"] <= 5_000_000, "all-row nested helper P95")
    return dict(samples=samples, render_ns=quantiles, first_measured_candidate_ns=values[0],
                first_measured_candidate_is_not_assumed_cold=True, **owner_metrics)


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE ONLY: isolated policy worker lifecycle and IPC require review")
