# Independent package notice correction experiment v3

The owner separately authorized one third independent bounded Actions experiment
on `experiment/luna-actions-lexical-20261005`. This is its unexecuted source-only
activation preparation. Both new v3 CLI entry points are enabled for review;
no active v3 workflow, source E, trigger F, publication, ref update, live claim,
download, installation, native import, parser call, GPU or model call is created
or performed here. Final independent review and release of the exact activation
remain pending.

The full v2 activation source and all earlier source directories remain
byte-identical. Both earlier terminal run results, workflows, claims, source
manifests and activation histories are preserved without resetting, relabeling,
resuming or retriggering them. This experiment has its own protocol, source
manifest, workflow path and private ephemeral claim namespace. Its reviewed
license policy, diagnostic implementation and all other acceptance controls are
unchanged from the sealed 78-test source-only candidate inventory SHA-256
`61518e07bd305d742485d45099f0dce99cac4c20792d20ad5e9b723109e6ad5a`.
The original sealed candidate remains untouched with both CLIs disabled.

## Evidence and correction

The first run, 37266603727, ended in setup with only the broad retained category
`operation_failed`. Its exact cause remains unknown.

The second run, 37275192309, attempt 1, used source commit
`64df92dfa7cd1d688f921ad546a60a2433770235` and trigger commit
`2bf3da881b74023ed46750e982991c9423a3bf15`. Its retained diagnostic receipt proves
that the exact SudachiPy wheel, archive paths/types, RECORD, core metadata,
package identity, dependency list, and tags passed validation. Its
`license_notices` step rejected because no non-directory member had a basename
starting, case-insensitively, with LICENSE, LEGAL, or NOTICE. No dictionary
archive check, venv creation, installer, parser, or assessment was reached.
Both runs produced no lexical result.

A separately scoped read of the public SudachiPy wheel failed at DNS before
receiving bytes and was not retried. The complete wheel inventory and raw
metadata header presentation remain locally uninspected. The second run's
precise basename finding must not be expanded into an assertion that every kind
of attribution or license-related member is absent.

The original generic requirement for a license-like wheel basename is replaced
by a package-specific provenance and retention policy. The exception is confined
to the unchanged exact SudachiPy 0.6.11 CPython 3.12 wheel filename, SHA-256 and
size, exact core-metadata SHA-256 and size, and verified versioned upstream source
LICENSE. It is not a general missing-license exception. Another package,
version, filename, wheel, or metadata identity is rejected. The code does not
guess whether the authenticated metadata uses License, License-Expression, a
classifier, or another header representation.

## Verified source notice provenance

Three complete notice texts already present in the reviewed public source are
mandatory. Their SHA-256, byte length, Git blob identity, version tag, package
version, and immutable source commit are bound by `license_policy.py`:

