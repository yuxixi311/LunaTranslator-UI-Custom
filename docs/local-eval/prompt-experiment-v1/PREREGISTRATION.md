# Existing 1.8B minimal-prompt experiment v1

Status: preregistered, NOT EXECUTED. Frozen before the prompt designer inspected
any independent fresh source cases or private semantic criteria.

Candidate wording is immutable for this run:

准确保留原文中的否定、条件和人物关系，不补充原文没有的信息。

Insert this one sentence on a new line after the existing general Chinese
instruction, before its blank line and source text. No examples, glossary,
context history, source-specific rules, model changes, or automatic repairs.
Baseline remains the exact existing official instruction. Neither arm updates
the production provider or its saved configuration.

## Frozen inputs and execution

- Experiment ID: `hymt18-minimal-semantics-v1`
- Existing 40 sources: SHA256 `051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`;
  label all 40 REGRESSION because the old holdout has already been inspected
- Independent new 24 source-only cases: SHA256
  `c518015f981bb177eca1a9db0806e134c01d8b9951e6c88c5a78d0eb4e6abefc`;
  freeze/reference criteria stay separately with the independent reviewer,
  never part of the runner, public repo, model requests, or inference kit
- Q4 model: 1,133,080,448 bytes; SHA256
  `dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699`
- Runtime: existing official llama.cpp b11349 / fb4b2737a; verify existing
  runtime file hashes against the previously verified desktop artifact
- Official 1.8B template SHA256:
  `b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee`
- Sampling unchanged: temperature .7, top_p .6, top_k 20, repeat_penalty 1.05,
  min_p .05, repeat_last_n 64, seed 42, max_tokens 512; stream false,
  cache_prompt false; require returned cached_tokens=0
- Context 2048, one slot, threads 2, batch/ubatch 128; same process-owned,
  loopback-only service and previously approved process-only CORS restriction
- Inference phase has an independent 600-second owned-process stop watchdog;
  socket timeout is also the smaller of 180 seconds and remaining budget. Startup
  retains its existing 180-second gate. Cleanup may add a few seconds. Timeout
  preserves incomplete evidence and stops only the owned server
- 64 paired cases / 128 requests. Alternate baseline/candidate pair order by
  case index, balancing 32 AB and 32 BA pairs. One process, no model reload per
  arm. No output-dependent changes, retries, or early promotion.
- Original RAM preflight (weights + 2300 MiB) and CUDA VRAM reserve
  (weights + 1024 MiB), continuous memory monitor, security-warning gate,
  explicit device/offload evidence, and owned-process cleanup unchanged
- No model downloads, new binaries, credentials, live app changes, driver
  changes, other processes terminated, or online translation comparison

## Predeclared decision rule

Report old regression and fresh results separately. Format checks include the
reviewed general integrity checker for tags/attributes and numbered/sequential
printf. The historical basic-token metric is retained under its narrow name and
cannot substitute for the stronger check. Blind A/B semantic review
against independent criteria before revealing the arm key. Critical errors
include wrong negation/condition scope, wrong participant or role, reversed
causative/passive meaning, or unsupported factual additions. Score each output
0=critical error, 1=meaning preserved with material wording issue, 2=meaning
preserved and usable; record uncertainty, don't force a pass. These overall
scores are descriptive only. The separately frozen binary per-fact criteria
govern semantic acceptance; a favorable wording score cannot override a failed
required fact. Keep those criteria unchanged. The evaluator is
model-authored, not qualified bilingual-human validation.

Candidate is only worth further validation if it has fewer critical semantic
errors on fresh cases, no new critical error in any previously correct paired
case, no new structural failure, and no unacceptable regression on the old set.
Tie/inconclusive means no promotion. A finite synthetic pass cannot establish
quality above Google or general deployment suitability.

Report per-arm p50/p95 wall latency and server prompt/completion token counts,
paired differences and overall RAM/VRAM peaks. Predeclared cost guard for further
consideration: median and p95 latency increases each <=25%, with existing
resource gates satisfied. This small one-process run cannot attribute RAM peaks
to an individual arm or establish deployment RAM minima. Even a favorable result
only supports another independent validation step, never automatic default
promotion. No second candidate is chosen from these results in this run.

## Desktop execution window

Run only after the other authorized short experiment ends and the parent
confirms the timing/resource window. Reuse the previously verified model,
llama-server.exe and nvidia-smi.exe paths. Keep the application and other model
processes stopped by their own authorized owners, never kill by name.

Example (substitute verified paths and a NEW output directory):

python tools/local_eval/run_prompt_experiment.py --gguf MODEL.gguf --server llama-server.exe --out NEW_RESULTS --fresh-fixture sources.json --backend cuda --nvidia-smi nvidia-smi.exe --restrict-cors-to-loopback

If a gate fails, stop and preserve the incomplete metadata; do not lower the
reserve or force a fallback. After successful cleanup:

python tools/local_eval/summarize_prompt_experiment.py NEW_RESULTS --fresh-fixture sources.json

Return raw results, wire evidence, server log, metadata, manifest, summary and
blind sheet to the parent. Keep the mapping file separate from the reviewer
until their ratings are frozen. Do not publish private runtime paths/logs.
