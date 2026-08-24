# Modification Notice / 修改说明

This file provides the prominent modification notice required for this unofficial LunaTranslator fork.

本文件用于明确标注该非官方 LunaTranslator 改版的修改范围和日期。

## Project identity

- Fork name: **LunaTranslator UI Optimized Custom Edition**（LunaTranslator UI 优化客制版）
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
