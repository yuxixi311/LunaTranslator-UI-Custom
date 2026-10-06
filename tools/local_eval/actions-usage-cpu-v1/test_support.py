"""Test-only loading of current derivative modules and pinned frozen policy."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT
POLICY = ROOT / "policy"
PINS = json.loads((ROOT / "UPSTREAM_PINS.json").read_bytes())


def load_verified(name, path, expected):
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == expected, str(path)
    if name in sys.modules:
        module = sys.modules[name]
        assert Path(module.__file__).resolve() == path.resolve()
        return module
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    module.__test_verified_sha256__ = expected
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


upstream_hashes = {name: sha256((ROOT/name).read_bytes()).hexdigest()
                   for name in ("actions_policy.py", "cpu_harness.py", "diagnostics.py")}
load_verified("actions_policy", UPSTREAM / "actions_policy.py", upstream_hashes["actions_policy.py"])
H = load_verified("cpu_harness", UPSTREAM / "cpu_harness.py", upstream_hashes["cpu_harness.py"])
load_verified("diagnostics", UPSTREAM / "diagnostics.py", upstream_hashes["diagnostics.py"])
load_verified("_integrity_guard", POLICY / "_integrity_guard.py", "bbbecdb62ff12030428d5da662beb537d7fe6aba49357d641f78d3e84e6554a7")
P = load_verified("usage_example_policy", POLICY / "usage_example_policy.py", "f94a9af78a2c1694f432c4a12850fd0e27e0c6d067180810e1dc87064d650df9")
BANK = (POLICY / "runtime_bank.frozen.json").read_bytes()
assert sha256(BANK).hexdigest() == P.FROZEN_BANK_SHA256
ALIAS = H.alias_for("11111111111141118111111111111111")


def fake_inputs():
    from usage_runner_core import ROW_IDS
    pairs = json.loads(BANK)["records"]
    source_rows, metadata, schedule = [], [], []
    challenge_types = ["literal", "metalinguistic", "polarity", "participant_assignment",
                       "source_ambiguity", "otherwise_inappropriate", "polarity", "participant_assignment"]
    for row in ROW_IDS:
        if row.startswith("N"):
            family, offset = divmod(int(row[1:])-1, 4)
            role = "carrier" if offset < 2 else "challenge" if offset == 2 else "control"
            # Public conditioning texts are test data, NEVER claimed holdouts.
            source = pairs[family]["source_ja"] if offset < 3 else f"synthetic unmatched control {family}"
            metadata.append(dict(id=row, family=f"wb{family+1:02d}", role=role,
                                 challenge_type=challenge_types[family] if role == "challenge" else None,
                                 expected_surface_reasons=["surface_eligible"] if offset < 3 else ["no_match"]))
            first = "A" if offset == 0 else "B" if offset == 1 else (
                ("A" if family % 2 == 0 else "B") if offset == 2 else ("B" if family % 2 == 0 else "A"))
        else:
            source = f"synthetic unmatched regression {row}"
            first = "A" if ROW_IDS.index(row) % 2 == 0 else "B"
        source_rows.append(dict(id=row, source=source))
        schedule.append(dict(id=row, arm_order=[first, "B" if first == "A" else "A"]))
    return source_rows, metadata, schedule


def fake_inventory(core, source_rows=None, metadata=None, schedule=None):
    original = fake_inputs()
    source_rows = original[0] if source_rows is None else source_rows
    metadata = original[1] if metadata is None else metadata
    schedule = original[2] if schedule is None else schedule
    return core.freeze_inventory(source_rows, metadata, BANK,
        source_digest=H.digest(H.canonical(source_rows)), metadata_digest=H.digest(H.canonical(metadata)),
        schedule_rows=schedule, schedule_digest=H.digest(H.canonical(schedule)))
