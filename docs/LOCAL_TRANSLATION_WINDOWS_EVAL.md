# Portable Windows evaluation kit (not a quality result)

This extends the frozen 2026-10-03 standalone model experiment to Windows.
**A first Windows 1.8B Q4 run exists, but is not a safety-passed GPU baseline:**
its log contains a security warning and lacks actual CUDA offload evidence.
See the [sanitized audit](LOCAL_TRANSLATION_WINDOWS_BASELINE_AUDIT_20261003.md).
The corrected runner and its GPU proof gate still require a new Windows retest.
Linux-hosted unit tests and platform mocks do not prove hardware execution.
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

Before executing either command, obtain explicit owner approval for a process-only
browser-origin restriction to this server's exact loopback port. The required
`--restrict-cors-to-loopback` option expresses that approved choice; without it,
the runner refuses before executing even the runtime version probe. It passes
`--cors-origins http://127.0.0.1:<port>` to the child. This limits browser response
reads; it is **not authentication or server-side Origin rejection**. Local clients
remain unauthenticated. It creates no credentials and changes no persistent setting.
Do not pass the flag on the owner's behalf without that approval.

```powershell
python -m unittest discover -s src/tests -p 'test_local*.py' -v

# CUDA: NVIDIA tools and driver must already be present and verified.
$server = 'D:\Luna test\runtime\llama-server.exe'
$smi = 'C:\Windows\System32\nvidia-smi.exe'
python tools/local_eval/run.py --restrict-cors-to-loopback --model 1.8b --gguf 'D:\Luna test\models\Hy-MT2-1.8B-Q4_K_M.gguf' --server $server --backend cuda --nvidia-smi $smi --gpu-index 0 --out 'D:\Luna test\results\18-cuda'
# Only after the first process is fully closed and resource gates are satisfied:
python tools/local_eval/run.py --restrict-cors-to-loopback --model 7b --gguf 'D:\Luna test\models\Hy-MT2-7B-Q4_K_M.gguf' --server $server --backend cuda --nvidia-smi $smi --gpu-index 0 --out 'D:\Luna test\results\7-cuda'
python tools/local_eval/blind_review.py 'D:\Luna test\results\18-cuda' 'D:\Luna test\results\7-cuda' 'D:\Luna test\review'
```

For CPU, use the official CPU executable and `--backend cpu` (the default), omitting
`--nvidia-smi`/`--gpu-index`. Do not pair a CPU run with a CUDA run. CUDA selects the
NVIDIA index via its measured UUID in the child-only `CUDA_VISIBLE_DEVICES`, then
requests `CUDA0` and 99 offloaded layers. No persistent environment variables are
set. The runner now places `-lv 4 --log-colors off --no-log-jsonl` before device
parsing: b11349 maps native GGML INFO to TRACE level 4, hidden by its default 3.
Before any fixture request, the fresh log must show all of:
- `using device CUDA0`
- `offloaded N/M layers to GPU`, with 0 < N <= M
- `CUDA0 model buffer size = X MiB`, with X > 0

`CUDA_Host`, device enumeration, requested flags and low latency are not proof.
This demonstrates startup placement, not every operation on GPU; only N=M proves
full layer offload. Missing evidence fails closed and stops only the owned child.
A detected `security:` log message blocks the first or next fixture request.
Checks run during readiness, before each fixture and at the end; they do not
continuously interrupt an already in-flight request.
Do not suppress warnings or add a skip switch to obtain a result.

`--no-warmup` disables the runtime's default empty inference before readiness, so
the evidence check precedes model inference. No replacement warmup is sent.
New timings use `perf_counter`, recording its implementation/resolution in metadata.
Warm-file-cache load time excludes runtime warmup and the first fixture can include
first-inference costs. Do not pool or directly attribute latency changes against the
old default-warmup/15.625-ms-clock baseline to GPU or model changes.

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

The original kit passed 104 Linux-hosted tests, but one lifecycle test then failed
on Windows because its fake process lacked a fake valid job guard. The corrected
helper supplies a synthetic guard; explicit regressions still reject missing,
invalid, and throwing guards. The production guard is unchanged. New runner tests
cover missing CORS opt-in, security warnings before/after the first fixture, missing
or false CUDA proof, command ordering, and cleanup. See the sanitized audit for
final cloud validation; these checks do not replace the required Windows retest.
