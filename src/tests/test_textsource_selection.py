"""Regression tests for mutually exclusive text-source selection."""

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "LunaTranslator"),
)

from myutils.textsource_selection import select_exclusive_text_source

failures = []


def check(name, condition):
    print(("PASS" if condition else "FAIL"), name)
    if not condition:
        failures.append(name)


def statuses(**enabled):
    return {
        key: {"use": enabled.get(key, False)}
        for key in ("mssr", "texthook", "ocr", "copy", "filetrans")
    }


# Legacy Learning UI state: both flags survived an upgrade.  Hook must match
# the selector display and become the sole runtime source.
legacy = statuses(texthook=True, ocr=True)
check(
    "legacy Hook+OCR resolves to Hook",
    select_exclusive_text_source(legacy) == "texthook",
)
check(
    "legacy state normalized to Hook only",
    legacy["texthook"]["use"]
    and all(not state["use"] for key, state in legacy.items() if key != "texthook"),
)

# An explicit user choice must override the migration priority.
explicit = statuses(texthook=True, ocr=True)
check(
    "explicit OCR selection wins",
    select_exclusive_text_source(explicit, preferred="ocr") == "ocr",
)
check(
    "explicit OCR state normalized",
    explicit["ocr"]["use"]
    and all(not state["use"] for key, state in explicit.items() if key != "ocr"),
)

# Existing valid and disabled states remain well-defined.
single = statuses(copy=True)
check(
    "single Clipboard selection preserved",
    select_exclusive_text_source(single) == "copy" and single["copy"]["use"],
)
disabled = statuses()
check("all-disabled state remains disabled", select_exclusive_text_source(disabled) is None)

print()
print("RESULT:", "ALL PASS" if not failures else f"FAILURES: {failures}")
sys.exit(0 if not failures else 1)
