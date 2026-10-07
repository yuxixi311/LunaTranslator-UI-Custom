# Hy1.8B explicit-name glossary pilot — frozen design before fresh authoring

Status: source/design preparation only. No new model execution is authorized by this document. The parent coordinates a separately approved desktop window after implementation, review and consumer verification. Existing defaults remain unchanged. Use only the existing pinned Hy-MT2-1.8B Q4; no Qwen, fourth model, larger weights, quantization change, training, paid API or real user text.

## Hypothesis and one factor

The existing explicit terminology path may reduce definite name-as-common-word errors and loss of explicitly named participants. It is not a general remedy for causative/passive grammar, relationship direction or omitted context. Prior generic instruction variants and source-context injection remain failed experiments; this does not repeat them.

A uses the unchanged ordinary translation-only prompt. B adds the existing official terminology reference block for literal matches from a fixed fictional-project name canon. Raw Japanese source, model, chat template, sampling, seed and output protocol are otherwise identical. No previous source/translated history, few-shot example, automatic entity inference, output replacement or repair is used.

This is an input-policy test of an already implemented feature, not a new model capability. Official terminology support is documented in Tencent's 1.8B card at revision `9a341cd1b679d3efd23b46e847b01745a71ed792`; weights remain the previously pinned GGUF repository revision `b27182d810fa3ceb6ed04e7c324c54e35c0d209c`.

## Canon, matcher and exact rendering

Canon SHA-256: `7cc5bdb3626dd4e781070dca708428c0ef81048d72b067a71f9e15c795814337`. It was independently created before any new source/reference case: 光→光, 翼→翼, 蓮→莲, 桜→樱, 泉→泉, 遥→遥. It contains only explicit name renderings and a neutral project description, with no plot, role, recipient, context or reference-answer facts. It simulates a user/project-supplied dictionary. Never infer entries from held-out answers or select a custom dictionary for each sentence.

Match all entries against the original source in stored order using the current escaped-literal `re.search` path: `case-sensitive=false`, `whole-word=false`. No oracle removal of ordinary-word or subword matches. The fixed canon has unique nonempty source/destination strings and no overlap, newline, control or instruction syntax. Any unexpected canon modification, duplicate, empty or invalid entry stops preflight. Report all matched entries/counts, including inappropriate homograph activation. No-match B must be byte-identical to A.

The exact baseline user content is:

`将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}`

For a nonempty match set, B is:

`参考下面的翻译：\n{entries}\n将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}`

Each entry is exactly `{src}翻译成{dst}`, joined with a single newline. This mirrors `hymt2_make_messages`/`make_gpt_dict_text(..., needinfo=False, split="翻译成")`; no comments are passed. With Japanese source, current Chinese-conversion logic leaves the declared destination strings unchanged. Prove equivalence with the actual existing matcher/prompt methods using fake dependencies. The tested source is `rawtext`, never the placeholder-rewritten intermediate or a post-replacement result.

## Fixed sample size and split

Use 32 paired sources: eight already-seen regressions plus 24 genuinely new independently authored cases. All previous fresh sets are now seen and cannot be described as new holdout.

The seen regressions are fixed to original40 IDs: passive-02, passive-05, relationships-02, relationships-05, boundaries-02, omissions-05, placeholders-05 and literal_text-01. Their fixture SHA remains `051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`. These are only regression checks, never fresh improvement evidence.

New24 is authored only after this protocol/canon freeze:

- 6 target cases using the canon's ordinary-word name forms in source-unambiguous person contexts
- 6 target cases with explicit named recipients/agents/patients whose identities and direction are stated by the source
- 4 ordinary named-entity controls
- 4 matched ordinary-word/subword homograph negative controls
- 4 no-match grammar/format controls

Use natural fictional Japanese, one line and at most 200 characters. No real user text. Each target has an independently declared entity/name-form ID and scenario ID before inference. Two paraphrases of the same name/scenario do not count twice as independent success contexts. Include at least two distinct entities/name forms across qualifying improvements. No-match controls contain none of the literal canon keys. Negative controls must still activate the real matcher. Preserve these strata before outputs. Programmatically reject exact overlap with previous source fixtures; do not expose private criteria to prompt designers.

