# Existing 1.8B boundary-placement experiment v2

Execution update: the frozen kit completed on Windows. Mechanical gates passed,
but the blind semantic review found new critical regressions; do not promote.
See the [audited result](../../LOCAL_TRANSLATION_PROMPT_V2_RESULT_20261003.md).
The original preregistration below is preserved as historical text.

Original status: preregistered, NOT EXECUTED. The candidate wording/placement was fixed
before the new validation worker generated cases; the prompt designer has not
inspected new validation sources or private criteria.

## Preserve v1, change one placement decision

The [v1 result](../../LOCAL_TRANSLATION_PROMPT_V1_RESULT_20261003.md) is rejected
and preserved, including its eleven new historical critical failures, two fresh
semantic improvements, four unresolved cases, 36 new structural failures and
failed latency gates. Do not strip its prefaces or rewrite those results.

Use exactly the same extra sentence as v1:

准确保留原文中的否定、条件和人物关系，不补充原文没有的信息。

Move that sentence to a separate line **before** the unchanged official general
translation instruction. The candidate is exactly:

准确保留原文中的否定、条件和人物关系，不补充原文没有的信息。
将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：

{source text}

The baseline remains the exact official instruction and source without the
extra sentence. The final colon and blank line immediately precede only source
text. No examples, additional wording, system prompt, glossary, context,
postprocessing, output stripping, repair, sampling change, or model change.

This tests v2 against the unchanged baseline in one matched run. It does not
replay the failed v1 arm and cannot by itself establish within-run causal
attribution of v1→v2 differences. Placement is the only intended v1→v2 prompt
change. The boundary hypothesis follows the published official model-card
instruction shape; no assertion about undisclosed training data is made.

## Data, blinding and unchanged decision gates

- Experiment ID: `hymt18-boundary-placement-v2`
- Old 40 fixture SHA256:
  `051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`
- v1's formerly fresh 24 source-only fixture SHA256:
  `c518015f981bb177eca1a9db0806e134c01d8b9951e6c88c5a78d0eb4e6abefc`
- Both groups are now **64 regression cases**, not untouched held-out evidence
- New independent 24 source-only fixture SHA256:
  `45f2d9617a70a234b4f9e635afa47c60701e52266a4ed23eded0d836239e8d52`
  Its separate frozen binary criteria remain private and never enter model
  requests or the public source kit
- 88 paired cases / 176 requests, balanced 44 baseline-first and 44 candidate-first
- Blind semantic ratings must freeze before the arm key is revealed; report new
  24 and old 64 separately, preserving any uncertain criterion as null
- Binary per-fact criteria govern acceptance. Auxiliary 0/1/2 wording scores are
  descriptive and cannot override a failed required fact
- To merit further validation: fewer critical errors on the new 24, no new
  definite critical error in a previously correct paired case, no new structural
  failure, and no unacceptable historical regression. Tie/uncertainty is not a win
- Median and nearest-rank P95 latency increases must each stay <=25%; unchanged
  resource gates must pass. This does not constitute general quality acceptance
  or superiority over Google, and never promotes a production default automatically

## Pinned runtime, resources and evidence

Reuse only existing official Hy-MT2 1.8B Q4 bytes and llama.cpp b11349 / fb4b2737a.
Model SHA256 `dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699`,
size 1,133,080,448 bytes. Official 1.8B template SHA256
`b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee`.
Independently compare actual existing runtime files/driver tool with their
previously verified records; a self-consistent evidence manifest is not attestation.

Sampling unchanged: temperature .7, top_p .6, top_k 20, repeat_penalty 1.05,
min_p .05, repeat_last_n 64, seed 42, max_tokens 512, stream false,
cache_prompt false and returned cached_tokens=0. Context 2048, one slot,
threads 2, batch/ubatch 128, no runtime warmup. No inference retry.

Same process-owned loopback service and previously approved exact-origin CORS
restriction, RAM gate (weights + 2300 MiB), CUDA VRAM gate (weights + 1024 MiB),
continuous resource guard, security-warning gate, positive CUDA log proof and
owned-process cleanup. Independent inference watchdog remains 600 seconds;
startup has its own independent owned-child watchdog at 180 seconds, and cleanup
can add a few seconds. Readiness polling/socket timeouts remain secondary checks;
a slowly arriving HTTP response cannot keep the owned server alive beyond that
startup stop deadline.
Do not lower gates, close unrelated user applications, alter drivers/security,
download bigger weights or change production application settings to force a run.

Record complete raw requests/responses, wire hashes, source/runtime hashes,
logs, completion/cache evidence and positive clocks. Preserve incomplete runs.
General integrity failures, newline failures, historical narrow-token failures
and legacy-only flags are reported separately. Legacy-only flags must be reviewed,
not mislabeled general-integrity failures or silently erased.
Report matched per-arm token/latency distributions and paired differences.
RAM/VRAM peaks describe the whole process, not an attributed per-arm memory effect.

## Coordinated execution only

The parent coordinates the next desktop resource window; this document does not
start a model. Use supported source transfer only. Private criteria and arm key
must remain separate from the reviewer's source/output sheet.

python tools/local_eval/run_prompt_experiment_v2.py --gguf VERIFIED_MODEL --server VERIFIED_SERVER --out NEW_RESULTS --fresh-fixture sources-v2.json --previous-fixture sources-v1.json --backend cuda --nvidia-smi VERIFIED_DRIVER_TOOL --restrict-cors-to-loopback

After successful completion and owned-process cleanup:

python tools/local_eval/summarize_prompt_experiment_v2.py NEW_RESULTS --fresh-fixture sources-v2.json --previous-fixture sources-v1.json

Return complete evidence to the parent. Give the independent reviewer only the
blind text sheet, neutral instructions and separately frozen private criteria.
Retain the arm key until ratings are frozen. No further candidate is selected
by tuning these new cases within this experiment.
