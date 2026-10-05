# Cloud lexical feasibility result — 2026-10-05

**The frozen lexical rule failed its 16/16 gate: 14/16 diagnostic decisions matched. Do not advance this unchanged rule to a GPU translation experiment.** The third independent Actions attempt completed all 48 CPU parsing calls; workflow success means execution completed, not that the lexical gate passed. Hy1.8B remains experimental, the [supplied-glossary round](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md) remains **inconclusive**, and no model/default promotion follows.

This is a sanitized development checkpoint. No new translation was generated, so these results cannot establish translation quality or resolve the earlier semantic uncertainty. The dated [2026-10-04 checkpoint](LOCAL_TRANSLATION_CHECKPOINT_20261004.md) and its launch failures remain historical records; the completed Actions probe below updates the lexical execution status.

## Exact execution and separate attempt history

The application feature-branch base for this checkpoint is [b085881](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/b08588159059ed47c3928eaddbe6ff782ecf48da) on `codex/local-translation-presets`. The CPU experiments ran separately on `experiment/luna-actions-lexical-20261005`; their trigger commits are not the application branch tip.

| Independent Actions attempt | Source / trigger commits | Terminal result |
| --- | --- | --- |
| [First: 37266603727](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37266603727) | [b9ec9e9](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/b9ec9e9cdac848f180cef6fa10aed219a09b4bb0) / [57690a7](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/57690a7473208b692364e93eb4bd855b6c9cd629) | Setup failure; retained category `operation_failed`; exact cause unknown |
| [Second: 37275192309](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37275192309) | [64df92d](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/64df92dfa7cd1d688f921ad546a60a2433770235) / [2bf3da8](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/2bf3da881b74023ed46750e982991c9423a3bf15) | Setup rejected SudachiPy's legacy license-filename predicate before parsing |
| [Third: 37282785136](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37282785136) | [318a6aa](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/318a6aa383d29aed8d54e800566559ad973909ed) / [d2dd972](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/d2dd972c5242c1c81e3e04a1df2b22bffe6eac9f) | Execution completed; 48 confirmed parsing calls; lexical gate failed 14/16 |

Each run was a separately authorized push activation with GitHub run attempt 1. The third run's protocol is `luna-actions-lexical-license-20261005-v3`, using `.github/workflows/luna-lexical-license-v3.yml`. Its GitHub timestamps are 08:18:10–08:18:28 UTC; this is run lifecycle time, not parser latency. The first two setup failures are separate records, not partial lexical scores or successful reruns. Their retained parser counters are null. The second run's phase ordering shows parsing was not reached; neither later run retrospectively establishes the first failure's exact cause. Three infrastructure attempts are not three Hy optimization rounds.

