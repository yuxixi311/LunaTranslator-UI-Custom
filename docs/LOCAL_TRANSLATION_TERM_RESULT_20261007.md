# Deterministic terminology-lock result — 2026-10-07

## Decision

**No demonstrated incremental advantage; no promotion.** The optional Hy-MT2-1.8B Q4 baseline, existing providers, defaults and UI v1.0.1 remain unchanged. The candidate demonstrated zero faithful canonical fixes in zero families and caused one structural rejection where the baseline was faithful. The run also remains operationally incomplete. Passing observed timing statistics does not override either finding.

The single [CPU run 37571991218](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37571991218), attempt 1, ended with GitHub conclusion `failure`. It used source A [`882b7066bb8e0a569b60e5768ce949c14f4822c9`](https://github.com/yuxixi311/LunaTranslator-UI-Custom/tree/882b7066bb8e0a569b60e5768ce949c14f4822c9/tools/local_eval/actions-term-cpu-v1) and trigger B [`3591e399452f33f51aa6ddf528d9480ba984d7a2`](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/3591e399452f33f51aa6ddf528d9480ba984d7a2). This checkpoint summarizes retained evidence; it is not a successful-runtime certificate or product activation.

## Frozen question and scope

The deterministic policy used explicit fictional application-wide terminology declarations, protected eligible supplied terms during generation, and restored their declared forms under the existing output guard. Six safe declarations and one globally unsafe homograph were frozen, with the same ordered declaration projection for every record in scope. The mechanism tested canonical consistency, not general word-sense inference. A fully canonical baseline supplies no incremental benefit to recover.

The 88 paired sources comprised 69 historical/seen abstentions and 19 fresh cases. The fresh population contained 12 active carriers and seven abstaining controls. The fresh cases cover a narrow vocative/work-order domain; they do not establish general Japanese–Chinese translation quality. Only fresh19 received the new semantic review reported below, not all 88 pairs.

Full-template token preflight completed before generation. Baseline counts ranged from 29 to 81 tokens; active candidate deltas ranged from −3 to 0. All 12 carriers were active, with no token-budget abstentions. The frozen 384-token prompt ceiling and added-token ceiling `min(16, floor(0.40 × baseline_tokens))` were unchanged.

## Fresh19 semantic result

Two independent label-blind model-assisted reviewers agreed on all 38 fresh arm-level fidelity labels. Aggregate labels were:

| Fresh19 outcome | Baseline | Candidate |
| --- | ---: | ---: |
| Faithful | 13 | 13 |
| Material error | 3 | 3 |
| Unresolved | 3 | 2 |
| Structural rejection | 0 | 1 |
| Total | 19 | 19 |

For the 16 canonical-applicable cases, baseline was canonical in 16/16; candidate was canonical in 15/16 with one structural rejection. Three cases per arm were not applicable. Canonical correctness is separate from whole-row fidelity: correct terminology alone does not make the surrounding translation faithful.

There were **zero demonstrated faithful canonical fixes and zero benefiting families**. One faithful baseline became a candidate structural rejection. No new delivered-text material-error row was established; that narrower observation does not erase the structural regression or turn unresolved rows into passes.

These are model-assisted judgments, with no professional human validation. Execution records were public and arm-identified, so label blinding does not guarantee treatment concealment. Reviewer agreement is not an independent human accuracy benchmark. The narrow fresh19 population is now seen evaluation material and must not be reused as an untouched holdout or tuned to claim a recovered benefit.

## Retention, accounting and observed costs

All 176 raw arm outputs were retained; 173 final texts passed the mechanical guard. Three mechanical rejections comprise the same historical row in both arms and one fresh candidate row. These are guard outcomes, not semantic labels. No arm was unobserved, and rejected rows remained in all applicable numeric populations.

All 378 scheduled HTTP requests were recorded as consumed and validated; their inventory and accounting were independently checked: one health request, one model-list request, 176 preflight counts, 176 completions and 24 recurring counts. Generation usage was 8,531 prompt tokens plus 2,732 completion tokens (11,263 total; zero cached). Count-only input tokens totaled 10,216: 8,531 preflight plus 1,685 recurring. Independent checks reproduced 264 preflight request hashes, 176 output/receipt/timing bindings and 176 deterministic restoration/guard results without new model or tokenizer calls. Five payloads matched their manifest hashes; all six final JSON files matched the corresponding retained log records.

| Fixed paired timing population | Pairs | Median candidate/baseline | Nearest-rank P95 |
| --- | ---: | ---: | ---: |
| All88 | 88 | 0.9997090142429031 | 1.0685673364300496 |
| Fresh19 | 19 | 0.9895422209918384 | 1.106254468810627 |
| Active all | 12 | 0.9800824218891644 | 1.106254468810627 |
| Active fresh | 12 | 0.9800824218891644 | 1.106254468810627 |

Every observed median/P95 was below the frozen 1.25 ceiling. Helper PREPARE had 88 samples, median 996,954.5 ns and P95 1,248,760 ns, below its 5,000,000 ns P95 threshold. The first observed PREPARE sample is not assumed to be a cold start. These CPU observations establish neither full protocol success nor Windows/GPU performance.

## Operational incompleteness

The terminal record remains `incomplete` / `OPERATIONAL_FAILURE`, with whole-attempt `cleanup_confirmed=false` and `protocol_complete=false`. The supervisor snapshot also reports both flags false, and `CONTROLLER_RESULT_REJECTED` is retained. Successful protocol reconciliation, helper lifecycle and helper resource metrics were not published. Helper resource/lifecycle success therefore remains unknown.

Individual child receipts report confirmed cleanup, including helper exit 0 and server exit −9 after a graceful-shutdown wait timeout. Those receipts do not override the aggregate false flags. The reported `preflight/OWNER_FAILURE` stage is stale as a failure locator after measured work resumes; the server shutdown timeout does not establish an inference deadline failure. The exact failing condition is unknown. No orphan process, clean whole-attempt exit, or helper memory violation is inferred.

Runner peak RSS was 36,409,344 bytes and server peak RSS was 2,417,573,888 bytes; runner RSS is not helper RSS. Retained-output and accounting checks do not supply missing full private wire evidence or successful protocol reconciliation. Preserve the original unsuccessful terminal records rather than rewriting them as a pass.

## Evidence and rollback lineage

- Executed kit manifest SHA-256: `505eb9a67fe86634168934c403fddf7321fc1da4169e498288e3782e23e24de4`
- Frozen source-plan SHA-256: `dd6ecaa158ebbd8582f52823b89ae196caf52fd017f4418c43874fb44a982322`
- Final public evidence manifest SHA-256: `479fe163cf23c50443e43b0b2204ee116429f95d7e522a9f1addd42e68906877`
- Output payload SHA-256: `474608e2f3ff2b39a10de28c934210d15405d96f03a5378ef70e3ec5f2193af2`
- Independent binding/arithmetic audit SHA-256: `7b445e44e6fac45323a7c3f221995687998dcc78158ab129cf539e0d6b14dc3a`

The documentation baseline is commit `0b44ae8b21d97cf840b0e8d3746ba1e5aa65ae2f`; the candidate and its trigger remain preserved at A and B above. No candidate is enabled by this documentation change. Retaining the unchanged optional baseline is the rollback decision. Preserve the [short-example rejection](LOCAL_TRANSLATION_USAGE_RESULT_20261006.md), [sense-prefix failure](LOCAL_TRANSLATION_SENSE_RESULT_20261006.md), [NER result](LOCAL_TRANSLATION_NER_RESULT_20261005.md), [POS lexical result](LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md), [inconclusive glossary round](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md), and [earlier checkpoint](LOCAL_TRANSLATION_CHECKPOINT_20261004.md), including failures and uncertainty. This summary contains no private grading criteria, full fresh source/output text or raw host logs.

## Bounded next decision

The examined sequential methods are exhausted: supplied glossary remains inconclusive; grounded speaker/context work lacks a defensible source-provenance prerequisite; microexamples failed token/coverage feasibility; sense-prefix and GiNZA-derived POS/NER work demonstrated no general benefit; term lock demonstrated no advantage. These findings do not justify forcing another inference round, relaxing gates or overfitting seen cases.

Keep baseline, or prepare a feasibility proposal for curated, licensed Japanese–Chinese parallel training data and a small LoRA. Such a proposal must address usable rights and provenance, contamination-resistant held-out evaluation, data quality, cost and hardware measurements before execution. No GPU run, model/data download or training is released by this checkpoint. No training has been performed as a next step, and fit within 12 GB is unmeasured. A separate synthetic reporting repair may improve precise failure and helper-lifecycle records while retaining every historical failed result.
