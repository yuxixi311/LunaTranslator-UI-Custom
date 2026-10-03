# Three-way Japanese-to-Chinese pilot, with a conditional fourth arm

Status: preregistered; no model download, Google request or model inference has
been performed by this preparation. Preserve all earlier rejected experiments.
This is a small synthetic comparison of declared deployment policies, not an
isolated architecture comparison or a claim of general market superiority.

## Fixed arms and inputs

The first stage compares the installed Luna Google provider, existing
Hy-MT2-1.8B Q4, and Qwen3.5-2B Q4_K_M. Use exactly the same 48 Japanese source
strings and Simplified Chinese target. No glossary, context, added examples,
extra prompt sentence, output repair, retry or selection among samples.

The 24 historical cases are the first, second and last entry in each of the
eight original categories. Preserve original bytes and IDs. Original 40-case
fixture SHA-256:
`051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`.
The independently frozen 24 new sources have SHA-256
`aa2d45eb8f30c5b1832e7720f40bcabd9ac7b7c544b39ce572bc2d99ac19c24c`.
Each category has three new cases. All inputs are single-line and at most 200
Unicode characters. No real user text or personal data is used.

Data/scoring rules were separately frozen before source authoring at SHA-256
`2dd62da3bf2bd104285d620b64c159aa9c2ec28fa06c06229d35c059dbd770d8`.
The original procedural draft is retained separately; revision 2 clarifies that
all anonymous pairwise preferences are scored before mapping. The designer and
runner implementer have not inspected the new sources or private criteria.
Private criteria remain outside inference inputs and the public repository.

## Existing Google provider, without launching the application

Use the unchanged installed `translator/google.py`, raw SHA-256
`d53887fa426a9bc7fb1031b3e5fbd45f9770f045e9854a3f49ebdb5a566b7694`.
Its LF-normalized bytes and AST match the repository provider at
`d9b9754a9f3e23ecafc9e1b6776d39c5782d302a`; differences are CRLF line endings.
The provider calls `https://translate-pa.googleapis.com/v1/translateHtml`,
performs its own line splitting and HTML unescape, and uses its existing bundled
client header. Do not copy or extract that header value into new code, config,
logs or artifacts. Do not substitute `googleapi.py`, a paid service, Gemini,
a different endpoint or another client key.

Read-only inspection establishes installed network mode 1 (libcurl) and default
system-proxy policy, with no explicit user override. The test uses existing
Python 3.12 x64 to load only the installed source definitions and libcurl DLL.
It compiles the original `proxysession` class and binds the original
`requests.Session` and `proxy.getproxy`, with inert app-state dependencies. It
never launches the app or imports its broad config, games, history or caches.
System-proxy lookup occurs only through the original function when a real call
is made; proxy values are never recorded. Do not silently change to WinHTTP,
PyPI requests or a substitute HTTP implementation.

Pinned installed dependencies:

| File | SHA-256 |
| --- | --- |
| requests.py | `968bbe3c3b68a9e2591d2a2acf08019593d17d45c02a1ef9ea4cc96f8dbfdf0a` |
| network/client/libcurl/requester.py | `7fc80265f98a77879874143ff32fbdf3c2e93e716f43976a5f729ea071dd6b93` |
| network/client/libcurl/libcurl.py | `5dde51d8b387b55166bc17c2dc0474ab4890a71ae9730a31056997db68a79504` |
| myutils/proxy.py | `d6213963569443a06535e6a030571dc453fe8b02250c68dec0d312c2886cfa33` |
| myutils/commonbase.py | `887e7ec67f069da4d132a03becf8892fd76ba8e2d41fb4c72610fa515fa3229e` |
| libcurl-x64.dll, 3,155,048 bytes | `9d785e07566b4324b2d143ab598ba9082695648d478d131be0805d401ad6cdc7` |

The pure-standard-library `network/structures.py` must match LF-normalized
SHA-256 `be08de95511309de5c3be42807a41031430de3b444e0ed9a91070adaf85b4b0b`;
its actual raw hash is recorded. No installed source/DLL is included in the kit.

First run one owned, zero-network host probe, bounded to 25 seconds including
cleanup. It loads the installed backend and exercises the unchanged provider
against a fake session, binding source hashes, Python executable/version and
collector/shared-code hashes. A matching successful proof is required before
collection. This establishes component compatibility, not rendered-app or full
live-configuration verification. If isolation fails, stop and report it; do not
launch the full application or inject code into its process.

