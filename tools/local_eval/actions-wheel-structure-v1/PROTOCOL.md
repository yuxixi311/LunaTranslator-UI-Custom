# Frozen proposal: exact49 wheel structural audit v1

Status: SOURCE ONLY. No acquisition, installation, package import, extraction, NER,
GPU, Actions activation, Git operation, or acceptance-gate change is authorized by
this file. Future execution requires a separate exact-scope approval and reviewed
source hashes. The prior R is eb9769ceaecdec84acb7882bb4027a3adc545d48. Its plac
failure proves an unsupported relocation category, not which category or member.

## Inputs and acquisition

Copy, do not amend, WHEELS49.frozen.json SHA256
c04f4e31641594e90b9a6436625ad20d0de550b5f8543d70d5d70f46458d3401.
Exactly 49 records, 207406351 archive bytes. The helper rejects any changed manifest.
Each request is a single GET to the exact frozen https://files.pythonhosted.org
URL, with the original filename and no URL query, redirect, retry, dependency resolution,
registry refresh, alternative domain, credentials, cookies, ambient proxy, package
cache, extra file, model fetch, or persisted package artifact. Default TLS validation
remains enabled. Ordinary DNS may occur; the logical GET count is not a bound on
DNS, TLS, or network packets. No browser or access-denial fallback is permitted. No HTTP error
body, response header, URL, filesystem path, traceback, exception string, or package
content enters a public result. Acquisition failure stops the batch immediately.

Acquisition runs in its own owned process group, capped at 240 seconds wall time,
120 CPU seconds, 512 MiB address space, 250 MiB total received body bytes, 256 MiB
single-file output size, 64 file descriptors, and one child. There is one sequential
request per record, with a bounded remaining-time socket timeout. Exact size and
SHA256 are checked during each download. The temporary wheel directory is new,
private, and owned by this invocation. Partial acquisition is explicitly incomplete;
no audit runs until all 49 exact hashes verify. No retries occur automatically.

Before the first GET, create ATTEMPT.json exclusively beside this reviewed helper.
Acquisition and audit share this single persistent attempt. Its finite receipt binds
the manifest, protocol, helper source, and interpreter executable SHA256. Any existing
receipt, including failure or interruption, blocks another attempt. Changing output
directory does not change this attempt key. Moving/copying the pack, deleting its
receipt, or substituting an interpreter is not a permitted retry. Terminal receipt
and finite result persist, while wheel bytes do not. This is a local one-shot guard,
not a claim of a global tamperproof authorization service.

## Owned, offline audit

After the acquisition process exits, a separate process audits the private wheel
directory, with no network API use. It is owned and reaped by the supervisor.
Limits: 600 seconds wall, 480 CPU seconds, 1 GiB address space, 64 descriptors,
256 MiB output-file size. At most 250 MiB of acquired archives, 2 MiB report bytes,
and 32 MiB temporary/report overhead are permitted; require 300 MiB free before
starting. Only archives and finite JSON state are written. No member is extracted.
Total decompressed bytes across the audit are at most 2 GiB, streamed once in
1 MiB chunks. Per wheel: 256 MiB archive, 1 GiB decompressed, 50000 members,
16 MiB central directory, 512 MiB member, compression ratio <=1000 above a 1 MiB
floor, 2 MiB metadata/captured startup/entry metadata, 16 MiB RECORD. At most128
captured metadata members and32 MiB captured bytes per wheel, including RECORD;
captured bytes are released between wheels. At most4096 parsed import declarations
are held across the entire closure. Across all
wheels: at most 100000 members. These caps preserve or tighten prior validator
bounds. Large dictionary/model wheels fit the compressed budget; their actual
expansion remains unobserved. The 600s/480s window provides substantial margin for
bounded decompression and three RECORD digest algorithms; exceeding it is an
explicit terminal resource result, never permission to expand limits or retry.
The 600-second ceiling is NEW proposed authorization, not an extension of the old
60-second setup permission. It covers a full closure inventory, including up to
2 GiB decompression and SHA256/SHA384/SHA512 per member, rather than setup until
the first unsupported package. These are conservative pre-acquisition bounds, not
measured runtime claims. The 240/600-second phase ceilings include spawn, final
serialization, and termination/cleanup work. Each phase reserves 10 seconds from
its ceiling: up to 2 seconds TERM, 3 seconds KILL/reap, and 5 seconds for cleanup
and finite receipt/report serialization. Owned work stops before that reserve.
At acquisition success only the required temporary wheel inputs survive into the
audit; on any failure they are removed. The final audit phase includes destruction
of all temporary wheel inputs. A blocked OS/filesystem operation or failed cleanup
is cleanup_uncertain/incomplete, not success or a retry authorization.
Supervisor wall limits and child RLIMITs apply independently. Termination sends
TERM then KILL to the owned process group, reaps it, removes only its temporary
directory, and writes a finite incomplete result when the operating system permits. Ordinary completion also destroys
all acquired archive bytes. External termination before cleanup is not success;
the owning environment must remove the invocation's private temporary directory.

## Ordered method definitions

1. Verify the immutable manifest and the exact archive identity (regular, single
   link, no symlink; pinned basename/size/SHA256; no mutation before/after read).
