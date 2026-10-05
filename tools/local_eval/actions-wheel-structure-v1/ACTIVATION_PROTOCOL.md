# One-shot GitHub activation: fixed49 archive audit v1

This is activation SOURCE PREPARATION. Publication and the actual trigger remain
separate gated steps. No workflow is installed by this source directory. The
exact49 audit authorization covers one acquisition and archive audit only; it
never authorizes installation, target imports, model/NER/GPU execution, later
quality evaluation, package caches/artifacts or automatic retries.

## Immutable inputs and publication split

The sealed audit helper remains byte-identical, SHA256
 a697eea878fa369863a38bfd3bd53821a48849a6de68df1b1e386c460ee06aed.
PROTOCOL.md, PROTOCOL_LOCK.json, SOURCE_FREEZE.json, WHEELS49.frozen.json and the
67-test synthetic suite also remain byte-identical. The sealed preparation
inventory was b34ab40dfd3c7fc5889856bbfdc275006af6b787801db81a0f2685f6bba8a599.
The separate wrapper, event guard, verified-byte bootstrap, activation tests and
workflow template are independently reviewed and bound by PREPARATION_INVENTORY.

Repository: yuxixi311/LunaTranslator-UI-Custom (public).
Branch: experiment/luna-actions-lexical-20261005.
New source S must have exactly one parent, terminal R
 eb9769ceaecdec84acb7882bb4027a3adc545d48.
S changes only the explicit flat source allowlist under
 tools/local_eval/actions-wheel-structure-v1/.
S adds no active workflow. Private receipts, raw metadata, prior logs/evidence,
private criteria, downloads and target package bytes are excluded.

Trigger T must have exactly one parent, actual reviewed S. T changes only
 .github/workflows/luna-wheel-structure-audit-v1.yml.
Its bytes must be the reviewed template rendered with actual S and exact source,
event-guard and bootstrap hashes. A pending-S rendering is not runnable and must
not be published as T. Source and trigger commit objects, sole-parent ancestry,
allowlisted diffs and remote identities must be independently verified at their
respective release steps. This source package does not perform those mutations.

## Exact event and one-shot identity

The workflow admits only a noncreated, nondeleted, nonforced push to the exact
public repository/branch, with before=actual S, after=T, attempt=1, and the exact
workflow path/ref/SHA on GitHub-hosted Linux X64 Ubuntu24. Checkout is pinned to
 actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1,
ref=the triggering SHA, depth=3, sparse source plus the single workflow, no tags,
submodules/LFS, credentials persistence, caches, configured secrets or artifacts.
Read-only contents permission is sufficient. No workflow_dispatch or schedule.

New workflow/concurrency/event/work/claim identity:
 luna-actions-wheel-structure-20261005-v1.
The guard verifies clean source, exact S/R and T/S ancestry, complete allowlist,
source hashes and exact workflow rendering before exclusively creating the event
work directory and EVENT_BINDING.json. The cached interpreter is pinned even
before that event claim. Wrapper preflight rechecks source/event/runtime and
requires the work directory to contain only EVENT_BINDING before creating a
single RUN_CLAIM.json. The unchanged helper then creates its own exclusive
ATTEMPT.json beside audit_wheels.py. Existing claims are terminal; output changes,
reset, force push, replay, rerun or new identity are not retry mechanisms.

ATTEMPT.json is the sole expected new source-directory file after helper entry.
Post-run source verification allows exactly that one additional bounded regular
file, whose schema/identity/PID/source/protocol/interpreter pins are validated.
No arbitrary added source file, directory, cache or bytecode is permitted. The
trusted-workspace/private-directory model and event guard are not a global
 tamperproof once-only service or protection against same-user source tampering.

## Interpreter and timing

Use only the existing official CPython3.12.14 cache entry at the runner's
 Python/3.12.14/x64, with completion marker,17752-byte executable and SHA256
 bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0.
Require CPython3.12.14/Linux/x86_64, isolated/no-site mode and the expected base
prefix. No setup-python, runtime download, package manager, installer or fallback.
A bounded stdlib-only child verifies that exact interpreter can start under the
unchanged helper's clean worker environment, before any audit attempt claim/GET.
The helper does not inherit ambient credentials, proxies or LD_LIBRARY_PATH.
The workflow can use the known cache lib directory to start the wrapper itself;
if a clean helper worker cannot start, stop without replacing the interpreter.

The frozen acquisition240-second/120-CPU-second/512-MiB and audit600-second/
480-CPU-second/1-GiB lifecycles and every file/expansion/output cap remain unchanged.
Wrapper preflight gets30 seconds including owned-probe termination reserve;
post-validation/framing gets30 seconds. Helper acquisition+audit+wrapper therefore
has a900-second planned ceiling. An external GNU timeout at930 seconds, followed
by KILL after5 seconds, is a final operational guard, not extra acquisition/audit
permission. A timeout never authorizes retry or an unobserved success.

The job timeout is20 minutes. Checkout is limited to2 minutes, source/event guard
and interpreter checks to1 minute, and wrapper step to16 minutes. Their maximum
step sum is19 minutes; the20-minute job ceiling is larger than all frozen phases
and bounded operational overhead. Neither a job timeout nor wrapper overhead
extends the240/600-second data-work limits. OS/signal limitations can leave cleanup
uncertain, as documented in the frozen protocol; report incomplete.

## Output and cleanup

The wrapper validates the helper's complete finite report against the original49
records, then binds it to the exact event/run/source/inventory/protocol/interpreter
identities and claim/report hashes. Do not print raw headers, paths, exceptions,
package contents, Git output or ambient environment. Missing, malformed or partial
helper output remains explicitly incomplete; no missing row means success.

Canonical JSON is capped at the helper's2-MiB report plus32KiB envelope. Base64 log
framing is capped at3MiB total, using BEGIN(length/SHA256/chunk count), numbered
12000-character CHUNK records and END. There is exactly one frame, with contiguous
indexes and matching decoded length/hash. Receivers reject incomplete/reordered/
duplicated/extra chunks and trailing content. The JSON includes every validated
helper row; no row filtering, truncation or raw-content passthrough. Report absence
uses report:null, finite incomplete status and a finite error code.

Only bounded finite JSON receipts/reports remain on the ephemeral runner and in
the framed log; no upload-artifact, cache action or archive retention. The helper
removes its owned acquired wheels. The wrapper never removes/reset claims or
changes input files. ja_ginza and dictionary data inside the49 pinned wheels may
be hashed but never loaded; no extra model fetch occurs. No acceptance gate is
changed and no compatibility finding authorizes installation.

## Verification before publication

Freeze this activation method before running activation tests. Test only synthetic
archives and injected fake transport/host/process/event bindings. Re-run the exact
67 inherited tests and all activation guard/ancestry/allowlist/runtime/claim/report/
framing/replay cases, with no Git mutation, real network, target wheel reads,
package imports, RLIMIT changes or Actions trigger. Independent review covers
source identities, the operational wrapper and exact pending-S template. Publish
only the reviewed public allowlist after the next release gate; actualT is separate.
