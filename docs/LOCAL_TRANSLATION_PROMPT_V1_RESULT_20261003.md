# Existing 1.8B prompt v1: reject candidate (2026-10-03)

## Decision

**Keep the attempted variant and its evidence, but do not promote it.** The
candidate fails its preregistered latency and structural-regression gates.
Production prompt/defaults are unchanged. This result does not establish better
semantic accuracy for either arm, superiority over online translation, or
Windows application/Qt acceptance. An independent model-assisted semantic review
was frozen before arm mapping; its mixed findings and unresolved cases are
reported separately below. It is not bilingual-human validation.

This was the exact standalone test kit at
[`385d49d`](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/385d49dede90728d13dccf6f94413222af3d24c2),
using the existing pinned Hy-MT2 1.8B Q4 model and llama.cpp b11349 runtime.
The [original preregistration](local-eval/prompt-experiment-v1/PREREGISTRATION.md)
and its historic commit preserve the exact candidate, sampling, case split and
decision rules. No larger model, new quantization or paid API was used.

## Verified execution and evidence

- 134 Windows headless tests pass; captured tests, runner and summarizer exit 0
- 64 paired cases / 128 requests complete: 40 historical regression cases and
  24 independently frozen synthetic cases; 32 baseline-first and 32 candidate-first
- Private evidence ZIP: 585,896 bytes, SHA-256
  `a41b0c4931c2d150e42311b8b6135bc02115f70a0b241bab77b11d55454585bf`
- All 91 outer manifest entries and 46 kit payload hashes verify; 45 repository
  payloads match the previously verified published source. The other payload is
  the independently frozen source-only fixture; its private criteria were not
  included in inference inputs
- All 128 exact locked requests, 256 raw request/response body hashes, JSON
  equality, case/arm order, zero cached-token counts, stop completions and
  nonempty output checks independently pass
- Runtime records match the prior strict run: 34 loaded runtime-file hashes and
  the 55-file pinned runtime inventory. The same pinned model/driver hash records
  are preserved. These are archived execution records, not a fresh disk scan
- Trace logs establish CUDA0 selection and 33/33 layer offload before the first
  input; the security-warning gate passes with the same exact-loopback CORS
  restriction. No memory guard or 600-second inference watchdog expiry is recorded
- The archived post-run observation reports no owned server/process or test-port
  listener. This is a point-in-time observation, not a current machine claim
- The 64-pair blind sheet preserves exact source/output text and unfilled scores.
  Only that sheet and neutral review instructions are passed to the semantic
  reviewer, with separately held frozen criteria. Arm mapping was withheld until
  ratings were frozen, then applied without changing any rating

The desktop audit reports 53 successful integrity checks. The subsequent cloud
audit independently recomputes the central source, wire, runtime-record, metric,
paired-transition and blind-sheet checks above. Integrity is not translation
quality. No private path, machine name, GPU UUID, raw log, weights or binary is
published in this report.

## Matched timing and structure

Times are per-request wall latency from this single matched run. P95 uses the
nearest-rank rule. Do not pool these values with earlier Linux/Windows runs or
interpret cross-run differences as an optimization.

| Split | Baseline median / P95 | Candidate median / P95 | Baseline / candidate structure failures | Newly failing pairs |
| --- | --- | --- | --- | ---: |
| All 64 | 86.491 / 136.149 ms | 158.153 / 222.899 ms | 2 / 38 | 36 |
| Historical 40 | 76.534 / 101.709 ms | 113.059 / 184.573 ms | 1 / 19 | 18 |
| Fresh 24 | 103.075 / 148.794 ms | 188.114 / 228.260 ms | 1 / 19 | 18 |

Overall candidate median latency increases **82.855%** and P95 **63.716%**, both
above the preregistered 25% limit. All 36 newly failing structural pairs were
previously passing in the matched baseline; no baseline structural failure is
resolved. The candidate has 37 newline-count failures and 38 failures under the
general integrity check. One additional failure is not a newline mismatch.