2. Verify ordinary single-disk non-ZIP64 ZIP structure, exact end/central directory
   boundaries, local header names/method/flags and nonoverlapping member regions,
   no preamble/comment/trailing payload, safe canonical relative member paths,
   duplicate/casefold/file-directory collision absence, ordinary file/directory
   types, allowed permission bits/compression, and every resource bound. Unsupported
   ZIP encodings/structures are hard terminal audit limitations, not install facts.
3. Stream every member and verify CRC, declared size, and SHA256/SHA384/SHA512.
   Verify complete, unambiguous RECORD with canonical hashes/sizes and self-row.
   Exactly one top-level *.dist-info/RECORD is required, even when its root differs
   from the filename-derived expected root. Zero is missing; multiple are ambiguous.
   RECORD.jws/RECORD.p7s alone retain existing unsigned-signature exclusions; report
   their counts. A missing/ambiguous RECORD, absent member, wrong digest, unsafe path,
   hash mismatch, malformed ZIP, access failure, or limit failure is terminal.
4. Only authenticated, safe archives produce compatibility observations. Record
   all top-level .dist-info and .data roots; classify purelib, platlib, scripts,
   headers, data, and unknown relocation schemes. An unknown safe scheme is an
   unsupported finding and its name is represented only by SHA256. Foreign roots
   and misplaced/absent metadata are compatibility findings (missing RECORD is
   already terminal). Map recognized scheme+relative destination abstractly, merge
   root/purelib/platlib under the current policy's library destination, and detect
   per-wheel and cross-wheel destination/casefold/file-directory collisions as
   compatibility findings. Raw archive path collisions remain hard safety failures. No
   actual installation prefix is chosen. Unknown mappings stay incomplete.
5. Inventory all ordinary member types and root/data/dist-info counts/bytes; compute
   an all-member inventory commitment. Inventory every .data/scripts member using
   count, length, content/path hashes, executable-bit boolean, and finite shebang
   classification. Inventory .pth, sitecustomize/usercustomize, bytecode, native
   library, entry_points.txt, and top_level.txt by finite classification/count/hash.
   Preserve exact setuptools pth/shim pin observations as compatibility evidence.
   Never execute or import them, rewrite a shebang, create a console script, or
   turn a matching hash into permission to install. Listing limits fail explicitly.
6. Check METADATA against its frozen core_metadata_sha256 at the expected root and at every
   discovered top-level *.dist-info/METADATA (including the chosen RECORD root);
   any discovered byte mismatch is terminal. Foreign or misplaced metadata therefore
   cannot mask an observed mismatch. Nested unrelated payload metadata is merely
   inventoried, not presumed to be the distribution metadata. Missing distribution
   metadata is explicitly unobserved with a compatibility finding. Byte mismatch is terminal. Bounded UTF-8 header parsing yields finite metadata
   version, field counts, Dynamic/import counts, syntax class and hashed field
   commitment. No raw headers/requirements/license content is emitted. Import
   absence means unknown, empty Import-Name means explicit empty, and namespace
   absence is separate. Detect import ambiguity/overlap across available metadata
   without importing packages. This is not a replacement semantic dependency,
   SPDX, target-tag, Python, platform, or runtime compatibility validator.
7. For every License-File declaration, inventory hashed declared path, retained
   RECORD-verified matches, expected modern dist-info/licenses placement, byte
   lengths and content hashes. Missing/unsafe declarations are compatibility
   findings, not silently loosened acceptance. Inventory additional notice-like
   names and bundled native libraries as heuristic counts/hashes, explicitly
   nonexhaustive. No notice content, legal-clearance claim or artifact deletion
   follows from naming. All archive members remain authenticated until cleanup.
8. Accumulate bounded compatibility findings across all 49. Hard failures stop
   immediately and mark current record failed and subsequent records not attempted.
   Every manifest index always has acquisition/audit status; no absent row implies
   success. Full structural completion is distinct from install acceptance, runtime
   compatibility, NER quality and notice/legal review. All remain unapproved/unrun.

## Finite evidence contract

Public report contains only fixed key names/enums, booleans, bounded integers,
frozen manifest package names/versions, manifest/archive/core metadata SHA256,
and bounded SHA256 commitments/observations. No arbitrary member paths or raw
scheme names are allowed, including in errors. Per-file fact lists are capped:
128 startup records, 4096 script records, 1024 notice declarations/matches, 4096
notice/native inventory entries, 256 import declarations, 32 unknown scheme hashes.
At most 49 record results and 2 MiB JSON. A list exceeding its cap is explicitly
terminal/incomplete, never silently truncated. Results use unobserved for absent
facts. Archive evidence is released only after full RECORD integrity; partial
facts on a failed wheel are not emitted as authenticated observations. Hash-only
facts are evidence pointers, not proof of benign code or installability.

## Source verification and release conditions

Freeze this protocol and its SHA256 before finalizing implementation and running helper tests.
Synthetic ZIPs only may test all positive and negative paths, including scripts,
all recognized/unknown schemes, traversal/symlink/collisions, malformed RECORD,
changed hashes/metadata, startup/hooks, notice placement, missing records,
closed public error projection, budget/deadline/redirect/access failures, cleanup,
and partial/completed 49-row status accounting. Test acquisition with injected
fake transport only; no live network or target-wheel reads. Independent source
review and manifest/helper/test hashes are prerequisites to requesting future
acquisition approval. This pack has no active workflow and cannot trigger Actions.
