# Frozen public scientific decision protocol

The following gate text is reproduced verbatim from the original mechanism DESIGN.md,
SHA-256 `179908ab59331b8fac13b8248d0849832b06beccf9236aba2ee43dbb6f0e84fc`. It contains public decision rules, not private row criteria.
No scientific gate is changed. The implementation pins all actual public source
and lexicon bytes separately. The population is 48 fresh rows plus 40 exposed
legacy regressions, one baseline/candidate pair each, with every row retained.
The exact 44/44 AB/BA pair schedule and all source identities are fixed in code.

The operational amendment specifies perf_counter_ns for the authoritative elapsed
interval and enumerates 442 total requests including 176 measured completions.
It also explicitly changes the original private-arm blinding arrangement to
transparent public arm evidence and later fresh label/order review packets.
Public accessibility means treatment blinding is not guaranteed; reviewers must
not look up external results. These are declared operational/review amendments,
not relaxed quality, coverage, uncertainty or resource gates. The candidate has
not produced any real result in this source-only preparation.

## Coverage gate, before any model output

Before any model output, publish hint-active decisions and coverage counts.
Require ≥18/24 contrasting rows active, with BOTH contrasting rows active in
≥8/12 families, and at least one such complete pair per headword (≥2/4 contrast
rows for each of six headwords). Require at least one active ambiguous row per
headword (≥6/12). The eight potentially active control rows above must all be
active; the two no-match and two multiple-key rows must all use exact NO_HINT.
Coverage failure makes the fixed study inconclusive, not an invitation to edit
the frozen mechanism/inventory or quietly omit difficult rows.


## Qualifying fixes and quality decisions

For a fresh, hint-active, source-resolved row, a qualifying fix requires BOTH:
(a) baseline has a definite critical lexical error on the matched headword;
(b) candidate is a definite faithful pass for the whole row, including that sense,
negation, participants and structure. Count one fix per qualifying row, then
count distinct matched headwords. Improvements only to non-headword errors,
inactive rows, legacy rows, minor wording, or unresolved judgments do not qualify.

Proposed advance gate: ≥2 qualifying fixes on ≥2 distinct headwords, zero new
critical errors and zero new structural failures across ALL 88 rows, coverage
passed, and all resource gates passed. A critical or structural regression means
candidate is a definite failure on a dimension baseline definitely passes; moving
an old error to a different dimension still counts. Report remaining baseline and
candidate failures even when neither qualifies as a new regression. Unsupported
claims of universal translation gain are forbidden for this small diagnostic.

Any source-permitted reading of an ambiguous row can be faithful. A legitimate
unlisted sense is never wrong merely because it is absent from the inventory.
Ambiguity must not be assigned an invented single correct gold sense. Material
uncertainty about a fix, regression, structure or coverage → INCONCLUSIVE unless
another already-definite gate failure determines failure. If everything is
adjudicated but there are fewer than two fixes, the advance gate fails; do not
search another prompt. Compare naturalness only where BOTH outputs are definite
faithful passes; fluency never offsets semantic or structural harm.


## Resource, paired-cost and invalid-measurement decisions

Target helper peak RSS ≤32 MiB and warm lookup/render P95 ≤5 ms. Measure helper
RSS including its interpreter and loaded sidecar in an isolated process, excluding
the already-loaded main model/tokenizer. Report token-count overhead separately
and include it in candidate end-to-end latency. No extra model calls or downloads.
CPU-only standard library lookup does not imply either measured bound has passed.

For each complete row i, cost ratio is candidate total monotonic elapsed time
divided by baseline elapsed time, including local hint preparation/token counts,
model generation and unchanged output guard. Ratio P95 uses nearest rank at
ceil(0.95*n); median is the middle value or the mean of two middle values. Report
median/P95 of paired ratios for all 48 new rows, active new rows, all 88 rows and
all active rows. Every one of these four strata must have median and P95 ≤1.25.
Also report raw latency distributions, output/prompt token counts and AB/BA
breakdowns; never substitute ratio-of-medians for these paired ratios. Zero,
nonfinite, missing, timeout-truncated or timer-resolution-limited measurements
are invalid; an empty active stratum cannot pass. The run is incomplete or
inconclusive, never repaired by dropping rows. Material order/noise uncertainty
also makes the cost conclusion inconclusive. Timing resolution/environment
stability and exact lookup measurement boundaries still need operational review.

The 384-token cap covers the whole chat template. A hint exceeding 64/384 falls
back to ordinary baseline translation and remains scored. A BASELINE over384,
unknown tokenizer/chat template, or unavailable/failed real token counter blocks
the full run at preflight, rather than silently dropping a paired case. If such
a defect appears after generation begins, stop and mark the study incomplete.
Only pre-output validation can establish whether the fully frozen study is runnable.

