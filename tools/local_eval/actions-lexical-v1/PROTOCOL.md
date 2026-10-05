# Luna Actions lexical experiment: source preparation

The owner has separately approved this new GitHub Actions target in the public
repository `yuxixi311/LunaTranslator-UI-Custom`: one standard hosted CPU job on
an independent experimental branch, fixed official dependencies followed by one
offline 48-call lexical probe, and the disclosed GitHub operational logs plus
sanitized summary. Preparation remains source-only pending final review and
publication release. This file is not a push or execution instruction. No
workflow has been activated and no live phase has run as part of this
preparation. The previous recovery and readiness attempts remain terminal DNS
failures. They are not reset, resumed, or reclassified.

## Review and activation

1. Review this source and its exact `SOURCE_MANIFEST.json` digest. The baseline is
   the 23 public files at commit `d452ac242211991ddd3439cd451c39e5d988c249`, under
   `tools/local_eval/cloud-lexical-v1`. No historical execution manifest, claim,
   raw log, private archive, or host-specific path is an input to this job.
2. After the owner authorizes publication and this one job, create source commit
   A on the dedicated branch `experiment/luna-actions-lexical-20261005`. A adds
   only this new source directory and contains no active experiment workflow.
   Verify the selected baseline's workflow inventory before any push. At the
   reviewed base, existing workflows are manual, pull-request, or reusable;
   none has an active push trigger. Do not create a pull request as activation.
3. Construct B with A as its only parent. B adds only
   `.github/workflows/luna-lexical-one-shot.yml`. Stamp A and the reviewed source
   manifest/event-guard hashes into the workflow. Review B's exact commit SHA,
   parent, complete diff, action pin, branch and permissions before publishing.
   Ensure the remote branch already exists at A, then make only the authorized
   non-forced A-to-B update. Creating the branch directly at B is rejected.
4. The workflow's only event is a push to that exact branch changing that exact
   workflow path. Its job condition requires the named public repository, exact
   before=A, a non-created/non-deleted/non-forced push, and run attempt 1.
   Checkout selects `github.sha` explicitly. The guard verifies after/HEAD,
   workflow ref/SHA, one parent=A, a workflow-only diff, a clean tree, exact
   source inventory, and every source digest. There is no dispatch, schedule,
   PR, tag, reusable, matrix, rerun, self-hosted, or alternate-branch route.
5. Record the observed B SHA and Actions run ID when the event is accepted. Do
   not repush, recreate, reset, force-push, rerun, or try another branch after an
   uncertain trigger or a failed/interrupted job. Inspect the existing run.
   A later experiment requires a new reviewed identity and explicit authority.

Workflow dispatch is deliberately absent: GitHub requires its workflow file on
the default branch for that event. This plan makes no changes to main, v1.0.1,
release workflows, product defaults, desktops, or unrelated coding environments.

## Once-only limits

The exclusive event directory and claim prevent repeating the experiment in the
same job workspace. `github.run_attempt == 1` rejects GitHub reruns. Fixed
branch/before/parent/path checks reject routine extra pushes, branch creation and
force pushes. A fixed concurrency group serializes matching jobs and does not
cancel a running job.

These controls do **not** implement an atomic, global exactly-once ledger.
Distinct duplicate event deliveries can receive distinct run IDs and fresh
ephemeral disks; concurrency can serialize them rather than deduplicate them.
No durable write, cross-run claim, cache, artifact, token-based remote lock, or
external service is used. The operator must make exactly one authorized ref
update and never deliberately retrigger it. If platform-wide deduplication is
a strict requirement, this design is blocked until a separately authorized
durable coordination mechanism is reviewed. Do not describe this as globally
at-most-once or exactly-once.

## Runtime and supply chain

The only runner label is GitHub's standard `ubuntu-24.04` x64 hosted runner,
with a 15-minute job timeout. Standard public-repository compute is free under
GitHub's published billing rules. There are no larger, paid, GPU or self-hosted
runners, storage uploads, caches or artifacts.

`actions/checkout` v7.0.1 is pinned to
`3d3c42e5aac5ba805825da76410c181273ba90b1`. It uses read-only `contents` permission,
no persisted credentials, no submodules/LFS/tags, and a depth-two sparse checkout
of the two source directories and experiment workflow. The Actions platform
provides its ordinary short-lived token and action-download/checkout network
operations. No user secret, custom credential, environment secret, external
service credential or permission escalation is requested. Nothing in this
workflow writes back to the repository.

The job requires the **already present** official tool-cache entry
`RUNNER_TOOL_CACHE/Python/3.12.14/x64` and its completion marker. It invokes that
interpreter directly; there is no `setup-python`, runtime download, installation,
package upgrade, fallback interpreter, or alternate toolchain. If the entry is
missing, incomplete or incompatible, stop before acquiring wheels. Assert
CPython 3.12.14, Linux x86_64, compatible glibc and the exact base cache prefix.
Record the actual interpreter SHA-256 and runner image OS/version in the
sanitized report. Pass only that validated runtime's `lib` directory as
`LD_LIBRARY_PATH` to owned children, without inherited suffixes.

The current official Ubuntu24.04 image inventory lists CPython3.12.14. Image
contents are mutable over time; this is a fail-closed availability requirement,
not an immutable image guarantee. Interpreter/shared-library provenance is the
official hosted image's trust boundary. Recorded interpreter hashes identify
observed bytes; they do not prove that the entire runtime was independently
reproduced or cryptographically verified against CPython source.

