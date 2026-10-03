# Terminal three-way pilot and exploratory semantic review — 2026-10-03

The frozen 48-case Google/Hy/Qwen comparison remains **incomplete**. Google produced 40 scored outputs before terminal transport failure. There is no formal winner, no claim of beating Google, no production promotion and no fourth-arm trigger. No further collection or deletion of the one-shot recovery claim is planned.

The separately requested, post-collection masked review supplies a useful narrower decision: retain Hy-MT2-1.8B Q4 as the experimental local baseline. The tested Qwen3.5-2B Q4 deployment produced substantially more definite semantic errors while using more memory and time. This result does not establish a general ranking of model families or their other prompts, sampling settings or languages.

## Evidence and evaluation status

Original source kit: commit `3b7db61fcb6511f7835a86592a958433dbd2b78f`. Both pinned local arms completed 98 template/tokenizer probes, one smoke and 48 scored requests on the same verified runtime, driver and GPU. Hy used full 33/33 CUDA offload; Qwen used 25/25 with thinking explicitly off. The Windows kit discovered 195 tests: 193 passed and two permitted external-source comparisons were skipped. These are harness checks, not whole-application or rendered-UI acceptance.

Google used the unchanged installed provider and original libcurl route. Initial readiness failed. A separately authorized second attempt completed readiness and 14 scored requests, then failed. A separately authorized, independently reviewed fixed-suffix recovery preserved those outputs and collected another 26 before terminal failure. Its 27 fake tests passed. The recovery did not rerun either local arm or replace successful Google outputs.

There are 44 guard-counted attempts, 41 successes including readiness, three transport failures and 40 unique scored Google outputs. Active Google collection totaled 111.609 seconds across the segments. One failed scored case and seven unsent cases remain unavailable; a guard count does not attest that a request reached Google. Failure cause remains unknown. Failures are availability evidence, not invented translation errors. Every failure, successful output and persistent one-shot claim is retained. The original and segmented complete validators still reject the partial dataset.

Both rating files were hash-verified and frozen before mapping. Separate fresh reviewers received only neutral packets and fixed criteria. One reviewed 40 anonymous triples; another reviewed all 48 anonymous local pairs. Labels were independently randomized per case and pack. Keys, timing, model identities, missing-case information and raw artifacts were withheld. The exporter and arithmetic auditor did not score translations. This was **model-assisted review, not human bilingual validation**; provider style may remain recognizable despite label masking.

The full local48 review is primary for local-only conclusions. Common40 ratings are primary only for descriptive comparisons on those observed cases. Repeated local judgments are not extra observations and are neither pooled nor selected for favorable results.

## Primary local48 review

Counts are definite pass / definite material-fidelity fail / uncertain. Uncertainty is retained, not forced into error or success.

| Split | Hy 1.8B Q4 | Qwen3.5 2B Q4 |
| --- | --- | --- |
| Historical24 | 18 / 3 / 3 | 10 / 12 / 2 |
| Fresh24 | 19 / 1 / 4 | 7 / 15 / 2 |
| All48 | 37 / 4 / 7 | 17 / 27 / 4 |

For reviewed protected structure, Hy has 47 pass / 1 fail / 0 uncertain; Qwen has 42 / 5 / 1. The independent mechanical checker reports Hy one failure and Qwen four. These are distinct measures: reviewer judgments can address literal-span meaning or spacing beyond the mechanical token/tag/newline checks. Neither arm had a mechanical newline-count failure.

Naturalness is eligible only when **both outputs definitely pass fidelity and structure**:

| Split | Eligible / total pairs | Hy preferred | Qwen preferred | Tie | Ineligible |
| --- | --- | --- | --- | --- | --- |
| Historical24 | 8 / 24 | 4 | 1 | 3 | 16 |
| Fresh24 | 6 / 24 | 4 | 1 | 1 | 18 |
| All48 | 14 / 48 | 8 | 2 | 4 | 34 |

No eligible pair in this primary review received an uncertain naturalness preference. Relative to Hy's definite fidelity passes, Qwen has nine historical and ten fresh definite failures; there are zero opposite definite fail-to-pass cases. These are observed paired transitions, not a substitute adjudication of the incomplete original three-way gate.

Hy's four definite fidelity failures are concentrated in passive/causative roles (two) and relationships/recipient or ownership relations (two). Uncertainty also remains around pronoun reference, event status and exact age/time boundaries. The familiar causative/role errors have not been fixed by simply completing the new run. Its protected-placeholder failure also remains visible; the application integrity guard can reject such output, but rejection is not semantic improvement.

Qwen's definite fidelity failures span negation4, passive4, relationships3, boundaries2, omissions3, placeholders4, pragmatics4 and literal_text3. Reviewer explanations identify changed actions or conditions, lost or altered named roles, omitted content, and damaged literal/protected content. This breadth does not support treating the result as one isolated formatting issue. It also does not identify the causal contribution of quantization, training, template or sampling: the comparison used each model's declared official deployment policy, one seed and one output per input.

## Exploratory common40 comparison

Common40 contains all historical24 but only fresh16. Observed fresh coverage is negation, passive, relationships, boundaries and omissions three each, plus placeholders one. Missing fresh coverage is placeholders two, pragmatics three and literal_text three. This ordered, transport-truncated subset is category-skewed; independence of missingness from source content is unknown. Do not extrapolate to fresh24 or reweight absent categories.

