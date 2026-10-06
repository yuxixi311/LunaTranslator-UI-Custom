# Persistent policy worker: proposed operational amendment

Status: source-only proposal and fake state-machine tests. No worker, process,
IPC endpoint, server, network, model or tokenizer is launched. This changes the
old one-shot helper lifecycle and therefore requires independent review and
explicit execution release. The known prior runner RSS exceeds 32 MiB; placing
policy work in that runner cannot establish this experiment's helper RSS gate.

## One owned worker and exact time bounds

Use exactly one non-daemon child holding only the exact policy, production guard
excerpt, eight-record bank, bounded protocol state, and standard-library imports.
Its actual full-process peak RSS, including interpreter/imports/bank, must remain
<=32 MiB. Do not substitute runner/module-allocation or unrelated-worker metrics.

- Child lifetime is <=600 seconds from launch, INCLUDING cleanup. The last 20
  seconds are reserved for termination/reaping. No new command may begin after
  min(child launch +580 seconds, existing post-ready/work/phase deadline)
- Bootstrap plus all synchronous command round trips and response validation,
  including normal FINISH, cumulatively consume <=15 seconds of active wall
  time. Bootstrap individually consumes no more than that remaining budget
- Each command has one absolute deadline equal to the minimum of its remaining
  active budget, child launch +580 seconds, and inherited post-ready/work/phase
  deadlines. No retry, fresh timeout reset, queued concurrent command, or
  unbounded read/write/wait is permitted
- Worker cumulative user+system CPU must be <=15 seconds. Idle time waiting for
  model calls is excluded only from active wall accounting, never from child
  lifetime, parent ownership, CPU/RSS guards, or existing global deadlines
- Emergency termination/reaping uses the shared existing cleanup reserve and
  completes by min(failure +20 seconds, child launch +600 seconds, inherited
  cleanup/lifecycle/outer deadline). Parent interruption follows this same path
- The coordinator must confirm exit/reaping before reporting cleanup success;
  unknown/late cleanup is terminal and incomplete. No background daemon survives

This explicitly replaces the old 15-second total child-lifetime meaning with a
15-second aggregate active-work allowance plus a bounded idle-inclusive lifetime.
It does not enlarge the existing 600-second post-ready, 780-second work,
800-second server lifecycle, 1,475-second outer, 20-second cleanup, HTTP deadline,
memory, disk, evidence, generation, or acquisition limits.

## Exact finite command inventory

One READY response follows verified bootstrap. It binds the exact policy, guard,
bank, interpreter/worker identity and genuine cold-start observation. READY is
part of the aggregate active-work allowance, not another model/count request.

For each of the fixed 87 rows, in fixed order:

1. PREFLIGHT PREPARE receives id, original source, and original baseline-message
   digest. The worker executes the exact frozen prepare policy. It returns a
   bounded plan, reason, record ID, and baseline/prospective message digests
2. The parent performs exactly two actual complete-chat counts. If surface
   eligible, PREFLIGHT GATE sends B/C and matching digests and returns the exact
   frozen admission decision. If ineligible, the parent requires positive plain
   B/C, B<=384, C==B and identical baseline/prospective messages; no helper GATE
   is needed because admission is already false and token-independent

Only after all 174 counts and coverage checks pass may the parent send one SEAL,
binding the full preflight receipt digest and exact E. The existing ledger
separately forbids every completion before this seal.

Each measured candidate row then receives MEASURED PREPARE. Eligible rows also
receive MEASURED GATE after their two fresh measured HTTP counts. Ineligible
rows send the exact preflight-bound baseline and require no measured GATE/count.
Candidate intervals include synchronous IPC, decoding/validation and all policy
work, along with counts, generation and the unchanged output guard. The worker
must reproduce preflight message digests, selection, eligibility, B/C (for
eligible rows), and admission; any drift terminates before that generation.

Finally, one FINISH closes the finite state machine and reports bounded resource
and timing facts. It is charged to the same 15-second aggregate work allowance.

Exact parent command count: 174 PREPARE +2E GATE +SEAL +FINISH =176+2E.
For the audited E=24 population this is 224 commands, plus one READY response.
The previously discussed 287-command alternative sends unnecessary GATE messages
for all 87 preflight rows; it is not used here. No unused command capacity permits
additional work. HTTP inventory remains exactly 350+2E=398 for E=24.

## Message, state, and data bounds

Use one four-byte unsigned big-endian length followed by exactly that many
UTF-8 JSON bytes. A single request or response payload is <=32,768 bytes; framing
adds four bytes. Reject zero/oversized/truncated/trailing frames, duplicate keys,
nonfinite JSON, wrong types, unexpected fields/ops/row/phase/sequence, unknown
pins, and malformed Unicode. No unbounded line read, buffering, parser recovery,
concurrent command, or raw exception response is allowed.

PREPARE sends only one source copy (<=4,096 Unicode code points), its id, phase,
and baseline-message digest. The exact baseline is reconstructed by the worker
and digest-checked. The parent retains its original baseline object and uses it
by identity on every abstention; it does not replace it with a deserialized copy.
An eligible response returns at most one prospective user message. Source,
baseline and prospective UTF-8 JSON byte caps are enforced before writes.

At most one current candidate plan is retained. Across phases, keep only 87
compact source/message hashes and eligibility/admission/count receipts, capped
at 64 KiB serialized, plus the fixed bank <=16 KiB. Discard each raw source/current
plan after the required reply. Do not retain private criteria, answers, output
translations, arbitrary command strings or paths. The helper performs no HTTP,
filesystem mutation, model/tokenizer work, subprocess launch or application import.

Worker errors use a closed finite error code and terminal state. Raw source,
exception strings, tracebacks, environment, process dumps, credentials and full
IPC payloads are not public logs or protocol exports. The parent retains only
the already authorized bounded experiment evidence. No extra public export is
created by this amendment.

## Timing and unresolved native bridge

The 87 helper samples are actual nested measured PREPARE round trips from before
bank validation/selection through completed candidate-plan response validation,
before network token counting. Include all 87, their first sample, and nearest-
rank P95. The first measured sample is not assumed cold after preflight. Report
actual bootstrap cold start separately without another benchmark invocation.
Gate IPC remains in the candidate end-to-end interval. Normal finish and one-time
startup costs are explicitly reported; no candidate-specific recurring work is
moved into an untimed phase.

The fake protocol does not prove OS process identity, RSS enforcement, pipe
backpressure handling, interrupt safety, or cleanup. A reviewed native bridge
must wire owned-child launch, independent deadline/RSS/CPU supervision, bounded
stdin/stdout, cancellation and reaping to the preserved coordinator/controller.
Until that bridge and this amendment are independently accepted, execution stays
unconditionally disabled.
