# Source-only Windows probe preparation

This directory contains an inert plan validator, fake lifecycle model and unreachable CPU probe template. It is **not an installer or an executable Windows probe release**. No user computer, native DLL, CUDA, Torch, model download, wheel download or network operation is used by the tests.

## Run the offline tests

From this directory: `python -m unittest -v test_harness.py`. `python harness.py` prints a disabled plan. `python cpu_probe.py.txt` prints a disabled result and never imports Torch. None of these commands install anything.

## Boundaries implemented and tested

- A plan is always execution-disabled, even with complete-looking metadata and an explicit setup mode. There is no installer, subprocess launcher or native sampler to enable accidentally.
- Metadata validation rejects missing URL/version/SHA256/byte/license/compatibility/dependency data, missing direct packages, incomplete closure claims, nonofficial hosts, duplicate names, unresolved dependency names and totals over 4 GiB. It does not prove upstream metadata or actual wheel bytes; review attestation is not a solver or signature.
- The injected lifecycle accepts only the local fake clock/resources/process types. It models startup free RAM ≥4 GiB, runtime free RAM ≥2 GiB, sampled tree RSS ≤2 GiB, a 110-second work deadline and exit/cleanup by 120 seconds. Setup plus the full probe must fit inside 30 minutes; the final five minutes of the 35-minute overall budget stay reserved.
- Sampled RSS is a stop threshold, never a hard cap. No Windows RSS or available-memory enforcement has been implemented or tested.
- Cleanup is modeled only for a process with verified ownership; unverified ownership prevents launch and unconfirmed cleanup blocks success. No PID-name matching, user-process termination or security settings are used.
- Receipts contain fixed status codes, flags and numeric samples. No user paths, raw exceptions, child logs, environment contents, headers or credentials are included.
- GPU execution remains disabled pending reviewed CUDA context/driver/workspace overhead and a total-device sampling/stop policy. The proposed 256 MiB tensor allocator budget cannot cap total VRAM.

## Inert CPU probe source

`cpu_probe.py.txt` contains a permanently gated function. Its unreachable body prepares the built-in HunYuanDenseV1 model with two layers, hidden size 128, four heads/two KV heads, intermediate size 256, vocabulary 256, sequence length 32 and batch one. Rank-eight LoRA targets q/k/v/o; two optimizer steps check target-only finite loss, frozen base gradients, adapter gradients and save/release/reload equivalence. The base is random and deterministically re-created, never loaded from pretrained assets. Only an adapter reload uses PEFT's local loader. Architecture/API correctness remains subject to runtime validation with the frozen package set.

## Requirements before any Windows execution

1. Complete and independently review the frozen official Windows wheel closure, hashes, bytes, licenses, compatible tags and exact versions. Verify actual local wheel bytes and allow no source builds or online resolver fallback. Current metadata file is deliberately incomplete.
2. Implement and review an owned Windows process-tree backend with race-safe creation/ownership, process-tree RSS and free-memory sampling, monotonic deadlines, child-output suppression, bounded cleanup and exit confirmation. Normal subprocess parent termination alone is insufficient to guarantee descendant cleanup; a tested ownership mechanism is needed. Do not infer it from these fakes.
3. Implement a bounded setup stage with isolated venv/cache/temp locations, disk-growth monitoring ≤12 GiB, download ≤4 GiB, no automatic retries and the shared time budget. No installer code is included in this revision.
4. Obtain approval for the exact verified interpreter, private target directory, frozen download/install scope, CPU probe, limits and retention. Private runtime paths belong only in the future Desktop task, not public source or receipts.
5. Review and freeze that final source. Preserve CPU-only operation unless the separate CUDA initialization budget and stop rules are approved. A passing random CPU probe would not establish real-model quality, GPU compatibility, training fit or authorization.

Source basis: the retained [independent source review](windows-probe-source-review-20261007.json) and [verification record](VERIFICATION.json) describe the inert preparation and unchanged code/test hashes. This README is a public metadata projection: its private proposal locator was removed; the historical review and verification record retain the original reviewed README hash. PUBLIC_MANIFEST.json identifies the separate original and projected README hashes. No runtime behavior or test source changed.