| Split | Google fidelity P/F/U | Hy fidelity P/F/U | Qwen fidelity P/F/U |
| --- | --- | --- | --- |
| Historical24 | 19 / 3 / 2 | 19 / 3 / 2 | 10 / 14 / 0 |
| Observed fresh16 | 13 / 2 / 1 | 11 / 1 / 4 | 5 / 10 / 1 |
| Common40, descriptive only | 32 / 5 / 3 | 30 / 4 / 6 | 15 / 24 / 1 |

Reviewed structure failures on common40 are Google1, Hy1 and Qwen2, with no structure-uncertain judgments. Hy's one fewer definite fidelity failure than Google is not a win: it has more uncertain judgments, and Google-pass/Hy-fail versus Google-fail/Hy-pass transitions are 2/2 on historical24 and 1/1 on fresh16. Qwen's corresponding transitions against Google are 11/1 and 8/0.

| Pair and split | Eligible / total | First preferred | Second preferred | Tie | Ineligible |
| --- | --- | --- | --- | --- | --- |
| Google / Hy, historical24 | 14 / 24 | 9 | 2 | 3 | 10 |
| Google / Hy, fresh16 | 9 / 16 | 6 | 0 | 3 | 7 |
| Google / Qwen, historical24 | 8 / 24 | 4 | 1 | 3 | 16 |
| Google / Qwen, fresh16 | 5 / 16 | 4 | 1 | 0 | 11 |
| Hy / Qwen, historical24 | 9 / 24 | 5 | 3 | 1 | 15 |
| Hy / Qwen, fresh16 | 5 / 16 | 4 | 1 | 0 | 11 |

There are 50 eligible pair judgments across all three pair types; they are not 50 independent source cases. None received an uncertain preference. No pooled historical-plus-fresh winner or statistical-superiority claim is made.

## Reviewer disagreement is preserved

On the same40 local outputs, Hy has one fidelity disagreement: pass in the triple review versus uncertain in the primary local review. Its structure ratings agree. Qwen has four fidelity disagreements: two pass→uncertain, one fail→pass and one fail→uncertain, plus one structure pass→uncertain. Local-pair eligibility differs on four cases. Among the 11 local pairs eligible in both reviews, two preferences differ, each becoming a tie in the primary review. These remain independent judgments; no favorable rating was substituted and no post-unblinding regrading was used.

## Measured cost and limits

| Measurement | Hy 1.8B Q4, 48 cases | Qwen3.5 2B Q4, 48 cases |
| --- | --- | --- |
| Pinned model bytes | 1,133,080,448 | 1,280,835,840 |
| Median local request | 108.657 ms | 150.919 ms |
| Nearest-rank P95 | 192.972 ms | 247.614 ms |
| Peak owned-process RSS | 1.590 GiB | 3.204 GiB |
| Startup | 1.245 s | 1.445 s |
| Post-readiness phase | 6.634 s | 8.572 s |
| Per-PID VRAM | Unmeasured | Unmeasured |

Qwen's median is 38.9% higher, P95 28.3% higher and measured RSS about 2.02 times Hy's in this run. Both local startup/post-readiness budgets and resource guards passed. These standalone GPU results are not low-end-hardware certification or total application memory measurements.

The 40 successful Google scored requests have median provider/parse time 343 ms and P95 406 ms. This excludes fresh-host startup and failed calls, and uses a different available subset from the local48 table. It is neither GPU inference time nor the installed application's cache performance. The 111.609-second active-collection figure includes pacing and failed-worker time; wall-clock gaps between segments are separate. The remote backend/version is undisclosed. Do not use this table as an equal-environment speed ranking.

## Decision and next work

Keep Hy as the small experimental reference; do not replace it with the tested Qwen policy or promote any new default. The evidence supports concentrating further quality work on causative/role direction, named recipients and exact boundaries. It does not show that another generic instruction sentence will fix these issues: the earlier prompt and source-context trials remain rejected.

A future bounded glossary/name-preservation study could address a narrow, explicitly supplied terminology problem, but cannot be presented as a solution to Japanese causal grammar. It would require a separately frozen plan, independent cases and cost measurement before any run. Training or fine-tuning would be a separate data, hardware and validation project; none has been done here. No further model download, online collection or fourth arm follows automatically from this report.

The existing 1.13-GB model requirement is still substantial and has not been reduced. Keep weights optional, explicitly downloaded/imported and removable; do not bundle them into the learning translator. Smaller weights or quantization changes need their own quality evidence. Human bilingual adjudication and the remaining Windows application/packaging checks remain prerequisites for a release-level quality claim. See the [updated roadmap](LOCAL_TRANSLATION_TEST_PLAN.md#2026-10-03-terminal-three-way-pilot-and-current-roadmap).

## Audit anchors and publication scope

- Post-collection analysis plan SHA-256: `d33ffc12e3734a6e38ba0fdbcd9c36ea46f1dfe9fd2cd55b682f902b85903ae3`
- Frozen triple ratings: `b3d7b3b42c126664a16392a57eadb7282d7f9b28782f6e77a956d622c091b84d`
- Frozen local-pair ratings: `91b51716ca22dca5b5d5628fc403062c83c0c20258b7cc8d58daf892ca0fa7f1`
- Terminal archive: `ab1c417f4bddd6b36202678c223fa852994b342b87f72f13ea9837a9d83d34e1`

Independent audits verified packet membership, exact output/criteria projection, both rating hashes, full schema and pair eligibility, all mapped counts and paired transitions, and preserved reviewer disagreement. These are evidence-consistency checks, not independent human truth labels. This report publishes sanitized aggregate findings only: no private criteria, complete fresh source/output, arm key, machine path, credential, raw runtime log or model weight is included.
