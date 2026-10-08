# Development handoff — 2026-10-08

Branch: `codex/local-translation-presets`.

## 当前交接入口

本次是源码、证据和接续说明归档，不是新二进制发行。翻译工作请先读 [10 月 8 日总节点](docs/LOCAL_TRANSLATION_CHECKPOINT_20261008.md)、[完整后续路线](docs/LOCAL_TRANSLATION_ROADMAP_20261008.md) 和 [新本地对话交接](docs/LOCAL_TRANSLATION_LOCAL_HANDOFF_20261008.md)。UI v1.0.1、已有 providers、默认配置和可选 Hy1.8B baseline 保持原状。下面保留 UI 实现与原生验收待办。

## Latest source change

The small dictionary popup now toggles closed when its active source word is clicked again with either mouse button. Its header shows the word and `已查词` when a result is displayed. A new word still follows the configured lookup/append behavior.

The implementation separates source-word clicks from explicit dictionary-content navigation. It cancels the dismissed viewer's callback identity without stopping shared dictionary engines or erasing cached data needed for full-window/Anki transfer. Mouse-gesture tokens address focus-out-before-release, canceled selections, duplicate callbacks, and a newer source click overtaking an older callback.

Headless tests execute the changed Python methods and browser event handlers with synthetic inputs and fake UI/engines. They do not launch Luna or establish native Windows event ordering or appearance. The exact test commands and native checklist are in [LOOKUP_POPUP_TOGGLE.md](docs/LOOKUP_POPUP_TOGGLE.md).

## Next step and blocker

Run the focused Windows acceptance checklist in a disposable portable copy before producing a binary. Native PyQt/Windows/WebView interaction and visual verification are still pending; the source-only cloud checks cannot certify them. No application release, installer, model weight or user configuration is included in this checkpoint.

The separate local-translation project retains its existing evidence and experimental status. The [2026-10-04 checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261004.md) records its historical cloud-startup blocker; that is not the current blocker. Later completed and incomplete runs are preserved in the [roadmap](ROADMAP.md), and the [2026-10-08 checkpoint](docs/LOCAL_TRANSLATION_CHECKPOINT_20261008.md) is the current continuation point. This UI change does not execute or alter that experiment.

