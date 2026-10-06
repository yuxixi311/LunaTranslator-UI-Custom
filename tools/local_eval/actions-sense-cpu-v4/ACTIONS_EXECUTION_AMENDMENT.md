# Source-only Actions operational amendment

This derivative preserves the accepted dot kit manifest
316f679cd8dd1cedcea57652401db0220c64db1560ed1b057c187d59103be1a6 in
an unchanged local snapshot. Its base contract is retained as
BASE_OPERATIONAL_CONTRACT.md. This document explicitly supersedes the base
contract's dot-only paths, separately asserted host namespace, pre-frozen host
library hashes, runner-side private arm key, private-only export and output schema.
CONDITIONAL_RELEASE.md adds the separately reviewed conditional Actions/owned-
worker admission policy. No native execution, publication or trigger is performed
by this source preparation; actual external activation remains a root release.

## Scientific and operational bounds

SCIENTIFIC_PROTOCOL.md publishes the exact frozen quality/coverage/uncertainty
/resource gate text with the original DESIGN SHA, without private row criteria.
The frozen renderer, source/lexicon/model/tokenizer/server/template/integrity pins,
sampling, eligibility, pair order, quality gates and cost gates remain fixed:
88 pairs, 176 completions, 442 ordered HTTP calls (264 token-count calls, 176
completion calls, health and models once each), zero cache and no retry. Costs
remain median and nearest-rank P95 of row-wise ratios, with every one of the four
strata checked at 1.25. perf_counter_ns is authoritative. The original 1,475-second
attempt ceiling, phase caps, 20-second cleanup reserve, RAM/RSS/helper/disk/2-GiB
staging bounds, two pinned assets, redirect budget and 64-MiB retained evidence
limit remain unchanged. No additional native loader or ABI-inspection child is
introduced. Unknown resources, unsupported formats and any first failure stop.

## One-shot provider and paths

Reuse the established public repository's push-only A→B workflow pattern.
A adds exactly the reviewed source inventory, with a frozen prior source-parent.
B has sole parent A and changes only .github/workflows/luna-sense-cpu-v4.yml.
The exact workflow byte template binds A, the inventory SHA and bootstrap SHA.
The job requires the precise repository/branch, a normal public push, unchanged
non-created/non-deleted branch, run_attempt=1 and standard ubuntu-24.04.
No dispatch, schedule, pull-request trigger, automatic retry or force push exists.
Before publication/activation, root independently checks current ref, A/B objects,
source parent, exact changes and absence of an existing B run; after execution it
reconciles the GitHub run/job record. No API probe, credential or live handshake
is added here. Reactivation is a new explicit owner-authorized attempt.

GitHub-supplied run ID, job ID, workflow SHA/ref, runner environment, architecture,
ImageOS/ImageVersion and exact immutable workflow are trusted-service provenance,
not cryptographic attestation. A label or caller-provided full-VM boolean alone
is insufficient. The guard uses bounded local read-only git commands within one
60-second setup bound. The job has a 30-minute outer limit covering checkout,
source guard and attempt; this backup neither changes the inner 1,475 seconds nor
proves cleanup. GitHub cancellation can itself be delayed. The independent inner
controller continues to report an unconfirmed outcome for a stuck owned worker.

Source is exactly GITHUB_WORKSPACE/tools/local_eval/actions-sense-cpu-v4.
Owned state is exactly RUNNER_TEMP/luna-sense-cpu-20261005-v4; evidence is its
attempt subdirectory. They are canonical, disjoint and never silently relocated.
Exclusive state directories plus the immutable local claim catch local collision;
external one-shot identity is A→B and run_attempt=1, not durability across fresh
runner VMs. Every Python worker rebinds these exact roots from the fixed claim.

## Staged actual host checks

Before claim or acquisition: verify trusted provider context, Linux/x86-64,
actual CPU SSE2 flags, C.UTF-8, readable PID1 systemd/status/NSpid, a single self NSpid, recorded self
PID/cgroup/mount namespace fingerprints, a single cgroup-v2 mount rooted at / and readable
complete visible limits/ancestry. Only the exact verified standard-provider
workflow plus these observations justifies the policy decision to treat the
visible root as the host hierarchy. These observations do not prove initial
namespace identity. No cross-UID /proc/1/ns dereference, ptrace, sudo or unshare
operation is used. Root must independently reconcile the provider run/job record. Missing/contradictory topology or unknown effective headroom
stops before acquisition. True hierarchy-root memory.max/current are not invented;
the preserved resource reader uses host memory at that root and checks non-root
ancestor limits. Capacity/disk/namespace are rechecked immediately before launch.

