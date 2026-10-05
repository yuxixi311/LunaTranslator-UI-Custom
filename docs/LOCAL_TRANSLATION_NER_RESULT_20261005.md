# GiNZA NER admission result — 2026-10-05

**The exact-Person NER candidate completed 73/73 CPU pipeline calls and passed its resource gates, but failed both frozen admission gates: 14/16 historical diagnostics (required 16/16) and 16/24 fresh cases (required 24/24). It is not eligible for GPU advancement or promotion.** Hy1.8B remains an optional experimental baseline, and the [supplied-glossary round](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md) remains **inconclusive**.

The installation and execution milestone is real: the pinned GiNZA 5.2.0 stack loaded and ran after the bounded plac script-layout correction. The admission result is not a robust optimization. On the historical diagnostics, it removes two false activations while losing two expected person entries; on the fresh population, it misses eight of eleven expected entries. No Hy translation calls or GPU comparison ran, so no translation-quality improvement is established.

This sanitized source checkpoint supplements the [earlier POS lexical result](LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md) and [2026-10-04 checkpoint](LOCAL_TRANSLATION_CHECKPOINT_20261004.md). Their failures and uncertainty remain part of the record.

## Execution identity and infrastructure history

The application branch base for this checkpoint is [5587dbb](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/5587dbbcaf3874e80b1b95b33385f23ee6f617b2) on `codex/local-translation-presets`. The experiments ran separately on `experiment/luna-actions-lexical-20261005`.

The completed [run 37350713392](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37350713392) used protocol `luna-ner-cpu-plac-v5`, source commit [66d4550](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/66d45508da6ab6cfa567b10376c376221286e442), trigger commit [08cc4d1](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/08cc4d1183cbd5e57b00a826e85a3eac065f468b), and GitHub run attempt 1. All 73 planned calls completed: one fixed smoke call, 16 historical diagnostic calls, 32 seen-regression calls, and 24 fresh calls. Workflow completion and resource eligibility are separate from admission acceptance.

| Record | Source / trigger commits | Observed terminal result |
| --- | --- | --- |
| [NER v1: 37305143765](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37305143765) | `d63ec309be4c70056c742a6b5a6cc92f655014e1` / `265c7ad2cb1dd508bf2bdf8bcd9efb7dbd2dd82c` | Setup failed at anyio wheel validation; the retained v1 evidence does not identify a narrower subcheck |
| [NER diagnostic v2: 37310071065](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37310071065) | `b9bb623849882931b25987957643e4ab04d61227` / `3b5d525909baa80e4bb7c7dd487f3f29de1a458f` | Setup rejected anyio with `metadata_dynamic_forbidden` |
| [NER dynamic v3: 37318441092](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37318441092) | `c809d101294aabf5b4d8a6d222ae8d8154db7135` / `bfad907ff4f1bb7c1cc6f5389b657cece46b9d64` | Setup rejected idna's observed metadata version 2.5 as unsupported |
| [NER metadata v4: 37327170748](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37327170748) | `602d78a8ee2af4938545d508b938607f00f73d3b` / `eb9769ceaecdec84acb7882bb4027a3adc545d48` | Setup rejected plac with `layout_relocation_scheme_unsupported` |
| [Fixed-49 archive audit: 37340800137](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37340800137) | `6a8da3a9a00ec942c0e87376338b04a0d71ec416` / `e8713691d8c8814fc407eaa014252d331e640535` | All 49 acquisitions and structural audits completed; plac script relocation remained a compatibility finding; no installation, package import or NER execution |
| [NER plac v5: 37350713392](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37350713392) | `66d45508da6ab6cfa567b10376c376221286e442` / `08cc4d1183cbd5e57b00a826e85a3eac065f468b` | Setup and all 73 CPU calls completed; resource gates passed; both admission gates failed |

