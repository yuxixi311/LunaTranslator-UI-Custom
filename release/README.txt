Luna Translate UI v1.0.1
========================

非官方 LunaTranslator UI 与日语学习改版
Unofficial LunaTranslator UI and Japanese-learning fork

项目与源码 / Project and source
--------------------------------
https://github.com/yuxixi311/LunaTranslator-UI-Custom

本项目基于 HIllya51/LunaTranslator 修改，不是官方版本，也不代表上游
作者立场或获得其背书。原项目及本修改版依据 GNU GPL v3 发布。

This is an unofficial modified version of HIllya51/LunaTranslator. It is not
an official release and is not endorsed by the upstream author. The upstream
project and this modified version are distributed under GNU GPL v3.

运行 / Run
----------
1. 解压到普通可写目录；不要覆盖原版，也不要放入 C:\Program Files。
2. 双击 LunaTranslator.exe。
3. 仅当目标游戏需要相同的管理员权限时，使用 LunaTranslator_admin.exe。

1. Extract to a normal writable directory. Do not overwrite an upstream
   installation or place this build under C:\Program Files.
2. Run LunaTranslator.exe.
3. Use LunaTranslator_admin.exe only when the target game requires elevation.

主要改动 / Highlights
---------------------
* “常用设置”提供 Hook / OCR / Clipboard 文本来源选择，并修复旧配置中
  Hook 与 OCR 冲突造成的游戏连接问题。
* 喇叭按钮左键朗读当前日文，右键暂停/继续；旁边按钮循环切换
  0.6X / 0.8X / 1.0X。
* 默认 Nanami 日语自然女声，保留 Keita 男声；在线自然音色需要网络。
* 连续省略号在送入 TTS 前转换为停顿，不再读成连续的“点”。
* MeCab 继续负责词元、假名、词性与查词；内置 GiNZA 5.2 离线模型提供
  学习分组、文节边界、词元详情及保守的句法角色提示。
* 更柔和的词性底色、圆角边界、同色悬停和更清晰的设置层级。
* 自动更新默认关闭，避免官方更新覆盖改版内容。

* Common Settings exposes Hook / OCR / Clipboard and repairs conflicting
  legacy Hook+OCR states.
* Left-click the speaker to read the current Japanese source text; right-click
  to pause/resume. The adjacent button cycles 0.6X / 0.8X / 1.0X.
* Nanami is the default Japanese natural voice; Keita remains selectable.
  These edgeTTS voices require network access.
* Consecutive ellipses become a speech pause rather than repeated “dot” words.
* MeCab keeps token/furigana/POS/dictionary duties. Bundled offline GiNZA 5.2
  adds learning groups, bunsetsu boundaries, token details, and conservative
  syntax-role hints.
* Softer study colors, rounded boundaries, same-family hover feedback, and
  clearer settings hierarchy.
* Auto-update is disabled by default so upstream updates do not overwrite the
  fork.

注意 / Notes
------------
* 发布包不含个人 userconfig、翻译记录或缓存。测试前请备份已有配置。
* 定制启动器没有上游私有代码签名证书。Windows 首次运行可能显示
  SmartScreen；应用内部已有的 Python 文件摘要检查仍然保留。
* GiNZA 结果是统计学习提示，并非绝对正确的语法结论。
* MeCab 注音与分词仍需要可用词典，例如 UniDic。

* The archive excludes personal userconfig, translation records, and caches.
  Back up existing configuration before testing.
* The customized launcher cannot use the upstream private signing certificate.
  Windows SmartScreen may appear; existing internal Python digest checks remain.
* GiNZA output is a statistical learning hint, not an infallible grammar result.
* MeCab furigana and segmentation still require a dictionary such as UniDic.

许可证 / License
----------------
完整 GPLv3 文本见 LICENSE。修改与第三方归因见
LICENSE_AND_ATTRIBUTION.md；其他运行时许可证见 LICENSES 和各包的
.dist-info 目录。与本二进制对应的完整源码位于上方项目仓库的 v1.0.1
标签。

See LICENSE for GPLv3. Modification and third-party attribution is in
LICENSE_AND_ATTRIBUTION.md; additional runtime notices are under LICENSES and
the packages' .dist-info directories. Corresponding source is available at
tag v1.0.1 in the repository above.


v1.0.1 小窗口查词优化 / Popup lookup hotfix
--------------------------------------------
左键查词后，小窗口显示“词语 · 已查词”。同一词再次左击或右击会关闭
小窗口；关闭后迟到的查询结果不会再次弹出。不同词查询及右键追加保持原状。
本次更新不包含尚未完成的本地翻译模型开发；已有 GiNZA/OCR 运行时保持不变。
39 项 Python 回归测试、6 项浏览器桥接场景及打包完整性验证通过。
本次未运行 Windows 原生界面/焦点回归；这不等同于完成原生 GUI 验收。

A repeated left/right click on the active source word closes the small lookup
popup. Late results cannot reopen it. Different-word lookup/append is retained.
Only this popup hotfix is included; unfinished local-translation model work is
excluded. Existing released GiNZA/OCR/runtime components are retained unchanged.
39 Python regressions, 6 browser-bridge scenarios and package integrity checks
passed. Native Windows GUI/focus regression testing has not been run for this
hotfix. See RELEASE_NOTES.md and BUILD_INFO.json for scope and verification.
