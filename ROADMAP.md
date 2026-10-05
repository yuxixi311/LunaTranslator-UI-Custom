# Development roadmap

This branch contains development source and checkpoints, not a new binary release.

## Small dictionary popup

- [x] Show the current word and a queried status in the popup
- [x] Close the active lookup on another left or right click on the same source word in the same sentence, including while the lookup is pending
- [x] Preserve different-word lookup, right-click append, dictionary links, full-window lookup, copy actions, and existing settings
- [x] Invalidate late dictionary results after closing; correlate source mouse gestures across focus-loss and asynchronous renderer callbacks
- [x] Add headless popup/renderer regression checks and independent code review
- [ ] Run the focused native Windows/PyQt/WebView acceptance checklist before packaging a binary

See [popup behavior, verification and remaining acceptance](docs/LOOKUP_POPUP_TOGGLE.md).

## Local translation

Hy1.8B remains experimental; the supplied-glossary round remains **inconclusive**. The separate cloud lexical probe has now completed 48 CPU parsing calls, but its frozen lexical gate **failed at 14/16 (required 16/16)**. Workflow success records execution, not quality acceptance. No new translation or GPU comparison ran.

See the [2026-10-05 lexical result and decision](docs/LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md), including the three separate Actions attempts, measured costs and evidence limits. The [2026-10-04 checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md) remains the historical source/launch record; its blocked-execution status is superseded by the new result.

- [x] Complete the fixed 16-diagnostic / 32-seen CPU lexical probe and record its failed gate
- [ ] Analyze whether a materially different general mechanism is justified; no supported low-cost replacement is ready yet, and the frozen failures and seen regressions must be preserved
- [ ] Only for a justified new candidate, preregister the rule, costs, unchanged 16/16 diagnostic gate and a new independently authored semantic holdout before considering a reviewed same-model GPU trial
- [ ] Complete the remaining [translation acceptance plan](docs/LOCAL_TRANSLATION_TEST_PLAN.md) before any release-level claims

Do not promote or schedule GPU evaluation of the unchanged failed lexical rule. The maximum of three Hy optimization rounds is a ceiling, not a quota; the three Actions setup/execution attempts are not three semantic optimization rounds. Keeping baseline is a valid decision. The popup's native Windows acceptance remains pending, and UI tests provide no translation-quality evidence.