Each is a distinct record with GitHub run attempt 1. For v1–v4, confirmed pipeline-call counters are null, not measured zero; each failed during setup before the parser phase. Later findings do not retroactively supply a missing earlier subcheck. The prior POS probe's three attempts remain documented in its separate report. Infrastructure recovery attempts and the archive audit are not completed Hy semantic optimization rounds.

The fixed-49 audit acquired 207,406,351 compressed bytes and structurally audited 4,516 members totaling 553,459,131 uncompressed bytes. It established archive evidence with a finding, not runtime compatibility or legal clearance. The v5 change addressed the reviewed plac 1.4.7 script layout on the already pinned stack; it did not alter the NER admission policy, diagnostic inputs, fresh criteria or acceptance gates. This successful run establishes operation in the measured Linux environment, not a general runtime guarantee.

## Frozen admission mechanism

The [bound policy](https://github.com/yuxixi311/LunaTranslator-UI-Custom/blob/08cc4d1183cbd5e57b00a826e85a3eac065f468b/tools/local_eval/actions-ner-cpu-plac-v5/ner_entry_policy.py) admits a canon entry only when it occurs in the unmodified source and **every** literal occurrence exactly matches an entity span labeled `Person`. Missing, non-Person, containing or partial spans withhold the entire entry. Withholding means insufficient qualifying evidence; it does not prove ordinary-word meaning. The entry policy does not use case IDs, expected labels, destination aliases, dictionary POS or confidence scores.

The observed model was `ja_ginza` 5.2.0, with `tok2vec` and `ner` enabled, using the Japanese tokenizer in SplitMode.C. This replaces the earlier POS evidence source while retaining conservative all-occurrence admission. The comparison below concerns whole-case admitted-entry sets and individual unexpected/missed entries, not translation accuracy.

## Historical diagnostics and seen regressions

| Historical diagnostic stratum | POS exact cases / total | NER exact cases / total |
| --- | ---: | ---: |
| Explicit person | 4/4 | 2/4 |
| Ordinary word | 3/4 | 4/4 |
| Mixed use of the same key | 3/4 | 4/4 |
| Partial word | 2/2 | 2/2 |
| No match | 2/2 | 2/2 |
| **Total; gate 16/16** | **14/16 — FAIL** | **14/16 — FAIL** |
| False-positive entries | 2 | 0 |
| Missed expected entries | 0 | 2 |

The exact-case total is unchanged, but the errors changed type. The candidate withheld the two historical false activations and also withheld two expected person entries. A lower false-positive count alone is insufficient when genuine names lose activation.

Across the 32 already-seen sources, matcher-active cases decreased from 12 with POS to 5 with NER. Seven previously active cases became inactive; there were no newly active cases. These are activation changes, not seven proven translation regressions or an improvement in source fidelity. No new translation output exists to decide that question.

The historical arithmetic was independently checked against the public expected decisions and recorded admissions. This check validates counts, not the correctness of the fixture labels or generalization. The 16 diagnostics and 32 regression sources were already exposed development material.

## Fresh 24-case aggregate

The primary offline evaluator graded the fresh admissions against the private rubric frozen before the model outputs and supplied the aggregate assessment below. The independent operational and historical audit did not regrade the fresh cases. This report does not reproduce the private criteria.

| Fresh assessment | Observed |
| --- | ---: |
| Exact whole-case admitted-entry sets; gate 24/24 | **16/24 — FAIL** |
| Expected-abstention cases correct | 14/14 |
| Positive cases with the complete expected set | 2/10 |
| Additional positive cases with only a partial expected set | 1 |
| Expected entries admitted | 3/11 |
| Missed expected entries | 8/11 |
| False-positive entries | 0 |

The 16 exact cases consist of all 14 expected-abstention cases plus only 2 of the 10 positive cases. One further positive case admitted part of its expected set and still failed whole-case exactness. Thus 16/24 must not be presented as strong name recovery, and zero false positives does not establish a robust optimization.

These are model-assisted fixture judgments for a bounded entry-admission task, not bilingual-human validation or population-level NER/translation accuracy. The fresh set was frozen before this run; after execution and assessment it is now exposed evaluation material and cannot serve as an untouched holdout for another iteration. This checkpoint does not publish fresh source text, per-case fresh decisions, full parser output or private criteria.

## Measured Linux costs

The run used CPython 3.12.14 on Linux x86_64 with glibc 2.39, on the reported Ubuntu 24 runner image `20260927.320.1`. Resource gates passed for this execution.

| Measurement | Observed |
| --- | ---: |
| Cold initialization | 3.099744 s |
| Warm P95 across all 72 scored calls | 21.661866 ms |
| Warm P95 across the fresh 24 calls | 21.453165 ms |
| Process CPU time | 6.133452 s |
| Peak process RSS | 478,056 KiB (466.852 MiB) |
| GPU use / translation-model calls | None / 0 |

Phase wall times, including phase lifecycle management, were download 2.169730 s, setup 15.656140 s and parse 6.584097 s. All three phases exited zero, did not time out and recorded confirmed cleanup. Their limits remained 240 s for download and 60 s each for setup and parse. Cold, warm, CPU and phase timings have different, overlapping scopes and must not be summed into an end-to-end latency estimate.

These standalone Linux CPU costs do not establish Windows ABI compatibility, game coexistence, Hy memory usage, end-to-end translation latency, model-weight reduction or a release-ready installation. Archive integrity, retained notices and successful installation do not constitute exhaustive license or redistribution clearance.

## Decision

1. Keep Hy1.8B as the optional experimental baseline. Retain the supplied-glossary round's inconclusive judgment and the historical failed prompt/context and incomplete comparison records.
2. Stop this unchanged exact-Person candidate before GPU evaluation. Its resource pass cannot override either failed admission gate, and installation recovery does not justify promotion.
3. A future optimization would need a materially different, generalizable mechanism with a testable reason to preserve genuine-name recovery while preventing false activation. Preserve all existing failures and abstention obligations; do not add word/case exceptions, tune against exposed answers, relax the gates or regrade old cases to claim success.
4. Only a justified new candidate could warrant a separately reviewed, preregistered plan with fixed mechanism and costs, the preserved historical regression gate, and a new independent holdout with private criteria frozen before outputs. The present 24 cases are now regression material. No new experiment follows automatically from this checkpoint.
5. Generic prompt loops, a larger model, or training are not established next steps by this result. The maximum three Hy optimization rounds remains a ceiling, not a quota; retaining baseline is a valid stopping decision. Any later translation claim still requires the [translation acceptance plan](LOCAL_TRANSLATION_TEST_PLAN.md), masked source-fidelity review and appropriate human review.

This checkpoint changes no application code, provider, default, model weights, popup behavior, release branch or binary package.

## Audit anchors and publication boundary

- Completed-run source inventory SHA-256: `d253d7d239084700aa746854e241a8fabf52afc169204dc1fdafee82699361af`
- Frozen dependency manifest SHA-256: `c04f4e31641594e90b9a6436625ad20d0de550b5f8543d70d5d70f46458d3401`
- Bound policy SHA-256: `cf439dac564b81cd04a22c2172435ec42082b4a38ee8e76ac222167483060363`
- Completed evidence SHA-256: `91a4dfb06f79f331b01fb8bd186492f73e1c2b4fa54d65af34ead91c17b400ac`

The public checkpoint is limited to sanitized aggregate results, resource summaries, commit/run references and hashes. Phase/setup and installed-inventory receipts are bound by hashes, but their full ephemeral bodies and raw child logs were not retained; those inventories cannot be independently reconstructed from the public evidence.

This report excludes raw host paths, private reviewer criteria, complete fresh source/output packets, raw runtime archives, credentials, Library identifiers and model files. Hashes bind evidence identity; they do not make omitted content publicly available or independently reproducible.
