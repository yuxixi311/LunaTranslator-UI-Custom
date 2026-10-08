# Fresh authorization-gated preparation regressions

Fresh guarded execution passes 105/105 diagnostic and 86/86 safety cases (191 executed passes), on source SHA-256 `00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630`, candidate `974d95a3-29c7-4294-9f46-33d247dd72f2`. None of these results was inherited from the frozen inert preparation. Ten obsolete per-chunk JSON progress cases remain explicitly `superseded`, excluded from passed and executed counts. The journal suite owns their append-only journal fault replacements.

Only the new preparation's `candidate/adapted_offline_test.py` needed adaptation. `candidate/adapted_safety_test.py` remained unchanged but was freshly rerun against the new source and test hashes. Frozen `torch-journal-design-20261008` files, this preparation's `original/` and `inert_base/`, and the candidate main source were not edited by this task.

## Changed assertions

The original diagnostic suite block from `restored_connect_memory_leaves` through the authorized CLI worker-dispatch cases was restored verbatim from this preparation's preserved `original/offline_test.py`. This replaces the inert derivative's unconditional `OFFLINE_PREPARATION_ONLY` expectations with the actual authorization-gated behavior:

- An authorized synthetic DirectHTTPS connection reaches one memory DNS/socket/TLS handshake only
- Missing authorization blocks CLI and DirectHTTPS before side effects, with `EXECUTION_NOT_AUTHORIZED`
- Synthetic connect/handshake errors preserve their first diagnostic despite simulated close failures
- Invalid host, port, tunnel, or TLS verification settings fail before memory DNS
- A DirectHTTPS connection cannot reconnect or repeat its one permitted use
- The real stdlib HTTP formatting path produces one fixed GET on an in-memory wire with no authorization, proxy authorization, cookie, or range headers
- A second OneGET attempt fails without another memory send
- Authorized synthetic CLI cases dispatch only to mocked supervisor/worker leaves, retaining no-real-IO assertions

All 63 original named safety cases and all 23 candidate static-proof gates pass again. Journal-aware proof fixtures, unique fake descriptors, unbuffered fake journal/final IO, validated journal crash recovery, first-error/secondary-error assertions, and pre-load native/disk/network/process/thread guards are unchanged.

The candidate authorization file remains absent. Synthetic authorization documents exist only inside the per-test memory filesystem. This work does not authorize or perform live execution.

## Guarded commands and receipts

    python3 -I -S -B candidate/adapted_offline_test.py
    python3 -I -S -B candidate/adapted_safety_test.py

Both runners require Python 3.12 and install guards before loading the candidate subject. Every network, write, process, exit, thread, disk, read, and native guard counter is zero. No real network request, download, native PC operation, subject file write, or worker process occurs.

Fresh stdout receipts are `candidate/adapted-offline-results.json` and `candidate/adapted-safety-results.json`. `ADAPTED_REGRESSION_MANIFEST.json` records source/test hashes, exact superseded cases, and counts. Adjacent unified diffs show changes relative to `inert_base/`; the safety diff is empty because no code change was needed.
