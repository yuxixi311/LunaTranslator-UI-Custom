# Windows 1.8B Q4 evidence audits (2026-10-03)

The first-run audit below remains historical. A separately identified strict retest
now verifies CUDA placement and the runner security gate; see the [strict retest](#strict-retest-of-398afc2).
Translation-quality acceptance is still not established.

## Historical first baseline

**Not a safety-passed GPU baseline, a semantic pass, or a model quality upgrade.**
The first Windows run completed 40 synthetic requests, but retained a startup
security warning and did not capture CUDA placement proof. Do not resume with the
old command, publish its raw evidence, or relabel the run as verified CUDA.

## Evidence identity and integrity

The original private ZIP is 240,986 bytes, SHA-256
`b089041f70f8977c872b9de608a965d5314c133f1d439995c5a89284c0b3f050`.
Its 73 manifest entries all match recorded bytes/SHA-256; no duplicates. The only
unlisted file is the manifest itself. The archive's identity is not the identity
of this sanitized summary or any future sanitized derivative. Original logs and
metadata contain private computer names/paths and are not published here.

All 40 wire request/response pairs pass strict base64 decoding, byte SHA-256 and
parsed-object equality against results. IDs/order, split labels, sources and
recomputed formatting match the frozen fixture. All finish reasons are `stop` and
reported cached prompt tokens are zero. Completion is not semantic correctness.

## Output comparison, not a blinded quality verdict

Compare exact Unicode content without normalization against the frozen Linux
1.8B Q4 results. Requests match after removing only the ephemeral model alias.
30/40 output texts match exactly; 10 differ (5/16 diagnostic, 5/24 holdout):
negation-01, negation-03, negation-04, relationships-02, boundaries-01,
omissions-01, omissions-03, omissions-05, placeholders-05, pragmatics-02.

Both runs preserve the checked token/tag multiset in 39/40 cases and newline
counts in 40/40. Windows placeholders-05 changes `{player}` into `{玩家}`; the
reference instead corrupts identifier/markup. Neither passes this format case.
These narrow checks do not prove full structure or semantics.

Source-based preliminary error flags include:
- negation-04: Windows renders “never again” as “twice” and adds a male recipient
- passive-02: both shift the manager-forces-speaker agency
- passive-05: both lose/reverse who kept whom waiting
- relationships-05: both turn the recipient's name into an adverb and corrupt roles
- boundaries-02: both lose the precise under-ten/ten-and-up threshold
- pragmatics-03: both change “did not ask” into “do not want”

These are non-blind automated diagnostics, not independent bilingual-human
adjudication, accuracy estimates, significance claims or model win rates. The
public synthetic fixture's expected facts have not been bilingual-human validated.
No inputs, prompt, sampling parameters, seed or historical output files were tuned.

## Timing and GPU limits

The old Windows run reports median 0.078125 s and nearest-rank P95 0.09375 s,
warm-file-cache readiness 1.125 s, and sampled process RSS 1,642,360,832 bytes
(about 1.53 GiB). Its clock resolution is 15.625 ms. These are one run's local
observations, not stable precision estimates, end-user latency or speedup claims.
Per-PID VRAM is null, with zero samples: unmeasured, not zero.

The command requested CUDA0 and 99 GPU layers, but default verbosity was 3.
Pinned b11349 maps native GGML INFO messages to TRACE=4, so CUDA/model placement
messages are filtered before output. This explains why neither ordinary redirection
nor the complete retained log provides proof; it does not retroactively prove
GPU execution or CPU fallback. Label this run **CUDA requested, offload unverified**.

Upstream pinned sources:
- [GGML INFO-to-TRACE mapping](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/common/log.cpp)
- [Actual selected device](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/src/llama.cpp#L303-L309)
- [Actual offload and buffer logs](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/src/llama-model.cpp#L1911-L1932)

## Safety and corrected candidate

The retained startup warning says no API key is set and CORS allows all origins.
Loopback binding does not negate it. The old runner reached inference despite the
written stop condition: this is a failed safety gate, not a reason to skip it.
The archived post-run check reports the owned process and listener closed; it does
not certify current machine state.

The corrected runner refuses launch without an explicit owner-approved
`--restrict-cors-to-loopback` opt-in. This configures only the child server's exact
loopback browser origin; local clients remain unauthenticated. It adds no keys or
persistent settings. Runtime execution of this new policy requires owner approval.
[Exact CORS behavior](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/tools/server/server-http.cpp#L330-L360),
[warning condition](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/tools/server/server.cpp#L331-L333).

It captures trace logs before device parsing, disables default startup warmup,
checks security warnings before every fixture, and requires selected CUDA0,
positive offloaded layers and a positive CUDA0 model buffer before the first
fixture. CUDA_Host is not GPU model-buffer proof. Unknown/missing evidence stops
only its owned process; no bypass exists. Timings now use a recorded high-resolution
performance clock. No-warmup changes first-request/readiness timing definitions;
keep new results separate from the old baseline.

The Windows unit failure was a fake-process fixture missing its fake job guard.
The helper now supplies one, with explicit missing/invalid/throwing-guard regressions;
production lifecycle protection remains unchanged. See the [retest instructions](LOCAL_TRANSLATION_WINDOWS_EVAL.md).

Cloud validation: 111 synthetic local-translation tests pass (104 baseline plus
7 new regressions), Python compilation and `git diff --check` pass, and independent
code review found no blocking defect. Review verified the pinned upstream log forms,
logging levels/order, no-warmup flag and CORS semantics. Windows retest, verified CUDA
placement, per-PID VRAM measurement, app/Qt integration and quality acceptance
remain unverified. No real model or paid API was executed in this cloud audit.


## Strict retest of 398afc2

This is a separate owner-approved run of exact kit commit
`398afc2be55da05815c0757029e9d2e031f94d31`, not a rewrite of the first baseline.
The private strict evidence ZIP is 457,070 bytes, SHA-256
`a7ae607d3b9242aef3111307dcff4e075c201f9de038f295cc2347d6b5a6e504`.
The ZIP and this sanitized summary have distinct identities. No raw private log,
local path, computer name, GPU UUID, runtime binary or weight is published here.

### Independently verified execution checkpoint

- All 33 frozen-kit files in the archive byte-match the exact repository commit;
  the recorded runner SHA-256 matches the committed runner
- Windows tests: 111 tests pass; captured test and runner processes exit with code 0
- Command has trace verbosity before CUDA device selection, no startup warmup,
  loopback-only binding and the approved exact loopback browser origin restriction
- At process-log time 0.474881 s: actual CUDA0 device selection
- At 0.633782 s: 33/33 model layers offloaded to GPU
- At 0.633787 s: positive CUDA0 model buffer of 1075.74 MiB
- First fixture task starts at 1.143094 s, after all three placement proofs;
  the log contains 40 fixture tasks and 40 prompt timing records
- No `security:` warning appears in the captured log; startup gate records passed
- The tokenizer `special_eos_id`/`special_eog_ids` warning is retained, not suppressed
- Archived post-run observation at 08:41:39 UTC reports no matching task processes
  or listener on the test port; this is a historical cleanup check, not a current scan

This establishes actual model-layer CUDA placement on the tested RTX 4070 Ti and
successful completion of this runner's security gate. It does not prove every
operation ran on GPU or that an unauthenticated loopback server is universally safe.
CORS remains browser-response read control, not authentication or Origin rejection.
The residual tokenizer warning is an open compatibility observation; these 40
`stop` completions do not prove its absence of impact on other inputs.

### Separate strict-run timing and resources

Recomputed from the 40 raw results: median 69.1309 ms; nearest-rank P95 93.3574 ms;
first fixture 75.4463 ms. Warm-file-cache readiness is 1.1472615 s, with startup
warmup disabled. The recorded clock is QueryPerformanceCounter with a 100 ns
reported resolution; that is a clock property, not demonstrated measurement precision.
Sampled process RSS peaks at 1,642,655,744 bytes (about 1.53 GiB). Per-PID VRAM is
null with zero samples, not zero usage. The 1075.74 MiB model-buffer log is a distinct
allocation observation and must not be relabeled peak process VRAM. No low-RAM
resource guard stop was recorded.

Do not pool this run with the first baseline or infer a speed improvement from
69.13 versus 78.125 ms: logging, warmup and timing clock definitions differ. Both
are single sequential synthetic short-text runs, not game/OCR load measurements.

### Quality and remaining work

All 78 unique archive manifest entries independently match size and SHA-256.
All 40 raw wire exchanges pass strict base64 decoding, byte hashes and JSON-object
equality against recorded results. Requests/IDs/order/splits match the unchanged
frozen fixture and sampling; compared runs differ only in ephemeral model alias.

Strict output content is exactly identical to the prior Windows output in 40/40
cases (16/16 diagnostic, 24/24 holdout). Against frozen Linux Q4, equality remains
30/40 (11/16 diagnostic, 19/24 holdout), with the same ten differing IDs listed above.
Token-multiset preservation is 39/40; newline-count preservation is 40/40.
`placeholders-05` still translates `{player}` to `{玩家}`. The previously described
causative/waiting-role errors, recipient-name corruption, never-again mistranslation,
age-boundary imprecision and speech-act change all remain in these identical outputs.

This is non-blind source-based diagnostic comparison, not a bilingual-human
adjudication or model win rate. The strict runtime correction supplies missing
safety/GPU evidence; it has not improved the observed translations.

The standalone Windows/CUDA evidence checkpoint is complete. The quality target,
7B/different-model comparison, bilingual-human blinded adjudication, app/PyQt
integration, offline/game-load behavior and release acceptance remain open.
See the [acceptance roadmap](LOCAL_TRANSLATION_TEST_PLAN.md#2026-10-03-strict-windowscuda-checkpoint-and-next-gates).
No additional model or desktop execution was performed by this cloud audit.
