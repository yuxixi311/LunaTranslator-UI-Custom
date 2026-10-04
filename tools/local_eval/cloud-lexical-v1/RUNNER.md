# Public controlled lexical runner snapshot

**NOT EXECUTED.** The public wrapper is a distinct packaging revision of the reviewed one-shot Linux runner. The pure policy, phase implementation, bounds and fake tests are retained. Its only runner-code changes are the introductory description, the preparation hash and manifest filenames. A new public manifest does not inherit review or execution approval from the active frozen pilot.

Run the standard-library fake tests from `README.md` for preparation. `python -I -B pilot_runner.py freeze` exclusively writes `PUBLIC_EXECUTION_MANIFEST.json` from the pinned public preparation and runner files; this preparation command performs no package download or analyzer work. The generated SHA must be independently reviewed before any real phase. No execution manifest is included in this checkpoint, and no real execution command is recommended here.

The retained controller implements download, setup, parse and assess in that order. A future approved execution must bind the exact reviewed manifest SHA. `RUN_CLAIM.json` and `RUN_LOCK` bind a persistent one-shot attempt. Never delete a stale, running or terminal claim to retry. Source bytes and prior artifacts are rechecked at each phase. A lexical rejection is a completed experiment only if all technical evidence is complete; it does not promote a candidate.

Downloads are exactly the two pinned official URLs, with no proxy inheritance,
redirect, retry, alternate endpoint or source build. A 240-second owned lifecycle
covers both transfers; exact lengths and hashes and the aggregate 100 MiB ceiling
are enforced. Preflight checks 2 GiB available disk and memory.

The 60-second setup lifecycle includes all archive member and RECORD checks,
dictionary identity, venv creation, CPython's bundled offline ensurepip, isolated
offline pip installation, and installed-byte inventory. Pip uses --no-index,
--no-deps, --no-compile, --no-cache-dir and --only-binary=:all:. Archive traversal,
links, encryption, duplicates, .pth/egg-link startup hooks and wheel .data
relocations fail closed. All payload hashes must agree with RECORD and aggregate
uncompressed/installed bytes remain at most 512 MiB. Packaged license and legal
notices are retained in both original wheels and the installed distribution.

The sole parser child uses the isolated venv and explicit absolute dictionary,
packaged resources, userDict=[], SplitMode.C, and surface projection. Bundled
default plugins remain active; this does not claim internal normalization is
disabled. Source and raw token slices are preserved and validated. There are
exactly 16 diagnostic and 32 seen calls, no warmup, cache, alternate modes or retry.
Only the controller assessment stage reads expected labels, after all 48 outputs
and source-only entry decisions validate. It records per-case/per-stratum gates
and separate seen occurrence/span/POS/OOV/dictionary diagnostics.

Parser RLIMIT_CPU is 15 seconds, RLIMIT_AS is 1 GiB and RLIMIT_FSIZE is 4 MiB.
Peak RSS is measured separately in KiB on Linux, plus initialization and per-source
latencies. The 60-second lifecycle includes startup and output. A parent alarm
covers blocked spawn, native initialization, parsing and writing, reserving seven
seconds inside the ceiling for TERM/KILL and cleanup. Descendants inherit the
owned process group, including setup pip processes. Only that group is signalled.
Failed cleanup is terminal, retains the claim, and returns nonzero. As with any
userspace watchdog, the bound assumes OS scheduling and signal delivery.

Setup and parser deny Python socket audit events and inherit a minimal environment
and isolated working/configuration directories. The audit hook is not an OS
network sandbox: the pinned native extension is assumed not to perform direct
native networking. ensurepip is the bundled standard-library offline bootstrap.
The parser imports no spaCy, GiNZA, ja_ginza, Luna, translation model or GPU stack.
No arbitrary private environment values are exported.

Optional reviewer verification can call owned_process with an owned standard-
library Python child that prints a constant or sleeps, using a temporary directory.
This is a process/watchdog check, never an additional tokenization call.

No result establishes semantic accuracy, translation quality, Hy improvement,
Windows ABI behavior or Windows speed. A complete 16/16 lexical match permits
only consideration of a separately frozen semantic experiment.
