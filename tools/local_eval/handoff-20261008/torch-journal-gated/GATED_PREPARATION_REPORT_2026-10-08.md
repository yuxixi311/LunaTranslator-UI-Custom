# Authorization-gated journal derivative — 2026-10-08

This is a separately identified source-only preparation. It restores the original identity-bound CLI and DirectHTTPS entrances around the reviewed journal implementation. It is not an activated run and contains no execution authorization.

Candidate ID: `974d95a3-29c7-4294-9f46-33d247dd72f2`.

Source SHA-256: `00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630`.

Frozen inert predecessor: `bb1dc03d42731916b4959f3cd546863efb798b844493b5621f28f78bab77678a`, independently tested 318/318; its separate review bundle SHA-256 remains `b8bac6a0662f325fbb7e4afae34f8a71579913cc0f50442b4aa447619da853ff`.

Original reviewed source: `b6f8e0f56c6966bdef809da506c284adf1b5c61df88665be8132bc4a1a5401b4`.

The only changed definitions relative to the inert source are main and DirectHTTPS; both now match the original source byte-for-byte. Other changes are the new candidate ID and the SOURCE_ONLY label/comment. The complete journal, resource, cleanup, static inspection and error-handling implementation is unchanged. Source diffs against both predecessors are included. All predecessor files and old attempt evidence remain untouched.

Fresh testing for this derivative passed 410/410 cases: 219 journal/authorization cases, 105 adapted offline regressions and 86 adapted safety cases. The 219 cases include all 127 journal cases rerun and 92 checks of actual authorization/identity gates using fake filesystem, process, socket and disk APIs. Missing or mismatched authorization is rejected before write/network/process actions across the relevant entries. No old 318 result was carried forward as a new pass. Ten historical JSON-progress cases are separately superseded and never counted as passes. All native/network guard counters are zero. The independent reviewer separately reran all 410 cases on these exact source/test hashes, with every native/network guard count zero, and issued PASS with no open source-preparation blockers. The independent receipt records those results and bindings.

The candidate identity remains preparation_only/live_execution_authorized=false. The supplied output/attempt.json is an unconsumed source/ID/URL/hash binding only. No execution-authorization.json or consumed execution/request/static marker is supplied. Normalized review metadata, when present, approves source preparation and fake-test evidence only; it does not authorize execution. Restored gates are not a request to run the program or copy it to the user's computer.

The unchanged scope is one GET to the original pinned Torch wheel URL, whole-body SHA-256 `fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae`, exactly 4,294,967,296 maximum body bytes, separate 4,402,341,478-byte owned-disk cap, 32 MiB control reserve, 900-second total download and 60-second total static-inspection budgets. The journal is counted within existing disk/time allowances. No extra request, retry, redirect, install, import, execution of downloaded code, dependency acquisition, privilege change or cleanup expansion was added.

The journal samples successful writes every 1 MiB plus six lifecycle events and caps itself at 4,102 frames/8,548,576 bytes. Each frame is length bounded, sequence/digest checked, flushed and fsynced. Any write, flush, fsync or close failure remains fail-closed and unretried; a separate exclusive final checkpoint and confirmed successful worker exit are required. A partial journal never passes the gates.

The old per-chunk JSON mechanism closed and replaced files but did not fsync them. The new sampling is deliberately coarser process-crash evidence, with no implied exact counter or power-loss guarantee from a partial prefix. The original PermissionError/JSON_REPLACE cause is still unknown. Report/static checkpoint replacement remains unchanged, and fake tests are not a Windows reproduction or live-download success.

See LOCAL_HANDOFF_AND_REPORT_REQUIREMENTS.md for the separate future approval, exact copying/source verification boundaries, later supervisor command shape, original budgets and required reports/retention. No native candidate run was performed; candidate functions were exercised only with fake APIs under guards.
