"""Strict, bounded fixture reads and independently replayable output validation.

No fixture is opened on import. The fresh fixtures/criteria were not read when
authoring this code. Only the author-provided schema and immutable hashes were
used; fake files exercise the readers offline.
"""
import json
import os
from pathlib import Path
import stat
import statistics
import unicodedata

from ner_adapter import (Case, Population, POPULATIONS, SMOKE_SOURCE, POLICY_SHA256,
    MODEL_CONFIG_SHA256, MAX_JSON_INPUT_BYTES, MAX_EVIDENCE_BYTES, PIPELINE_COMPONENTS,
    COLD_SECONDS, CPU_SECONDS, MAX_RSS_KIB, WARM_P95_SECONDS, ProbeFailure,
    require, finite_number, nearest_rank_p95, canonical_json, sha256_bytes,
    validate_population, validate_bindings)
from ner_entry_policy import EntitySpan, evaluate_entries

FIXTURE_HASHES = {
    "diagnostic_sources": "5a02d97443f724e974a12aa18a972138314440f36f358c488df151c4aebea9e9",
    "seen_sources": "51bdc8829a59b50e2ac3c82932b9421734dada333dcc6c6ef58fde78974ab72d",
    "old_canon": "7cc5bdb3626dd4e781070dca708428c0ef81048d72b067a71f9e15c795814337",
    "fresh_sources": "2dfdd379e98bc210dfe04073081c4051809ce05216ee25c3baef74bac242662c",
    "fresh_canon": "12b81554051ff4c0456315a4de834224ca46708acf677eba90e32de7755d62b0",
}
CASE_FIELDS = {"diagnostic": {"id", "source", "category"},
               "seen": {"id", "source", "category", "status"}, "fresh": {"id", "source"}}


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def decode_json(data, limit):
    require(type(data) is bytes and len(data) <= limit, "json_size_exceeded")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(ProbeFailure("invalid_json_number")))
    except ProbeFailure:
        raise
    except Exception:
        raise ProbeFailure("invalid_json") from None


def read_pinned_file(root, pin, cap=MAX_JSON_INPUT_BYTES):
    require(type(pin) is dict and set(pin) == {"path", "bytes", "sha256"}, "invalid_file_pin")
    require(type(pin["path"]) is str and type(pin["bytes"]) is int and 0 < pin["bytes"] <= cap,
            "invalid_file_pin")
    path = Path(pin["path"])
    require(not path.is_absolute() and len(path.parts) > 0 and all(p not in (".", "..") for p in path.parts),
            "unsafe_file_path")
    root = Path(root).resolve(strict=True)
    target = root / path
    require(target.resolve(strict=True) == target, "unsafe_file_path")
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == pin["bytes"],
                "file_type_or_size_mismatch")
        data = stream.read(cap + 1)
    require(len(data) == pin["bytes"] and sha256_bytes(data) == pin["sha256"], "file_hash_mismatch")
    return data


def population_from_documents(documents, input_pins):
    """Schema conversion only; testable with fake documents, no file access."""
    require(type(documents) is dict and set(documents) == set(FIXTURE_HASHES), "fixture_roles_mismatch")
    canons = {}
    for name in ("old", "fresh"):
        document = documents[name + "_canon"]
        expected = {"entries", "project_description"} if name == "old" else {"entries"}
        require(type(document) is dict and set(document) == expected and type(document["entries"]) is list
                and len(document["entries"]) == 6, "invalid_canon_document")
        keys = []
        destinations = []
        for entry in document["entries"]:
            require(type(entry) is dict and set(entry) == {"src", "dst"}, "invalid_canon_document")
            require(type(entry["dst"]) is str and 0 < len(entry["dst"]) <= 16,
                    "invalid_canon_destination")
            require(not any(ch.isspace() or unicodedata.category(ch) in {"Cc", "Cf", "Cs"}
                            for ch in entry["dst"]), "invalid_canon_destination")
            keys.append(entry["src"])
            destinations.append(entry["dst"])
        require(len(set(destinations)) == len(destinations), "duplicate_canon_destination")
        canons[name] = tuple(keys)
    cases = []
    for group, count in POPULATIONS:
        rows = documents[group + "_sources"]
        require(type(rows) is list and len(rows) == count, "population_count_mismatch")
        for row in rows:
            require(type(row) is dict and set(row) == CASE_FIELDS[group] and type(row["source"]) is str,
                    "invalid_case_document")
            # Category/status are pre-existing fixture data. They never enter the
            # model, policy, decision, or published evidence.
            cases.append(Case(row["id"], row["source"], group, "fresh" if group == "fresh" else "old",
                              sha256_bytes(row["source"].encode("utf-8"))))
    return validate_population(Population(tuple(cases), canons, input_pins))


