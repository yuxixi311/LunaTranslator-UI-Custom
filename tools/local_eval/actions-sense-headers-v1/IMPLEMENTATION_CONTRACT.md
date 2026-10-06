# Single initial GET header observation

This standalone kit implements protocol SHA-256
258087a02ea74cb8ab8a1daba55af68f68fd273f0c089c51164b52dc81179db2.
The exact protocol and official-host field snapshot are included unchanged.
There are no model, translation, dataset, private-criteria or download-harness
dependencies. Existing consumed source, claims and result archives are untouched.

## Admission and identity

Native work is disabled on ordinary import or unbound CLI invocation. The
workflow verifies bootstrap bytes; the isolated bootstrap verifies the manifest
and every source payload before loading either runtime module. Owner admission
requires the exact public repository and experiment branch, a non-created,
non-deleted, non-force push, run attempt1, standard GitHub-hosted Ubuntu24.04 x64,
clean source, exact G/H ancestry and exact source/workflow bytes. G has sole parent
5e7b952ea2a81873ca67390a7cde42df63527356 and adds the complete manifest inventory.
H has sole parent G and changes only .github/workflows/luna-sense-headers-v1.yml.
The source directory is tools/local_eval/actions-sense-headers-v1.

One worker must be the direct child of the exact admitted owner command, using
the same Python executable and verified source/protocol/run binding. It receives
an absolute monotonic work deadline and rechecks its live parent around work.
A late-starting child cannot begin a request after the work deadline. This is
trusted-service/owned-process provenance, not cryptographic attestation against
malicious same-UID code or fabricated GitHub service context.

## Exactly one request, then stop

Only the frozen initial asset-0 GET is available. Its request bytes include Host,
Accept-Encoding identity and Connection close, with no credential, cookie,
Range, additional query, proxy or User-Agent. DNS is invoked once. Empty,
nonpublic, malformed or unsupported address results stop; only the first public
TCP address is attempted. TLS retains certificate and hostname verification.
Partial socket sends complete this single request, without reconnect or retry.

The parser retains the reviewed2048-byte line,16384-byte block and64-field caps,
historical HTAB handling, and strict header syntax. Each application read asks
for one byte and stops exactly at the first complete header block. A200 response
does not start a body read. Location is classified transiently and never followed.
There is no asset-file write, extraction, model call or loopback HTTP request.
Zero application body reads does not imply zero body transmitted by the server
or buffered by the kernel/TLS implementation.

## Ownership, time and memory

The owner arms the30-second monotonic lifecycle before child launch. Worker work
and successful result acceptance stop at20 seconds; bounded cleanup has the
remaining10 seconds. Fresh checks follow blocking/delayed callbacks and result
validation, and precede subsequent native actions. After30 seconds an unresolved
outcome is incomplete/unconfirmed. The implementation does not promise to
interrupt every OS syscall or guarantee reap. Late Popen outcomes remain unknown,
and the worker's independent deadline/parent checks prevent late request work.

The owner imposes a conservative128MiB address-space ceiling inherited by the
worker. This is stricter than the approved128MiB worker-RSS ceiling, and bounds
the two owned processes to at most256MiB combined address space; RSS is also
observed. Failure to establish/observe capacity stops. Source checkout and bounded
read-only Git admission precede the diagnostic lifecycle. The workflow's2-minute
job timeout is a backup, not evidence of successful30-second cleanup.

## Closed output and unknown progress

OUTPUT_SCHEMA.json freezes the exact record fields/types/enums. Each receipt
binds protocol SHA, complete source-manifest SHA, source G, workflow H, run ID,
attempt1 and exact request-byte SHA. Owner acceptance checks those bindings and
canonical JSON, one line and2048 bytes maximum. The worker frame is captured only
in bounded memory; stderr is discarded. Worker plus owner frame budgets stay
within4096 bytes. No runtime evidence or asset file is written by this kit.

Only the21 official snapshot hosts and the old expected bridge receive fixed
host-class identifiers. Unknown hosts become OTHER_UNREVIEWED_HOST. No arbitrary
host, address, path, signed URL, query, header/status text, exception value or hash
of such values is emitted. Classification never grants connection permission.

Null host/progress means unobserved. In particular, an uncertain launch, rejected
or late worker result must not invent zero acquisition attempts. Model/body/
redirect counters are fixed zero by source construction. Header observation may
complete while the observed target remains rejected by the old download policy.
This is diagnostic completion, not acquisition or model success.

If bootstrap or final output fails, the separate fixed incomplete fallback says
SOURCE_OR_EXECUTION_BLOCKED, without asserting admission denial or zero requests.
It is not a bound diagnostic receipt. It contains no arbitrary values.

## Release and verification

Local implementation and fake tests do not publish or activate this source.
Root separately reviews the exact inventory, remote G, rendered H, current ref
and run absence before any authorized single non-force activation. There is no
dispatch, rerun or automatic follow-on model attempt.

run_inert_tests.py prohibits native sockets, DNS, child/thread starts, resource
limit changes and live proc/sys reads. Tests cover all host classes, parser caps,
EOF, privacy, exact request/no-follow/no-body behavior, native-boundary delays,
closed bindings, source admission, parent loss, and conservative cleanup results.
