# Local translation development checkpoint — 2026-10-04

**Hy1.8B remains experimental. The first supplied-glossary optimization round is inconclusive, and the subsequent cloud lexical feasibility pilot has not executed. No candidate is promoted.**

This checkpoint packages source, tests and development status on the existing feature branch. It is not an application release or a model-weight distribution. Earlier reports and failed experiments remain part of the record.

## Completed work and limits

- The optional local-provider implementation and protected-format checks are already on this branch. They preserve the existing providers and surface integrity failures; format protection is not proof of semantic accuracy
- The [three-way report](LOCAL_TRANSLATION_THREEWAY_RESULT_20261003.md) preserves the incomplete Google comparison (40/48), the separate exploratory common-40 review, and the primary local-48 review. Missing Google cases are category-skewed. There is no formal winner or fourth-arm trigger
- The [first glossary-round report](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md) records two definite source-fact corrections in distinct cases. They concern an object/event interpretation and an explanation's audience, not a demonstrated general grammar or name-recognition fix
- That round also changes one baseline definite-pass interpretation to uncertain. This uncertainty blocks promotion under the unchanged safety gate. Both arms already achieved canonical-name compliance on all 12 applicable cases. Cost gates passed; quality acceptance did not
- Earlier generic prompt and context trials failed their frozen gates. They are not repeated or relabeled as successful by this checkpoint

Reviews are model-assisted, not independent human bilingual certification. All previously exposed evaluation cases are now seen regression material.

## Current lexical hypothesis

Before spending another GPU round, test whether one conservative source-derived rule can activate the existing glossary more appropriately. SudachiPy 0.6.11 and the core 20260723 dictionary would provide token spans, part-of-speech fields and dictionary/OOV information. An entry is admitted only when every literal occurrence exactly matches a known person-name token. Mixed, partial and unknown occurrences withhold the whole entry.

This all-occurrence rule matters because the existing glossary prompt applies to a whole entry, not a specific occurrence. A person-name match cannot safely grant a mapping to the same surface used elsewhere as an ordinary noun. Tokenization and POS still cannot establish the intended sense of an ambiguous name, ownership, or sentence meaning.

The [Sudachi paper](https://aclanthology.org/L18-1355/) treats tokenization and named-entity recognition as separate concerns. The [versioned SudachiPy API](https://github.com/WorksApplications/sudachi.rs/blob/v0.6.11/python/py_src/sudachipy/sudachipy.pyi) supplies the span, POS and OOV fields used here. These sources support testing the mechanism, not a claim of translation improvement.

The fixed feasibility set consists of 16 illustrative synthetic diagnostics and 32 seen regression sources, for exactly 48 planned tokenizer calls. These are mechanism diagnostics, not fresh translation holdout evidence. All 16 predeclared entry decisions must match before considering a new semantic experiment. Expected decisions are used only after token evidence has been collected. No analyzer result exists yet.

The reviewed cloud plan pins two official PyPI wheels totaling 73,904,174 compressed bytes (70.481 MiB), with a 100 MiB download ceiling. Setup includes archive/RECORD checks, extraction and offline installation inside 60 seconds. The dictionary must match the previously observed 217,466,039-byte digest. The owned parser is bounded by a 60-second lifecycle, 15-second CPU limit and 1 GiB address-space limit. These are planned limits, not measured parser costs. No new product dependency or weight is bundled.

## Verified blocker and launch history

The cloud execution request failed before the pilot created its one-shot claim or output directory. The immutable execution-manifest digest remains `4299f5c616bf574dbce7fd9192406294cae973f93348ff41b6705fd679254a09`.

| Check on 2026-10-04 (UTC) | Observed outcome | Pilot activity |
| --- | --- | --- |
| 03:17 reporting checkpoint (launch at 03:16) | bubblewrap mount-target error, OS error 20, exit 101 | None recorded |
| 03:51 | Same startup error, exit 101 | None recorded |
| 04:22 reporting checkpoint (launch completed at 04:23) | Same startup error, exit 101 | None recorded |
| 04:53 | `CreateProcess: TurnAborted`, no detailed reason | None recorded |

Postchecks found no claim or run directory each time. There were no package downloads, installations, tokenizer calls or new GPU inference. `TurnAborted` does not identify a user cancellation or permission denial, and does not establish recovery of the earlier startup defect. The environment problem is not a lexical-policy failure or a translation score.

The owner requested half-hour cloud retries through the original route. This document records status only; it does not start a retry or authorize changing sandbox/security settings. Windows fallback preparation was cancelled at the owner's request. Ordinary development stays in the cloud; genuinely Windows-specific application QA or hardware validation remains a separately coordinated desktop task.

## Next development path

1. Recover the supported cloud launch route and complete the single frozen lexical probe. Check existing claim/evidence before each authorized startup check; never repeat a consumed or completed probe, remove its claim, or switch routes around a denial
2. Audit package/dictionary identity, all 48 token records, resource/cleanup evidence and the exact 16 diagnostic decisions. If the rule loses legitimate names or admits ordinary/mixed uses, record the failed mechanism rather than patching individual answers or changing the dictionary after seeing results
3. Only if that mechanism evidence justifies it, freeze one low-overhead Hy1.8B round-two candidate and a new independently authored semantic holdout. Retain all old cases, including the unresolved ownership interpretation and ordinary-word negatives, with their original criteria
4. Run the reviewed same-model GPU comparison once under resource and quality gates, followed by masked source-fidelity review, uncertainty preservation and independent arithmetic review. Canonical spelling and latency cannot substitute for semantic acceptance
5. Adopt only an evidenced safe improvement. The current optimization series has a maximum of three rounds, not a requirement to exhaust them. An inconclusive or adverse result can justify retaining baseline

No larger generator, weight training, paid API, user-corpus upload or unproven default promotion is part of this path. Model weights remain optional; their existing size has not been reduced. Release-level claims still require remaining application/game-load acceptance and appropriate human review.

## Publication boundaries

The [public cloud lexical source snapshot](../tools/local_eval/cloud-lexical-v1/README.md)
contains 23 files and passes 30 pure/fake preparation and packaging tests. Its
public source-manifest SHA-256 is
`f1c42c5f3550d4ac736de2582c175de6812ae464bf9d5778619a822f9e598ce3`.
Sanitized metadata and separate manifest names give it a distinct identity from
the original frozen pilot. It contains no execution manifest and requires review
of any future execution manifest before use. Passing these tests does not verify
native-package compatibility or analyzer behavior.

The repository checkpoint contains reusable development source, tests, notices and a sanitized progress/roadmap record. Illustrative lexical diagnostics can include their expected entry decisions; they are public development tests. Private semantic grading criteria, reviewer packets and notes, full fresh model outputs, raw execution archives, machine paths, credentials, runtime identity records, model weights and cancelled Windows draft code are excluded. The public preparation snapshot must not be mistaken for the private frozen execution manifest or evidence of an executed pilot.