def load_frozen_population(root, file_pins):
    """Future runtime only. Exact hashes prevent fixture/version substitution."""
    require(type(file_pins) is dict and set(file_pins) == set(FIXTURE_HASHES), "fixture_roles_mismatch")
    documents, input_pins = {}, {}
    for role, digest in FIXTURE_HASHES.items():
        pin = file_pins[role]
        require(type(pin) is dict and pin.get("sha256") == digest, "fixture_freeze_mismatch")
        documents[role] = decode_json(read_pinned_file(root, pin), MAX_JSON_INPUT_BYTES)
        input_pins[role] = {"bytes": pin["bytes"], "sha256": digest}
    return population_from_documents(documents, input_pins)


def replay_row(row, source, keys):
    require(type(row) is dict and {"tokens", "entities", "entries", "admitted_canon_indexes"} <= set(row),
            "invalid_evidence_row")
    require(type(row["tokens"]) is list and 0 < len(row["tokens"]) <= 256, "invalid_token_evidence")
    previous = 0
    for bounds in row["tokens"]:
        require(type(bounds) is list and len(bounds) == 2 and all(type(v) is int for v in bounds),
                "invalid_token_evidence")
        start, end = bounds
        require(previous <= start < end <= len(source), "invalid_token_evidence")
        require(not source[previous:start] or source[previous:start].isspace(), "invalid_token_evidence")
        previous = end
    require(not source[previous:] or source[previous:].isspace(), "invalid_token_evidence")
    require(type(row["entities"]) is list and len(row["entities"]) <= 256, "invalid_entity_evidence")
    spans = []
    for entity in row["entities"]:
        require(type(entity) is dict and set(entity) == {"start", "end", "label"}, "invalid_entity_evidence")
        start, end = entity["start"], entity["end"]
        require(type(start) is int and type(end) is int, "invalid_entity_evidence")
        spans.append(EntitySpan(start, end, source[start:end], entity["label"]))
    try:
        decision = evaluate_entries(source, keys, spans)
    except Exception:
        raise ProbeFailure("invalid_entity_evidence") from None
    starts = {start: index for index, (start, _) in enumerate(row["tokens"])}
    ends = {end: index for index, (_, end) in enumerate(row["tokens"])}
    require(all(span.start in starts and span.end in ends and starts[span.start] <= ends[span.end]
                for span in spans), "entity_token_alignment_mismatch")
    actual = [{"canon_index": i, "admitted": entry.admitted,
               "occurrences": [{"start": o.start, "end": o.end, "exact_person": o.exact_person}
                               for o in entry.occurrences]} for i, entry in enumerate(decision.entries)]
    expected_indexes = [i for i, entry in enumerate(decision.entries) if entry.admitted]
    # JSON canonical bytes distinguish bool/int and prevent Python equality from
    # accepting false as 0 in offset or canon-index evidence.
    require(canonical_json(row["entries"]) == canonical_json(actual)
            and canonical_json(row["admitted_canon_indexes"]) == canonical_json(expected_indexes),
            "decision_replay_mismatch")


