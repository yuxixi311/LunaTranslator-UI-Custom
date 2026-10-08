# Luna 本地翻译总节点：2026-10-08

## 当前结论

保留可选 Hy-MT2-1.8B Q4 baseline，不推广已失败候选。现有 providers、默认设置与 UI v1.0.1 不变。仓库是开发源码与审计节点，不含新安装包、可用训练环境或质量提升承诺。

本节点从 `a33dd731998f63e6ffd7d5fff1e2612d5cbcac80` 接续，补齐后续数据/LoRA 方案、Windows 依赖检查、失败记录与 journal 准备状态。用户接续时应使用实际发布后的最终 commit；本文件不伪造尚未产生的提交号。

## 已尝试方法与不可抹除的负面结果

| 方法 | 实际证据 | 结论及限制 |
| --- | --- | --- |
| Supplied glossary | [既有报告](LOCAL_TRANSLATION_HY_GLOSSARY_RESULT_20261003.md)保留基础设施失败与语义不确定性 | inconclusive，不改写为质量成功或确定质量失败 |
| Sudachi POS / GiNZA NER | [POS](LOCAL_TRANSLATION_LEXICAL_RESULT_20261005.md) admission 失败；[NER](LOCAL_TRANSLATION_NER_RESULT_20261005.md)完成 73 次 CPU 调用，历史 14/16、新鲜 16/24 均未过门槛 | 不沿用原规则晋升 GPU 测试 |
| Sense prefix | [88 对 CPU 比较](LOCAL_TRANSLATION_SENSE_RESULT_20261006.md)，176 次翻译、442 次计划请求；fresh48 两位独立模型辅助评审均给 baseline 39 个明确整行通过，candidate 为 35/34 | 共识 2 个 baseline 通过→candidate 失败，0 个明确关键失败→整行通过修复；成本与语义均失败，FAIL_NO_PROMOTION |
| 稀疏双语微例句 | [计划 87 对的预检](LOCAL_TRANSLATION_USAGE_RESULT_20261006.md)；176 个 readiness/count 请求完成；24 个 eligible 中仅 2 个落入新增 token 预算，只有 2 carriers / 1 family，未达 12 / 6 | NO_GO，0 次生成；没有语义胜负或成对成本结果；整体清理不确定另记 |
| Grounded speaker/context | 当前检查的 adapter 未形成可辩护的同记录 speaker/body 来源契约 | 来源前提 NO_GO，不是测得的质量失败；不臆造上下文 |
| Deterministic term lock | [88 对、176 个原始输出、378 请求](LOCAL_TRANSLATION_TERM_RESULT_20261007.md)；173 个最终文本通过机械 guard；新语义评审仅 fresh19 | baseline 13 faithful / 3 material error / 3 unresolved；candidate 13 / 3 / 2 加 1 structural rejection；canonical 16/16 对 15/16 加 1 rejection；0 修复、0 获益家族；无增益、不推广 |

Sense fresh48 成对耗时比中位数 1.4155785885060757、P95 1.6367162196176535，超过冻结 1.25 上限；所有必需群体至少一个成本统计失败。Term 的观测成本比通过，但整体 `cleanup_confirmed=false`、`protocol_complete=false`，终态 `incomplete / OPERATIONAL_FAILURE`；子进程回执不能覆盖整体失败，helper resource/lifecycle 成功未证实。两类结果均不能推断 Windows/GPU 性能。

评审是独立模型辅助、标签盲化，不是专业人工验收，也不保证隐藏处理组。fresh48、fresh19 和更早已暴露测试均为已见回归资料，不能重新称为未触碰 holdout 或据此反复调参。

## 数据和 LoRA：仍是可行性方案

- 当前 24 条模型辅助合成开发原型：23 条暂留、1 条歧义隔离；没有人工双语认证。保守关联图只有一个连通分组，不能切成独立 train/test；默认不进入首次训练。
- 已检查 Tatoeba 日/中 CC0 名单与直接翻译链接交集，eligible 为 0。不得悄悄扩大授权语料或把无链接句子拼成平行对。
- 未来 ≤200 对只是候选数据可行性上限，需来源/使用与再分发权限、歧义、版本、审校身份及关联分组。独立评估作者不得接触训练样本、修订反馈或私有测试标准。
- 官方 trainer 精确实现审核仅部分完成；方案不等于代码已审完或环境兼容已证实。12GB 显存能否容纳未实测。
- 拟议 BF16 LoRA、短序列、少量样本/步数、保存释放重载、最终 Q4_K_M 回归均是后续方案；未批准训练、GPU 租用、模型权重下载或相关费用。pipeline smoke 通过也不等于翻译改善。

