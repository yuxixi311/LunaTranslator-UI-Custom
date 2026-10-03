# Bounded Hy1.8B glossary experiment

Prepared implementation only. No model execution, desktop action, download, live HTTP request, DLL loading, or real-child test was performed during preparation. Defaults are not changed. Parent must independently review and coordinate the separately authorized GPU window.

## Layout and invocation

Keep this directory beside these unchanged inputs:

- `luna-threeway-repair-zip-verification/`: reviewed resources, safety, model metadata, integrity code and official template. Import checks pin all used dependencies before loading them.
- `luna-hy-glossary-policy-work/`: glossary policy, AST production adapter, source pins and pinned production source files.
- `luna-hy-glossary-independent/canon.json`: frozen project dictionary. Source fixture may be supplied by explicit path.
- `luna-hy-glossary-design/RUNTIME_PINS.private.json`: frozen runtime/server/driver pins. Keep this and execution evidence private.

`run_hy_glossary.py` accepts --gguf, --server, --out, --historical-fixture, --fresh-fixture, --design, --nvidia-smi, --runtime-pins, --gpu-index and --restrict-cors-to-loopback. Model is fixed to hy18. Output must not exist. The shared owned-model lock prevents participating concurrent runners. A persistent experiment/design claim in the machine temporary directory prevents another invocation, including after technical failure; the runner never deletes that claim. No retry is authorized by this implementation. Its exact claim bytes are archived as run-claim.json, hash-bound to metadata and checked offline for experiment, design, source, code and run identity. Offline validation never needs the original machine temporary directory or output path.

The run verifies pins and model metadata, applies the original RAM/VRAM reserves, starts one full33/33 CUDA process, captures every raw wire response, performs130 probes before any completion, then runs one no-match smoke plus64 scored outputs. It retains the reviewed separate180-second startup and post-readiness absolute watchdogs, terminal late-budget failure, continuous resource monitoring, and owned-process cleanup. Only exact loopback CORS is enabled. Failed token bounds abort the entire preflight. Matched dictionary entries are never clipped or silently discarded.

`validate_hy_glossary.py OUTPUT --historical-fixture PATH --fresh-fixture PATH --design PATH` is offline. It rejects unexpected artifacts, missing evidence, changed code/pins, wrong runtime inventory, source/order/prompt/token tampering, incomplete cleanup, resource and absolute-budget failures. It gates latency by median(B)/median(A) and nearest-rank P95(B)/nearest-rank P95(A), both overall and for the exact same matcher-active pairs. Per-case B/A ratios are descriptive only. It and explicitly leaves semantic eligibility unknown. No-match output differences are descriptive sampling/execution variability.

## Review exports

Execution metadata includes canon, prompts, matched entries and identities; never give it to the primary reviewer. Primary masked source/output export and independently frozen source-only criteria must be prepared separately by the parent. Canonical-compliance review may only follow primary review freeze. This directory does not include a review pack or private criteria, and cannot decide semantic promotion.

## Fake verification

Run `python -m unittest -q test_hy_glossary` in this directory. Every process, socket, HTTP transport, GPU and RAM interaction in lifecycle tests is synthetic. Tests cover fixed probe/completion order, bounded prompts, pending pin refusal, exact paired metrics, no-match variability, rehashed tampering, startup/blocked calls/final-response expiry, delayed timer callback races, cleanup timing, cleanup lock retention, and successful cleanup release. They do not run a model or launch even a harmless real child.
