# Frozen three-way pilot data and scoring rules

Frozen before new source generation. Execution route, model/template checks and
transport controls remain separately pending. No inference is authorized by this
file. Fresh source contents/private criteria remain unseen by the prompt designer.

## Inputs and evaluation

48 cases:24 historical plus24 independently frozen fresh inputs. Historical
selection is mechanically fixed to first, second and last case in each of the
eight original categories, preserving original source bytes. Freeze the selected
IDs and hashes before generating fresh cases. All cases single-line; new sources
<=200Unicode characters. No real user text, personal data or credentials.

Fresh cases use three cases in each of the same eight categories: negation,
passive/causative roles, relationships/referents, boundaries/conditions, omissions,
placeholders/markup, pragmatics and literal text. Sources/private binary criteria
freeze separately before the designer sees cases. The rubric also records natural
Chinese phrasing independently from source fidelity. Valid ambiguity is correct;
unsupported resolution is not rewarded.

An independent reviewer gets source plus randomized anonymous outputs, no arm
mapping, prompts, network/runtime logs or prior ratings. Score all eligible anonymous pairs (A/B, A/C, B/C) after per-output
fidelity, freeze every preference, then select Google-versus-local comparisons
only after arm mapping. Reviewers are never told which anonymous pair contains
Google. Freeze ratings before
mapping. Classify critical error/pass/uncertain; structure separately; naturalness
preference only where both outputs preserve required meaning. Do not treat
uncertain judgments as wins or force them into an accuracy percentage. Score
per-output fidelity first. For each local arm versus Google separately, naturalness
preference is local/Google/tie/uncertain only when BOTH outputs are definite
semantic passes and preserve protected structure. Report eligible-pair coverage
and excluded uncertainty for both comparisons; do not rank all three by style
before checking fidelity. New definite critical means Google definite pass and
local definite fail; any uncertain critical verdict excludes that pair from
definite transitions, while remaining visible in totals.

A local arm can demonstrate a bounded pilot win only with fewer definite critical
errors than Google on fresh24, zero new definite paired critical errors against
Google, no new structural failures, and more naturalness wins than losses among
jointly correct fresh pairs. Report all ties and uncertainty. Historical24 must
show no new definite critical/structural regression against the existing Hy arm
for the Qwen arms. This historical comparator is tautological for Hy itself and
is not presented as an independent Hy quality gate.
If Google has zero critical errors, strict superiority is not established by
this pilot; do not change the rule after seeing the result.


## Exact historical selection

Original40 fixture SHA256051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1.

- negation-01
- negation-02
- negation-05
- passive-01
- passive-02
- passive-05
- relationships-01
- relationships-02
- relationships-05
- boundaries-01
- boundaries-02
- boundaries-05
- omissions-01
- omissions-02
- omissions-05
- placeholders-01
- placeholders-02
- placeholders-05
- pragmatics-01
- pragmatics-02
- pragmatics-05
- literal_text-01
- literal_text-02
- literal_text-05

Fresh public schema: {schema_version:1,cases:[{id,category,source}]}. Exactly24
cases, three per category, unique IDs, single-line source<=200Unicode characters.
Private criteria must enumerate2–4 material facts per case, valid ambiguous
readings, acceptable paraphrases and forbidden inventions. Naturalness judges
Chinese fluency/word choice only after definite semantic fidelity and structure
pass. No required reference wording or style preference may manufacture a
critical semantic error. Preserve uncertainty for genuine ambiguous readings.