## Native Windows 运行时与两次真实失败

候选目标为已有 Windows Python 3.12 与 Torch 2.10.0+cu128；Transformers 5.6.0 等仅是候选元数据，不是已闭合依赖或已安装证明。Torch 完整 wheel 字节数和完整依赖闭包仍未知。历史资源快照不代表当前可用性，需本机重新核对，也不能作为训练可行性证明。公开文档不保留私人主机路径。

两个真实 Torch GET 均收到 HTTP 200，均未取得完整 wheel、未进行成功静态检查：

1. 首次在 51,658,752 bytes 的已记录进度附近发生 `OUTPUT_ERROR`；精确根因未知，不补写尚未证实的字段。
2. 第二次 recorded received 72,478,592 bytes、written 72,462,208 bytes；首错为 `JSON_REPLACE / PROGRESS_BEFORE_WRITE / PermissionError / errno 13 / winerror 5`。收到字节与写入字节不得混为一谈。

8 轮无网络合成探针采用 2 秒间隔，共 63 次操作、17,502 bytes、约 14.11 秒，全部通过；这不能排除真实运行中的瞬时冲突。supervisor 仅在 worker 退出后读取 checkpoint，因此当前源码证据不支持“内部读者并发占用是已确认原因”。原始 PermissionError 原因仍未知；不修改 ACL、不提权、不停安全软件、不用重试删除掩盖错误。

## 新 journal 候选：准备完成，真实结果未发生

- Candidate ID：`974d95a3-29c7-4294-9f46-33d247dd72f2`
- `run_check.py` SHA-256：`00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630`
- 本候选新鲜 fake 检查共 410 项通过（219 + 105 + 86）；10 个旧 per-chunk JSON 检查明确 superseded，不能计入通过数，也不能挪用 inert predecessor 的 318 passes。
- 追加 journal 每成功写入 1MiB 抽样，另含生命周期事件；每帧 payload ≤2,048 bytes，总帧 ≤4,102，总文件 ≤8,548,576 bytes，逐帧检查、flush/fsync。仍占用原时间与磁盘预算。
- 这会降低 crash 后可观察粒度。有效但不完整的 journal 只给下界前缀，不能证明下载完整或 PASS；fsync 不是无条件断电保证。worker 成功退出、最终 checkpoint、完整大小/哈希和原有所有门槛仍必需；最终报告及静态 checkpoint 的替换风险仍存在。

既有 ZIP 是冻结准备包，不重新生成：`luna-torch-journal-gated-preparation-20261008.zip`，270,447 bytes，SHA-256 `ac1606f1d56870c29a0f9e1b7f98bb1a8efd6c59ff9cc93d668ace5c7e02b96d`。包内没有 `execution-authorization.json`；`preparation_only` 与 `live_execution_authorized=false` 是归档时状态，不是对后续用户授权的否认，也不能自行变成运行授权。

用户之后已明确批准该精确候选的一次 GET 与静态检查。新本地对话需核对授权范围、包/源码/测试绑定、现存 claim/报告和消费状态，再由操作员创建精确四键授权对象。未执行不等于失败，fake 通过不等于原生 Windows 成功，授权不等于已经运行。

## 公开与私有证据边界

本次归档只收录可公开源码、脱敏汇总、准备证据与清单；私有评分标准、私有逐行判定、完整私有 wire 日志不进入公开仓库。没有读取或复制这些私有资料来补齐归档。缺失的私有清单或对象映射须明确记为未盘点/缺失，不能从汇总伪造或重建。公开清单是公开归档范围，不声称覆盖全部私人资料。

下一步见[路线](LOCAL_TRANSLATION_ROADMAP_20261008.md)与[本地交接](LOCAL_TRANSLATION_LOCAL_HANDOFF_20261008.md)。UI 原生 Windows/PyQt/WebView 验收仍单列在 [UI 检查表](LOOKUP_POPUP_TOGGLE.md)，不能用本节点替代。