Median prompt tokens rise from 40 to 57; median completion tokens rise from 12
to 29. Longer generated output accompanies the slowdown; these counts do not
prove a single causal explanation for every latency difference.

Whole-process sampled RSS peaks at 1,767,247,872 bytes (about 1.646 GiB), with
286 samples. Minimum sampled available RAM is 2,949,775,360 bytes. Per-process
VRAM remains **unmeasured** (null, zero samples), not zero usage. Model-layer
offload evidence is separate from peak VRAM measurement. Readiness with warm
file cache and runtime warmup disabled is 1.1246 seconds. These are neither
per-arm memory comparisons nor deployment minimum-resource guarantees.

## Observed instruction-boundary failure pattern

The v1 addition appears **after** the official instruction's final colon, before
the blank line and Japanese source. Several outputs paraphrase the added
Chinese instruction as an unwanted preface, followed by extra newlines and the
translation. For example, historical `negation-03` begins with a Chinese
instruction to preserve negation, conditions and relationships before its actual
translation. Historical `placeholders-01` returns only a paraphrase of the added
instruction, omitting the source's placeholders and sentence.

This supports an **instruction/source boundary hypothesis**, not a proven model
internals diagnosis. No output has been stripped, repaired, retried or rescored
to hide the failure. The complete failed attempt remains available for audit.
Semantic ratings may explain other behavior but cannot rescue this candidate's
already-failed mechanical gates.

## Frozen blinded semantic review, then deterministic arm mapping

The independent reviewer read only the shuffled source/output sheet, neutral
instructions and separately frozen per-fact criteria. Ratings were frozen with
SHA-256 `7da37961ebe9c660b64e4b1ed619f44912ea916667d527c4b505833bc44c34c8`
before the recorded arm key was applied. Sources, outputs and ratings were not
edited during mapping. This is one model-assisted review of synthetic text,
not expert gold adjudication or a general accuracy estimate.

| Split | Baseline critical fail / pass / uncertain | Candidate critical fail / pass / uncertain | New definite failures | Resolved definite failures |
| --- | --- | --- | ---: | ---: |
| Historical 40 | 6 / 32 / 2 | 17 / 23 / 0 | 11 | 0 |
| Fresh 24 | 6 / 17 / 1 | 4 / 19 / 1 | 0 | 2 |

“New” means baseline definite pass to candidate definite fail; “resolved” means
baseline definite fail to candidate definite pass. Two historical baseline-
uncertain/candidate-pass pairs are **not** counted as resolved failures.
Pairwise semantic preferences are 11 baseline, 2 candidate, 47 ties and
4 unresolved. The two fresh improvements do not cancel eleven new historical
critical failures, the structural regressions or the cost-gate failures.

Four cases retain clause-level or source-interpretation uncertainty: two
historical and two fresh. One fresh case is already a definite failure from an
independent clear error despite another criterion remaining uncertain. Thus
“cases with any uncertainty” and the table's whole-output uncertain verdicts
are different counts. No null criterion received half credit or a forced pass;
further adjudication remains separate and cannot change the mechanical rejection.

## Next bounded question, not a deployment change

Keep the same model, runtime, sampling, resource gates and exact extra sentence.
Test only its placement: put the sentence **before** the unchanged official
translation instruction so that the final colon and blank line directly precede
only the source. This follows the boundary shape of the official model-card
examples; it is not a claim about undisclosed training data or a generic chat
template substitution.

The existing 64 cases now form a regression set for further iterations. They
must not be relabeled untouched held-out data. Any new accuracy claim needs new
independently frozen validation sources and private criteria, blinded ratings,
and unchanged failure/cost gates. No v2 inference is reported here; execution
requires a separately coordinated resource window. No automatic default change,
larger weights, output stripping or silent online fallback is authorized by this
result.
