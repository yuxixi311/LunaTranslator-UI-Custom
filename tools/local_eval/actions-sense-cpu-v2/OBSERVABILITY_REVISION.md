# Narrow finite observability correction

Base: published manifest ada2668eb6e6221be5d8b9567116056284a81873837c909b50986e899a2ec2dc.
The base and its exact 41 payloads remain unchanged in their original preparation
directory. This correction is separate source work. It does not rerun/reset the
consumed attempt or authorize a new workflow, acquisition or model call.

The actual failed run's initiating cause remains unknown. The new classifications
are prospective instrumentation. They must never be retroactively assigned to
that run merely because an inert fixture reproduces a possible failure path.

## Closed schema and meaning

A single diagnostic.json joins the existing public snapshot and public hash
manifest. The terminal record also carries its latest finite diagnostic, so an
error during export/final-manifest work can still be distinguished. The record
is at most 4096 encoded bytes and stays within the existing 16-MiB public snapshot
and 64-MiB owned-output budgets. Its explicit fields are:

- Schema, source-manifest SHA and attempt ID; unavailable bindings remain null
- Last entered stage, plus a latched first-failure stage and finite category
- Claim states NOT_ENTERED / CREATE_PENDING / CREATED / DURABLE, and journal
  states NOT_ENTERED / CREATE_PENDING / OPEN / DURABLE
- Exactly two asset records: attempted-asset and exchange-intent counters,
  bytes returned by payload reads, bytes confirmed by successful write return
  values, and verified status; unavailable observations stay null
- Exactly five child-role records: acquire, validate, version, server and helper;
  launch intent/pending/returned/unconfirmed state, handle adoption, observed
  exit and bounded code, recorded cleanup-wait timeout, cleanup state and optional finite
  worker detail
- A deduplicated list of fixed cleanup categories distinguishing child/process,
  pipe/socket/thread, journal and evidence-finalization uncertainty

Counters describe recorded operations. Exchange intents are not proof a complete
HTTP request reached a server. Written byte counts do not prove disk durability
or bound unconfirmed effects of a failed syscall. Missing worker diagnostics are
not converted to zero. Pending claim/launch operations are not reported absent.
An EXITED child and its numeric code do not alone identify an unexpected failure:
normal owned cleanup may deliberately terminate a server. First-failure category
and cleanup state remain separate.

Only enum members and bounded numbers/booleans/nulls are projected. Exact static
require-message comparisons may select a finite code internally. Unknown messages
remain UNKNOWN_FAILURE; there is no substring-derived network diagnosis. A DNS
or TLS stage identifies the operation being attempted, not a guessed external
cause. No exception text/args/repr, traceback, environment, host paths, headers,
URLs, signed queries, process argv, private criteria or keys are exported.

## Minimal wiring

- diagnostics.py holds only fixed schema, counters and projections. It imports
  json and re. Helper adds this small module to its prior five-module bootstrap;
  SSL, acquisition, runtime and controller modules remain excluded. The same
  32-MiB helper cap and measurement scope apply.
- Parent stage markers precede risky operations; claim/journal transitions are
  recorded around creation/writes/syncs. Existing process observations update
  child states without extra child probes. First failure is retained separately
  from cleanup categories and subsequent export failures.
- Asset instrumentation records the existing two attempts/eight exchange-intent
  budget, DNS/connect/TLS/send/header/body/sync/close stage, verified status and
  partial byte counters. It makes no additional request, retry or network probe.
- One bounded LUNA_WORKER_DIAGNOSTIC frame (at most 2048 bytes) reports worker
  admission/failure; successful acquisition/validation receipts embed the same
  closed schema. Parent reads only those closed, manifest-bound fields from its
  already owned bounded logs after cleanup. Missing/truncated/invalid frames keep
  unknown states. Helper success output remains its original result object.
- Intentional SystemExit propagates without a duplicate bootstrap error label.
  Unexpected bootstrap exceptions retain a fixed sanitized fallback.

The narrow proven cleanup correction closes the newly opened journal descriptor
if a post-open claim-finalization exception occurs before handoff to the caller.
The original claim is retained and the first diagnostic failure is latched before
cleanup. A failed close is recorded, not retried. Claim-file write errors are latched
before file cleanup. Root-directory close completes before journal ownership
can be handed to the caller; a failed root close therefore closes the unhanded
journal. Secondary claim, root and journal close failures have separate categories
and cannot replace the first exception or diagnostic category. This fixture does not
establish the cause of the original failed run.

All scientific data/model/sampling/quality/coverage/cost rules and all original
request, redirect, byte, resource, phase and cleanup limits remain fixed. No
inference, host, network or child action was used to prepare or test this source.
All tests use inert objects; no private criteria or fresh source semantics were
read. The existing independent controller still bounds blocking owned operations;
diagnostics do not claim to interrupt a syscall or guarantee delivery/cleanup.

OPENSSL_HOST_POLICY_AMENDMENT.md is a separately authorized and documented
acceptance change for exactly two SONAMEs. It is not an inferred cause of the
original run and does not authorize a new execution.