- SudachiPy 0.6.11: `WorksApplications/sudachi.rs`, tag `v0.6.11`, commit
  `90fd6068c80c2fc3b63e0dbab0e341475bad4d8f`, root LICENSE, 11,357 bytes,
  SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`
- SudachiDict-core 20260723: `WorksApplications/SudachiDict`, tag `v20260723`,
  commit `4813c1cddda74f98a416f92b26d961424ecf8767`, root LICENSE-2.0.txt,
  11,358 bytes, SHA-256
  `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`
- The same SudachiDict version and commit, complete root LEGAL, 6,037 bytes,
  SHA-256 `725a8776b38e058b185e905594bc9a2437dbf3787df022fffeefedb9a84e4665`

The source provenance review compared local Git blob identities against complete
official version-tag trees. SudachiPy's source packaging declares Apache-2.0 and
references the parent LICENSE in MANIFEST.in. SudachiDict's packaging source
copies LICENSE-2.0.txt and LEGAL into its package. These source facts do not prove
their exact wheel locations. The complete LEGAL text, including its UniDic,
NEologd and other attributions, is retained without summarizing or editing it.

License bytes alone cannot prove a package version: Apache texts can be identical
across releases. A mismatched version, source commit, tag URL, or source blob
mapping is rejected even if the SHA-256 of the text remains unchanged.

## Supplied notice selection and retention

Only RECORD-verified regular archive members are eligible. The bounded selector
includes every member whose basename starts with LICENSE, LEGAL, NOTICE,
COPYING, COPYRIGHT, or AUTHORS; every file below recognized LICENSE(S), LEGAL,
NOTICE(S), COPYING, or COPYRIGHT(S) directory components; and all actual members
matching declared License-File relative suffixes. This supports arbitrary
basenames such as `licenses/Apache-2.0.txt`, package-root layouts, dist-info
layouts, and multiple supplied matches. It does not invent a wheel path.

Declared file names must be safe and resolve to supplied members. A missing or
unsafe declaration fails closed; no unobserved declaration is assumed to exist
or be absent. This selection rule is explicit and does not claim to discover
all legal obligations embedded in arbitrary source or native binaries.

For SudachiDict-core, the original requirement for a supplied file with basename
LICENSE-2.0.txt remains. Its packaged bytes are authenticated by the unchanged
exact wheel and RECORD checks. The source LICENSE and packaged LICENSE are
retained as separate byte streams; equality is deliberately not required because
packaging may change newline conventions. The same distinction applies to any
supplied LEGAL or other notice.

After both complete archives pass, setup exclusively creates a notice bundle
containing all three upstream texts and every selected supplied notice, byte
for byte. At most 32 supplied notices and 1 MiB of their combined content are
allowed per package; excess fails, rather than truncating or omitting notices.
The three upstream texts add exactly 28,752 bytes. Nothing is extracted before
the archive validation completes, and these files are not executable inputs.

Setup then verifies that supplied notices also survive installation unchanged
and that the external bundle and its inventory remain exact. The setup phase
receipt additionally binds the bundle manifest and a small retention receipt.
Before later phases, existing completion validation checks those retained bytes
again. A missing, altered, extra, or redirected bundle file, or a missing/altered
installed notice, rejects completion.

The public summary adds only a fixed policy identifier, the manifest's SHA-256
and length, and bounded file/byte counts. It emits no notice text, arbitrary
member name, local path, exception text, environment, header, or new URL. New
steps are fixed enums: `license_provenance`, `notice_bundle`, and
`notice_retention`; the existing `license_notices` step remains. The original
80-event setup limit and 32 KiB total public-summary limit are unchanged.

## Controls and scope

Wheel versions, filenames, URLs, SHA-256 values, compressed sizes, and acquisition
order are unchanged. Both exact wheel downloads remain bounded by one GET each,
no retry/redirect/mirror/proxy fallback, 100 MiB aggregate, and 240 seconds. The
official cached CPython 3.12.14-only requirement, 2 GiB disk/memory floors,
60-second setup/parse/assessment phases, 512 MiB expanded and installed payload
limits, isolated venv, offline ensurepip/pip flags and socket audits remain.

All non-license archive/RECORD/metadata/dependency/tag/dictionary checks remain.
No resource budget is increased to compensate for retention work. The parser
still has 15 CPU seconds, 1 GiB address space, 4 MiB output, exactly 48 calls
(16 exposed diagnostics plus 32 seen examples), no warmup, SplitMode.C, six canon
entries, and the unchanged all-occurrence policy and 16/16 gate. No model, GPU,
translation provider, Hy, product-default change, or Windows performance claim
is introduced. Technical completion and lexical gate success remain distinct.

One exclusive attempt identity, run attempt 1, exact source/event/parent binding,
workflow-only trigger diff, read-only repository permissions, and no retry/reset
controls remain. Job-local controls are not a global exactly-once ledger. Python
socket auditing is not an OS network sandbox; native package trust is unchanged.

This is reviewed **package-source notice preservation for a non-redistributed
diagnostic execution**. It is not legal clearance or a complete native dependency
license audit. Official Rust dependencies include licenses beyond Apache-2.0;
the precise compiled transitive contents have not been inspected. No wheel,
dictionary, interpreter, model, binary, or notice bundle is being distributed by
this source-only preparation, and no legal-compliance claim follows from tests.

## Staged E/F activation review

Protocol: `luna-actions-lexical-license-20261005-v3`.
Branch: `experiment/luna-actions-lexical-20261005`.
Workflow: `.github/workflows/luna-lexical-license-v3.yml`.
The private runtime directory is exactly `$RUNNER_TEMP/` plus the new protocol,
with exclusive EVENT_BINDING.json and RUN_CLAIM.json in that namespace. Neither
prior claim directory is read, reset, replaced or reused.

1. Review the final v3 source, immutable source manifest, exact publication
   allowlist and disabled workflow template. Source E has sole parent the
   current second trigger D2 `2bf3da881b74023ed46750e982991c9423a3bf15`.
   E adds only the new v3 source directory and SOURCE_MANIFEST.json. E adds no
   active workflow and changes no v1/v2/baseline source, manifest or result.
2. After the real source E exists and is independently reviewed, replace only
   the two `__REVIEWED_SOURCE_COMMIT_E__` placeholders in WORKFLOW_REVIEW.yml.in
   with its exact 40-character SHA. Do not guess a source hash or change the
   prepared source-manifest or event-guard hash during rendering.
3. Create workflow-only trigger F with E as its sole parent, adding only the new
   v3 workflow path. Review the rendered bytes, exact F, sole-parent relation
   and complete tree diff before the one E-to-F ref update. E and F remain
   uncreated and unset in this preparation.
4. Both ref updates use the existing approved branch and ordinary non-forced,
   noncreated, nondeleted pushes. The activation event must have before=E,
   after=F, exact public repository/ref/workflow and run attempt 1. The runtime
   guard verifies F HEAD, sole parent E, the single-workflow diff, clean tree,
   exact source inventory and immutable file hashes before preparing packages.
5. Both previous workflows remain byte-identical. Each filters only its own
   distinct workflow path and additionally requires its frozen earlier source
   as event.before. Neither E nor F changes those paths. Reverify these bytes
   and the current D2 branch tip before publication, and preserve both results.

The template remains outside any active workflow directory. Its pinned checkout
and read-only permissions, official cached CPython 3.12.14 without provisioning
or fallback, 240/60/60/60-second phases and 15-minute job cap are unchanged.
It uses no artifact/cache upload or secret inputs. Raw logs, parser output and
notice bundles remain private in the ephemeral job workspace. Only the bounded,
approved sanitized diagnostics and summary may be emitted, with the unchanged
32 KiB summary ceiling.

Stop on any unexpected branch tip, missing runtime, changed baseline, unrelated
diff or failed gate. There is no branch recreation, reset, force push, dispatch,
automatic retry, alternate branch or recovery route. This third independent
experiment does not reclassify either earlier terminal failure.

The new source manifest binds the unchanged public baseline at
`d452ac242211991ddd3439cd451c39e5d988c249`, the v3 files, the reviewed candidate
inventory and prior D2. It excludes itself to avoid a hash cycle. The reviewed
workflow pins its complete SHA-256 and the event-guard SHA-256 before executing
either. Only the exact reviewed E/F publication sequence may activate this
preparation after final review release.

## Fake-only validation and references

Run `python -I -B run_fake_tests.py` here. Its guards prohibit real transport,
process launches, signals, venv creation, ensurepip/pip execution, and native
imports. New tests cover the observed no-legacy-basename shape, exact artifact
identity, missing/tampered/symlink notices, wrong-version and source provenance,
alternate metadata header presentation, recognized notice directories, declared
notice locations, distinct packaged/upstream newlines, retention corruption,
and the full 48-case summary with maximum diagnostics and retention fields.
Existing integrity, resource, event, one-shot, privacy and lexical tests remain.
Activation tests mock both CLI dispatchers and every child-command boundary,
check failure sanitization, and exercise both script entrypoint trailers.
Passing these tests does not establish real setup or parser compatibility.

- Second run: https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37275192309
- SudachiPy source LICENSE: https://github.com/WorksApplications/sudachi.rs/blob/90fd6068c80c2fc3b63e0dbab0e341475bad4d8f/LICENSE
- SudachiPy setup: https://github.com/WorksApplications/sudachi.rs/blob/90fd6068c80c2fc3b63e0dbab0e341475bad4d8f/python/setup.py
- SudachiPy manifest: https://github.com/WorksApplications/sudachi.rs/blob/90fd6068c80c2fc3b63e0dbab0e341475bad4d8f/python/MANIFEST.in
- SudachiDict source LICENSE: https://github.com/WorksApplications/SudachiDict/blob/4813c1cddda74f98a416f92b26d961424ecf8767/LICENSE-2.0.txt
- SudachiDict complete LEGAL: https://github.com/WorksApplications/SudachiDict/blob/4813c1cddda74f98a416f92b26d961424ecf8767/LEGAL