Exactly 49 Google provider calls are permitted: one fixed readiness sentence,
then 48 scored inputs. One short-lived owned worker per call, single-flight,
with actual transport starts at least two seconds apart. Each worker lifecycle
is bounded to 25 seconds, reserving seven seconds inside that limit for cleanup.
The complete Google collection has a 240-second budget including host startup,
pacing and cleanup. No collection retries or extra probes.

The original libcurl timeout tuple `(10, 10)` means a 10-second connect limit and
20-second total curl limit, not a separate read-idle limit. The outer worker
budget can stop it sooner. TLS verification stays enabled; redirects reject.
Python observers delegate to the original curl-perform and callback functions,
record successful transfer completion, and cap body/header bytes at 65,536/16,384
before the original callback copies or queues them. A parseable partial body
with a failed curl transfer is rejected. No native handle is manually freed or
modified; terminating the owned worker is the cleanup boundary.

Stop on challenge, CAPTCHA, quota/rate-limit, auth/permission failure, unexpected
response, incomplete transfer or budget expiry. Never bypass or switch routes.
Persist only synthetic IDs/text, sanitized results/status/timing and verified
hashes; no headers, proxy/config values, exception representations or arbitrary
URLs. Google observations are not remote attestation. The service's backend
model/version is undisclosed; record collection time and provider version.
Do not infer official API support, pricing or license permission from an endpoint.

## Pinned local models and generation policy

| Arm | Bytes | Revision | SHA-256 |
| --- | ---: | --- | --- |
| Hy-MT2-1.8B Q4 | 1,133,080,448 | `b27182d810fa3ceb6ed04e7c324c54e35c0d209c` | `dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699` |
| Unsloth Qwen3.5-2B Q4_K_M | 1,280,835,840 | `f6d5376be1edb4d416d56da11e5397a961aca8ae` | `aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223` |

Qwen's official base is revision `15852e8c16360a2fea060d615a32b45270f8a8fc`,
Apache-2.0. Preserve its license and template attribution. Qwen's official
7,755-byte template SHA-256 is
`273d8e0e683b885071fb17e08d71e5f2a5ddfb5309756181681de4f5a1822d80`.
The actual Q4 embedded template must match this or the verified tool-loop-only
variant `7f0e529032c25183bcd66c7f238da2d377f43be754a94e2725a58c4e16d2ed67`.
Reject an unexpected template or architecture. Explicitly load the official
text template with `--jinja --reasoning off --no-mmproj` and request
`chat_template_kwargs.enable_thinking=false`. `reasoning-format none` alone does
not disable thinking. Do not strip visible or hidden reasoning to manufacture
translation output.

Hy uses its original official template SHA-256
`b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee`.
Both user messages are the same ordinary instruction:

将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：

{source}

Each model retains its own chat template and declared sampling. Hy uses
temperature .7, top_p .6, top_k 20, repeat_penalty 1.05, min_p .05,
repeat_last_n 64. Qwen uses its official non-thinking text recommendation:
temperature 1, top_p 1, top_k 20, min_p 0, presence_penalty 2,
repeat_penalty 1. Unspecified sampler behavior remains that of the pinned runtime.
Both use seed 42, max_tokens 512, stream false and cache_prompt false, with zero
returned cached tokens required. Different policies are not an architecture-only
comparison; one sample per input does not estimate sampling variance.

## Runtime, budgets and evidence

Use only the existing verified llama.cpp b11349 runtime, full commit
`fb4b2737a808a3fb7c2117a498f43815dc9be53e`. Source support is not proof of actual
GGUF/runtime compatibility. Verify exact model, template, runtime, DLL and driver
hashes on the consumer. Inspect bounded GGUF metadata before launch.

One model resident at a time, CUDA required, no CPU fallback. Keep context 2048,
threads 2, one slot, batch/ubatch 128 and no runtime warmup. Preserve owned
loopback service and the previously approved exact-origin CORS restriction,
security-warning checks and owned-process cleanup. Require CUDA0, a positive GPU
model buffer, and complete `(block_count + 1)/(block_count + 1)` offload. GGUF
block_count already includes any NextN/MTP blocks; do not add them twice.

