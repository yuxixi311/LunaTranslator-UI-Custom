# Existing 1.8B source-context test: limited utility, reject promotion (2026-10-03)

## Decision

**Do not promote this context treatment. Stop unguided prompt iteration on the
current evidence.** Two of twelve paired-context families show robust additional
referent resolution, below the preregistered minimum of four. There is one new
definite critical error in a source-sufficient control, unwanted background
content, two new mechanical structure failures, and a 31.332% P95 latency increase
against the 25% limit. No output stripping, gate relaxation or additional run was
used to turn this into a pass.

The exact test-only source is
[`634bbae`](https://github.com/yuxixi311/LunaTranslator-UI-Custom/commit/634bbaec9a1d90e95498e60278d7de0f66542e06).
The [frozen design](local-eval/source-context-v1/PREREGISTRATION.md) remains
byte-for-byte unchanged, including its original not-executed status at freezing.
This report records the later execution. Both arms use the same official
background-information prompt layout, with empty versus preceding original
Japanese source context. Neither is the production default prompt. This test
cannot directly justify changing the application's existing conversation-history
behavior, which may contain earlier model translations.

## Verified execution and mechanical result

- 154 Windows headless tests pass; captured runner and summarizer exit 0
- 32 pairs / 64 completions, balanced 16 empty-first and 16 context-first;
  12 families with two alternate contexts each, plus eight source-sufficient controls
- All 192 non-inference template/tokenizer probes finish before completions,
  inside the same 180-second post-readiness watchdog
- Private evidence ZIP: 659,321 bytes, SHA-256
  `11ea884b5c2cc14e60ec5e387dfeb7805ed78847128805f9d957ad78aabea9dc`
- 105 archive entries include a manifest covering 104 payload entries. All
  payload hashes verify; 56 source-kit payloads match the original staging
  (55 repository files and one source-only fixture)
- All 512 raw request/response body hashes validate: 128 for completions and
  384 for probes. Exact requests, case order, applied template, token counts,
  nonempty stop completions and zero cached-token evidence independently verify
- Maximum measured context is 29 tokens, and full templated prompt is 73 tokens,
  within the fixed 128/384 limits. Probe time is 0.7850 seconds, reported separately
  from model-request latency
- The pinned model/driver records, 34 loaded runtime hashes and 55-file runtime
  inventory match previously verified records. CUDA0/33-layer offload precedes
  inference. Resource/security gates pass; no watchdog expiry is recorded
- The recorded post-run check finds no owned process or test-port listener.
  This is an archived observation, not a claim about the machine's current state

The desktop audit records 61 passing integrity checks. Independent cloud audit
revalidates the central source, wire, runtime-record, metric, token-bound and
review-input bindings. This establishes evidence consistency, not translation
quality or remote attestation. No private paths, raw logs, private criteria,
complete fresh text, weights or binaries are published here.

| Split | Empty-context median / P95 | Populated-context median / P95 | Mechanical structure failures empty / populated |
| --- | --- | --- | --- |
| All 32 | 71.839 / 106.631 ms | 79.678 / 140.041 ms | 0 / 2 |
| Family alternatives 24 | 69.070 / 106.631 ms | 79.678 / 140.041 ms | 0 / 1 |
| Controls 8 | 78.765 / 84.579 ms | 78.206 / 129.807 ms | 0 / 1 |

Overall median latency increases 10.911%; nearest-rank P95 increases 31.332%.
The overall population is the preregistered cost gate; subgroup values cannot
override it. The two new mechanical failures are newline/structure violations,
one in a family alternative and one control. Neither is a harmless line-ending
normalization: both outputs emit translated background content before the target.

Median prompt tokens increase from 42 to 61.5, completion tokens from 11.5 to 13.
Whole-process sampled RSS peaks at 1,741,750,272 bytes (about 1.622 GiB), with 122
samples; minimum sampled available RAM is 2,674,704,384 bytes. Per-process VRAM
is unmeasured (null/zero samples), not zero usage. Warm-file-cache readiness with
runtime warmup disabled is 1.1356 seconds. These do not establish per-arm memory
cost or universal deployment minimums.

## Input-aware masked-label semantic review

The independent model-assisted reviewer saw each output's actual available
source context, source target, shuffled presentation label and frozen criteria.
It did not receive prompts, arm keys, timing/mechanical results or prior ratings.
Context availability can reveal treatment, so this is **not fully treatment-blind**.
Ratings froze at SHA-256
`584c9506bf75e51b7eee3e8e7fd08362128240a044a517142e8fb38c208b8253`
before the separate key was applied. All 64 exact output/context bindings were
checked and ratings preserved without edits. This is not bilingual-human validation.

A faithful unspecified empty-context translation is correct. Added contextual
resolution is evaluated separately; absent information is never treated as a
baseline mistranslation. Null judgments stay uncertain.

| Split | Empty-context critical fail / pass / uncertain | Populated-context critical fail / pass / uncertain | New definite critical errors / resolved |
| --- | --- | --- | --- |
| Family alternatives 24 | 4 / 12 / 8 | 4 / 12 / 8 | 0 / 0 |
| Controls 8 | 0 / 8 / 0 | 1 / 7 / 0 | 1 / 0 |
| All 32 | 4 / 20 / 8 | 5 / 19 / 8 | 1 / 0 |

Only two families meet every robust-utility requirement: both empty-context
outputs correct and unresolved, both alternate-context outputs correct and
supported/resolved, no contamination and no required uncertainty. Two of twelve
is below the fixed threshold of four; it is a small-sample utility observation,
not an accuracy percentage. The qualifying families resolve an omitted object
and an offered-seat recipient across both alternative contexts. Five individual
context outputs receive narrow
resolution credit, but the additional output also contains contamination and
unsupported gender, so it cannot qualify its family.

Two controls contain unwanted context import or target loss; one introduces the
new definite critical error. A separate family alternative chooses the wrong
fruit despite its supplied context. Uncertainty in its empty-context interpretation
means this is not counted as a definite paired regression, but it still violates
the no-unsupported-resolution requirement.

The review marks five populated-context scope/structure failures versus none
for the empty arm. These include extra background prose or target loss without
newlines; they are **different from the mechanical check's two failures**.
Definite contamination is 0 versus 6, with six uncertain outputs in each arm.
Some outputs retain a critical-correctness judgment while a different required
criterion is uncertain: there are 10 empty-arm and 8 populated-arm outputs with
any required uncertainty. No uncertainty was converted into an improvement.

## What to do with the three preserved attempts

The [first prompt attempt](LOCAL_TRANSLATION_PROMPT_V1_RESULT_20261003.md)
failed instruction boundaries, cost and semantic regression gates. The
[placement correction](LOCAL_TRANSLATION_PROMPT_V2_RESULT_20261003.md) passed
cost/structure but introduced critical semantic regressions. This bounded
source-context test demonstrates a little genuine referent-resolution utility,
alongside contamination and failed gates. The samples, prompts and reviews differ;
do not pool them into a single accuracy estimate or claim cross-run causality.

Keep the experimental local option explicitly limited and optional. These tests
do not justify promoting any candidate, making automatic context the default,
or promising online-translator quality. Existing model weights remain optional
first-use downloads rather than bundled application weight, and this work has
not made the model itself smaller.

The next useful choices are product/data work rather than another broad prompt:

- A user-confirmed, application-scoped glossary could address specific name/term
  ambiguity. Test such a concrete need independently; terminology replacement
  cannot be assumed to repair passive/causative role reversals, and neither a
  glossary benefit nor a new glossary implementation is established here
- Meaningful model adaptation would require a lawful curated parallel corpus,
  held-out human bilingual evaluation, training/compute budget and deployment
  verification. Fine-tuning has not been performed and its cost or benefit is
  not established
- Preserve these failures and uncertainties for diagnosis. All 32 new inputs now
  count as historical evidence. No fourth generic prompt, larger model, new
  inference or automatic product promotion is part of this checkpoint
