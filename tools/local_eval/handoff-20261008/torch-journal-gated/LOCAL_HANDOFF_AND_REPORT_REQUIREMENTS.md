# Gated journal candidate: local handoff and reporting

Preparation only. No local copy, candidate activation, live request or native execution is authorized by this document. The frozen inert predecessor remains a separate artifact and must not be edited or reused as this candidate's test evidence.

## Exact candidate

- Candidate ID: `974d95a3-29c7-4294-9f46-33d247dd72f2`
- Source SHA-256: `00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630`
- Base journal implementation: inert source `bb1dc03d42731916b4959f3cd546863efb798b844493b5621f28f78bab77678a`
- Original downloader: `b6f8e0f56c6966bdef809da506c284adf1b5c61df88665be8132bc4a1a5401b4`

The original identity-bound CLI and DirectHTTPS entry gates are restored byte-for-byte. The `SOURCE_ONLY = False` constant labels removal of the inert hard-stop; it grants no authority. `candidate-identity.json` still says preparation_only and live_execution_authorized false. No `execution-authorization.json` is supplied. Main, worker, supervisor and connection paths must stop at their authorization gates when that file is absent. Do not run this CLI merely to demonstrate the failure; the fake tests cover that case without native I/O.

The supplied `output/attempt.json` is an unconsumed candidate/source/URL/hash binding. It is not an execution-started, request-attempt or static-attempt marker and does not authorize a request. No consumed markers are included. Keep all prior attempts and their markers intact.

## Before any approved local handoff

The parent first checks the final manifest, fresh hash-bound test receipts and independent review. Do not inherit the inert predecessor's 318 passes as results for this derivative. Ten historical per-chunk JSON cases remain separately superseded; all actually counted tests must be freshly executed against this source.

Only after separately authorized copying, place the exact candidate directory into a new isolated user-approved local directory. Use an existing verified Windows Python 3.12 interpreter. Do not install or upgrade Python, dependencies, Torch or other software as part of this handoff. Do not reuse old attempt directories, change ACLs, elevate privileges, disable security tools, retry failed deletes or move old markers aside.

Verify the copied source and all five TEST_FILES against the final manifest, verify identity and unconsumed attempt binding, and verify no authorization or consumed marker unexpectedly exists. Existing or conflicting files are a stop condition, not a reason to overwrite or clean them. Preserve `candidate` as the exact work root with its single `output` directory. The runtime rejects aliases, symlinks and reparse points.

Any future authorization must be explicit for this exact candidate/source, target environment, single request and static-inspection scope. An authorization document is not a substitute for that approval. Only after approval may the authorized operator create the four-key execution authorization object expected by candidate_preflight, naming this candidate ID and exact source hash with action `single_download_and_static_check` and authorized true. Do not include that file in preparation or archive it as though it were current approval.

## Bounded later execution scope, if approved

The one permitted URL is:

`https://download-r2.pytorch.org/whl/cu128/torch-2.10.0%2Bcu128-cp312-cp312-win_amd64.whl`

Expected whole-body SHA-256:

`fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae`

- Body cap: exactly 4,294,967,296 bytes (4 GiB)
- Owned disk-increment cap: exactly 4,402,341,478 bytes (41 × GiB // 10), distinct from the body cap
- Initial free disk: 8 GiB; minimum free: 2 GiB; control reserve: 32 MiB
- Download budget: 870 seconds active, 900 seconds total
- Static-inspection budget: 50 seconds active, 60 seconds total
- At most one GET, no retry, no redirect, no inherited proxy, no HEAD/Range/probe request
- No package installation, import, execution, transitive dependency download or model evaluation

Windows stalls can delay watchdog scheduling; these are ordinary checked/watchdog budgets, not guaranteed real-time preemption. Do not extend them to compensate for fsync latency.

For a later approved execution, invoke only the supervisor using the verified Python 3.12 interpreter and absolute work/output paths. The command shape is `python.exe -I -S -B <absolute-candidate-root>\run_check.py supervise <absolute-candidate-root> <absolute-candidate-root>\output`. This is a reference for the separately authorized operator, not an instruction to execute during preparation. Do not directly invoke workers or connect paths, generate alternative execution entrances, modify source to bypass gates, or retry a consumed attempt.

## Disclosed persistence change

The old per-chunk JSON checkpoint closed and replaced files but did not fsync them. The journal samples every 1 MiB of successful writes plus six lifecycle events, with a 2,048-byte payload cap, 4,102-record cap and 8,548,576-byte file cap. Every frame is checked, flushed and fsynced. The journal consumes the existing disk/time allowances.

This reduces process-crash observation granularity; it does not claim to retain every old before/after-write checkpoint. A partial journal only supplies a validated lower-bound prefix. It never proves a completed request or a successful download. OS fsync acknowledgment is not an unconditional device/power-loss guarantee. The historical PermissionError cause remains unknown.

The separate exclusive final checkpoint is written only after journal closure and remains required together with confirmed zero worker exit and all original count/hash/body/fsync/disk/time gates. Any journal/final write, flush, fsync or close failure aborts without automatic retry. A parseable file cannot overrule an unsuccessful worker exit. Report and static-checkpoint replacement behavior remains unchanged and may still fail.

## Required run report and retention

Any later execution report must include exact source/candidate/test/review bindings and distinguish downloaded bytes from written bytes, unknown counts and durable-body confirmation. It must report request_count, get_send_attempts, response/body/hash status, complete first error (fixed operation/context/exception type/errno/winerror), bounded secondary errors, journal count/digest/closure status, final-checkpoint persistence, worker return code/confirmed exit, termination/timeouts, sampled disk extrema, both stage timings, static-inspection results, report persistence and cleanup outcome.

If final JSON is missing, label a validated source-bound journal prefix as lower-bound evidence only. Recover a validated terminal recorded failure when available; do not invent an unknown first error, exact byte total or successful pass. Do not claim report persistence or worker exit unless independently established.

Retain source/identity/attempt markers, journal, final checkpoint and reports for audit. Existing scoped partial-body cleanup only occurs after confirmed worker exit and successful supervision under the original rules. Retain a verified wheel as originally specified. No new journal deletion, old-attempt cleanup or disk-pressure deletion is authorized. Report an incomplete/unknown result as such; obtain the next bounded decision instead of automatically retrying.
