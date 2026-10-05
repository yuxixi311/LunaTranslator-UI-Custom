# Independent setup diagnostic experiment v2

This is the source-only activation preparation for the owner's separately
authorized second independent CPU lexical experiment on the existing branch
`experiment/luna-actions-lexical-20261005`. The source enables both CLI entry
points for review, but no active workflow, source/trigger commit, publication,
live claim, download, installation, native import, parser call, or model call
has been created by this preparation. Final publication and activation are
withheld until independent review and the coordinating owner's release.
Tests use synthetic archives and substituted boundaries only.

The original `actions-lexical-v1` and `cloud-lexical-v1` source directories remain
byte-identical. The original v1 workflow, source manifest, and first terminal
failure remain preserved. This experiment uses a distinct protocol, source
manifest, workflow path, run identity, and private temporary/claim namespace.
The sealed unactivated diagnostic review inventory has SHA-256
`bfe7c018299a95bc76a6bd7deb7a2ae669874764c88e42aa455e7ac2c22e13ec`.
Its original directory remains unchanged; activation edits exist only here.

## Established first-run evidence

The first and terminal Actions run is
https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37266603727,
job 111624652941, run attempt 1. Its source commit A is
`b9ec9e9cdac848f180cef6fa10aed219a09b4bb0` and trigger commit B is
`57690a7473208b692364e93eb4bd855b6c9cd629`.

The official cached CPython 3.12.14 identity and source/event checks passed.
The two exact wheels completed their hash-verified 73,904,174-byte acquisition
in 0.615255265 seconds. Setup exited 1 in 0.164218977 seconds, with cleanup
confirmed and no timeout. Its retained category is `operation_failed`.
The parser and assessment phases never started. No lexical result exists.

The exact setup exception and failing check were not retained. Timing does not
identify a cause. This candidate neither recovers that missing evidence nor
claims a causal fix. The first run remains terminal; its source, manifests,
receipts, claim, and activation history are never reset or reclassified.

## Finite diagnostic contract

Four independently exclusive receipts cover preflight, setup, ensurepip, and
local installation. Each event contains only an enumerated step, an optional
allowlisted public package identifier, one of `started`, `passed`, `rejected`,
or `operation_failed`, and a bounded elapsed-seconds number. The implementation
enumerates every permitted step. There is no exception class, exception text,
traceback, environment, header, URL, arbitrary member name, local path, source
text, parser surface, or translation field in these receipts.

The setup validator retains the original acceptance requirements for archive
digests, safe member paths/types, startup hooks and relocation, aggregate
expanded payload, RECORD location/size/encoding/inventory/self/format/member
hashes and lengths, exact metadata bytes, identity/dependencies, tags, notices,
dictionary bytes, and the dictionary's declared license. Paired tests exercise
the new and unchanged original validators on the same synthetic inputs.

Only the two public package identifiers `SudachiPy` and `SudachiDict-core` are
allowed in comparison evidence. At most nine comparisons cover their wheel,
metadata, canonical dependency-list and tag-set digests, plus the dictionary
digest for SudachiDict-core only. Each includes expected and observed SHA-256
and byte length, with an equality flag. Expected values must equal the unchanged
public pins or their defined canonical serialization. Dependencies/tags are
serialized as compact ASCII JSON; tags are sorted after deduplication, matching
the original set-based check. No raw dependency expression or metadata is
retained. Arbitrary package/slot pairs and forged expected hashes are rejected.

Each process writes `started` before a boundary and replaces that entry's status
after completion. Nested installer receipts survive a wrapping subprocess error,
so the summary includes both the setup launch boundary and the nested cause's
fixed step. Event counts are capped at 9/80/18/18 and receipt byte limits at
4/24/8/8 KiB respectively. The existing total public-summary ceiling remains
32 KiB. The collector reads a bounded number of bytes and revalidates the whole
schema and pinned comparisons before emitting anything. Unexpected, oversized,
malformed, or unapproved receipts become only `invalid_receipt`; absent receipts
become only `not_recorded`.

A `started` event means that boundary did not persist a completion receipt. It
does not establish whether it ran partially, failed, or was interrupted. A
receipt-write failure or process death before the first receipt may leave only
that state or `not_recorded`. The owned lifecycle remains the authority for
timeout and cleanup. Per-step timing includes nested work and can overlap; do
not sum it into phase time or infer causes from elapsed time. This finite
instrumentation localizes tested failure boundaries; it cannot guarantee an
exact cause for every possible operating-system interruption.

## Controls retained

- One exclusive attempt identity; no retry, rerun, recovery, resume, alternate
  branch, force push, or reset route
- Fixed source/event/before/parent/workflow-only-diff checks, read-only repository
  permissions, run attempt 1, exact source inventory and source hashes
- Official preinstalled CPython 3.12.14 only; no runtime fallback or installation
- Same two exact public wheel URLs, hashes, sizes, order, one GET apiece, no
  redirects/retries/proxy inheritance/mirrors, and 100 MiB acquisition ceiling
- 2 GiB disk and memory preflight floors; 240/60/60/60-second owned phase limits
  and 15-minute job ceiling in the reviewed activation workflow