The CPU baseline derives from the pinned upstream GGML_NATIVE=OFF,
GGML_BACKEND_DL=ON, GGML_CPU_ALL_VARIANTS=ON build and x64 base backend. Optional
backend ISAs are not all required. Release tar layout fixes llama-b11349 and
$ORIGIN search behavior. These are build/dispatch provenance, not observed ABI
success. References:
- https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/.github/workflows/release.yml
- https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/ggml/src/CMakeLists.txt#L441-L518
- https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/ggml/src/ggml-cpu/CMakeLists.txt#L1-L17

A small pure parser supports only glibc new cache version 1.1, explicit little
endianness, bounded entry/string offsets and x86-64 flag 0x303. For the closed
standard dependency set it rejects relevant hwcaps, duplicate/ambiguous entries,
missing dependencies and paths outside the reviewed system library directory.
It does not guess hardware capability priority or implement a general loader.
Actual cache and resolved library bytes are hashed, ELF dependencies inspected,
and their closure required. Library/cache/interpreter resolutions are rechecked.
Unrecognized cache format stops with no subprocess fallback. Header/entry layout
and flags come from official glibc source:
- https://raw.githubusercontent.com/bminor/glibc/glibc-2.39/sysdeps/generic/dl-cache.h
- https://raw.githubusercontent.com/bminor/glibc/glibc-2.39/sysdeps/generic/ldconfig.h

After the archive hash and bounded extraction: verify the pinned server and every
member, exact ELF64/x86-64 interpreter/dependencies, ordered archive directory,
$ORIGIN-only RPATH/RUNPATH and absence of archive/host basename collisions. Cache
membership is a resolution candidate, not ABI success. Unsupported ELF/dependency
resolution stops before binary execution. The existing single 15-second version
child remains a distinct real ABI/version observation before the server/model.
Host image/ISA/library/cache/archive facts remain unobserved in this source stage.

## Authorized public records and label-blind review

The owner approved public fictional sources, model translations and allowlisted
metrics. Private criteria and real user data are excluded. The runner no longer
creates, receives, reads or exports an arm key or blinded grading packet.
The claim binds only the opaque parent preregistration and private-criteria digests. Root retains the
private criteria and constructs fresh independently randomized reviewer labels
and presentation order after the run. Reviewer packets contain no run links,
treatment identities or treatment metadata; reviewers must not look up external
results. Public evidence remains accessible, so this is label-blind review with
no guaranteed treatment blinding. This limitation must accompany any result.

Only the following closed schemas may leave the worker. The snapshot JSON records are: sources.json,
translations.json, accounting.json, metrics.json, diagnostic.json and their public manifest.json.
Every export retains all 88 source rows, 176 scheduled arm states and 442 planned
call identities, including failed, unobserved or unknown entries. It includes
exact authorized translation text, selected integer token usage/cache evidence,
scoreable empty/length/integrity flags, authoritative arm nanoseconds, selected
resource metrics including validated helper RSS/render P95, measured numeric
components including token-counter overhead and, when fully reconciled, the four
row-ratio strata, AB/BA quantiles, active membership and token totals. No generic object copying or arbitrary file upload
is allowed. Exclude raw exceptions, host paths, environment, headers, response
wires, signed URLs, criteria, keys and credentials on success and failure alike.

The separate LUNA_PREFLIGHT_JSON log schema is bounded to 64 KiB and is emitted
only after all 88 token-preflight pairs complete, before helper/generation and
outside measured arm intervals. It binds the component/source-plan/schedule and
public source/lexicon hashes; records only row IDs, active/eligible booleans,
integer prompt counts, request-body hashes and numeric coverage counts; and
states pass/fail coverage. It is also retained in budgeted metadata.json.
Coverage failure is published as failure and then the original ledger gate
forbids generation. An incomplete token preflight cannot emit a completed
receipt. Publication failure is terminal. Publication stays inside the original
60-second preflight and 600-second post-ready budgets; no time is added.

