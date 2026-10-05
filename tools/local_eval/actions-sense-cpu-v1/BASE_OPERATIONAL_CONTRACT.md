# Source-only end-to-end operational kit revision

This supplements CPU proposal 5bed5798df1352a44bcea3f5eb14f553be14588d0d6d31f5a8477a7b80bc5512,
output revision 3b2dc2f1ccf3596028d3f7078d011881dbbafc61fdf488c6e9063153e4d5b059 and the independently reviewed
notice/redirect evidence 7d58466fea3fd99523e7310b56fea8e489df60595b75dff08d280b68f0c55cb4.
It adds no executable approval. Every native entry remains unconditionally blocked.

The kit's claim validator preserves all fixed scientific/resource/count/time and
output identities from the accepted core. It supersedes only the core's dormant
empty redirect-policy placeholder with the explicit policy below, binding this
contract, the complete kit manifest, reviewed host compatibility evidence and
preclaim host-check result by full SHA-256. The original core validator is reused
on a documented legacy-policy view; the actual immutable claim contains the
superseding exact policy. No raw criteria or private reference is accepted.

Only the two pinned initial HTTPS URLs may start an asset request. Subsequent
Locations may use exact ASCII host cas-bridge.xethub.hf.co for the model, and
release-assets.githubusercontent.com for the runtime, port 443 only. There are
no wildcard or cross-provider hosts. Each redirect must be received in the same
asset's immediate response; no CDN URL can be constructed independently. Require
normal certificate verification, a nonempty absolute path, no userinfo, fragment,
literal controls/backslash, encoded path separators, dot/parent path segments or
ambiguous repeated path encoding. The provider-issued query is opaque and passed
unchanged. Signed paths/queries are never logged. Maximum URL length is 2 KiB;
the original streamed header, body, redirect, exchange, deadline and asset hash
limits apply. No credentials, cookies, proxies, retries or alternate routes.

Before claim or acquisition, require a reviewed host plan binding the current
cgroup namespace, proof of complete ancestor visibility, exact CPU requirements,
locale support, ELF interpreter, host-library paths/hashes, loader-cache evidence
and reviewed archive-library directories. Missing/unknown evidence stops before
any download. Non-mutating host checks precede acquisition; RAM, effective cgroup
headroom and free disk are checked again immediately before server launch.
The namespace assertion is a separately reviewed prerequisite, not inferred from
a namespace-visible root or a numeric host-memory reading.

Acquisition and validation run in two separately owned isolated Python workers,
under the parent's independent deadlines and resource monitor. Workers append
bounded/fsynced phase/counter events to the existing fixed journal. The parent
reserves 64 KiB within the unchanged total 64 MiB evidence allowance for the
workers' combined journal writes; each worker has a 32 KiB maximum. No worker
creates or replaces the claim. All partial assets/extraction/evidence are kept.

Extraction supports bounded ordinary POSIX ustar and short GNU headers. It
rejects extended/PAX/GNU long-name records, unsupported members, bad checksums,
absolute/parent paths, devices, FIFOs, hard links and unproven symlinks. Unsupported
archive shape stops; there is no extraction-tool fallback. Regular payloads stay
under 512 MiB and 1,024 members. At most an additional 2 MiB of decoded tar framing
is accepted, with at most 64 KiB retained per decompression output chunk.
All archive members and notices are preserved; no install script runs.

The validation worker verifies the pinned server and every extracted regular
file, records the bounded member manifest, inspects ELF64/x86-64 dependency names
without ldd or executable probes, and rejects unresolved loader/dependency/CPU
questions. The single allowed version child remains a separate 15-second stage.
The sole server uses the fixed alias and CPU arguments. Python workers use the
existing absolute interpreter with isolation and no inherited search variables;
the verified bootstrap loads exact manifest-bound local source bytes, never pyc.

The coordinator owns claim, phase transitions, workers, version, server, helper,
all deadline monitors, sockets and evidence. First failure forbids later phases.
Cleanup/finalization remains within the original 20-second reserve and outer
1,475-second ceiling. The private pre-frozen key drives the blinded grading view;
the final manifest records real derived hashes and unknown/unobserved states.
There is no public export, semantic grading, output repair or changed denominator.

The immutable release/approval decision remains external to this inert source.
No plan file, claim field, argument or environment setting activates the kit.
Activation changes reviewed source hashes and requires a separately approved
release. Passing synthetic tests does not establish live OS or model behavior.

An independent controller remains outside one explicitly owned daemon coordinator
thread from preclaim work through every final manifest/write/fsync. It does not
take the worker's locks, perform its I/O or make a blocking join. Original phase,
work, lifecycle, outer and cleanup deadlines remain authoritative; the controller
reserves the existing 20 seconds within the outer/lifecycle ceilings. It sets
cancellation at expiry, suppresses late success, and returns an explicit
incomplete/cleanup-unconfirmed outcome if that owned worker or an OS operation
has not confirmed exit. The owner monitors stop only registered children/sockets.
Per-operation persistence and phase checkpoints prohibit subsequent mutations
after cancellation or deadline. The controller cannot interrupt a blocked syscall
or guarantee kernel cleanup. No time, process/model call, request or retry
allowance is added; partial/ambiguous claims and evidence remain consumed.
