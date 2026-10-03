# Portable Windows evaluation kit (not a quality result)

This extends the frozen 2026-10-03 standalone model experiment to Windows.
**Windows execution, CUDA loading, actual 4070 Ti memory/latency and model quality
are still UNRUN.** Linux-hosted unit tests and platform mocks do not prove them.
Application providers, defaults, saved configuration and historical result files
are unchanged. This kit is not an app release or Windows/Qt acceptance test.

## Freeze and safety boundaries

- Exactly the existing 40 synthetic Japanese cases, SHA-256
  `051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`.
  Never rewrite cases to improve scores. Existing diagnostic/holdout labels remain;
  these now-public cases are not an unseen benchmark.
- The pinned official Hy-MT2 1.8B and 7B templates remain different. The prompt,
  sampling, seed, context, batching, two threads and output limit remain frozen.
  See [source and hash catalog](LOCAL_TRANSLATION_EVAL_20261003.md).
- Python standard library only. Use an already available Python 3.10+ interpreter.
  Nothing downloads, installs drivers/packages, changes persistent settings,
  creates services, changes firewall rules, or touches the Luna configuration.
- Run sequentially in a new scratch folder, with no game/OCR load. No elevation.
  Never stop unrelated processes to obtain headroom. Stop if the machine becomes
  unresponsive, driver/runtime support is missing, or a security warning appears.
- Physical RAM must cover the full model file plus **2300 MiB**, even for CUDA.
  Windows uses `GlobalMemoryStatusEx.ullAvailPhys`; Linux uses `/proc/MemAvailable`.
  This is a conservative policy, not a measured universal minimum. Linux cgroup
  limits are not detected: independently confirm any container/job limits.
- CUDA also requires measured free VRAM covering model bytes plus **1024 MiB**.
  CUDA does not bypass the RAM gate. There is no automatic CPU fallback.
- Every ~50 ms, a separate RAM monitor attempts to read available physical RAM.
  Below **768 MiB**, or if that measurement fails, it stops only its owned child,
  waits 3 seconds, then kills that same child if necessary and waits 3 seconds.
  This is best-effort monitoring, not a hard OS resource limit. A blocked OS API
  or sudden memory spike may outrun it; preflight headroom remains mandatory.
- Working-set/RSS and per-PID VRAM are separate. RSS is sampled at ~50 ms; VRAM
  queries at ~1 second, with a 3-second command timeout. WDDM often reports N/A:
  `peak_process_vram_bytes: null` means unmeasured, never zero. Whole-GPU free
  memory is only a preflight observation, never reported as process VRAM.

## Prepare on the authorized Windows computer

1. Use a fresh isolated checkout of the reviewed feature commit. Preserve LF
   bytes, for example `git clone -c core.autocrlf=false --branch codex/local-translation-presets https://github.com/yuxixi311/LunaTranslator-UI-Custom.git Luna-eval-kit`,
   then check out the exact reviewed commit supplied with the handoff. Do not use
   a moving branch as the identity of the run. An existing CRLF conversion will
   fail the fixture/template hash gate; do not bypass or change the expected hash.
2. Obtain **only** the official pinned model files and verify their size/SHA-256
   against the existing catalog. Do not download every quantization unnecessarily.
   For the primary comparison use `1.8b` Q4_K_M and `7b` Q4_K_M.
3. Use the [official llama.cpp b11349 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11349).
   Choose its Windows x64 CPU build, or CUDA 12 build with its matching portable
   CUDA 12.4 DLL archive if the already-installed driver supports it. Verify
   release provenance, archive hashes/attestations and keep their evidence before
   executing. Extract the complete package and required DLLs into the isolated
   runtime directory; never mix CPU/CUDA versions. No driver update is authorized
   by this kit. If compatibility cannot be established, stop and report it.
   The runner checks the pinned build string and records executable/DLL hashes;
   neither is a signature or upstream archive authenticity check.
