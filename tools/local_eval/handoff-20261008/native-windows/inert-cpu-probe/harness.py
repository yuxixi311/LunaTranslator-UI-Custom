"""Inert plan validator and injected fake lifecycle model. No native backend exists."""
from dataclasses import dataclass
import json
import math
import re
from urllib.parse import urlsplit

GIB = 1024 ** 3
EXECUTION_ENABLED = False  # Documentation only: no executable backend or installer exists.
CUDA_ENABLED = False
LIMITS = {
    "download_bytes": 4 * GIB, "disk_growth_bytes": 12 * GIB,
    "overall_seconds": 2100, "active_seconds": 1800,
    "cleanup_reserve_seconds": 300, "probe_seconds": 120,
    "probe_cleanup_seconds": 10, "startup_free_ram_bytes": 4 * GIB,
    "runtime_free_ram_bytes": 2 * GIB, "process_tree_rss_bytes": 2 * GIB,
}
OFFICIAL_HOSTS = {"files.pythonhosted.org", "download.pytorch.org"}
REQUIRED_PACKAGES = {"torch", "transformers", "peft", "accelerate", "safetensors"}


def validate_manifest(manifest):
    """Metadata checks, not independent proof of dependency closure or wheel bytes."""
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest_invalid"]
    if manifest.get("target") != "cp312-win_amd64":
        errors.append("target_unverified")
    if manifest.get("closure_reviewed") is not True:
        errors.append("closure_unreviewed")
    review_hash = manifest.get("closure_review_sha256")
    if not isinstance(review_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", review_hash):
        errors.append("closure_review_missing")
    wheels = manifest.get("wheels")
    if not isinstance(wheels, list) or not wheels:
        return errors + ["wheel_closure_missing"]
    names, total = set(), 0
    for wheel in wheels:
        if not isinstance(wheel, dict):
            errors.append("wheel_invalid")
            continue
        name = wheel.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append("wheel_name_invalid")
        elif name in names:
            errors.append("duplicate_wheel")
        else:
            names.add(name)
        for key in ("version", "license", "filename"):
            if not isinstance(wheel.get(key), str) or not wheel[key].strip():
                errors.append("wheel_metadata_missing")
        filename = wheel.get("filename", "")
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_.+!-]+\.whl", filename):
            errors.append("wheel_filename_invalid")
        try:
            url = urlsplit(wheel.get("url", ""))
            if (url.scheme != "https" or url.hostname not in OFFICIAL_HOSTS
                    or url.username or url.password or url.port not in (None, 443)
                    or url.query or url.fragment or not url.path.endswith("/" + filename)):
                errors.append("wheel_url_unverified")
        except (ValueError, TypeError):
            errors.append("wheel_url_unverified")
        wheel_hash = wheel.get("sha256")
        if not isinstance(wheel_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", wheel_hash):
            errors.append("wheel_hash_missing")
        size = wheel.get("bytes")
        if type(size) is not int or size <= 0:
            errors.append("wheel_bytes_unknown")
        else:
            total += size
        if wheel.get("target_compatible_reviewed") is not True:
            errors.append("wheel_target_unreviewed")
        if not isinstance(wheel.get("requires"), list) or any(
                not isinstance(dep, str) for dep in wheel.get("requires", [])):
            errors.append("wheel_dependencies_unknown")
    if not REQUIRED_PACKAGES.issubset(names):
        errors.append("required_wheels_missing")
    for wheel in wheels:
        if isinstance(wheel, dict) and isinstance(wheel.get("requires"), list):
            if any(not isinstance(dep, str) or dep not in names for dep in wheel["requires"]):
                errors.append("wheel_dependency_missing")
    if total > LIMITS["download_bytes"]:
        errors.append("download_budget_exceeded")
    return sorted(set(errors))


def plan(manifest=None, mode="plan"):
    blockers = validate_manifest(manifest)
    if mode not in ("setup-and-cpu", "cpu-only"):
        blockers.append("explicit_execution_mode_missing")
    blockers += ["windows_owned_process_tree_backend_missing",
                 "windows_resource_sampler_missing", "installer_missing",
                 "independent_execution_review_missing", "execution_disabled"]
    return {"schema": "windows-probe-plan-v1", "execution_enabled": False,
            "cuda_enabled": False, "limits": dict(LIMITS),
            "blockers": sorted(set(blockers)),
            "hard_rss_cap_enforced": False,
            "cuda_blocker": "initialization_budget_and_stop_rule_unreviewed"}


@dataclass
class FakeClock:
    seconds: float = 0.0

    def now(self):
        return self.seconds

    def advance(self, seconds):
        self.seconds += seconds


@dataclass
class Sample:
    free_ram_bytes: int
    tree_rss_bytes: int
    owned_tree_verified: bool = True


@dataclass
class FakeResources:
    samples: list
    index: int = 0

    def sample(self):
        value = self.samples[min(self.index, len(self.samples) - 1)]
        self.index += 1
        if isinstance(value, Exception):
            raise value
        return value


@dataclass
class FakeProcess:
    finish_at: float | None = 1.0
    exit_code: int = 0
    cleanup_succeeds: bool = True
    owned: bool = True
    launched: bool = False
    stopped: bool = False
    terminate_calls: int = 0

    def launch(self):
        self.launched = True

    def poll(self, clock):
        if self.stopped or (self.finish_at is not None and clock.now() >= self.finish_at):
            return self.exit_code
        return None

    def terminate_owned_tree(self):
        if not self.owned:
            return False
        self.terminate_calls += 1
        self.stopped = self.cleanup_succeeds
        return self.stopped


def simulate_probe(clock, resources, process, setup_elapsed=0.0):
    """Only exact local fake classes accepted; never launches a subprocess.

    Models sampled stop thresholds, NOT a hard RSS cap. A real implementation
    would require race-safe ownership, monotonic deadlines and native review.
    """
    if (type(clock) is not FakeClock or type(resources) is not FakeResources
            or type(process) is not FakeProcess):
        raise TypeError("fake_backend_required")
    result = {"schema": "windows-probe-simulation-v1", "simulated": True,
              "execution_enabled": False, "cuda_enabled": False,
              "phase": "preflight", "status": "blocked", "reason": "unknown",
              "peak_sampled_tree_rss_bytes": 0, "minimum_sampled_free_ram_bytes": None,
              "exit_confirmed": False, "cleanup_confirmed": False,
              "hard_rss_cap_enforced": False}
    started = clock.now()
    if (type(setup_elapsed) not in (int, float) or not math.isfinite(setup_elapsed)
            or setup_elapsed < 0 or setup_elapsed + LIMITS["probe_seconds"] > LIMITS["active_seconds"]):
        result["reason"] = "insufficient_active_budget"
        return result

    def sample():
        value = resources.sample()
        if (type(value) is not Sample or type(value.free_ram_bytes) is not int
                or type(value.tree_rss_bytes) is not int or value.free_ram_bytes < 0
                or value.tree_rss_bytes < 0 or value.owned_tree_verified is not True):
            raise ValueError("invalid_resource_sample")
        result["peak_sampled_tree_rss_bytes"] = max(result["peak_sampled_tree_rss_bytes"], value.tree_rss_bytes)
        old = result["minimum_sampled_free_ram_bytes"]
        result["minimum_sampled_free_ram_bytes"] = value.free_ram_bytes if old is None else min(old, value.free_ram_bytes)
        return value

    try:
        initial = sample()
        if initial.free_ram_bytes < LIMITS["startup_free_ram_bytes"]:
            result["reason"] = "startup_ram_below_floor"
            return result
        if initial.tree_rss_bytes > LIMITS["process_tree_rss_bytes"]:
            result["reason"] = "tree_rss_exceeded"
            return result
        if not process.owned:
            result["reason"] = "ownership_unverified"
            return result
        process.launch()
        result["phase"] = "probe"
        deadline = started + LIMITS["probe_seconds"] - LIMITS["probe_cleanup_seconds"]
        while True:
            value = sample()
            if value.free_ram_bytes < LIMITS["runtime_free_ram_bytes"]:
                result["reason"] = "runtime_ram_below_floor"
                break
            if value.tree_rss_bytes > LIMITS["process_tree_rss_bytes"]:
                result["reason"] = "tree_rss_exceeded"
                break
            code = process.poll(clock)
            if code is not None:
                result["status"] = "passed" if code == 0 else "failed"
                result["reason"] = "child_completed" if code == 0 else "child_failed"
                break
            if clock.now() >= deadline:
                result["reason"] = "probe_deadline"
                break
            clock.advance(min(1.0, deadline - clock.now()))
    except Exception:
        result["reason"] = "resource_or_process_interface_failed"
    finally:
        if process.launched:
            result["phase"] = "cleanup"
            # Terminate only our owned tree; never target a PID/name from logs.
            clean = process.terminate_owned_tree()
            while not clean and clock.now() < started + LIMITS["probe_seconds"]:
                clock.advance(min(1.0, started + LIMITS["probe_seconds"] - clock.now()))
                clean = process.stopped
            result["cleanup_confirmed"] = bool(clean)
            result["exit_confirmed"] = bool(clean and process.poll(clock) is not None)
            if not result["exit_confirmed"]:
                result["status"] = "blocked"
                result["reason"] = "owned_tree_cleanup_unconfirmed"
        result["elapsed_seconds"] = clock.now() - started
        result["overall_elapsed_seconds"] = setup_elapsed + result["elapsed_seconds"]
    return result


if __name__ == "__main__":
    # CLI intentionally has no setup/execute option, file input, subprocess or network.
    print(json.dumps(plan(), sort_keys=True, indent=2))
