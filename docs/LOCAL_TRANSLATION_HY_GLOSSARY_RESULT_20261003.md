# Hy1.8B supplied-name glossary pilot — 2026-10-03

**The pilot is technically complete but semantically inconclusive; do not promote it.** Two definite source-fact errors were resolved in distinct fresh named-participant cases, meeting the minimum resolution count. One previously definite-pass case became uncertain, so the frozen zero-new-critical safety condition cannot be established. Cost gates passed. No defaults or model weights changed.

This is round one of a bounded Hy1.8B-only optimization investigation. It tests the existing supplied-glossary feature, not training, a larger model or a general prompt rewrite. The preceding failed instruction/context experiments and incomplete Google comparison remain unchanged.

## Frozen setup and review

The executable source checkpoint is `371c5bac2ff755d4ccb362f7097a48b84eefbc0b`; the [preregistration](../tools/local_eval/hy-glossary-v1/consumer/luna-hy-glossary-design/PREREGISTRATION.md) has SHA-256 `492967489479a4756e7df5161a0d952385261094ce7e6e289289d8e8307da2a9`. A uses ordinary translation instructions; B adds the existing glossary block when the actual escaped-literal matcher finds an entry. Both consume the original Japanese source. Six fixed fictional names, sampling, runtime, model and source order were frozen. No-match prompts are byte-identical.

There are eight seen regressions and 24 independently authored fresh cases: six ordinary-word person names, six explicit named participants, four other named entities, four matched common-word/subword negatives and four no-match grammar/format controls. Fresh criteria were frozen before outputs. The designer saw the public source inputs after the candidate/fixture freeze; this did not change the candidate. Private criteria were withheld from prompt design.

One independent model-assisted reviewer first judged source-only fidelity, protected structure, target facts, contamination and eligible naturalness under randomized per-case labels. Primary ratings were frozen before the same reviewer saw canonical-name requirements. Canonical compliance was then frozen before identity mapping. A source-permitted variant never becomes a semantic error merely because the canon prefers a spelling. Canonical names can reveal treatment; labels do not guarantee treatment blinding. This is not human bilingual validation.

## Semantic observations

Counts are **pass / definite fail / uncertain**, with no uncertainty forced into pass or fail.

| Population | Baseline A fidelity | Glossary B fidelity |
|---|---:|---:|
| All 32 | 24 / 5 / 3 | 25 / 3 / 4 |
| Seen regressions 8 | 4 / 3 / 1 | 4 / 3 / 1 |
| Fresh 24 | 20 / 2 / 2 | 21 / 0 / 3 |
| Explicit named participants 6 | 4 / 2 / 0 | 6 / 0 / 0 |
| Ordinary-word person names 6 | 5 / 0 / 1 | 4 / 0 / 2 |
| Matched negative controls 4 | 4 / 0 / 0 | 4 / 0 / 0 |
| Other named entities 4 | 3 / 0 / 1 | 3 / 0 / 1 |
| No-match controls 4 | 4 / 0 / 0 | 4 / 0 / 0 |

- Two baseline target-fact **and** fidelity failures became definite passes, across two distinct entities and scenarios. They concern a source-stated object/event meaning and an explanation's audience in named-participant sentences. They are not evidence that the model newly learned names, or that all role/causative errors are fixed.
- There are zero observed new definite fidelity errors and zero new definite structure errors. Each arm retains one historical structure failure; both have 24/24 fresh structure passes. Historical definite fidelity failures remain three per arm.
- One fresh target changes from baseline definite pass to candidate uncertain because an ownership/forgotten-property interpretation is unresolved. This could affect the new-critical gate and independently blocks promotion. Three other cases are uncertain in both arms; preserve all four, without selecting a favorable regrading.
- Both arms pass spelling compliance on all 12 applicable names; 20 cases are not applicable. Canon compliance therefore offers no measured improvement and cannot substitute for semantic fidelity.
- Negative controls have zero definite or uncertain candidate contamination. The one definite contamination judgment in each arm is the same historical case. All four matched negatives pass fidelity and structure, but baseline is preferred for naturalness on three, with one tie. These are style judgments, not invented semantic failures; they also caution against unnecessary glossary activation.
- Naturalness is eligible on 22/32 pairs: baseline preferred 3, glossary 4, ties 15; 10 pairs are excluded. Fresh-only: 19 eligible, baseline 3, glossary 4, ties 12. Historical: 3 eligible ties, 5 excluded. Do not infer broad superiority from these small counts.
- All 16 no-match pairs have identical output bytes. They demonstrate repeat consistency in this run, not glossary benefit.