4. For CUDA, locate the **existing NVIDIA-driver-provided** `nvidia-smi.exe` and
   verify its Authenticode signature and NVIDIA publisher, e.g.
   `Get-AuthenticodeSignature -LiteralPath 'C:\Windows\System32\nvidia-smi.exe'`.
   Require `Status: Valid` and the expected NVIDIA signer; the actual installed
   path may differ. Never substitute a download or a same-named PATH executable.
   Pass its verified absolute path explicitly. CPU runs do not require this tool.
5. Record hardware, OS, driver, Python, git commit and `git status --short`, plus
   runtime archive URLs/hashes and signature check results in a separate local
   handoff record. Do not place usernames, private paths/text or unrelated process
   listings in a public report. The raw run metadata intentionally includes local
   paths; share only a reviewed/sanitized copy if publishing is later authorized.

## Run from repository root in PowerShell

Replace paths below with the verified existing files. Each output directory must
not exist. Quote paths with spaces/Unicode. Use the same backend, selected GPU,
exact runtime directory and kit revision for both candidates.

```powershell
python -m unittest discover -s src/tests -p 'test_local*.py' -v

# CUDA: NVIDIA tools and driver must already be present and verified.
$server = 'D:\Luna test\runtime\llama-server.exe'
$smi = 'C:\Windows\System32\nvidia-smi.exe'
python tools/local_eval/run.py --model 1.8b --gguf 'D:\Luna test\models\Hy-MT2-1.8B-Q4_K_M.gguf' --server $server --backend cuda --nvidia-smi $smi --gpu-index 0 --out 'D:\Luna test\results\18-cuda'
# Only after the first process is fully closed and resource gates are satisfied:
python tools/local_eval/run.py --model 7b --gguf 'D:\Luna test\models\Hy-MT2-7B-Q4_K_M.gguf' --server $server --backend cuda --nvidia-smi $smi --gpu-index 0 --out 'D:\Luna test\results\7-cuda'
python tools/local_eval/blind_review.py 'D:\Luna test\results\18-cuda' 'D:\Luna test\results\7-cuda' 'D:\Luna test\review'
```

For CPU, use the official CPU executable and `--backend cpu` (the default), omitting
`--nvidia-smi`/`--gpu-index`. Do not pair a CPU run with a CUDA run. CUDA selects the
NVIDIA index via its measured UUID in the child-only `CUDA_VISIBLE_DEVICES`, then
requests `CUDA0` and 99 offloaded layers. Review `server.log` to confirm the actual
backend/offload; requested CUDA flags alone are not proof of GPU execution. No
persistent environment variables are set.

## Evidence and stop conditions

Each run keeps `metadata.json`, `results.jsonl`, exact request/response body bytes
(base64 plus SHA-256) in `wire.jsonl`, `server.log`, and a file-hash `manifest.json`.
A failed/partial run stays incomplete; do not edit it into a pass. Errors before
output creation simply stop without a completed record. Runtime binaries and
model weights are never committed or published by this kit. A file manifest
catches accidental changes, not adversarial rewriting or a trusted signature.

The review tool checks raw-wire hashes/content, file hashes, complete 40-case
ordering, matching frozen requests, stop finish reasons and matching execution
configuration, resource helper, runtime executable/DLLs, backend and GPU identity.
The historical schema-1 Linux pair remains readable without rewriting its original
harness hash; new schema-2 runs cannot be paired with it.

Give only `review.json` to independent bilingual reviewers; keep `key.json` hidden
until scoring is locked. Preserve diagnostic and holdout scores separately. The
previous automatic Q4/Q8 review is not a new human quality result. Report actual
latency/RSS/VRAM only after successful hardware execution, and keep missing VRAM
explicit. No claim of a quality improvement, Windows acceptance, offline-game
integration, or a release follows from merely preparing this kit.

## Cloud validation before handoff

All 104 local-translation regression tests passed (85 existing plus 19 new platform/safety tests). Independent code review, Python compilation and `git diff --check` passed. These checks used Linux and mocks; no Windows model process or GPU quality run was performed.
