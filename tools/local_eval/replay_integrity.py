"""Replay existing frozen synthetic outputs through the integrity guard.

No inference, repair, model download, or semantic scoring occurs. Inputs must
contain all 40 unique IDs from the unchanged frozen fixture.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/LunaTranslator"))
from myutils.local_translation import LocalTranslationError
from myutils.local_translation_integrity import needs_integrity_check, validate_integrity


def replay(path):
    fixture = ROOT / "src/tests/fixtures/local_translation_eval_20261003.json"
    fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if fixture_hash != "051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1":
        raise ValueError("Frozen fixture changed")
    cases = {row["id"]: row for row in json.loads(fixture.read_text(encoding="utf-8"))["cases"]}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if Counter(row["id"] for row in records) != Counter({key: 1 for key in cases}):
        raise ValueError("Expected all 40 unique frozen case IDs")
    results = []
    for row in records:
        case = cases[row["id"]]
        source = case["source"]
        expected_prompt = "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n" + source
        if row["request"]["messages"] != [{"role": "user", "content": expected_prompt}]:
            raise ValueError("Input is not the frozen baseline request")
        translated = row["response"]["choices"][0]["message"]["content"]
        status = "not_guarded"
        if needs_integrity_check(source):
            try:
                validate_integrity(source, translated)
                status = "accepted_structure"
            except LocalTranslationError:
                status = "rejected_structure"
        results.append({"id": case["id"], "split": case["split"], "guard": status})
    return {"kind": "recorded-output replay, not fresh inference or semantic evaluation",
            "fixture_sha256": fixture_hash, "results_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "counts": dict(Counter(row["guard"] for row in results)), "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.results), ensure_ascii=False, indent=2))