## One job, fixed phases

The control process verifies the source/runtime and 2 GiB free-disk/available-
memory floors, then exclusively claims this new job identity before the first
wheel request. It owns each phase process group, including cleanup, and stops on
any error, deadline, incomplete output or failed cleanup. It never calls the
baseline controller, baseline freeze, baseline claim, or an old staged runner.

1. Acquisition: at most one direct GET for each of the two exact official PyPI
   wheel URLs, in order, using ordinary DNS/TLS. No HEAD readiness request,
   retries, redirects, proxy inheritance, mirrors or TLS changes. Exact
   compressed bytes total 73,904,174, subject to the original 100 MiB aggregate
   cap and 240-second owned lifecycle. Each complete wheel is hash verified.
2. Offline setup: one 60-second owned lifecycle. Verify every wheel member,
   RECORD hash, metadata, dependency inventory, license notice and dictionary
   identity before installation. Expanded payload and installed payload each
   have their own 512 MiB cap. Create an isolated venv with the same interpreter,
   bundled `ensurepip`, then install only the two local wheels with no index,
   dependencies, compilation, cache or extra packages. The Python socket audit
   hook also wraps ensurepip's own pip subprocess. No package update is allowed.
3. Offline probe and assessment: separate 60-second parser and 60-second
   assessment lifecycles in this same job. Parser bounds remain 15 CPU seconds,
   1 GiB address space and 4 MiB output. Exactly 16 exposed diagnostics plus 32
   seen examples, one source-only batch, 48 tokenizations, no warmup or extra
   call. SplitMode.C, the six-entry canon and all-occurrence admission policy
   remain unchanged. Assessment reads expected decisions only afterward and
   applies the same 16/16 lexical gate.

The required dictionary is 217,466,039 bytes with SHA-256
`53fa281d11eef3769712fe1c3c892117338f9892bee6daf4dad51daa5281bb6f`.
The active phase ceilings total 420 seconds. Runner startup, action checkout,
source/host checks and bounded summary generation are separately covered by the
15-minute job timeout; they are not counted as wheel bytes or phase time. A
user-space watchdog relies on OS scheduling and signal delivery.

Offline means no intended network operation plus Python socket auditing. It is
not an OS network sandbox; native official package code is assumed not to
bypass that restriction. No model, translation provider, Hy, GPU, training,
application binary, Windows performance test or product-default change exists.

## Public evidence and privacy

GitHub necessarily retains its own operational logs: runner/image, action,
checkout, version and step metadata. They cannot be promised to contain only our
summary. The custom runner prints at most 32 KiB of schema-controlled JSON and
writes the same content to the job summary. It suppresses arbitrary exceptions,
stack traces, environments, HTTP error bodies, full input strings, raw surfaces,
translations and full parser/assessment output. Phase logs, downloaded wheels,
installed files, claims and raw outputs remain only on the ephemeral runner and
are never uploaded by this workflow.

The sanitized successful summary retains source/trigger/run identity, wheel and
dictionary pins, runtime identity, phase timing/cleanup, parser call count,
memory/CPU timing, 16 diagnostic pass flags and stratum names, and 48 public case
IDs with token/occurrence counts and numeric admitted-canon indexes. Seen rows
are current decisions, not pass/fail regression scores because they have no
new independent expected labels. Hashes reference ephemeral raw output and the
installed inventory; those hashes alone do not preserve independent replay or
allow a reviewer to recover tokenization after the runner is discarded.

Only completed parse evidence establishes 48 calls. An interrupted parser may
have made some calls; a failure report must not infer zero from missing output.
Passing exposed lexical examples is lexical-feasibility evidence only, never a
new accuracy, semantic, translation-quality, Hy or Windows performance claim.

A green job and `state: complete` mean the technical pipeline completed. They
can coexist with `lexical_gate_passed: false`, which means the fixed mechanism
failed its exposed diagnostic gate and the baseline should be retained. The
first line of the job summary prominently reports the lexical gate as PASSED,
FAILED, or NOT ASSESSED and, when assessed, the matched count out of 16. Report
that mechanism outcome alongside technical completion; never call a green job
translation-quality success. This distinction does not change the fixed gate
or the controller's technical-completion exit status.

## Licenses and official references

The repository's existing GPL-3.0 license applies to this source. The unchanged
baseline retains pinned SudachiPy Apache-2.0 and SudachiDict Apache-2.0 license
texts and additional UniDic/NEologd notices. Runtime wheel inspection checks
packaged notices. This preparation redistributes no wheels, dictionaries, models
or interpreter binaries. Checkout's pinned source is MIT licensed; CPython has
its versioned PSF license and third-party notices.

- Base source/license: https://github.com/yuxixi311/LunaTranslator-UI-Custom/tree/d452ac242211991ddd3439cd451c39e5d988c249
- Pinned checkout/license: https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1
- Official runner inventory: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md
- CPython license: https://github.com/python/cpython/blob/v3.12.14/LICENSE
- Official Python availability manifest: https://github.com/actions/python-versions/blob/77ca8ada59c43eeb7af4c21e3bd55f6a2c65847b/versions-manifest.json
- Hosted runner definitions: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Public compute billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Push/dispatch events: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- Concurrency semantics: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

Source-only validation is `python -I -B run_fake_tests.py`. It denies real
networking, subprocess launches and native package imports, while substituting
fake boundaries. Fake fixtures and temporary claims are not live attempts.
