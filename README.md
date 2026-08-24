# LunaTranslator UI Optimized Custom Edition

[简体中文](#简体中文) · [English](#english) · [本改版下载 / Fork releases](../../releases)

> [!IMPORTANT]
> 这是一个基于 [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator) 制作的个人使用向、非官方客制化分支，主要调整 UI 与日语学习辅助功能。它不是 LunaTranslator 官方版本，也无意替代原项目。首次接触 LunaTranslator、需要完整功能说明或希望获得官方版本时，请优先访问[上游项目](https://github.com/HIllya51/LunaTranslator)、[官方使用说明](https://docs.lunatranslator.org/)和[上游 Releases](https://github.com/HIllya51/LunaTranslator/releases)。

---

## 简体中文

### 项目定位

本项目最初为个人使用和日语视觉小说学习需求制作，是 LunaTranslator 的 **UI 优化与功能辅助添加版本**。Hook、OCR、剪贴板取词、翻译接口、词典框架和语音合成框架等核心能力均来自 LunaTranslator 及其贡献者；本分支主要在这些能力之上调整界面结构、交互习惯和学习辅助体验。

这个仓库适合希望尝试本分支特定界面和学习功能的用户。若你只需要通用、稳定且持续更新的 LunaTranslator，请优先使用[原项目](https://github.com/HIllya51/LunaTranslator)。

### 本改版对原项目做了什么

#### UI 与交互优化

- 增加“常用设置”首页，将常用选项集中展示，并明确使用 `Hook / OCR / Clipboard` 英文名称。
- 重新整理常用设置、词书设置的间距、层级、下拉框宽度和模型状态展示，减少拥挤感。
- 默认使用更精简的学习型悬浮工具栏，同时保留恢复完整按钮配置的能力。
- 将日语分词显示调整为柔和底色、圆角边界、同色悬停和句法角色色线，使学习单元更容易辨认。

#### 日语朗读辅助

- 在悬浮工具栏加入喇叭按钮：左键朗读当前显示的日文原文，右键暂停或继续。
- 加入 `0.6X / 0.8X / 1.0X` 三档语速切换按钮。
- 默认选择 Nanami 日语自然女声，并保留 Keita 男声等可选音色。
- 将连续省略号转换为自然停顿，避免语音合成逐个读出“点”。

#### 日语学习辅助

- 保留 MeCab 的分词、假名、词性和点击查词能力。
- 内置 GiNZA 5.2 离线模型，作为第二阶段句法分析辅助。
- 提供“学习分组（推荐）／文节边界／词元详情”三档显示。
- 默认学习分组会把相邻依存结构组合成更适合学习的单元，例如将 `役に + 立ってたなら` 作为连续结构呈现，同时保留底层文节和词元信息。

#### 问题修复与改版保护

- 修复旧配置同时启用 Hook 与 OCR 时，Hook 可能无法正确选择游戏文本源的问题。
- 默认关闭自动更新，避免上游官方更新直接覆盖本改版；用户仍可在设置中重新开启。
- 刷新客制启动器的 Python 文件摘要，避免本改版的合法文件反复触发应用内部“可能遭遇篡改”警告。

### 哪些内容仍以原项目为准

本改版没有重新发明 LunaTranslator 的完整翻译器能力。以下内容仍主要由上游提供和维护：

- 游戏 Hook、OCR、剪贴板等文本获取基础能力；
- 翻译器、词典、文本处理、内嵌翻译和语音合成框架；
- 大部分引擎兼容性、资源下载和通用故障排查；
- LunaTranslator 的长期更新与完整用户文档。

请通过使用本改版的同时关注、使用并支持 [LunaTranslator 原项目](https://github.com/HIllya51/LunaTranslator)。

### 使用文档与问题反馈

本项目暂不单独维护教程网站。继承自 LunaTranslator 的通用功能请参考 [LunaTranslator 官方使用说明](https://docs.lunatranslator.org/)。该文档由上游维护，其中的界面截图、设置名称和下载链接可能与本改版不同。

本分支新增功能和行为差异以本 README、[Release Notes](../../releases)及仓库内的修改说明为准。改版特有问题请提交到本仓库；不要把仅在本改版中出现的问题报告给上游作者。

### 下载与使用

1. 从[本改版 Releases](../../releases)下载 `Luna-Translate-UI-x64.zip`。首个发布包暂时保留了项目改名前的文件名。
2. 使用 Release 提供的 `SHA256SUMS.txt` 校验文件。
3. 解压到普通可写目录，不要覆盖 LunaTranslator 原版，也不要放入 `C:\Program Files`。
4. 双击 `LunaTranslator.exe`；只有目标游戏确实需要管理员权限时才使用 `LunaTranslator_admin.exe`。

发布包为便携版，不包含个人配置、翻译记录或缓存。建议将原版和本改版放在不同目录，并在测试前备份现有 `userconfig`。

### 已知限制

- 客制启动器没有上游项目的私有代码签名证书，因此 Windows 可能在首次运行下载文件时显示 SmartScreen。
- Nanami、Keita 等 edgeTTS 自然音色需要网络；内置 GiNZA 句法分析可离线运行。
- MeCab 假名和分词仍需要可用的 MeCab 词典，例如 UniDic。
- GiNZA 是统计模型，其结果是学习提示而不是绝对正确的语法结论。
- 新语速从下一次语音合成开始生效，不会改变已经开始播放的音频。

### 源码、归属与许可证

LunaTranslator 原始代码及贡献归 [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator) 和相应贡献者所有。本项目是其非官方修改版本，不受上游作者认可或背书。

本项目整体依据 **GNU General Public License version 3（GPL-3.0-only）** 发布。发布可执行文件时，同一版本标签提供对应源码、修改说明和打包信息。详见 [LICENSE](LICENSE)、[LICENSE_AND_ATTRIBUTION.md](LICENSE_AND_ATTRIBUTION.md)、[MODIFICATIONS.md](MODIFICATIONS.md) 和 [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md)。

---

## English

### Project scope

LunaTranslator UI Optimized Custom Edition is a personal-use-oriented, unofficial fork of [LunaTranslator](https://github.com/HIllya51/LunaTranslator), created for Japanese visual-novel reading and study. Core capabilities—including Hook, OCR, clipboard capture, translation providers, dictionaries, and the TTS framework—come from LunaTranslator and its contributors. This fork mainly changes the interface, interaction preferences, and learning aids built on top of them.

It is not an official release and does not replace upstream. Users who want the general, stable, continuously maintained application should prefer the [upstream project](https://github.com/HIllya51/LunaTranslator) and its [official releases](https://github.com/HIllya51/LunaTranslator/releases).

### Changes made by this fork

#### UI and interaction

- Adds a Common Settings home page with explicit `Hook / OCR / Clipboard` source names.
- Reworks spacing, hierarchy, dropdown widths, and model-status presentation in common and dictionary settings.
- Uses a compact learning-focused floating toolbar by default while retaining the full button configuration.
- Presents Japanese learning units with soft POS backgrounds, rounded borders, matching hover feedback, and syntax-role underlines.

#### Japanese reading controls

- Adds a speaker button: left-click reads the current Japanese source text; right-click pauses or resumes.
- Adds a `0.6X / 0.8X / 1.0X` speech-rate cycle.
- Selects the Nanami natural Japanese female voice by default while keeping Keita and other available voices selectable.
- Converts consecutive ellipses into a pause instead of pronouncing repeated “dot” words.

#### Japanese-learning aids

- Keeps MeCab for tokens, furigana, part of speech, and dictionary clicks.
- Bundles an offline GiNZA 5.2 model as a second syntax-analysis stage.
- Offers `Learning groups (recommended) / Bunsetsu boundaries / Token details`.
- Groups adjacent dependency structures into learner-facing units while preserving the underlying bunsetsu and token data.

#### Repairs and fork protection

- Repairs legacy Hook+OCR states that could prevent Hook from selecting the correct game source.
- Disables auto-update by default so an upstream update does not overwrite the customized build; it can be re-enabled.
- Refreshes the customized launcher's Python digests so legitimate fork files do not repeatedly trigger the application's alteration warning.

### What remains upstream

The underlying capture, translation, dictionary, text-processing, embedded-translation, TTS, engine-compatibility, resource, and general troubleshooting systems remain upstream LunaTranslator work. Please visit, use, and support the [original LunaTranslator project](https://github.com/HIllya51/LunaTranslator).

### Documentation and issue routing

This fork does not maintain a separate tutorial website. For inherited features, use the [official upstream LunaTranslator user guide](https://docs.lunatranslator.org/). Screenshots, setting names, and download links there may differ from this customized interface.

Fork-specific behavior is documented in this README, the [Release Notes](../../releases), and the modification records in this repository. Report fork-only issues here rather than to the upstream maintainers.

### Download and run

1. Download `Luna-Translate-UI-x64.zip` from the [fork releases](../../releases). The first archive retains its pre-rename filename.
2. Verify it against `SHA256SUMS.txt`.
3. Extract it to a normal writable directory. Do not overwrite an upstream installation or place it under `C:\Program Files`.
4. Run `LunaTranslator.exe`; use `LunaTranslator_admin.exe` only when the target game requires elevation.

The portable archive excludes personal configuration, translation records, and caches. Keep upstream and customized installations in separate directories and back up any existing `userconfig` before testing.

### Known limitations

- The customized launchers cannot use the upstream project's private signing certificate, so Windows SmartScreen may appear on first run.
- Nanami, Keita, and other edgeTTS natural voices require network access; bundled GiNZA syntax analysis runs offline.
- MeCab still needs a usable dictionary such as UniDic.
- GiNZA provides statistical learning hints, not infallible grammar judgments.
- A new speech-rate setting applies to the next synthesis request and does not retime audio already playing.

### Source, attribution, and license

Original LunaTranslator code and contributions belong to [HIllya51/LunaTranslator](https://github.com/HIllya51/LunaTranslator) and the respective contributors. This fork is unofficial and is not endorsed by or affiliated with the upstream author.

The combined modified work is distributed under **GNU General Public License version 3 (`GPL-3.0-only`)**. Corresponding source, modification notices, and packaging information accompany binary releases. See [LICENSE](LICENSE), [LICENSE_AND_ATTRIBUTION.md](LICENSE_AND_ATTRIBUTION.md), [MODIFICATIONS.md](MODIFICATIONS.md), and [THIRD_PARTY_SOURCE.md](THIRD_PARTY_SOURCE.md).
