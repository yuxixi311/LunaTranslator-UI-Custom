# Luna Translate UI

**An unofficial UI and Japanese-learning fork of [LunaTranslator](https://github.com/HIllya51/LunaTranslator).**

[简体中文](#简体中文) · [English](#english) · [Releases](../../releases)

> [!IMPORTANT]
> This project is not an official LunaTranslator release and is not endorsed by the upstream author. LunaTranslator and its contributors retain copyright in the original project. This modified version is distributed under GNU GPL v3.

## 简体中文

### 项目简介

Luna Translate UI 是基于 LunaTranslator 的非官方改版，重点优化日语视觉小说的学习和阅读体验。它保留 Hook、OCR、剪贴板、翻译、查词和语音合成等原有能力，同时重新整理常用设置、悬浮工具栏、日语朗读和句法学习界面。

本仓库不取代上游项目。通用功能、原版文档及新版本请访问 [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator)。本仓库的 Issues 仅用于跟踪此改版引入的功能和问题。

### 主要改动

- 新增“常用设置”首页，并将文本来源明确显示为 `Hook / OCR / Clipboard`。
- 修复旧配置同时启用 Hook 与 OCR 时，Hook 无法正确连接游戏的问题。
- 默认使用精简的学习型工具栏，同时保留在设置中恢复完整按钮的能力。
- 增加喇叭按钮：左键朗读当前日文原文，右键暂停或继续。
- 增加 `0.6X / 0.8X / 1.0X` 三档朗读速度按钮。
- 默认使用 Nanami 日语自然女声，并保留 Keita 男声可选项；在线自然音色需要网络。
- 朗读前将连续省略号转换为停顿，避免读成连续的“点”。
- MeCab 继续负责词元、假名、词性和点击查词；内置 GiNZA 5.2 离线模型作为第二阶段句法增强。
- 提供“学习分组（推荐）／文节边界／词元详情”三档显示。默认学习分组会将 `役に + 立ってたなら` 等紧邻依存结构显示为一个更容易理解的学习单元，同时保留底层文节与词元数据。
- 采用柔和词性底色、同色圆角边界、同色悬停和句法角色色线，并重新整理词书设置与常用设置的间距和层级。
- 关闭自动更新默认值，避免官方更新直接覆盖本改版；用户仍可在设置中重新开启。
- 刷新定制启动器已有的 Python 摘要，避免修改后的合法文件每次启动都触发应用内部的“可能遭遇篡改”警告。

### 下载与使用

1. 从 [Releases](../../releases) 下载 `Luna-Translate-UI-x64.zip`。
2. 校验 Release 同时提供的 `SHA256SUMS.txt`。
3. 解压到普通可写目录，不要直接覆盖原版 LunaTranslator，也不要放入 `C:\Program Files`。
4. 双击 `LunaTranslator.exe`。需要管理员权限连接某些游戏时，可使用 `LunaTranslator_admin.exe`。
5. 在“设置 → 常用设置”中选择 Hook、OCR 或 Clipboard。

发布包为便携版，不包含个人配置、翻译记录或缓存。建议将原版和本改版放在不同目录，首次使用前自行备份现有 `userconfig`。

### 使用注意

- 定制启动器没有上游项目的私有代码签名证书，因此 Windows 可能在首次下载运行时显示 SmartScreen 提示。应用内部的摘要检查仍然保留。
- Nanami 和 Keita 的 edgeTTS 自然音色需要网络；GiNZA 句法模型包含在发行包中，句法分析本身离线运行。
- MeCab 假名和分词仍需要可用的 MeCab 词典，例如 UniDic。
- GiNZA 输出是统计学习提示，不是绝对正确的语法结论。日语省略主语、主题与主语差异、复杂并列等情况可能产生误判。
- 朗读倍率从下一次合成开始生效，不会改变已经在播放的音频。

### 源码与许可证

本项目是 LunaTranslator 的修改版本，整体依据 **GNU General Public License version 3（GPL-3.0-only）** 发布。发布可执行文件时，同一版本标签提供完整对应源码、修改说明和打包脚本。你可以使用、研究、修改和再分发，但再分发时必须继续遵守 GPLv3。

详见 [LICENSE](LICENSE)、[LICENSE_AND_ATTRIBUTION.md](LICENSE_AND_ATTRIBUTION.md)、[MODIFICATIONS.md](MODIFICATIONS.md) 和 [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md)。

---

## English

### About

Luna Translate UI is an unofficial LunaTranslator fork focused on Japanese visual-novel reading and language learning. It keeps the upstream Hook, OCR, clipboard, translation, dictionary, and TTS capabilities while reorganizing the common settings, floating toolbar, Japanese reading controls, and syntax-learning presentation.

This repository does not replace upstream. For general functionality, upstream documentation, and official releases, visit [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator). Issues in this repository should be limited to changes introduced by this fork.

### Highlights

- Adds a Common Settings home page with explicit `Hook / OCR / Clipboard` source selection.
- Repairs legacy Hook+OCR configurations that could prevent Hook from selecting the correct game source.
- Uses a compact learning-focused toolbar by default while retaining the full button configuration.
- Adds a speaker control: left-click reads the current Japanese source text; right-click pauses or resumes.
- Adds a `0.6X / 0.8X / 1.0X` speech-rate cycle.
- Selects the Nanami Japanese natural female voice by default and keeps Keita available; these online voices require network access.
- Converts consecutive ellipsis characters to a pause before speech synthesis instead of pronouncing repeated “dot” words.
- Keeps MeCab responsible for tokens, furigana, part of speech, and dictionary clicks, while an embedded offline GiNZA 5.2 model provides a second syntax-analysis stage.
- Offers `Learning groups (recommended) / Bunsetsu boundaries / Token details`. The default view can group adjacent dependency structures such as `役に + 立ってたなら` into a learner-facing unit without discarding the underlying bunsetsu or token data.
- Uses soft POS backgrounds, same-family rounded borders and hover feedback, syntax-role underlines, and less crowded dictionary/common settings layouts.
- Disables auto-update by default so an official update does not overwrite the fork; it can still be re-enabled in Settings.
- Refreshes the existing Python digests in the customized launcher so legitimate modified files do not trigger the application's own alteration warning on every start.

### Download and run

1. Download `Luna-Translate-UI-x64.zip` from [Releases](../../releases).
2. Verify it against the accompanying `SHA256SUMS.txt`.
3. Extract it to a normal writable directory. Do not overwrite an upstream installation or place it under `C:\Program Files`.
4. Run `LunaTranslator.exe`; use `LunaTranslator_admin.exe` only when a target game requires elevation.
5. Choose Hook, OCR, or Clipboard in Settings → Common Settings.

The portable release excludes personal configuration, translation records, and caches. Keep the upstream application and this fork in separate directories, and back up any existing `userconfig` before testing.

### Important notes

- The customized launcher cannot use the upstream project's private code-signing certificate, so Windows SmartScreen may appear on the first run of a downloaded archive. The application's internal digest checks remain enabled.
- Nanami and Keita edgeTTS voices require a network connection. The bundled GiNZA syntax analysis runs offline.
- MeCab furigana and segmentation still require a usable dictionary such as UniDic.
- GiNZA output is a statistical learning hint, not an infallible grammar judgment. Omitted subjects, topic/subject distinctions, and complex coordination can be ambiguous.
- A new speed setting applies to the next synthesis request; it does not retime audio already playing.

### Source and licensing

This is a modified version of LunaTranslator and the combined work is distributed under **GNU General Public License version 3 (`GPL-3.0-only`)**. Every binary release is paired with its corresponding tagged source, modification notices, and packaging scripts. You may use, study, modify, and redistribute it subject to GPLv3.

See [LICENSE](LICENSE), [LICENSE_AND_ATTRIBUTION.md](LICENSE_AND_ATTRIBUTION.md), [MODIFICATIONS.md](MODIFICATIONS.md), and [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md).
