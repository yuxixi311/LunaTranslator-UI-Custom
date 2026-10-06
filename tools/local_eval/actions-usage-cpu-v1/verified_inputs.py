"""Pure loader for exact released PUBLIC source-only projection bytes.

No paths, I/O, private criteria, tokenizer counts, model calls, or generation.
Raw file pins and canonical core digests are retained as different bindings.
"""
RAW_PINS = {
    "sources87.json": "6eab3320dac90c215bb4cefad4dd50d5b1a09a1f1c028ec9ba90be4fe12c8ac7",
    "fresh_coverage32.json": "1733788dbcb99885cf0278227eea92e5ee23309a5b67a8aa190745342a088e24",
    "schedule87.json": "ac0f27a8e2d2632d7f8c1643a3088e5c53c6ea004584ab06df609591cf2ffe55",
}
MAX_INPUT_BYTES = 65536


def load_inventory(core, raw_inputs, bank_bytes):
    """OFFLINE source assembly/review only; matching is deliberately performed."""
    h = core.h
    h.require(type(raw_inputs) is dict and set(raw_inputs) == set(RAW_PINS), "public input closure")
    parsed = {}
    for name, expected in RAW_PINS.items():
        raw = raw_inputs[name]
        h.require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_BYTES and h.digest(raw) == expected,
                  "exact public source projection binding")
        parsed[name] = h.strict_json(raw)
    sources, coverage, schedule = (parsed[name] for name in RAW_PINS)
    inventory = core.freeze_inventory(sources, coverage, bank_bytes,
        source_digest=h.digest(h.canonical(sources)), metadata_digest=h.digest(h.canonical(coverage)),
        schedule_rows=schedule, schedule_digest=h.digest(h.canonical(schedule)))
    h.require(len(inventory.eligible_ids) == 24 and all(row.startswith("N") for row in inventory.eligible_ids) and
              inventory.request_total == 398, "frozen audited E=24/exact398 inventory")
    order = dict(inventory.schedule[::2])
    h.require(sum(order[row] == "baseline" for row in inventory.eligible_ids) == 12,
              "surface-eligible order balance; actual active balance remains unknown")
    return inventory


def load_runtime_inventory(core, raw_inputs, bank_bytes):
    """Native input binding without executing any matcher/admission in parent.

    Exact source-only artifacts were already matched at source freeze. The live
    worker independently reproduces all 87 surface decisions before completion.
    """
    from types import MappingProxyType
    from usage_runner_core import CoverageRow, Inventory, ROW_IDS
    h = core.h
    h.require(type(raw_inputs) is dict and set(raw_inputs) == set(RAW_PINS), "public input closure")
    data = {}
    for name, pin in RAW_PINS.items():
        raw = raw_inputs[name]
        h.require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_BYTES and h.digest(raw) == pin,
                  "exact runtime public-input binding")
        data[name] = h.strict_json(raw)
    h.require(type(bank_bytes) is bytes and len(bank_bytes) <= 16384 and
              h.digest(bank_bytes) == "9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a", "bank raw binding")
    sources, coverage, schedule_rows = (data[name] for name in RAW_PINS)
    source_map = {row["id"]: row["source"] for row in sources}
    declared_surface_rows = {row["id"] for row in coverage if row["expected_surface_reasons"] == ["surface_eligible"]}
    frozen_eligible = tuple(row for row in ROW_IDS if row in declared_surface_rows)
    schedule = tuple((row["id"], "baseline" if arm == "A" else "candidate") for row in schedule_rows for arm in row["arm_order"])
    return Inventory(MappingProxyType(source_map),
                     tuple(CoverageRow(**{**row, "expected_surface_reasons": tuple(row["expected_surface_reasons"])}) for row in coverage),
                     frozen_eligible, h.digest(h.canonical(sources)), h.digest(h.canonical(coverage)),
                     h.digest(bank_bytes), schedule, h.digest(h.canonical(schedule_rows)), 398)