The source-only factual rubric and valid-reading guidance are frozen by the independent author before outputs. Every source is judged by what it actually states. A valid literal name rendering, or a common-word reading permitted by the source, cannot become a baseline error merely because the reviewer later sees the canon. Canon-only informational benefit is reported separately and excluded from the semantic-improvement gate.

## Execution and bounded cost

Use the original Hy Q4 bytes/hash, b11349 runtime, official Hy template, existing exact-loopback CORS restriction, full33/33 CUDA proof, one owned process, context2048, threads2, batch/ubatch128, one slot and no runtime warmup. Keep model-bytes+2300MiB RAM and model-bytes+1024MiB VRAM preflight, continuous resource guard and owned-process cleanup. Per-PID VRAM stays unknown when unmeasured.

Use temperature0.7, top_p0.6, top_k20, repeat_penalty1.05, min_p0.05, repeat_last_n64, seed42, max_tokens512, cache_prompt=false and stream=false for every request. No hidden cache reuse, history, retries or additional model passes. One request per arm per source.

Pair order is fixed before inference: within the eight regression cases alternate AB/BA, four each; within each fresh stratum alternate AB/BA, yielding 12 each across fresh24. Total16 AB and16 BA. Source order and pair order are exported before execution and not changed based on outputs.

Startup watchdog remains180 seconds. A separate180-second post-readiness watchdog covers all probes, smoke and scored requests. There are 65 request prompts: one fixed no-match smoke plus64 scored prompts. Each has one apply-template and one tokenize call: **130 probes before any completion**, then one smoke and64 scored completions. The smoke is exactly `これは翻訳の接続確認です。`; both arms' no-match prompt is identical. Apply the established nonempty/Han/no-kana/no-reasoning/normal-stop sanity gates. Record actual returned prompt-token counts and require equality to preflight.

Every applied prompt, including template and generation prefix, must be <=384 tokens; B−A must be <=64 tokens per pair; B may use at most four matching entries. Any violation stops the entire run before the first completion. Do not trim entries, silently fall back, change sources or drop a case to fit a bound. Template, token, runtime, resource or response-integrity failure makes the experiment technically incomplete. Preserve raw outputs; structural/semantic errors are recorded for review, never stripped to manufacture success.

## Masked review and eligibility

Use independently randomized anonymous A/B presentation per case. Primary review sees source-only criteria and exact outputs, not canon, input prompts, timings, model condition or prior results. Record and freeze primary fidelity, protected structure, uncertainty and eligible naturalness judgments first. Then the same reviewer may see the canon solely for a separate canonical-compliance field; primary ratings must not change. Map identities only after all ratings freeze. Canonical names may reveal treatment; label masking is not a guarantee of treatment blinding.

Primary fidelity is source-only for both arms. Source-permitted name variants/readings pass. A retained name assigned to the wrong role is still a material error. Score canonical compliance separately; preferred-alias conformity and uncertain→preferred-name changes do not count as semantic fixes. Naturalness is eligible only when both outputs definitely pass fidelity and structure; report all ties, exclusions and uncertainty.

Fresh semantic eligibility requires at least two baseline definite targeted-error→B definite-pass resolutions, covering at least two distinct entities/name forms and distinct source scenarios in the predeclared fresh target strata. Count each context once. Require zero new definite critical errors and zero new definite structure failures across all32 (A definite pass→B definite fail), and zero B glossary/instruction or irrelevant-entity contamination in the negative-control stratum. No deterioration on homograph controls is acceptable. Material uncertainty that could change eligibility makes the result inconclusive, never a win. If A has no definite target errors, report inconclusive rather than relaxing the requirement.

Require B/A median and nearest-rank P95 latency ratios <=1.25 on the exact same paired sources, both overall and matcher-active subsets. No posthoc exclusions. Report active counts and each stratum, prompt/output tokens, probe/startup cost, RSS and measured/unknown VRAM separately. No-match pairs repeat identical prompts: any differences are execution/sampling variability, not glossary benefit. Keep the unchanged resource gates; no peak-memory reduction is presumed.

Technical incompleteness, any definite failed eligibility condition, or inconclusive uncertainty stops promotion of this candidate. Do not search for favorable seeds, wording or subsets. A successful pilot would support only this bounded explicitly supplied-glossary use case, not correction of all passive/role errors or superiority to Google. No new online comparison, fourth model or default change follows automatically.
