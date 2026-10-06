# Source-sense prefix result — 2026-10-06

**Final decision: FAIL_NO_PROMOTION.** The frozen Hy1.8B sense-prefix comparison completed all 176 translations, but failed the end-to-end cost gate and semantic acceptance. Two independent model-assisted reviews found fewer definite whole-row passes for the candidate on the 48 fresh cases, with two consensus definite baseline-pass-to-candidate-failure regressions and no consensus definite critical-failure-to-whole-row-pass fixes.

Keep Hy1.8B as the optional experimental baseline. Stop promotion of this unchanged prefix. This documentation checkpoint changes no application code, providers, defaults, model weights, popup behavior or UI v1.0.1 release. A completed workflow does not establish improved translation quality.

## Execution identity and completion

The application branch base for this checkpoint is [ec749944](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/ec749944fa0cbf9b5a7114d2c4dbe006e294fd65) on `codex/local-translation-presets`. The experiment is a separate execution record:

- [Run 37448197513](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37448197513), attempt 1, completed successfully on 2026-10-06
- Trigger commit [c23ef956](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/c23ef956fe80bda629d90915332c0feac33d061a)
- Frozen source commit [3d18c1d9](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/3d18c1d93665004db2c690f466e4ebf2c06ea98e), including the [scientific protocol](https://github.com/yuxixi311/LunaTranslator-UI-Custom/blob/3d18c1d93665004db2c690f466e4ebf2c06ea98e/tools/local_eval/actions-sense-cpu-v5/SCIENTIFIC_PROTOCOL.md)

All 88 paired cases produced 176 observed completion records: 48 fresh cases and 40 historical regressions, each with baseline and candidate output. All 442 planned loopback requests were consumed and validated. Prefix activation covered 44 fresh cases and no historical cases. The remaining cases stay in the required populations.

| Operational accounting | Observed |
| --- | ---: |
| Translation completions | 176 |
| Validated requests | 442 |
| Token-count requests | 264 |
| Count-only input tokens | 13,924 |
| Generation prompt tokens | 8,635 |
| Generated tokens | 2,249 |

The model and runtime receipts report verified size and digest, respectively 1,133,080,448 and 17,551,895 bytes. Acquisition, validation, version, server and helper children all exited zero; all child and terminal cleanup confirmations are true. The final protocol receipt is complete. An independent operational audit reproduced the public snapshot bindings, request accounting and timing arithmetic without new inference. Its operational pass is separate from the failed candidate decision.

Earlier infrastructure attempts and earlier candidate results remain distinct historical records; this completion does not retroactively turn any of them into a successful semantic experiment.

## Semantic assessment

Two independent model-assisted reviews used newly randomized labels and were frozen before label mapping. Review instructions prohibited external lookup. Execution evidence had already identified the arms publicly, so this is label-blind review **without guaranteed treatment blinding**, not a claim of fully blinded evaluation. The coordinating evaluator inspected the decisive source/output reasoning before recording the decision.

| Fresh 48-case assessment | Review 1 | Review 2 |
| --- | ---: | ---: |
| Baseline definite whole-row passes | 39/48 | 39/48 |
| Candidate definite whole-row passes | 35/48 | 34/48 |

The reviews agree on two definite fresh regressions from baseline whole-row pass to candidate failure. They agree on zero definite critical-failure-to-whole-row-pass fixes. These are consensus findings, not a claim that every individual judgment agreed or that no isolated fact improved. Disputed and uncertain cases remain disputed or uncertain; they were not converted into passes or omitted.

The candidate therefore does not meet semantic acceptance. Whole-row source fidelity matters: a local improvement cannot erase another consequential error in the same translation. These bounded model-assisted judgments are not professional human bilingual validation or an estimate of general translation accuracy.

The 48 cases were fresh for this comparison. After generation and review they are seen regression material and cannot be reused as an untouched holdout. This report publishes aggregate judgments only, without complete fresh source/output packets or private criteria.

## Frozen cost gate: failed

The preregistered ceiling was **1.25** for both the median and nearest-rank P95 of paired, per-row candidate/baseline elapsed ratios in every required population. The authoritative arm intervals include applicable prefix rendering and recurring token-count work.

| Required population | Rows | Median ratio | P95 ratio | Gate |
| --- | ---: | ---: | ---: | --- |
| Fresh | 48 | 1.4155785885060757 | 1.6367162196176535 | FAIL |
| Active fresh | 44 | 1.4295574134094298 | 1.6367162196176535 | FAIL |
| All cases | 88 | 1.1185247020998945 | 1.5708225288608912 | FAIL |
| All active | 44 | 1.4295574134094298 | 1.6367162196176535 | FAIL |

Median is calculated over the row-wise ratios; P95 is the nearest-rank value at `ceil(0.95 × n)`. A ratio of arm quantiles is a different statistic. The all-case median alone is below the ceiling, but its P95 fails, and both fresh-population statistics fail. The cost failure independently prevents promotion, regardless of semantic scoring.

Do not change populations, drop difficult cases, subtract prefix/token overhead or relax the ceiling after seeing these results.

| Reported CPU-run resource measurement | Observed |
| --- | ---: |
| Runner peak RSS | 37,064,704 bytes |
| Server peak RSS | 2,268,917,760 bytes |
| Helper peak RSS | 30,343,168 bytes |
| Helper render P95 | 133,038 ns (0.133038 ms) |

Reported helper resource gates passed. They do not override the end-to-end cost failure. These are CPU measurements; they establish no Windows, GPU, game-coexistence or application-release performance claim, and no model-weight reduction.

## Evidence limits and audit anchors

The public receipts and source bindings support output completeness and exact recomputation of the reported row-ratio statistics. Full raw HTTP wires, absolute arm/request timing intervals and continuous external host/resource attestation were not exported. Asset verification, cleanup and sampled RSS are runner receipts, not an independent rehash of the acquired model/runtime bytes or continuous observation of the host. The operational audit did not supply semantic grades.

| Evidence identity | SHA-256 |
| --- | --- |
| Frozen source manifest | `934502a50f608b29393e03187af03ee48c77d10ea3c0245d4de0560f64218d21` |
| Exact decoded job log | `ededa4bfe33db9ac34db3bcf68eca7d16e4a5050c1ca315efb87c39e0416a947` |
| Final public manifest | `472864ea7bd0501976de627d6df88e6f8e89c5a22cbeedd4d5636e646f218038` |
| Final accounting | `9539e6688e388e8b6d01e4fb770366967ada613022aa1046fc8a555209d25c40` |
| Final metrics | `f6a848f3ad433cf888fd8f33ea5f712d2b9099215d19e2d2da8843f77c3e5277` |

Hashes identify evidence; they do not make omitted contents available or prove semantic correctness. This checkpoint excludes private criteria and review packets, full fresh sources/translations, raw evidence archives, machine paths, credentials, Library identifiers and model files.

## Decision and next development path

1. Retain the optional experimental Hy1.8B baseline and the existing UI v1.0.1 release. Do not promote this prefix or advance the unchanged candidate to GPU evaluation.
2. Preserve the [inconclusive supplied-glossary round](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md), [failed POS lexical rule](LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md), [failed NER admission candidate](LOCAL_TRANSLATION_NER_RESULT_20261005.md), and earlier [prompt](LOCAL_TRANSLATION_PROMPT_V1_RESULT_20261003.md), [prompt-v2](LOCAL_TRANSLATION_PROMPT_V2_RESULT_20261003.md) and [context](LOCAL_TRANSLATION_CONTEXT_RESULT_20261003.md) results. Keep all earlier failures, unresolved interpretations and incomplete comparisons; this result supersedes their proposed experiment sequence, not their evidence.
3. Further work may begin with method-level source research only. One conditional feasibility question is whether sparse retrieval of trusted Japanese–Chinese microexamples is practical; no vetted aligned memory, ready candidate or translation gain is established. A future candidate needs a materially different, generalizable mechanism with a testable reason to improve source fidelity within the existing cost constraints. Do not repair individual outputs, add word/case exceptions, tune to these exposed answers or regrade old cases to manufacture a pass.
4. Before any new run, justify the mechanism, preregister its rule and resource/quality gates, preserve historical regressions and uncertainty, and freeze new independently authored fixtures and assessment criteria before outputs. A source proposal alone does not authorize execution; a new experiment needs a separately reviewed execution plan.
5. A larger generator or auxiliary sense model, weight training, a paid API, or another generic prompt loop is not an established next step. The maximum of three Hy optimization rounds remains a ceiling, not a quota. Retaining baseline is a valid stopping decision.

Release-level translation claims still require the [acceptance plan](LOCAL_TRANSLATION_TEST_PLAN.md) and appropriate human review. UI checks provide no semantic evidence.
