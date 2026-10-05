"""Source preparation for a single bounded CPU probe. Importing is inert.

The public CLI is deliberately stopped. Offline tests inject fake pipelines;
no dependency acquisition, NER import, installation, or run claim is performed.
The byte-identical entry policy is the independently frozen policy.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import statistics
import time

from ner_entry_policy import EntitySpan, evaluate_entries, validate_canon_keys

POLICY_SHA256 = "cf439dac564b81cd04a22c2172435ec42082b4a38ee8e76ac222167483060363"
MODEL_CONFIG_SHA256 = "8d2a3ad3a0be5664cf07a9270bcd0c262f3cff47519a5d58ad606325a8d82db9"
SMOKE_SOURCE = "これは文です。"
POPULATIONS = (("diagnostic", 16), ("seen", 32), ("fresh", 24))
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_JSON_INPUT_BYTES = 256 * 1024
MAX_RSS_KIB = 512 * 1024
CPU_SECONDS = 15.0
COLD_SECONDS = 5.0
WARM_P95_SECONDS = .025
PIPELINE_COMPONENTS = ("tok2vec", "ner")
EXCLUDED_COMPONENTS = ("parser", "attribute_ruler", "morphologizer", "compound_splitter", "bunsetu_recognizer")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


class ProbeFailure(RuntimeError):
    """Safe error category and call counters; never retain source/exception text."""
    def __init__(self, category, attempted=0, completed=0):
        self.category, self.attempted, self.completed = category, attempted, completed
        super().__init__(category)


def require(condition, category):
    if not condition:
        raise ProbeFailure(category)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def nearest_rank_p95(values):
    require(type(values) in (list, tuple) and len(values) > 0 and all(finite_number(v) for v in values),
            "invalid_timing")
    return sorted(values)[math.ceil(.95 * len(values)) - 1]


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    source: str
    population: str
    canon_id: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class Population:
    cases: tuple[Case, ...]
    canons: dict[str, tuple[str, ...]]
    # Original immutable file pins; no private expected decisions are accepted.
    input_files: dict[str, dict]


def validate_population(population):
    require(type(population) is Population and type(population.cases) is tuple, "invalid_population")
    require(len(population.cases) == 72 and type(population.canons) is dict
            and set(population.canons) == {"old", "fresh"}, "invalid_population")
    for keys in population.canons.values():
        require(type(keys) is tuple and len(keys) == 6, "invalid_canon")
        try:
            validate_canon_keys(keys)
        except Exception:
            raise ProbeFailure("invalid_canon") from None
    require(not set(population.canons["old"]) & set(population.canons["fresh"]), "invalid_canon")
    require(sum(len(k) >= 2 for k in population.canons["fresh"]) >= 2, "invalid_canon")
    expected = [name for name, count in POPULATIONS for _ in range(count)]
    ids = set()
    for case, group in zip(population.cases, expected, strict=True):
        require(type(case) is Case and type(case.id) is str and ID_RE.fullmatch(case.id) is not None,
                "invalid_case_id")
        require(case.id not in ids, "duplicate_case_id")
        ids.add(case.id)
        require(case.population == group and case.canon_id == ("fresh" if group == "fresh" else "old"),
                "population_binding_mismatch")
        require(type(case.source) is str and 0 < len(case.source) <= (80 if group == "fresh" else 256),
                "invalid_source")
        require(type(case.source_sha256) is str and SHA_RE.fullmatch(case.source_sha256) is not None
                and sha256_bytes(case.source.encode("utf-8")) == case.source_sha256, "source_hash_mismatch")
        if group == "fresh":
            counts = [len(re.findall(re.escape(k), case.source)) for k in population.canons[case.canon_id]]
            require(sum(n > 0 for n in counts) <= 2 and sum(counts) <= 4, "fresh_format_mismatch")
    require(type(population.input_files) is dict and 1 <= len(population.input_files) <= 16,
            "invalid_input_bindings")
    for name, pin in population.input_files.items():
        require(type(name) is str and ID_RE.fullmatch(name) is not None and type(pin) is dict
                and set(pin) == {"sha256", "bytes"} and type(pin["sha256"]) is str
                and SHA_RE.fullmatch(pin["sha256"]) is not None and type(pin["bytes"]) is int
                and 0 < pin["bytes"] <= MAX_JSON_INPUT_BYTES, "invalid_input_bindings")
    return population


def validate_bindings(bindings):
    names = {"protocol", "attempt_id", "source_inventory_sha256", "dependency_manifest_sha256",
             "installed_inventory_sha256", "model_inventory_sha256", "input_manifest_sha256"}
    require(type(bindings) is dict and set(bindings) == names, "invalid_bindings")
    require(bindings["protocol"] == "luna-ner-cpu-v1" and type(bindings["attempt_id"]) is str
            and ID_RE.fullmatch(bindings["attempt_id"]) is not None, "invalid_bindings")
    for key in names - {"protocol", "attempt_id"}:
        require(type(bindings[key]) is str and SHA_RE.fullmatch(bindings[key]) is not None,
                "invalid_bindings")


def sanitized_doc(source, doc, keys):
    """Validate original codepoint slices, then discard raw token/entity text."""
    require(type(doc.text) is str and doc.text == source, "document_text_mismatch")
    require(0 < len(doc) <= 256, "invalid_tokens")
    token_offsets, previous = [], 0
    for token in doc:
        start, text = token.idx, token.text
        require(type(start) is int and type(text) is str and text != "", "invalid_tokens")
        end = start + len(text)
        require(previous <= start < end <= len(source) and source[start:end] == text,
                "invalid_tokens")
        require(not source[previous:start] or source[previous:start].isspace(), "invalid_token_gap")
        token_offsets.append([start, end])
        previous = end
    require(not source[previous:] or source[previous:].isspace(), "invalid_token_gap")
    entities = doc.ents
    require(type(entities) in (tuple, list) and len(entities) <= 256, "invalid_entities")
    spans = [EntitySpan(ent.start_char, ent.end_char, ent.text, ent.label_) for ent in entities]
    try:
        decision = evaluate_entries(source, keys, spans)
    except Exception:
        raise ProbeFailure("invalid_entities") from None
    starts = {start: index for index, (start, _) in enumerate(token_offsets)}
    ends = {end: index for index, (_, end) in enumerate(token_offsets)}
    require(all(span.start in starts and span.end in ends and starts[span.start] <= ends[span.end]
                for span in spans), "entity_token_alignment_mismatch")
    evidence = {
        "tokens": token_offsets,
        "entities": [{"start": s.start, "end": s.end, "label": s.label} for s in spans],
        "admitted_canon_indexes": [i for i, entry in enumerate(decision.entries) if entry.admitted],
        "entries": [{"canon_index": i, "admitted": entry.admitted,
                     "occurrences": [{"start": o.start, "end": o.end, "exact_person": o.exact_person}
                                     for o in entry.occurrences]}
                    for i, entry in enumerate(decision.entries)],
    }
    return evidence


def check_resources(cpu_seconds, rss_kib):
    require(finite_number(cpu_seconds) and finite_number(rss_kib), "invalid_resource_measurement")
    require(cpu_seconds <= CPU_SECONDS, "cpu_gate_failed")
    require(rss_kib <= MAX_RSS_KIB, "rss_gate_failed")


def execute_batch(factory, population, bindings, *, clock=time.perf_counter,
                  cpu_seconds, peak_rss_kib):
    """Exactly smoke + 72 calls on success; errors stop immediately, no retry.

    The injected factory is used only by offline tests in this preparation.
    A separately released owned child must enforce its entire 60s lifecycle.
    CPU/RSS values are whole-process totals, including imports and smoke.
    """
    validate_population(population)
    validate_bindings(bindings)
    attempted = completed = 0
    records = []
    try:
        check_resources(cpu_seconds(), peak_rss_kib())
        cold_start = clock()
        pipeline = factory()
        require(tuple(pipeline.pipe_names) == PIPELINE_COMPONENTS, "unexpected_pipeline")
        cold = clock() - cold_start
        require(finite_number(cold) and cold <= COLD_SECONDS, "cold_gate_failed")
        check_resources(cpu_seconds(), peak_rss_kib())
        smoke_start = clock()
        attempted += 1
        smoke = sanitized_doc(SMOKE_SOURCE, pipeline(SMOKE_SOURCE), ())
        completed += 1
        smoke_duration = clock() - smoke_start
        require(finite_number(smoke_duration), "invalid_timing")
        check_resources(cpu_seconds(), peak_rss_kib())
        for case in population.cases:
            begin = clock()
            attempted += 1
            row = sanitized_doc(case.source, pipeline(case.source), population.canons[case.canon_id])
            duration = clock() - begin
            completed += 1
            require(finite_number(duration), "invalid_timing")
            check_resources(cpu_seconds(), peak_rss_kib())
            row.update(id=case.id, population=case.population, canon_id=case.canon_id,
                       source_sha256=case.source_sha256, source_codepoints=len(case.source),
                       elapsed_seconds=duration)
            records.append(row)
        all_times = [row["elapsed_seconds"] for row in records]
        fresh_times = [row["elapsed_seconds"] for row in records if row["population"] == "fresh"]
        metrics = {"cold_initialization_seconds": cold, "smoke_seconds": smoke_duration,
                   "all72_median_seconds": statistics.median(all_times),
                   "all72_p95_seconds": nearest_rank_p95(all_times),
                   "fresh24_median_seconds": statistics.median(fresh_times),
                   "fresh24_p95_seconds": nearest_rank_p95(fresh_times),
                   "cpu_seconds": cpu_seconds(), "peak_rss_kib": peak_rss_kib()}
        check_resources(metrics["cpu_seconds"], metrics["peak_rss_kib"])
        result = {"schema": "luna-ner-evidence-v1", "bindings": bindings,
                  "policy_sha256": POLICY_SHA256, "model": "ja_ginza", "model_version": "5.2.0",
                  "model_config_sha256": MODEL_CONFIG_SHA256,
                  "pipeline": list(PIPELINE_COMPONENTS), "tokenizer": "spacy.ja.JapaneseTokenizer",
                  "tokenizer_split_mode": "C", "positive_label": "Person", "input_files": population.input_files,
                  "complete": True, "attempted_pipeline_calls": attempted,
                  "completed_pipeline_calls": completed, "smoke": {
                      "source_sha256": sha256_bytes(SMOKE_SOURCE.encode()), "source_codepoints": len(SMOKE_SOURCE),
                      **smoke}, "records": records, "metrics": metrics,
                  "resource_gates_passed": metrics["all72_p95_seconds"] <= WARM_P95_SECONDS
                      and metrics["fresh24_p95_seconds"] <= WARM_P95_SECONDS,
                  "semantic_grading": "not_performed_private_offline_grading_required"}
        # Preserve complete bounded evidence on a warm gate failure, never claim success.
        require(len(canonical_json(result)) <= MAX_EVIDENCE_BYTES, "output_size_exceeded")
        return result
    except BaseException as exc:
        category = exc.category if type(exc) is ProbeFailure else "pipeline_or_measurement_failed"
        raise ProbeFailure(category, attempted, completed) from None


def load_spacy_pipeline_after_release():
    """Released only through the exact controller-bound owned CPU child."""
    import spacy
    import ja_ginza
    require(spacy.__version__ == "3.8.15" and ja_ginza.__version__ == "5.2.0", "version_mismatch")
    spacy.require_cpu()
    pipeline = ja_ginza.load(exclude=list(EXCLUDED_COMPONENTS))
    require(tuple(pipeline.pipe_names) == PIPELINE_COMPONENTS, "unexpected_pipeline")
    require(type(pipeline.tokenizer).__module__ == "spacy.lang.ja"
            and type(pipeline.tokenizer).__name__ == "JapaneseTokenizer"
            and pipeline.tokenizer.split_mode == "C", "unexpected_tokenizer")
    require("Person" in pipeline.get_pipe("ner").labels, "missing_person_label")
    return pipeline


def main():
    # Operational stops precede argument parsing, I/O, imports and claims.
    print('{"status":"stopped","reason":"source_preparation_only_not_released"}')
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
