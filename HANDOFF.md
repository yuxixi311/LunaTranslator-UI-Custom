# Development handoff — 2026-10-04

Branch: `codex/local-translation-presets`.

## Latest source change

The small dictionary popup now toggles closed when its active source word is clicked again with either mouse button. Its header shows the word and `已查词` when a result is displayed. A new word still follows the configured lookup/append behavior.

The implementation separates source-word clicks from explicit dictionary-content navigation. It cancels the dismissed viewer's callback identity without stopping shared dictionary engines or erasing cached data needed for full-window/Anki transfer. Mouse-gesture tokens address focus-out-before-release, canceled selections, duplicate callbacks, and a newer source click overtaking an older callback.

Headless tests execute the changed Python methods and browser event handlers with synthetic inputs and fake UI/engines. They do not launch Luna or establish native Windows event ordering or appearance. The exact test commands and native checklist are in [LOOKUP_POPUP_TOGGLE.md](docs/LOOKUP_POPUP_TOGGLE.md).

## Next step and blocker

Run the focused Windows acceptance checklist in a disposable portable copy before producing a binary. Native PyQt/Windows/WebView interaction and visual verification are still pending; the source-only cloud checks cannot certify them. No application release, installer, model weight or user configuration is included in this checkpoint.

The separate local-translation project retains its existing evidence, experimental status and cloud-startup blocker. See the [roadmap](ROADMAP.md) and [translation checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md). This UI change does not execute or alter that experiment.