- Same 512 MiB expanded and installed payload ceilings, isolated copied venv,
  bundled ensurepip, and local-only pip with no index/dependencies/compilation/
  cache; Python socket audit on setup and nested ensurepip's pip process
- Same 15 CPU seconds, 1 GiB parser address space, 4 MiB parser output, exact
  48 calls, 16 diagnostic plus 32 seen inputs, no warmup, SplitMode.C, six-entry
  canon, all-occurrence admission, and unchanged 16/16 diagnostic gate
- Same distinction between technical completion and exposed lexical gate
  outcome; no translation-quality, accuracy, semantic, Hy, GPU or Windows claim
- No artifact/cache upload, package/native execution during preparation, or
  disclosure of ephemeral raw setup/parser logs

The new `wheel_paths` boundary also checks canonical wheel paths before archive
inspection, strengthening path rejection without relaxing any original check.
Diagnostics add bounded work inside existing deadlines; there is no compensating
timeout or resource-limit increase. Socket auditing is not an OS network sandbox;
the same official native-package trust boundary remains. Job-local exclusive
claims and run-attempt gating are not a global exactly-once ledger.

## Staged C/D activation review

Protocol: `luna-actions-lexical-diagnostic-20261005-v2`.
Branch: `experiment/luna-actions-lexical-20261005`.
Workflow: `.github/workflows/luna-lexical-diagnostic-v2.yml`.
The runtime directory is exactly `$RUNNER_TEMP/` plus the new protocol, with
exclusive event binding and RUN_CLAIM.json inside it. No v1 receipt or claim is
read, reset, replaced, or reused. The second experiment is not a rerun of run 1.

The original A/B staging pattern becomes C/D for this independent experiment:

1. Independently review this source, complete immutable source manifest, exact
   source publication allowlist, and the disabled workflow template. Source
   commit C has sole parent B1 `57690a7473208b692364e93eb4bd855b6c9cd629`.
   Its only changes add the new v2 source directory and its SOURCE_MANIFEST.json.
   C contains no new active workflow and no baseline or v1 workflow changes.
2. After source C is created and reviewed, substitute only its exact 40-character
   SHA in the two source-commit placeholders of WORKFLOW_REVIEW.yml.in. Review
   the complete rendered workflow and its digest. Source/guard hashes are fixed
   during preparation; never change them during activation.
3. Create workflow-only trigger D, with C as its sole parent and only the new
   v2 workflow addition. Independently review exact D, the C/D parent relation,
   and the complete tree diff before the one C-to-D ref update. Source C and
   trigger D are uncreated and unset in this preparation.
4. Both events must be ordinary non-forced pushes on the existing approved
   branch, never created/deleted/recreated. The activation event has before=C,
   after=D, exact repository/ref/workflow, run attempt 1, and public repository.
   The runtime guard verifies D HEAD, sole parent C, exact workflow-only diff,
   clean tree, exact source inventory and all pinned file hashes.
5. The unchanged v1 workflow filters pushes to its own different workflow path;
   neither C nor D changes it. Its frozen before=A1 gate also rejects C/D.
   Verify both facts and its byte identity again against B1 before publication.
   Do not alter its path filter or first-run evidence.

The workflow is only an outside-repository template in this preparation. No
ref update, GitHub write, execution, or source-commit substitution is performed.
Stop on an unexpected branch tip, changed baseline, unrelated diff, missing
runtime, or any failed gate. There is no reset, force push, workflow dispatch,
recovery, retry, alternate branch, or automated rerun. Existing v1 branch-reuse
restrictions remain in its historical record; the owner's later explicit
same-branch authorization applies only to this separately identified experiment.

The source manifest binds the unchanged public baseline at
`d452ac242211991ddd3439cd451c39e5d988c249`, the v2 source files, and the original
phase limits. It excludes itself to avoid a hash cycle; the reviewed workflow
pins its complete SHA-256 and the event guard SHA-256 before executing either.
The public summary remains at most 32 KiB and contains only the approved
sanitized diagnostics, numeric results, and fixed public identities. Private
setup/parser logs and receipts exist only in the job's ephemeral workspace;
there is no artifact/cache upload or wider disclosure.

## Source-only verification

Run `python -I -B run_fake_tests.py` from this directory. The harness denies real
socket/DNS/HTTP operations, external process creation, signals, real venv
creation, ensurepip bootstrapping, pip module execution, and native package
imports. Focused tests temporarily substitute these boundaries, including the
nested bootstrap body. No actual wheel or dictionary is downloaded or loaded.

The suite includes malformed synthetic wheels, all declared validation groups,
preflight/child identity and resource errors, venv construction and creation,
ensurepip hook and nested child failures, installation flags and exits,
installed snapshot reads/inventory/limits/writes, receipt rejection, maximum
summary size, one-attempt claims, fixed gates, and unchanged public snapshots.
Mocked tests also exercise both CLI dispatchers, every child command, rejection
paths, sanitized failures, and distinct v2 identity. Passing fake tests is
source-level evidence only, not successful real setup.
