"""Freeze the independently reviewed public-source bank, without model/fixture work."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

if len(sys.argv) != 4:
    raise SystemExit("Usage: freeze_source_bank.py FREEZE_TIMESTAMP_UTC FIRST_REVIEW_RECEIPT SECOND_REVIEW_RECEIPT")

frozen_at = sys.argv[1]
review_inputs = [Path(arg) for arg in sys.argv[2:]]
assert all(path.is_file() for path in review_inputs)
reviews = []
for i, original_receipt in enumerate(review_inputs, 1):
    reviews.append({"file": Path(os.path.relpath(original_receipt, ROOT)).as_posix(), "sha256": digest(original_receipt)})

draft_path = ROOT / "bank.draft.json"
draft = json.loads(draft_path.read_text(encoding="utf-8"))
bank = copy.deepcopy(draft)
bank["bank_id"] = "luna-zh-wikibooks-usage-v1-20261006"
bank["status"] = "source_bank_frozen"
bank["source_frozen_at_utc"] = frozen_at
bank["source_freeze_scope"] = "Exactly eight independently source-reviewed pairs, original and converted texts, complete maps, anchors, focuses, source evidence, and attribution. This is not token/model/runtime-quality validation or execution permission."
bank["use_scope"] = "Local frozen source bank for a separately authorized and reviewed possible experiment. Actual token admission, runtime quality, fixture freeze, and execution review remain unverified. No model or fixture work was performed to create this artifact."
bank["runtime_projection_file"] = "runtime_bank.frozen.json"
bank["runtime_projection_binding_file"] = "SOURCE_FREEZE.json"
bank["independent_source_review_receipts"] = reviews
bank["preserved_draft"] = {"file": "bank.draft.json", "sha256": digest(draft_path)}
bank["admission_state"].update({
    "independent_bilingual_review_complete": True,
    "final_admission_complete": True,
    "admission_scope": "Source quality and orthographic adaptation only",
    "final_bank_frozen": True,
    "freeze_scope": "Source bank only; token and runtime validation remain unverified",
    "future_requirement": "Do not change, prune, replace, or rewrite the frozen eight-pair bank after preflight. Separately freeze independently authored evaluation fixtures and criteria before model outputs; satisfy the approved full-chat token gate and every unchanged global coverage gate before any authorized execution.",
})
bank["future_prefix_gate"] = {
    "status": "unverified_no_tokenizer_or_model_loaded",
    "token_count_unit": "Actual deployment tokenizer tokens in the complete rendered chat template, including wrapper and generation markers",
    "B": "Token count of the complete unchanged baseline chat template",
    "C": "Token count of the complete candidate chat template with the exact approved example wrapper",
    "delta": "C - B",
    "admission_predicate": "delta <= min(16, floor(0.40 * B)) AND C <= 384",
    "max_added_complete_chat_template_tokens": 16,
    "max_added_fraction_of_baseline_complete_chat_template_tokens": 0.4,
    "max_complete_candidate_chat_template_tokens": 384,
    "baseline_gate": "B > 384, an unknown template/tokenizer, or a failed actual token count blocks the attempt before any generation; do not drop the row.",
    "over_budget_row_rule": "A successfully counted row whose candidate delta or total exceeds the admission limits abstains to the unchanged baseline. The frozen eight-pair bank is never pruned, replaced, or rewritten. All unchanged global coverage requirements still apply; a coverage failure stops the attempt.",
    "no_proxy_counts": "Do not tokenize a standalone prefix as a substitute for C - B. Code-point lengths and estimated tokens do not prove admission. No source lengthening, sentence merging, truncation, or target rewrite may force admission.",
}
bank["literal_matching_precision"] = {
    "occurrence_counting_includes_overlaps": True,
    "focus_rule_scope": "Only the selected record's designated focus is scanned for occurrences outside its matched anchor",
    "normalization_or_morphological_exceptions": False,
    "semantic_disambiguation_guarantee": False,
}

for record in bank["candidates"]:
    record["status"] = "independent_source_review_accepted_source_frozen"
    record["proposed_orthographic_adaptation"]["status"] = "independent_bilingual_review_accepted_source_frozen"
    record["proposed_orthographic_adaptation"]["independent_review_required"] = "Completed for this exact frozen source pair and complete mapping; acceptance is bound by the independent source-review receipt hashes. It does not establish token admission or a unique reading of future inputs."
    notice = record["proposed_orthographic_adaptation"]["modification_notice"]
    record["proposed_orthographic_adaptation"]["modification_notice"] = notice.replace("This proposal has not been independently admitted.", "This exact adaptation was independently source-reviewed and is frozen for source use only; token/runtime validation is unverified.")
    record["model_assisted_quality_notes"]["bilingual_review_completed"] = True
    if "translation_ambiguity" in record:
        record["translation_ambiguity"]["status"] = "independently_accepted_with_explicit_ambiguity_retained"
        record["translation_ambiguity"]["review_requirement"] = "The recorded Chinese is one source-permitted reading, not the only acceptable reading of every future input. Independent reviewers accepted the modal focus and anchor with this ambiguity retained. Do not reject alternative faithful readings because they differ from the bank target."

assert len(bank["candidates"]) == 8
for prior, frozen in zip(draft["candidates"], bank["candidates"]):
    for key in ["id", "original", "original_pair_sha256_canonical_json_utf8", "source_excerpt", "source_excerpt_sha256_utf8", "contextual_anchor", "designated_focus"]:
        assert frozen[key] == prior[key], key
    for key in ["converted_zh", "changed_positions", "complete_position_map", "complete_position_map_schema"]:
        assert frozen["proposed_orthographic_adaptation"][key] == prior["proposed_orthographic_adaptation"][key], key

save_json(ROOT / "bank.frozen.json", bank)
runtime = json.loads((ROOT / "runtime_bank.json").read_text(encoding="utf-8"))
old_runtime_records = copy.deepcopy(runtime["records"])
runtime["bank_id"] = bank["bank_id"]
runtime["status"] = "source_bank_frozen"
assert runtime["records"] == old_runtime_records
assert runtime["records"] == [{"id": c["id"], "source_ja": c["original"]["ja"], "target_zh": c["proposed_orthographic_adaptation"]["converted_zh"], "contextual_anchor": c["contextual_anchor"]["text"], "designated_focus": c["designated_focus"]["text"]} for c in bank["candidates"]]
save_json(ROOT / "runtime_bank.frozen.json", runtime)

attribution = (ROOT / "ATTRIBUTION.md").read_text(encoding="utf-8")
attribution = attribution.replace("This local draft reuses", "This locally frozen source bank reuses")
attribution = attribution.replace("bank.draft.json", "bank.frozen.json")
attribution = attribution.replace("**pending final independent review, admission, and freeze**", "**independently accepted and source-frozen; actual-token and runtime-quality validation remain unverified**")
attribution = attribution.replace("This is a local review draft with community-sourced examples and model-assisted selection. It has not been professionally validated, published, or admitted for model/evaluation use.", "This is a local source-frozen bank with community-sourced examples and model-assisted selection. Two independent model-assisted bilingual reviews accepted the bounded source pairs and adaptations. This is not professional human validation or permission to execute. It has not been published or token/model/runtime-quality validated.")
(ROOT / "ATTRIBUTION.frozen.md").write_text(attribution, encoding="utf-8")

frozen_files = ["runtime_bank.frozen.json", "bank.frozen.json", "ATTRIBUTION.frozen.md", "source-capture-metadata.json", "source-particles-excerpts.txt", "source-adjectival-nouns-excerpts.txt"]
files = [{"file": f, "sha256": digest(ROOT / f), "bytes": (ROOT / f).stat().st_size} for f in frozen_files]
runtime_bytes = (ROOT / "runtime_bank.frozen.json").stat().st_size
provenance_bytes = sum(x["bytes"] for x in files if x["file"] != "runtime_bank.frozen.json")
assert runtime_bytes <= 16 * 1024
assert provenance_bytes <= 64 * 1024
binding = {
    "schema_version": "1.0",
    "bank_id": bank["bank_id"],
    "status": "source_bank_frozen",
    "frozen_at_utc": frozen_at,
    "validation_scope": "Independent source/bilingual review accepted. Actual full-chat token preflight and model/runtime quality are unverified. No fixture/model execution occurred in this curation task.",
    "records_frozen": 8,
    "complete_mapping_positions": 70,
    "orthographic_character_changes": 15,
    "all_source_target_anchor_focus_and_mapping_fields_unchanged_from_reviewed_draft": True,
    "runtime_projection_rule": "Copy all eight IDs, original Japanese, admitted converted Chinese, contextual anchors, and designated focuses in original selection order. Runtime header changes only bank ID and source-freeze status; all record fields are identical to the independently reviewed projection.",
    "runtime_max_bytes": 16 * 1024,
    "runtime_bytes": runtime_bytes,
    "separate_attribution_provenance_max_bytes": 64 * 1024,
    "separate_attribution_provenance_bytes_excluding_this_binding_and_manifest": provenance_bytes,
    "no_execution_permission": True,
    "drafts_retained": True,
    "review_receipts": reviews,
    "review_receipt_handling": "Existing independent receipts are referenced by relative filename and hash only. Their report contents are not copied into or loaded as part of the frozen runtime/provenance package.",
    "files": files,
    "manifest": "SHA256SUMS.frozen",
}
save_json(ROOT / "SOURCE_FREEZE.json", binding)
manifest_files = frozen_files + ["SOURCE_FREEZE.json", "freeze_source_bank.py"] + [r["file"] for r in reviews]
manifest = "".join(digest(ROOT / f) + "  " + f + "\n" for f in manifest_files)
(ROOT / "SHA256SUMS.frozen").write_text(manifest, encoding="utf-8")
print(json.dumps({"files": files, "source_freeze_sha256": digest(ROOT / "SOURCE_FREEZE.json"), "manifest_sha256": digest(ROOT / "SHA256SUMS.frozen"), "runtime_bytes": runtime_bytes, "separate_attribution_provenance_bytes": provenance_bytes}, ensure_ascii=False, indent=2))
