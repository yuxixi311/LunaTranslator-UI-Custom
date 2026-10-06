# Selected bounded scope before fixture authoring

This source-only scope selection narrows the conditionally reviewed proposal
whose SHA-256 is 9e2061fbe68c6607e90cb5c8c80195e81c9539ba0faa10b532307f3a7184cf43.
It does not authorize acquisition or inference, change the matching mechanism,
or relax a quality, coverage, latency, token, memory or cleanup gate.

## Fixed populations

- 32 newly and independently authored source rows, with private source-only criteria held by root
- All 40 published historical regression rows
- All 15 root-selected previously seen rows, without ratings or answers

The root-held source-only pack has SHA-256
77242de79d1469082117fb5ad93ea5dab6e042501baffd0e68c500a66b2fdf6d.
It must remain unread by the implementer until the bank and matcher are frozen.
No neutral row is added merely to reach a ceiling. M is therefore exactly 87
paired rows and the generation inventory is exactly 174 completions.
All old rows remain seen regressions and receive no fresh-improvement credit.

## Request bound

After all public source rows are fixed, compute E using only the frozen surface
matcher, before token-budget admission and without outputs or private criteria.
Freeze the exact request inventory and membership before launching:

- 174 preflight token-count requests
- 2E measured candidate token-count requests, including eventual token-budget fallbacks
- 174 translation completion requests
- One health and one model-identity request

The exact total is 350 + 2E. Require E <= 46 so the previously established total
ceiling of 442 loopback requests is not expanded. If it does not fit, stop before
launch and report the scope conflict; do not prune sources, change the matcher,
replace examples or omit accounting to fit the ceiling.

No additional token-only experiment, calibration generation, warm-up generation,
retry or output selection is included. Full token and coverage preflight still
precedes the first completion. The parent proposal's 530-request theoretical
maximum is not the selected execution scope.

## Token and cost ceilings

For the fixed 174 completions, the derived generation prompt-token ceiling is
174 x 384 = 66,816 and the derived generated-token ceiling is
174 x 512 = 89,088. Existing model context, counting validation, byte limits and
phase/resource deadlines remain required; token admission does not create any
extra request or generation allowance.

The example addition remains Delta = C - B <= min(16, floor(0.40 x B)), measured
on complete applied chat templates, with candidate C <= 384. Invalid baseline
counts or counting failures stop the attempt; an over-budget valid candidate
returns the unchanged baseline request for that row. Frozen coverage gates must
still pass, and every row remains in its original evaluation population.

Median and nearest-rank P95 of paired row-wise candidate/baseline end-to-end
elapsed ratios must remain <= 1.25 for every required population. Actual model
cost and translation quality remain untested. The token bound is a screening
constraint, not a prediction that the elapsed-cost gate will pass.

## Data and publication boundaries

The conditioning bank comprises eight licensed Wikibooks educational examples,
with complete originals, declared Traditional-to-Simplified adaptations,
attribution, license notices and source-capture provenance. It is not represented
as professionally validated or as original synthetic source text. Only the small
runtime projection enters prompts; attribution/provenance does not.

Any proposed public experiment source must include the required CC BY-SA 4.0
notices for that bank and its adaptations, public fictional evaluation sources,
and code/tests. Root-owned criteria, ratings, arm keys and real user content are
excluded. No source publication or live workflow is released by this selection.