RAM preflight remains model bytes plus 2300 MiB; free VRAM remains model bytes
plus 1024 MiB. Keep the continuous resource guard. Never lower gates or close
unrelated applications to force a run. Model runners use an exclusive lock;
failed/unconfirmed owned-child cleanup is terminal and retains the lock.

Each local startup has a 180-second watchdog. After readiness, another
180-second budget covers all 98 template/tokenizer exchanges, one unscored
smoke, and 48 scored calls. There are 49 inputs including smoke, two probes each;
maximum 196 non-inference probes across both local arms. All probes finish
before any completion. Full applied prompts, including generation prefixes,
must be at most 384 tokens, without truncation. Actual prompt-token usage must
match the probe. Preserve exact chronological wires and incomplete evidence.

The fixed smoke for each arm is:
これは翻訳の接続確認です。

It must finish normally, be nonempty, contain Han text and no Japanese kana;
local outputs must also have no visible/hidden reasoning. Google readiness
rejects common challenge/quota markers absent from the fixed source. This is a sanity check,
not proof of Chinese-language or semantic correctness. Failure stops the scored
batch; never tune/repeat smoke or replace it with an easier sentence.

Local timing eligibility is completion inside the fixed startup/post-readiness
budgets and unchanged memory gates. No additional median/P95 cutoff is applied
in this cross-model pilot. Report latency/token distributions, startup/probe/
smoke costs, RSS and measured VRAM separately. Unknown VRAM stays null. The
previous same-model prompt experiments' 25% gates remain failed and unchanged.
Google network/provider time excludes fresh-host overhead, which is separately
reported; it is not local GPU inference speed or user-app cache performance.

## Scoring, eligibility and conditional fourth arm

Use independently masked A/B/C labels for every case. The reviewer receives
only exact source/output text, neutral instructions and private frozen criteria.
Score each output for critical fidelity, protected structure and uncertainty.
Then score all eligible anonymous pairs A/B, A/C and B/C for naturalness only
when both outputs are definite fidelity and structure passes. Freeze every score
and preference before using the separate arm key; select Google-versus-local
comparisons only after mapping. Do not identify Google to the reviewer.

Preserve source-consistent ambiguity as correct. Never count uncertain judgments
as wins, force them into pass/fail, or let style cancel a factual error. Report
eligible naturalness-pair coverage, ties and excluded uncertainty. A new definite
critical error means Google definite pass versus local definite fail.

A local arm demonstrates a bounded pilot win only with fewer definite critical
errors than Google on the new 24, zero new definite paired critical errors against
Google, no new structural failures, and more naturalness wins than losses on
jointly correct fresh pairs. Qwen must also avoid new definite critical/structural
regression against Hy on the historical 24. That historical comparison is
self-comparison for Hy and is not an independent Hy quality gate. If Google has
zero critical errors, strict superiority remains unproven; do not change the rule.

Only after a technically complete three-way comparison, if both local arms
definitely fail the gate, add Qwen3-1.7B as the user-authorized conditional fourth
arm. Do not download it in stage one. Review its own immutable model/template/
license/runtime pins before one bounded run on the same frozen inputs. Preserve
the first three outputs; never rerun baselines for favorable sampling. Report
conditional selection and reused inputs, not a new untouched validation set.

Unavailable Google, failed startup/resource/smoke checks or incomplete evidence
mean blocked comparison, not a quality loss triggering more downloads. If
uncertainty could change eligibility, adjudicate before the fourth-arm trigger.
A definite failed gate can reject an arm despite uncertainty elsewhere.

No result automatically changes production providers, prompts, defaults or
context behavior. No weight is bundled into the application. Final code and
consumer kit require independent review and exact verification before the parent
coordinates the hardware/download window. Use supported transfer routes only.

## Primary model sources

- [Official Qwen model card and sampling](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/README.md)
- [Pinned Qwen Q4 artifact](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/blob/f6d5376be1edb4d416d56da11e5397a961aca8ae/Qwen3.5-2B-Q4_K_M.gguf)
- [Official Qwen license](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/LICENSE)
- [Pinned Hy model provenance](../../LOCAL_TRANSLATION_EVAL_20261003.md)
- [Pinned runtime Qwen implementation](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/src/models/qwen35.cpp)