A pre-attempt initial_unknown snapshot has every call explicitly unknown; it is
never a final assertion that no calls occurred. A complete final snapshot may
replace it only if all six records and the public manifest are present. A
missing/partial final snapshot leaves completion and accounting unconfirmed.
Public accounting's protocol_status describes protocol evidence, not cleanup;
only the independent terminal record can establish operational completion.
Bounded LUNA_PUBLIC_JSON snapshot lines and the single LUNA_PREFLIGHT_JSON
receipt are the sole structured job-log transports, plus the sanitized terminal
status. No other payload schema is allowed. JSON escaping prevents model newlines from becoming workflow commands.
Root reads those closed records plus the independently reconciled run/job status;
there is no added artifact-upload action, REST call or log/environment dump.
Each snapshot is bounded to 16 MiB; final files also share the unchanged 64 MiB
owned-output budget. Raw internal files remain only in temporary owned state.

## Remaining release inputs and honest limits

The source-parent, public plan/author/literal-audit receipts and opaque private
freeze/criteria digests in INPUT_COMMITMENTS.json are supplied by root. No private
criteria path or content is present. Root must review this source inventory,
publish/review immutable A, render exact B and explicitly release activation.
A/B placeholders are not old experiment commits. The conditional bootstrap,
runtime and helper gates described in CONDITIONAL_RELEASE.md are included in
immutable source A before publication. They require verified source/service or
owned-parent admission, not an environment or plan enable boolean. Workflow B
executes the reviewed source and never patches A or rewrites its manifest.
No real attempt/claim, host probe, asset download,
model output, publication or trigger was performed to prepare this derivative.
Synthetic tests establish source contracts only, not live enforcement or quality.

OBSERVABILITY_REVISION.md adds only the bounded finite diagnostic schema, closed
worker failure receipts, intentional-exit handling and a proved journal handoff
cleanup correction. The original failed run remains causally unresolved. This
source preparation does not rerun or reset it and authorizes no new attempt.

OPENSSL_HOST_POLICY_AMENDMENT.md separately adds exactly libssl.so.3 and
libcrypto.so.3 to the closed host-library list under the same resolution, hash,
ELF and unknown-ambiguity stops. Actual DT_NEEDED remains unobserved; the prior
run remains causally unresolved and no retry is released by this preparation.


## Exact model CDN compatibility candidate

This source-only revision adds exactly us.aws.cdn.hf.co alongside the existing
cas-bridge.xethub.hf.co for model asset0. Runtime asset1 still permits only
release-assets.githubusercontent.com. No wildcard, suffix match, extra official
domain, arbitrary Location follow or fallback is authorized. The changed policy
is carried explicitly in acquisition_source.POLICY and its preregistered digest.

The separately authorized header observation, GitHub run37440244990, reported
HTTP302, HF_META_US_AWS_CDN_HF_CO, CANONICAL_HTTPS_443, and REJECTS_HOST under the
old rule, with one initial GET, zero redirects followed/application body reads/
loopback calls, and confirmed cleanup. This is evidence of that new observation;
it does not reconstruct the Location of an earlier failed run. The finite class
is supported by the official metadata snapshot SHA-256
185aedecfb16392540015cb26078b2f4e687b719b476d724a1978c274d694f01, observed2026-10-06
from https://huggingface.co/.well-known/meta.json. No signed URL or raw header
value is copied into this kit.

Both model hosts retain the identical HTTPS443, canonical-authority, public-IP,
credential/control/fragment/path rules and opaque-query preservation. The query
is not decoded, repaired, synthesized or locally signature-validated. Existing
body size/hash validation, deadlines, bytes, redirect/exchange counts, resource
limits, scientific inputs, model pins and quality gates are unchanged. No retry
or claim reset exists. A later unsupported redirect still stops.

This is an explicit acceptance-policy change, not another claim of observational
equivalence. Only the named asset0 hostname is newly accepted; all other accepted
or rejected shapes retain the previous rules. Source-only preparation does not
release a new native attempt, publication or activation.
