# Source-only finite diagnostics correction

This separate correction passes 238 guarded tests. Published source manifest
ada2668eb6e6221be5d8b9567116056284a81873837c909b50986e899a2ec2dc remains unchanged.
The actual failed run's initiating cause remains UNKNOWN; no classification here
is retroactive. No host/network/model/native-child action, claim, Git mutation,
workflow rerun or reset occurred during this correction.

Reproduce:

    python -I -B /path/to/kit/run_inert_tests.py

OBSERVABILITY_REVISION.md defines the exact finite schema and bounded changes.
The parent now exposes source/attempt-bound stage, first failure, claim/journal,
asset-counter and child/cleanup states. Missing worker receipts remain unknown.
An intentional exit no longer acquires a second bootstrap failure label. A
separate inert reproduction proves that the published journal handoff exception
path can leave its newly opened descriptor unclosed; the correction closes that
owned descriptor without changing or retrying the claim. Root close precedes handoff; the first
write failure survives later claim/root close failures, and each descriptor
close is attempted once. This does not prove
that the actual run hit that path.

The added fake tests cover all claim creation/write/sync and journal boundaries,
worker admission and worker-journal failures, DNS/TLS/framing and partial-transfer
states, write/cleanup failures, first-failure preservation, child lifecycle and
missing/invalid receipts. Canary data cannot pass the closed projection. Existing
scientific, deadline, ownership, conditional-admission, public-data and coverage
regressions remain in the suite. Helper adds only diagnostics.py (json/re), keeps
the native stack excluded and retains the same 32-MiB limit/measurement scope.

No data, model, sampling, quality, coverage, cost, request, redirect, resource,
byte or time limit changes. The frozen renderer, evidence reconciliation,
helper benchmark/validator and audited source remain exact in behavior; added
instrumentation does not create extra probes or model requests. The independent
controller remains effective throughout cleanup/final I/O. Diagnostic delivery
can itself be incomplete; missing observations are never converted to success.

This is a reviewable source correction only. Any future publication or attempt
requires a separate explicit owner/root release and newly reviewed identities.
The already consumed run is not retried, repaired or reset by this package.

The separate OPENSSL_HOST_POLICY_AMENDMENT.md permits only libssl.so.3 and
libcrypto.so.3 under the existing cache/path/ELF/hash/closure rules. Positive and
negative inert fixtures pass; this explicit acceptance change is not a claimed
cause of the previous run and adds no installs, requests or execution release.