## Technical evidence and measured cost

The frozen consumer's 101 payload hashes matched. Windows passed 10 policy tests and 22 harness tests; independent cloud audits reran the archived validator and verified archive, consumer, request/response, claim and result-manifest bindings. The single run completed 130 preflight probes, one smoke and 64 scored outputs, with balanced 16 AB / 16 BA pairs. Full 33/33 CUDA offload preceded scored inference. Resource and deadline gates did not trigger; owned cleanup was confirmed and the one-shot claim is retained. Scored applied prompts used at most 62 tokens (limit 384), glossary increments at most 12 (limit 64), and at most two entries (limit four). Median prompt tokens were A 46 / B 52; median output tokens were 16 in each arm. These are standalone runner results, not rendered application acceptance.

| Same paired population | A median / P95 | B median / P95 | B/A median / P95 |
|---|---:|---:|---:|
| All 32 | 92.55 / 136.28 ms | 93.85 / 126.18 ms | 1.0141 / 0.9259 |
| Matcher-active 16 | 94.51 / 117.60 ms | 95.17 / 129.20 ms | 1.0069 / 1.0987 |

P95 uses nearest-rank arm quantiles on the same paired subset; all four ratios pass the <=1.25 limit. Per-case ratio quantiles are not the gate. Startup took 1.220 seconds, probes 2.043 seconds, and the complete post-readiness phase 8.798 seconds. Peak sampled process RSS was 1,676,537,856 bytes (about 1.56 GiB); per-PID VRAM was unmeasured. Cache reuse was disabled in requests and reported cached-token counts were checked, but cold-cache behavior was not independently established. No memory reduction or general hardware promise follows.

## Decision and next work

The >=2 distinct target-resolution condition passes; observed definite-error, structure and negative-contamination counts meet their numerical limits; the latency gate passes. **Material semantic uncertainty prevents a pass.** The protocol's homograph-control caution is preserved without retroactively redefining style preferences as definite semantic regressions. Keep this result inconclusive and experimental.

The useful signal is narrow: supplied terminology can change source-fact preservation at little measured request cost, but blind substring activation also changes ordinary words and does not guarantee participant interpretation. A possible next factor is source-derived lexical/name activation before the same glossary block. It must first demonstrate, on cloud-side tests, how it suppresses inappropriate compound/common-word activations while retaining explicit-person matches. Token boundaries or part-of-speech labels do not establish intended meaning; same-spelling names and ordinary nouns remain ambiguous, and this text-only test says nothing about homophones in speech.

Do not launch a second run merely to fill a three-round allowance. Before another GPU trial, freeze an implementable single activation rule, its dependency/RSS/startup cost, ambiguity/abstention behavior and new independently authored validation. All earlier cases, including the newly uncertain case with its unchanged source-only criteria, are retained as seen regressions; none is excluded to make a new candidate pass. Prefer existing lightweight rules first. Any tokenizer/dictionary dependency needs a separate license, download-size, platform and measured-memory review before installation. A filter cannot be presumed to resolve this trial's ownership ambiguity, so new semantic gates remain necessary. No case-ID exceptions, tuned aliases, output rewriting, repeated seeds, larger weights or training follow from this checkpoint. No additional model run is part of this report.

## Audit anchors

- Evidence ZIP SHA-256: `8b631b6057e89986ef1e9ee928908dbbbb2e5ab386139927962dedc5b8451bea`
- Result manifest SHA-256: `ba069d48f10b9895b5200fbc4d86b735bd658cf5784c8d8fc71e6c2dba790332`
- Primary frozen ratings SHA-256: `0cd40d77d999f5991f17c5450a07c5683b9bd98e0b20119d53939497a2c77ef4`
- Canonical frozen ratings SHA-256: `d74f39e06507a8ccd1eb91338b2db3cd8c45124ec3112f72295a0fef1fc0ac18`

Raw evidence, complete fresh outputs, private criteria, machine paths and hardware identifiers remain private. No Google-win claim, binary release or default promotion is established.
