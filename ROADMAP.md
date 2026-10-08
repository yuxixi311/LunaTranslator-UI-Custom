# Development roadmap

This branch contains development source and checkpoints, not a new binary release.

## 2026-10-08 当前接续节点

最新总览：[当前状态、失败与证据边界](docs/LOCAL_TRANSLATION_CHECKPOINT_20261008.md)、[分阶段路线](docs/LOCAL_TRANSLATION_ROADMAP_20261008.md)、[新本地对话交接](docs/LOCAL_TRANSLATION_LOCAL_HANDOFF_20261008.md)。历史结果不被本次归档替换。

当前仍维持可选 Hy1.8B baseline；尚无获证改善的候选。LoRA 仅进入数据与运行环境可行性研究，未训练、未证明 12GB 可行。Windows Torch 的两次实际 GET 均失败，尚无完整 wheel 或静态检查成功。新的 append-only journal 候选通过 410 项新鲜 fake 检查，但尚未产生真实 Windows 网络运行证据。

下一步限于核对现有 ZIP、精确源码/测试绑定和本地消费标记，按用户已明确批准的原范围进行至多一次指定 Torch GET 与静态检查。历史准备包未含 execution-authorization.json；操作员需先核对授权适用性再写入精确绑定，不能把这份公开文档当作授权。不得重用旧 attempt、自动重试、安装软件、下载模型或训练。成功后才准备完整依赖闭包与隔离安装方案；失败则保留证据并报告首错和保留状态。

## Small dictionary popup

- [x] Show the current word and a queried status in the popup
- [x] Close the active lookup on another left or right click on the same source word in the same sentence, including while the lookup is pending
- [x] Preserve different-word lookup, right-click append, dictionary links, full-window lookup, copy actions, and existing settings
- [x] Invalidate late dictionary results after closing; correlate source mouse gestures across focus-loss and asynchronous renderer callbacks
- [x] Add headless popup/renderer regression checks and independent code review
- [ ] Run the focused native Windows/PyQt/WebView acceptance checklist before packaging a binary

See [popup behavior, verification and remaining acceptance](docs/LOOKUP_POPUP_TOGGLE.md).

## Local translation

**The latest deterministic term-lock candidate has no demonstrated advantage and is not promoted.** The [2026-10-07 term-lock result](docs/LOCAL_TRANSLATION_TERM_RESULT_20261007.md) records 88 observed pairs, 176 retained raw outputs and 173 accepted final texts, but an operationally incomplete run. On the only newly semantically reviewed population, fresh19, both arms had 13 faithful outputs; the candidate introduced one structural rejection of a faithful baseline case and demonstrated zero faithful canonical fixes in zero families. Two independent label-blind model-assisted reviewers agreed on all 38 fresh fidelity labels; this is not human validation or guaranteed treatment concealment. Observed timing quantiles passed, while aggregate cleanup/protocol flags remained false and helper resource/lifecycle success was unestablished. Existing providers, defaults and UI v1.0.1 remain unchanged.

**The earlier short-example candidate is NO_GO before generation.** Only two of 24 eligible rows fit the frozen added-token budget, leaving two active carriers, one family and no challenge-type coverage. All 176 readiness/count requests completed; zero translation completions were issued. The [short-example result](docs/LOCAL_TRANSLATION_USAGE_RESULT_20261006.md) preserves the independent arithmetic and separate aggregate cleanup uncertainty. No semantic or paired-cost result is claimed.

**The earlier completed sense-prefix experiment is FAIL_NO_PROMOTION.** All 176 translations and 442 planned requests completed, but both the frozen end-to-end cost gate and semantic acceptance failed. Hy1.8B remains the optional experimental baseline; existing providers, defaults and UI v1.0.1 remain unchanged.

See the [2026-10-06 sense-prefix result and decision](docs/LOCAL_TRANSLATION_SENSE_RESULT_20261006.md). On the fresh 48 cases, two independent model-assisted reviews recorded 39 definite baseline whole-row passes each, versus 35 and 34 for the candidate. They agreed on two definite baseline-pass-to-candidate-failure regressions and zero definite critical-failure-to-whole-row-pass fixes. Disputed and uncertain cases remain retained. Reviews were label-blind after public arm-identified execution, without guaranteed treatment blinding or professional human validation.

The fresh paired row-ratio median was 1.4155785885060757 and nearest-rank P95 was 1.6367162196176535 against the frozen 1.25 ceiling. Every required population failed at least one cost statistic. Passing helper-resource gates and successful execution do not override these failures. The measurements are CPU-only and establish no Windows/GPU performance claim.

The [NER result](docs/LOCAL_TRANSLATION_NER_RESULT_20261005.md) remains a completed 73-call CPU probe with failed 14/16 historical and 16/24 fresh admission gates. The [POS lexical result](docs/LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md), [inconclusive supplied-glossary round](docs/LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md), [2026-10-04 checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md), and earlier failed prompt/context results remain historical records, including their infrastructure failures and semantic uncertainty.

- [x] Complete the fixed POS lexical probe and record its failed gate
- [x] Complete the pinned 49-wheel structural audit, retaining its compatibility and runtime/legal limits
- [x] Complete the 73-call CPU NER run and record both failed admission gates
- [x] Complete the 88-pair sense-prefix CPU comparison, independently audit operational accounting and costs, and record its failed semantic and cost decision
- [x] Freeze and test the sparse licensed bilingual-example candidate; record token-feasibility NO_GO without generation, budget relaxation or rerun
- [x] Review grounded speaker/context provenance; current inspected adapters lack a defensible same-record speaker/body contract, so this method remains NO_GO pending that prerequisite, not a measured quality failure
- [x] Freeze and run the bounded deterministic term-lock comparison; retain its failed candidate, independently checked accounting, fresh19 semantic aggregates and separate operational incompleteness
- [ ] Keep the optional baseline, or prepare a bounded feasibility proposal for curated licensed parallel training data and a small LoRA; establish provenance, held-out evaluation, costs and measured hardware feasibility before any execution
- [ ] Repair precise coverage-failure and helper-lifecycle reporting separately with synthetic regressions; retain the original failed records
- [ ] Before any new run, preregister the mechanism and costs, preserve historical regressions and uncertainty, and freeze new independent fixtures with a separately reviewed execution plan
- [ ] Complete the remaining [translation acceptance plan](docs/LOCAL_TRANSLATION_TEST_PLAN.md) before release-level claims

Stop promotion of the unchanged failed sense prefix, POS rule and NER admission rule; do not advance them to GPU evaluation. The sense experiment's fresh 48 cases, like the earlier fresh sets, are now seen regression material and cannot serve as another untouched holdout. No larger generator or auxiliary sense model, training, paid API or generic prompt loop follows from these results. The earlier maximum-of-three plan remains historical; the owner subsequently authorized sequential, separately frozen methods. That does not authorize retries after failure or relaxing a failed gate. The currently examined sequential methods are exhausted: supplied glossary inconclusive; grounded context blocked by source provenance; microexamples blocked by token/coverage feasibility; sense-prefix and GiNZA-derived POS/NER work without demonstrated general benefit; term lock without incremental advantage. Keeping baseline is a valid decision. A curated licensed parallel-data and small-LoRA feasibility proposal is the only new bounded research option recorded here: no download, GPU run or training is released by this checkpoint, no training has been completed, and fit within 12 GB is unmeasured. Do not force another inference round or tune against the now-seen fresh19. UI checks provide no semantic evidence.