def validate_evidence(data, population, bindings):
    validate_population(population)
    validate_bindings(bindings)
    value = decode_json(data, MAX_EVIDENCE_BYTES)
    top = {"schema", "bindings", "policy_sha256", "model", "model_version", "model_config_sha256",
           "pipeline", "tokenizer", "tokenizer_split_mode", "positive_label", "input_files", "complete",
           "attempted_pipeline_calls", "completed_pipeline_calls", "smoke", "records", "metrics",
           "resource_gates_passed", "semantic_grading"}
    require(type(value) is dict and set(value) == top, "invalid_evidence_schema")
    fixed = {"schema": "luna-ner-evidence-v1", "bindings": bindings, "policy_sha256": POLICY_SHA256,
             "model": "ja_ginza", "model_version": "5.2.0", "model_config_sha256": MODEL_CONFIG_SHA256,
             "pipeline": list(PIPELINE_COMPONENTS), "tokenizer": "spacy.ja.JapaneseTokenizer",
             "tokenizer_split_mode": "C", "positive_label": "Person", "input_files": population.input_files,
             "complete": True, "attempted_pipeline_calls": 73, "completed_pipeline_calls": 73,
             "semantic_grading": "not_performed_private_offline_grading_required"}
    for key, expected in fixed.items():
        require(canonical_json(value[key]) == canonical_json(expected), "evidence_binding_mismatch")
    smoke = value["smoke"]
    row_fields = {"tokens", "entities", "entries", "admitted_canon_indexes"}
    require(type(smoke) is dict and set(smoke) == row_fields | {"source_sha256", "source_codepoints"},
            "invalid_smoke_evidence")
    require(smoke["source_sha256"] == sha256_bytes(SMOKE_SOURCE.encode())
            and type(smoke["source_codepoints"]) is int and smoke["source_codepoints"] == len(SMOKE_SOURCE),
            "invalid_smoke_evidence")
    replay_row(smoke, SMOKE_SOURCE, ())
    records = value["records"]
    require(type(records) is list and len(records) == 72, "incomplete_evidence_population")
    extra = {"id", "population", "canon_id", "source_sha256", "source_codepoints", "elapsed_seconds"}
    for row, case in zip(records, population.cases, strict=True):
        require(type(row) is dict and set(row) == row_fields | extra, "invalid_evidence_row")
        require(row["id"] == case.id and row["population"] == case.population and row["canon_id"] == case.canon_id
                and row["source_sha256"] == case.source_sha256 and type(row["source_codepoints"]) is int
                and row["source_codepoints"] == len(case.source), "evidence_population_mismatch")
        require(finite_number(row["elapsed_seconds"]), "invalid_timing")
        replay_row(row, case.source, population.canons[case.canon_id])
    metrics = value["metrics"]
    metric_fields = {"cold_initialization_seconds", "smoke_seconds", "all72_median_seconds", "all72_p95_seconds",
                     "fresh24_median_seconds", "fresh24_p95_seconds", "cpu_seconds", "peak_rss_kib"}
    require(type(metrics) is dict and set(metrics) == metric_fields and all(finite_number(v) for v in metrics.values()),
            "invalid_metrics")
    all_times = [r["elapsed_seconds"] for r in records]
    fresh_times = all_times[-24:]
    require(metrics["all72_median_seconds"] == statistics.median(all_times)
            and metrics["all72_p95_seconds"] == nearest_rank_p95(all_times)
            and metrics["fresh24_median_seconds"] == statistics.median(fresh_times)
            and metrics["fresh24_p95_seconds"] == nearest_rank_p95(fresh_times), "metrics_replay_mismatch")
    require(metrics["cold_initialization_seconds"] <= COLD_SECONDS and metrics["cpu_seconds"] <= CPU_SECONDS
            and metrics["peak_rss_kib"] <= MAX_RSS_KIB, "resource_gate_mismatch")
    passed = metrics["all72_p95_seconds"] <= WARM_P95_SECONDS and metrics["fresh24_p95_seconds"] <= WARM_P95_SECONDS
    require(type(value["resource_gates_passed"]) is bool and value["resource_gates_passed"] == passed,
            "resource_gate_mismatch")
    return value
