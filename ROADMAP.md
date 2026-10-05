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

Hy1.8B remains an optional experimental baseline; the supplied-glossary round remains **inconclusive**. The GiNZA 5.2.0 NER candidate now installed and completed all 73 planned CPU calls after the bounded plac compatibility correction. Its resource gates passed, but both frozen admission gates **failed: 14/16 historical diagnostics (required 16/16) and 16/24 fresh cases (required 24/24)**. No Hy translation calls or GPU comparison ran.

See the [2026-10-05 NER result and decision](docs/LOCAL_TRANSLATION_NER_RESULT_20261005.md) for the completed installation, separate infrastructure attempts, measured Linux costs and evidence limits. NER removed the two historical false activations but lost two expected person entries. On the fresh set it missed 8 of 11 expected entries; all 14 expected-abstention cases passed, while only 2 of 10 positive cases matched completely. This is not a robust optimization or a translation-quality improvement.

The [earlier POS lexical result](docs/LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md) and [2026-10-04 checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md) remain historical records. The latest checkpoint adds the completed NER run and its failed admission results while preserving earlier launch/setup failures and semantic uncertainty.

- [x] Complete the fixed 16-diagnostic / 32-seen POS lexical probe and record its failed gate
- [x] Complete the pinned 49-wheel structural audit, retaining its plac compatibility finding and runtime/legal limits
- [x] Complete the 73-call CPU NER run and record both failed admission gates, measured costs and aggregate offline fresh assessment
- [ ] Revisit optimization only if a materially different generalizable mechanism is justified; preserve genuine-name recovery, abstention obligations and existing failures
- [ ] Only for such a candidate, preregister the rule and costs, retain the historical gate, and freeze a new independent holdout before considering a separately reviewed same-model GPU trial
- [ ] Complete the remaining [translation acceptance plan](docs/LOCAL_TRANSLATION_TEST_PLAN.md) before any release-level claims

Do not promote or schedule GPU evaluation of either unchanged failed admission rule. The fresh 24 cases are now exposed regression material. Generic prompt loops, a larger model and training are not justified next steps by this result. The maximum of three Hy optimization rounds is a ceiling, not a quota; infrastructure attempts and the archive audit are not semantic optimization rounds. Keeping baseline is a valid decision. The popup's native Windows acceptance remains pending, and UI tests provide no translation-quality evidence.
