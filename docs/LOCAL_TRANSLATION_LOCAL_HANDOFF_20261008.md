# 新本地对话交接：精确 journal 候选

本交接以最终发布的仓库 commit、[公开清单](../tools/local_eval/handoff-20261008/PUBLIC_MANIFEST.json) 与既有 ZIP 为输入。不要重新生成 ZIP，也不要把旧下载目录当作新 attempt。先读[当前节点](LOCAL_TRANSLATION_CHECKPOINT_20261008.md)和[路线](LOCAL_TRANSLATION_ROADMAP_20261008.md)。

## 1. 核验输入与现状

既有 `luna-torch-journal-gated-preparation-20261008.zip`：270,447 bytes，SHA-256 `ac1606f1d56870c29a0f9e1b7f98bb1a8efd6c59ff9cc93d668ace5c7e02b96d`。

候选 `974d95a3-29c7-4294-9f46-33d247dd72f2`；源码 `run_check.py` SHA-256 `00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630`。核验 manifest、五个 TEST_FILES、410 项 fresh fake receipts、独立 review、identity 和 `output/attempt.json`；10 个 superseded 旧检查不算通过。公开源码位于 [torch-journal-gated](../tools/local_eval/handoff-20261008/torch-journal-gated/)。不要修改源码绕过 gate。

用只读方式核对本机现存 claims、报告与消费标记。有相同 candidate 已开始/已消费、未知并发运行、冲突文件或绑定不一致，就先报告并依据已有证据接续，不清除/覆盖/搬走 marker，也不自动开新目录重复一次已消费操作。

确认为未消费后，使用新的隔离目录，保留 `candidate` 为确切工作根和其单一 `output` 目录；不能使用 symlink、alias、junction/reparse point。使用已有、核验过的 Windows Python 3.12。找不到匹配解释器或资源不足就报告具体阻碍，不安装 Python/软件，不切换电脑绕过。

## 2. 授权与执行只绑定本次范围

用户已明确批准本候选的一次精确 GET 与静态检查。原 ZIP 属准备阶段，故仍无 `execution-authorization.json`，identity 仍标记 `preparation_only` / `live_execution_authorized=false`。这不要求对不变的已授权步骤逐文件重复询问；也不能用一个归档文件伪造用户授权。操作员须在核对本次用户指令及精确目标/边界后，创建源码要求的四键对象：

```json
{
  "candidate_id": "974d95a3-29c7-4294-9f46-33d247dd72f2",
  "source_sha256": "00e0c240582533d666428530d55ede1cbcca6783919b6118abd4afa715d10630",
  "action": "single_download_and_static_check",
  "authorized": true
}
```

放置为工作根 `execution-authorization.json`；不要加入额外键，不修改 candidate identity，不将此文件加入公开归档或当作未来无限授权。若新对话没有能够核验的用户批准，则在进入 live 操作前确认；不要要求对已经核验且不变的批准再确认。

唯一 URL：`https://download-r2.pytorch.org/whl/cu128/torch-2.10.0%2Bcu128-cp312-cp312-win_amd64.whl`

完整 body 预期 SHA-256：`fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae`

- 最多 1 个 GET；0 retry、0 redirect、无继承 proxy、无 HEAD/Range/额外网络探测
- Body ≤4,294,967,296 bytes；自有磁盘增量 ≤4,402,341,478 bytes，二者分开计量
- 初始可用磁盘 ≥8GiB，最低可用 ≥2GiB，控制预留 32MiB
- 下载 active 870 秒 / total 900 秒；静态 active 50 秒 / total 60 秒；不因 fsync 延迟加时。这是常规 watchdog 边界，不能保证 Windows 调度停顿下的实时抢占
- 不安装、import 或执行 wheel；不下载传递依赖/模型，不评价翻译、不运行 GPU 或训练，不提权、不改变安全设置

仅通过 supervisor 启动一次，命令形状：

```text
<已核验的 python.exe> -I -S -B <absolute-candidate-root>\run_check.py supervise <absolute-candidate-root> <absolute-candidate-root>\output
```

用实际确认的绝对路径替换占位符；不得直接调用 worker/connect 入口或开替代入口。对原失败 attempt 和其 marker 只读保留。

## 3. 报告、留存与停止

报告至少包含 candidate/source/test/review 绑定、request_count/get_send_attempts、response/body/hash 状态、received 与 written 的分别计数、未知计数及 durable-body 证据；首错完整 operation/context/exception/errno/winerror、有限次级错误；journal 计数/摘要/关闭状态、final checkpoint 持久化、worker return code 与确认退出、终止/超时、磁盘采样极值、两阶段耗时、静态结果、报告持久化和 cleanup 状态。

缺 final JSON 时，只将有效且绑定正确的 journal 前缀记为下界；能恢复终态记录首错则如实恢复，否则标未知。不能从 parseable 文件推断零退出，不能编造完整字节数/PASS，不能以子记录覆盖整体失败。保留 source/identity/attempt markers、journal、checkpoint 和 reports；已有范围内的 partial body 清理仅在原规则所需退出确认后进行。不得新增 journal 删除、旧 attempt 清理或为腾空间删除文件。

成功：保留完整、哈希匹配的 wheel 及静态 metadata，返回精确路径和证据，再准备依赖闭包/隔离安装方案，不自动安装。失败/未知：停止，报告首错、已知/未知事实、保留与清理状态，不自动重试。原 PermissionError 根因未知，fake 通过不能作为根因已修复的证明。

## 4. 长期项目边界

baseline 和 UI 保持不变，现有负面结果不重算为成功。LoRA 只为后续可行性方向，需数据权利、独立分组、trainer/runtime 审核、资源与费用边界和适用授权；当前没有训练许可。私有评价标准与逐行判定保持私有；公开归档未盘点到的 private inventory 要明说缺失，不读取或重建它来“补齐”公共包。
