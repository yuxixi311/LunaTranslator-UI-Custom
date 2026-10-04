# LunaTranslator UI Optimized Custom Edition v1.0.1

## 中文

这是基于已发布 v1.0.0 的小窗口查词体验热修复，提供完整 Windows x64 便携包。

- 左键查询后，小窗口显示当前词和“已查词”
- 同一来源句中的同一词再次左击或右击会关闭小窗口，不会重复查询、重复追加或重复自动朗读
- 关闭后迟到的词典结果不会重新弹出；快速点击、失焦、选词取消和旧回调有对应保护
- 不同词查询/右键追加、词典内部链接、主查词窗口、复制及原有配置保持原有行为

本次不包含尚未完成的本地翻译模型开发。已发布的 GiNZA、OCR、Python/Qt 和其他运行时文件保留不变；只有七个查词界面源文件、两个启动器的现有文件摘要及版本说明更新。

验证：39 项 Python 回归测试、6 项 JavaScript 桥接场景，以及原有学习/朗读/文本源相关无界面测试通过。压缩包文件清单、CRC、逐文件变化范围和两个启动器的源文件摘要均检查。**本次未运行 Windows 原生 GUI/焦点回归，不能视为完成原生界面验收。**

下载 `LunaTranslator-UI-Custom-v1.0.1-x64.zip`，用同页 `SHA256SUMS.txt` 校验。建议解压到新目录并备份旧 `userconfig`；不自动修改本机安装。定制启动器继续保持未签名状态，Windows 可能显示 SmartScreen。

对应源码见 `v1.0.1` 标签；与 v1.0.0 比较可以看到本次独立的小改动。它仍是基于 HIllya51/LunaTranslator 的非官方 GPLv3 改版。

## English

A small popup-lookup hotfix on the released v1.0.0 baseline, supplied as a complete Windows x64 portable distribution. Repeating a left/right click on the active source word closes the popup; its header identifies the queried word. Late results cannot reopen a dismissed lookup. Different-word append, dictionary-content navigation, the main dictionary window and existing settings are preserved.

Unfinished local-translation model work is excluded. Existing released GiNZA/OCR/Python/Qt/runtime payloads are retained unchanged. The runtime delta is seven popup source files and their existing digest slots in two unsigned custom launchers.

39 Python regressions, 6 JavaScript bridge scenarios, existing headless learning/audio/source-selection tests and package-integrity checks passed. **Native Windows GUI/focus regression testing has not been run for this hotfix.** No native visual/game-compatibility claim is made.

Download `LunaTranslator-UI-Custom-v1.0.1-x64.zip` and verify with `SHA256SUMS.txt`. Extract to a new writable directory and back up existing configuration. The release does not update a local installation automatically. Launchers remain unsigned; Windows SmartScreen may appear.

Matching GPLv3 source and packaging instructions are at tag `v1.0.1`. See `BUILD_INFO.json` inside the archive for its pinned baseline and changed-file hashes.

---

## Previous release

# Luna Translate UI v1.0.0

## 中文

这是 Luna Translate UI 的第一个审阅版本，也是基于 LunaTranslator 的非官方 UI 与日语学习改版。

本版本包括：

- Hook/OCR/Clipboard 常用设置与旧配置冲突修复；
- 日文原文朗读、右键暂停/继续、Nanami/Keita 音色和三档倍速；
- 省略号朗读修复；
- 内置离线 GiNZA 5.2、学习分组、文节边界与词元详情；
- 重新设计的学习型词性配色、设置层级和界面间距；
- 定制启动器摘要刷新，避免应用内部重复出现文件篡改警告；
- GPLv3、第三方许可证和完整对应源码说明。

已知限制：启动器未使用上游代码签名证书；Windows 可能显示 SmartScreen；edgeTTS 自然音色需要网络；GiNZA 输出可能误判。

## English

This is the first review release of Luna Translate UI, an unofficial LunaTranslator UI and Japanese-learning fork.

It includes:

- Common Hook/OCR/Clipboard controls and legacy source-state repair;
- manual Japanese source reading, pause/resume, Nanami/Keita voices, and three speech-rate presets;
- ellipsis pronunciation repair;
- bundled offline GiNZA 5.2 with learner groups, bunsetsu boundaries, and token details;
- redesigned learning colors, settings hierarchy, and spacing;
- refreshed customized-launcher digests to avoid repeated in-application alteration warnings;
- GPLv3 compliance material, third-party notices, and corresponding tagged source.

Known limits: the launchers do not use the upstream signing certificate; Windows SmartScreen may appear; edgeTTS natural voices require network access; GiNZA analysis can be wrong.

Archive: `Luna-Translate-UI-x64.zip` (251,214,174 bytes)

SHA-256: `AAFDBCADEE8F75054EA3AA6783F6EFB18B5CC0697690CDF9311A311F4115D19A`

The same checksum is provided in the attached `SHA256SUMS.txt`.