The [v3 package-specific notice policy](https://github.com/yuxixi311/LunaTranslator-UI-Custom/blob/318a6aa383d29aed8d54e800566559ad973909ed/tools/local_eval/actions-lexical-license-v3/PROTOCOL.md#evidence-and-correction) replaced the generic license-like filename requirement with exact wheel/metadata identity plus versioned upstream notice provenance and retention. This fixed the reviewed setup path without changing the lexical rule, dictionary, cases or gate. Three external source notices and one supplied archive notice were retained, totaling 40,110 bytes. The receipt verifies this bounded notice policy; it is not exhaustive legal clearance for redistribution or native transitive dependencies.

## Frozen mechanism and observed decisions

The [all-occurrence rule](https://github.com/yuxixi311/LunaTranslator-UI-Custom/blob/318a6aa383d29aed8d54e800566559ad973909ed/tools/local_eval/cloud-lexical-v1/lexical_policy.py) admits a glossary entry only if every literal occurrence exactly spans a non-OOV core-dictionary token with person-name POS. It uses SudachiPy 0.6.11, SudachiDict-core 20260723 and SplitMode.C. Any partial, unknown or non-person occurrence should withhold the entire entry because the glossary applies to the whole entry, not one occurrence.

All 48 fixed calls completed: 16 exposed synthetic diagnostics and 32 previously seen regression sources. The predeclared lexical gate required all 16 diagnostic entry decisions to match.

| Diagnostic stratum | Matched / total |
| --- | ---: |
| Explicit person | 4/4 |
| Ordinary word | 3/4 |
| Mixed use of the same key | 3/4 |
| Partial word | 2/2 |
| No match | 2/2 |
| **Total; requirement 16/16** | **14/16 — FAIL** |

`LEX-O03` and `LEX-M03` both incorrectly admitted canon index 2 (`蓮`, mapped to `莲` in the [fixed canon](https://github.com/yuxixi311/LunaTranslator-UI-Custom/blob/318a6aa383d29aed8d54e800566559ad973909ed/tools/local_eval/cloud-lexical-v1/canon.json)). The ordinary-word and mixed-use negatives were therefore not reliably withheld even on this small diagnostic set. Exact spans, dictionary membership and person-name POS were insufficient to establish intended sense. The shared key is diagnostic evidence, not a justification for a word-specific exception.

Among the 32 seen sources, 12 remain matcher-active and 20 are inactive. The seen `person-01` case remains admitted. This mechanism therefore does not suppress activation in the case associated with the prior unresolved ownership interpretation. The seen `person-05` entry (`泉`) is omitted, while the plant-sense `negative-02` (`蓮`) remains admitted. These activation observations are regressions to investigate, not new translation judgments. No new Hy output exists, and these observations neither prove that a future translation would repeat the uncertainty nor resolve it. The original semantic judgments remain unchanged.

These are mechanism decisions, not 14/16 translation accuracy. All diagnostics are exposed development material; all 32 other sources are seen regressions. None can be relabeled an unseen semantic holdout. The earlier failed prompt/context trials, incomplete Google comparison and glossary-round uncertainty remain part of the record.

## Measured resources and limits

The same pinned official wheels totaled 73,904,174 compressed bytes (70.481 MiB). The extracted dictionary was 217,466,039 bytes, SHA-256 `53fa281d11eef3769712fe1c3c892117338f9892bee6daf4dad51daa5281bb6f`, matching the previously recorded Windows dictionary. This establishes dictionary byte identity, not Windows binary compatibility or performance.

| Cloud Linux parser measurement | Observed |
| --- | ---: |
| Cold initialization | 0.654967 s |
| Elapsed before writing parser output | 0.662106 s |
| Process CPU time | 0.751751 s |
| Peak process RSS | 134,476 KiB (131.324 MiB) |
| GPU use / translation-model calls | None / 0 |

The time scopes overlap and must not be summed. Phase wall times, including owned-process management, were download 0.465033 s, setup 6.178605 s, parse 0.815753 s and assessment 0.114018 s. Each phase exited zero, did not time out and recorded confirmed cleanup. The download ceiling was 100 MiB/240 s; setup, parse and assessment each had a 60 s lifecycle limit, and the parser retained its 15 s CPU/1 GiB address-space limits. No budget was increased to pass setup.

These standalone CPU observations do not measure Windows ABI behavior, game coexistence, Hy memory, translation latency or model-weight reduction. No bill or monetary charge is captured in this evidence; zero model calls does not establish a zero-cost Actions run.

## Decision and next development path

1. Retain the current Hy baseline and experimental status. Stop this unchanged lexical rule before GPU comparison; setup recovery is not grounds for promotion or another automatic run.
2. Continue only source-level analysis of the failure and possible general mechanisms. No supported low-cost replacement is ready to freeze from these results alone. The bound policy and recorded admissions imply that the existing exact-span, all-occurrence and non-OOV checks already passed the failing cases; repeating those checks cannot fix them. This is an inference from the policy and decisions, not a replay of retained raw tokens. A different candidate needs a specific, testable reason to handle ambiguous ordinary/person uses and the unresolved semantic risk. Do not add case-ID exceptions, tune individual words/aliases, rewrite outputs, switch dictionaries after inspecting answers or regrade old cases to manufacture a pass.
3. If a materially different mechanism is justified, preregister its rule, ambiguity/abstention behavior, dependency and resource costs before execution. Preserve the frozen 16/16 diagnostic gate and all seen regressions; a diagnostic pass remains necessary but insufficient for translation claims. Prepare a new independently authored semantic holdout with private criteria frozen before outputs and a new reviewed execution plan.
4. Only then consider a bounded, same-model GPU comparison under the existing quality/resource gates, masked source-fidelity review, preserved uncertainty and independent arithmetic review. A source-only proposal does not itself authorize a new run.
5. The Hy optimization series has a maximum of three rounds, a ceiling rather than a quota. The supplied-glossary round remains round one and inconclusive; this CPU probe supplies no completed second semantic optimization round. Retaining baseline and stopping is a valid outcome.

The [test plan](LOCAL_TRANSLATION_TEST_PLAN.md), remaining application/game-load acceptance and appropriate human review still apply. This checkpoint changes no provider, default, model weight, application code or popup behavior and packages no binary release.

## Audit anchors and publication scope

- Sanitized completed-run summary SHA-256: `bd098defb906d78186e705705e6fc8e36b02ea781d9d885251e7d3642d08751a`
- Bound v3 source-manifest SHA-256: `4f6e52b89adf337bfe936184de8067b779cd68301b13174ce50392193c53a45a`
- Parser-output SHA-256: `d66a850f63a3606bedb362141e2f361a1bb38bef8eb1a5590e34c866625b690b`

The retained public evidence is the bounded summary, phase lifecycle summaries, exact source pins and output hashes. Complete private phase receipts, full parser tokens and private child files were ephemeral and were not uploaded as Actions artifacts. This report excludes private semantic criteria, reviewer packets, complete fresh translation outputs, raw execution archives, machine paths, credentials, hardware identifiers and model weights. Output hashes establish identity, not public availability or independent reproduction of the omitted contents.
