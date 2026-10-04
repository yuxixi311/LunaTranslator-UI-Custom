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

The popup work does not change translation providers, model settings, lexical experiments or quality conclusions. Hy1.8B remains experimental; the supplied-glossary round remains inconclusive. The separate cloud lexical feasibility probe is blocked before execution.

Continue the existing [local-translation decision path](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md#next-development-path) and [acceptance plan](docs/LOCAL_TRANSLATION_TEST_PLAN.md). Do not promote a model, run a new comparison, switch execution routes, or treat UI tests as translation-quality evidence.
