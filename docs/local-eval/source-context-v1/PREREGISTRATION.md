# Source-context experiment design (not executed)

Purpose: test whether bounded original source context improves grounded referent
resolution with the existing 1.8B Q4 model. No runtime default changes. This is
not a generic instruction rewrite, and it cannot establish overall translation
accuracy or comparison with online providers.

## Evidence and scope

The preserved v1 experiment failed timing, structure and semantic regression
gates. V2 passes timing/structure but has two unambiguous historical semantic
regressions and no demonstrated fresh-set improvement. Explicit source roles
are already sufficient in several persistent causative/passive errors; context
is not assumed to repair that capability limitation. Proper-name/common-word
ambiguity may instead need user-approved terminology, which is a separate test.

Official source, checked 2026-10-03:
https://huggingface.co/tencent/Hy-MT2-1.8B#hy-mt2-translation-task-instruction-examples-chinese-english-comparison
The model card supplies background-information and terminology prompt examples.
The app's existing conversation history can contain previous model translations;
this test uses preceding original Japanese source only and does not characterize
that existing app path.

## Fixed treatment

Both arms use this exact literal user message, with no system message:

〖背景信息〗
{background}
请结合背景信息将以下文本翻译为简体中文。
〖待翻译文本〗
{source}

The empty arm uses an empty background string. The context arm supplies the
previous one or two original Japanese source sentences. There is no glossary,
model-generated translation/history, v2 extra sentence, explanation request,
postprocessing, response repair or retry. Identical targets under paired
alternative contexts distinguish following context from a fixed memorized guess.

This isolates available context within one prompt layout. Neither arm is the
production default prompt, so it cannot directly justify replacing that default.

## Bounds fixed before independent cases

- 12 mini-scene families, each with two alternate antecedent backgrounds and the
  same target: 24 input pairs. Eight source-sufficient controls: 32 pairs total,
  64 inference requests, balanced 16 empty-first and 16 context-first
- Context: one or two natural preceding source sentences, at most 128 Unicode
  characters and 128 tokens measured by the pinned tokenizer. Target: at most
  128 Unicode characters. Full rendered prompt: at most 384 measured tokens,
  including the applied chat-template and generation-prefix tokens
- Reject over-limit fixtures before inference; do not truncate or silently
  alter them. Record exact tokenization requests/evidence. No source answer,
  Chinese translation, explicit role annotation or command in background text
- Existing pinned Q4 weights/runtime/template, sampling, context 2048, one slot,
  threads2, batch/ubatch128, max output512, cache disabled, no runtime warmup
- Unchanged weights+2300 MiB RAM and weights+1024 MiB VRAM gates; continuous
  guard, loopback/CORS/security proof and owned-process cleanup
- Independent startup watchdog180 seconds; post-readiness watchdog180 seconds
  starts before the first tokenizer/template probe and includes every probe and
  inference request; no unbounded pre-inference phase. Validate all inputs with
  pinned runtime /apply-template and /tokenize before the first model completion,
  retaining the exact probe requests/responses. Maximum 192 probes and64 model
  requests. Tokenizer round trips are reported separately from model latency;
  stop and preserve incomplete output on expiry, never retry remaining cases
- Report median/P95 latency and prompt/completion tokens, sampled whole-process
  RSS, available RAM and VRAM if measurable. Keep each latency increase <=25%
  against matched empty-context arm across all 32 pairs. Also report family and
  control subgroup metrics separately without using them to override that gate.
  No claim of per-arm peak memory attribution

## Independent fixture and ground truth

A separate fixture author receives this design but no raw prior outputs or
private prior ratings. Freeze sources and binary per-fact criteria separately.
The prompt designer does not inspect new cases/criteria before the design and
harness are fixed. Use fresh vocabulary/scenes; do not paraphrase previous errors.

Each family must contain natural discourse, not an instruction revealing an
answer. Only the context changes between its alternatives. The criteria identify
which role/referent is supplied by context, what the target alone entails, and
which readings must remain open without context. Controls provide irrelevant
but compatible prior sentences while the target already supplies required facts.

## Scoring and gates

Freeze input-aware ratings before revealing the separate arm key or prompts.
Each presentation label includes its exact available background (empty or
populated), target and output, so the reviewer can assess support fairly. Never
give an empty-context output credit for facts available only to its paired arm.
Although A/B mappings and prompt wording remain hidden, background availability
can reveal treatment: this is input-aware masked-label review, not fully blinded
treatment review. Disclose that limitation. Preserve ambiguity as uncertainty.
Separate factual correctness from contextual information gain:

1. A faithful unspecified/ambiguous translation with no context is correct. Do
   not penalize it for failing to guess an antecedent absent from its inputs
2. A context-arm output may resolve a referent only when supported by supplied
   source context. Unsupported specific names, roles, gender or number are errors
3. Contextual resolution is a separate binary observation, not an accuracy bonus
   manufactured by relabeling the correct empty-context output as wrong. Natural
   explicit wording or an unambiguous contextual expression may demonstrate it;
   unresolved wording earns no gain but remains correct when faithful
4. Count a family as robustly resolved only if both alternate contexts yield
   their respective supported resolutions, preserve every source fact and add
   no unsupported content. Identical vague outputs do not establish resolution
5. Controls must preserve target meaning and avoid importing irrelevant context;
   additional background sentences in the translation count as added content

Eligibility for further validation requires no new definite critical semantic
error, no new structural failure, no unsupported resolution, and robust added
resolution in at least four of the twelve families. For each qualifying family,
BOTH duplicate empty-context outputs must be correct and unresolved, and BOTH
context outputs must be correct and resolve their respective antecedents. No
required judgment may be uncertain. Count each family once; never choose the
better duplicate or drop an unfavorable alternative. Report all families, including ineligible/uncertain
ones, without replacing them. Uncertainty is not a win. Report corrected wrong
guesses separately; do not use them to mask new errors. Resource/cost gates also
must pass. This is a bounded utility threshold, not statistical proof of general
improvement. No automatic production promotion follows any outcome.

## Delivery and stopping condition

Review this design, then freeze fresh cases/criteria, implement and review one
small test-only harness, and deliver one final verified source kit. Coordinate
one desktop window through the parent. Preserve evidence and input-aware masked-label scoring.
Do not create repeated minor transfer artifacts or bypass Library restrictions.
After the run, stop at the preregistered decision; no variant search or tuning on
new cases within this experiment.
