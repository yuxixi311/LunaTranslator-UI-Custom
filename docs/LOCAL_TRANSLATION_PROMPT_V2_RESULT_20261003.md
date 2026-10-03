# Existing 1.8B prompt v2: preserve experiment, reject promotion (2026-10-03)

## Decision

**V2 passes the matched timing and structural-regression checks but fails the
semantic eligibility gate.** The frozen model-assisted review identifies two
new unambiguous critical errors among 64 regression pairs. The 24 new pairs do
not show fewer critical errors. Keep the experiment and evidence; do not change
the production prompt or defaults. This is not bilingual-human validation, a
general accuracy percentage, or evidence of superiority over Google.

The exact source kit is
[`d201119`](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/d20111986b2b59e8eb25733b657f610241b0bdb3).
The [preregistration](local-eval/prompt-experiment-v2/PREREGISTRATION.md) fixes
one placement change: the same extra sentence from v1 precedes the unchanged
official translation instruction. Model, template, sampling and resource gates
remain pinned. The [failed v1 attempt](LOCAL_TRANSLATION_PROMPT_V1_RESULT_20261003.md)
is preserved. V1 and v2 ran separately; this is not a within-run causal comparison
between those candidates.

## Verified execution

- 143 captured Windows headless tests pass; runner and summarizer exit 0
- 88 pairs / 176 requests: 64 historical regression and 24 independently frozen
  synthetic cases, with 44 baseline-first and 44 candidate-first pairs
- Private evidence archive: 692,253 bytes, SHA-256
  `798d28a0899dfdeba45ed0eda3a715d855f8449fabc77f42bc7a1d16bd244724`
- All 98 outer manifest entries and 52 kit payload hashes verify; all payloads
  match the original cloud staging, including 50 previously verified repository
  files and the two source-only fixtures
- All 176 locked requests and 352 raw body hashes validate, with exact JSON,
  case/arm order, zero cached tokens, nonempty outputs and stop completions
- 34 loaded runtime hashes and the 55-file inventory match previously verified
  runtime records. Model and driver hash records also match
- CUDA0 and 33/33 offload precede inference; security/resource gates pass and
  neither the 180-second startup nor 600-second inference watchdog expires
- Recorded cleanup reports no owned process or test-port listener. This is an
  archived observation, not a current machine inspection

The archived desktop audit records 54 passing integrity checks. Cloud audit
independently verifies the central byte, wire, configuration, runtime-record,
metric and blind-sheet checks. These are integrity checks, not quality scores.
Private machine identifiers, raw outputs/logs, criteria, weights and binaries
are not published here.

## Matched cost and structure

Per-request wall latency uses nearest-rank P95. All values describe one matched
run, without retries, output stripping or repair.

| Split | Baseline median / P95 | Candidate median / P95 | Structure failures baseline / candidate | New / resolved failures |
| --- | --- | --- | --- | --- |
| All 88 | 85.899 / 138.087 ms | 87.229 / 139.563 ms | 3 / 2 | 0 / 1 |
| Regression 64 | 77.617 / 123.342 ms | 75.046 / 134.871 ms | 2 / 1 | 0 / 1 |
| New 24 | 122.814 / 146.982 ms | 126.070 / 160.046 ms | 1 / 1 | 0 / 0 |

Overall median increases 1.548% and P95 1.069%, within the 25% gate. Two
structural failures persist. Both arms have zero newline-count failures and
zero legacy-only token flags. Median prompt tokens are 44 versus 61; completion
tokens are 14 versus 14.5. Better format preservation does not establish correct
meaning: the single resolved identifier failure also contains a new semantic
error in the candidate.

Whole-process RSS peaks at 1,814,151,168 bytes (about 1.690 GiB), with 314 samples.
Minimum sampled available RAM is 3,626,385,408 bytes. Per-process VRAM is
unmeasured (null, zero samples), not zero usage. Warm-file-cache readiness with
runtime warmup disabled is 1.1257 seconds. These are not per-arm memory estimates
or minimum deployment requirements.

## Frozen blind semantic review

The independent reviewer received only the shuffled 88-pair source/output
sheet, neutral instructions and separately held frozen criteria. It did not
receive prompts, arm identities, prior ratings or runtime logs. Ratings froze
at SHA-256 `028dfdbcd0e0dcc3de8b361f8c22bb27e88440c63013bf46a72a51059af48d0c`
before deterministic arm mapping. Exact source/output matches were checked;
ratings and uncertainty flags were preserved without edits.

The following are whole-output critical-error flags from one model-assisted
review. A flag can be provisional when the reviewer also marked uncertainty.
They are not expert gold labels or population accuracy estimates.

| Split | Critical flags baseline / candidate | Flags without uncertainty baseline / candidate | New unambiguous critical errors | Resolved unambiguous critical errors |
| --- | --- | --- | --- | --- |
| Regression 64 | 13 / 12 | 9 / 8 | 2 | 3 |
| New 24 | 4 / 5 | 2 / 2 | 0 | 0 |

For these conservative transition counts, neither output in the pair may have
an uncertainty flag. A case-level uncertainty flag can concern only one clause;
therefore excluding that case does not prove its other errors are harmless.

The two unambiguous regressions are historical `placeholders-05` and
`fresh-passive-02` (the latter's name comes from v1; it is now regression data).
The former preserves the player identifier but changes the addressed player
into another missing object; the latter reverses who makes whom wait.
Three unambiguous historical resolutions are `negation-04`, `fresh-passive-01`
and `fresh-conditions-04`. Aggregate improvement in the historical flag count
cannot cancel new critical errors under the preregistered gate.

Raw flagged transitions also include one uncertain historical regression and
one uncertain historical resolution. The sole newly flagged fresh regression
is uncertain, and there are no fresh resolutions. Across both arms, 12 regression
pairs and five fresh pairs contain some uncertainty. Preserve those judgments
for separate bilingual adjudication rather than treating them as wins or
forcing pass/fail decisions. Reviewer structural flags separately agree with
the mechanical 3-to-2 result.

## What this attempt establishes

The v2 run avoids the widespread extra-newline behavior seen in v1, while its
matched baseline comparison stays within the timing gate. Separate run timing
cannot prove that placement alone caused the difference. The current evidence
still rejects promotion: preserving formatting and moving instruction text do
not reliably preserve participant roles or source meaning.

All 88 cases are now historical evidence for later experiments. Preserve v1/v2
artifacts and the unresolved judgments. A next attempt needs a separately frozen
bounded plan and independent validation; do not tune on these 24 cases and call
them untouched. No larger weights or additional model inference is part of this
checkpoint.
