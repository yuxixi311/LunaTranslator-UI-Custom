# Modification Notice / 修改说明

This file provides the prominent modification notice required for this unofficial LunaTranslator fork.

本文件用于明确标注该非官方 LunaTranslator 改版的修改范围和日期。

## Project identity

- Fork name: **LunaTranslator UI Optimized Custom Edition**
- Upstream: <https://github.com/HIllya51/LunaTranslator>
- Upstream baseline: `c7d00f7320e872f8717385e173a0d76f891aa9e9`
- Initial customization base: `deb32cf8384c29e5dea9d830b886ee416e555d0c`
- First packaged release: `v1.0.0`
- Main modification dates: 2026-08-20 through 2026-08-24

## Material changes

1. Added a reversible, learning-focused UI mode with redesigned surfaces, spacing, typography, toolbar content, and a Common Settings page.
2. Changed text-source labels to Hook, OCR, and Clipboard; normalized conflicting legacy source states and repaired the Hook game-selection flow.
3. Added manual reading of the current Japanese source text, pause/resume behavior, Nanami/Keita selection, ellipsis normalization, and 0.6X/0.8X/1.0X learning-speed controls.
4. Refreshed the customized launchers' existing Python integrity digests while accurately marking the modified binaries as unsigned.
5. Added GiNZA 5.2 as a lazy, offline second-stage syntax analyzer while preserving MeCab tokens, furigana, part-of-speech data, and dictionary-click behavior.
6. Added conservative learner-facing groups above raw GiNZA bunsetsu, three syntax detail levels, syntax tooltips, semantic POS colors, role underlines, and corresponding settings.
7. Added targeted regression tests, packaging checks, dependency locks, attribution material, and release documentation.

## Compatibility and limits

- Upstream functionality remains available through the full/classic settings and button configuration.
- Auto-update is disabled by default to avoid overwriting fork changes.
- GiNZA roles and learner-facing groups are statistical hints and can be wrong.
- Online edgeTTS voices require network access.
- The fork launchers do not carry the upstream project's code-signing identity.

For file-level history, review the Git commits following the upstream baseline. The complete modified source is released under GPLv3 together with every binary release.

## 2026-10-02: optional local translation setup (development branch)

- Added an isolated, opt-in Hy-MT2 quick setup, loopback-only provider, owned llama.cpp lifecycle, pinned size/SHA-256 model download with cancellation and atomic installation, and exact-model offline import. No model weights are bundled.
- Preserved previous interfaces, saved keys, enable states and advanced launcher settings. Reused Sakura/Hy-MT2 prompts and the existing inference engine.
- Modified `gui/setting/translate.py` to include the previously omitted flash-attention option without emitting a bare `auto` token.
- Modified `translator/sakura_base.py` to correctly format non-Chinese glossary prompts.
- Added synthetic integrity, lifecycle, configuration, transport and prompt regressions, plus setup, attribution and Windows/quality acceptance documentation. Windows execution and real-model quality remain unverified in this phase.

### Official preset fidelity correction

- Limited to the new local preset: Chinese instructions now use Chinese language names; the four fixed sampling values follow the pinned official 1.8B/7B card (.7 temperature, .6 top-p, top-k 20, repetition penalty 1.05). The direct llama.cpp adapter emits `repeat_penalty`, because the generic `repetition_penalty` field was ineffective in b11349. Existing provider behavior and saved settings are unchanged.
- Added prompt, wire-body, stale-setting and default-control regression tests. Documented real-model smoke-test semantic failures and the distinction between a configuration correction and demonstrated quality improvement.
