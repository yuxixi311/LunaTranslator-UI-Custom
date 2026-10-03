# 新固定输入集：Hy-MT2 1.8B 实测与可复现比较工具

日期：2026-10-03 UTC。**这次实际完成了同一 Hy-MT2 1.8B 的 Q4_K_M / Q8_0 量化对照，仍未完成 7B、Gemma、Google 在线或 DeepSeek 对照。Q8 修好了一个格式案例，但关键语义错误仍然存在，不能推荐为已经达到目标的质量升级。**

## 与历史测试的关系

旧报告中的 32+8 条完整输入与原始输出未从现存工作区找回。仓库保存的是 8 条种子及历史摘要，不能冒充旧 40 条。此次另写了 **全新的 40 条合成日文**，在任何模型输出出现之前固定字节与 SHA-256：

`051d2ef38f5a067c6a9ace4ebe3e149b00211c9fb29707779b8e725d3fee84f1`

[固定集](../src/tests/fixtures/local_translation_eval_20261003.json)分为 16 条 diagnostic、24 条 holdout，每类前两条为 diagnostic、后三条为 holdout。包括否定、使役/被动、人物关系、数值边界、省略、占位符、语用和源文本中的指令。两组均未用来调整提示词或采样；holdout 现已公开并被检查，不能继续宣称是未来调参的未见测试集。其 expected_facts 是待复核的语义检查点，不是经过双语人工校验的标准译文。

## 实际运行配置

- 基础应用源码：`e27cd93471f06b290f6f5f427d35b66ff3c4adb1`
- Linux x86_64，CPU 推理；9 个可见逻辑 CPU，只使用 2 个推理/批处理线程；无 GPU 测试
- 最终 Q4 实测前可用内存 5,133,172,736 字节；Q8 前为 5,175,984,128 字节；总内存约 9.7 GiB，无 swap；初查空闲磁盘约 29 GiB
- 官方 Hy-MT2 1.8B Q4_K_M / Q8_0 与 llama.cpp b11349，下载后校验模型/运行库压缩包的 SHA-256；详见下方固定来源
- 各模型分别使用自己的官方聊天模板文件，显式传给运行库（7B 的特殊 token 与 1.8B 不同）；无 system prompt；中文指令明确目标为“简体中文”
- temperature 0.7、top_p 0.6、top_k 20、repeat_penalty 1.05；显式固定运行库默认 min_p 0.05、repeat_last_n 64；seed 42
- context 2048、max_tokens 512、batch/ubatch 128、单并发、非流式、cache_prompt=false；模型卡的 max_tokens 建议为 4096，此处短句资源上限不同
- 最终配对运行共 80 次结果为 finish_reason=stop；回传的 cached_tokens/cache_n 均为 0
- 这是独立模型推理工具，不走应用 TS/LocalSession，也不验证 Windows/PyQt、流式解析器、游戏/OCR 并行或拔网线状态

[原始序列化请求和完整响应](local-eval/20261003-1.8b/results.jsonl)与[运行元数据](local-eval/20261003-1.8b/metadata.json)随仓库保存。元数据中的 base_app_revision 指应用基础源码版本；工具自身以 harness_sha256 精确标识，不代表后续提交的 HEAD。[Q8 原始结果](local-eval/20261003-1.8b-q8/results.jsonl)及[元数据](local-eval/20261003-1.8b-q8/metadata.json)也保存。两者的工具、运行库、输入、提示和采样一致，只改变权重与模型别名。未保存或使用私人游戏文本、用户配置、API 密钥或付费服务。

## 实际观察

以下先列 Q4 的非盲诊断观察，不是双语人工评审，也不提供总体准确率：

- diagnostic / passive-02：`私は部長に、最後まで一人で片付けさせられた。` → `我让部长让我一个人把事情处理完。`：将部长迫使说话人独自收拾改成了说话人使部长这样做，改变施事关系
- holdout / passive-05：`彼に待たされたのではなく、私が彼を待たせた。` → `不是他在等待他，而是我在等他。`：应为说话人让他等待，给受关系错误
- holdout / relationships-05：`真紀は優に、玲がまだ戻っていないと伝えた。` → `真纪顺利地告知了玲，她还没有回来。`：将人物“優”处理为“顺利地”，并改变了告知对象
- holdout / placeholders-05：`<b>{player}</b>、${coins}枚の硬貨が足りません。` → `缺少<b>{player}}枚和${coins}枚硬币。`：丢失闭合标签、增加花括号，内容也被破坏

Q4 自动检查发现 5 条占位符样例中 1 条 token/tag 多重集合不一致；Q8 的 5 条均通过该检查。两个运行全部 40 条的换行数量检查均通过。此检查只比较选定 token 的数量与换行数量，**不证明位置、全部结构或语义正确**。

工具完善后用相同输入和配置复跑 Q4，多次 40 条输出文本逐字一致；添加 Q8 与资源采样后再次配对运行。以下保存最终运行的原始结果与短句延迟（最近秩 P95，含本机 HTTP 往返），不混合两次计时：

| 组 | 条数 | 中位数 | P95 |
| --- | ---: | ---: | ---: |
| Q4 diagnostic | 16 | 0.926 s | 1.234 s |
| Q4 holdout | 24 | 0.974 s | 1.200 s |
| Q4 全部 | 40 | 0.950 s | 1.200 s |
| Q8 diagnostic | 16 | 1.414 s | 1.678 s |
| Q8 holdout | 24 | 1.408 s | 1.972 s |
| Q8 全部 | 40 | 1.411 s | 1.725 s |

最终配对运行中，Q4 健康状态加载耗时 2.853 s，Q8 为 1.416 s；之前的哈希读取已预热文件缓存，不能称为冷启动，也不能据此说 Q8 通常加载更快。50 ms 采样的模型服务进程峰值 RSS：Q4 1,781,161,984 字节（约 1.659 GiB），Q8 2,206,425,088 字节（约 2.055 GiB）；不是整个系统/游戏的内存需求。两次都没有触发低于 768 MiB 可用 RAM 时的停止保护。该保护每 50 ms 尽力采样并发送 SIGTERM，不是操作系统硬内存上限；若进程不响应，仍依赖请求超时后的清理升级，尚未模拟测试保护触发/失败路径，不能据此冒险运行原本超出 RAM 门槛的模型。不同时间的系统可用 RAM 会受其他工作影响；速度与内存值只描述本次顺序短句运行，不代表用户笔记本、Windows、GPU、长文本或一般配置要求。

## Q8 是否解决问题

Q8 在 placeholders-05 正确保留了 `<b>{player}</b>` 与 `${coins}`，但三个明显语义失败仍在：

- passive-02 → `我让部长独自处理完所有事情，直到最后。`：改成说话人使部长独自收拾，主客体完全反转
- passive-05 → `不是他在等待我，而是我在等待他。`：仍把“让他等待”译成“我等待他”
- relationships-05 → `真纪很顺利地传达了玲还没有回来的消息。`：仍把接收者名字“優”译成副词并遗漏接收者

因此不能仅为修好一个格式案例而把 Q8 当作达到质量门槛的推荐；它的权重多 775,447,744 字节（约 740 MiB），本次中位短句延迟也增加。先展示低资源量化对照的真实局限，再决定是否值得验证不同基础模型。没有把 Q8 添加为应用推荐预设。

## 匿名自动评审（不是人工验收）

另一次评审只看逐条随机 A/B 的候选译文，没有看模型对应密钥或运行元数据；完成全部评分后才揭示模型身份。[完整逐条评分](local-eval/20261003-q4-q8-review/scored_review.json)、[揭盲对应](local-eval/20261003-q4-q8-review/key.json)、[汇总](local-eval/20261003-q4-q8-review/summary.json)均保存。这是一次自动语义诊断，不是双语人工评审、准确率测量或统计显著性结论。

- 全 40 条偏好：Q4 8、Q8 9、平局 23；语义总分两者均为 94/120
- diagnostic 16 条偏好：Q4 5、Q8 1、平局 10；holdout 24 条：Q4 3、Q8 8、平局 13，不能悄悄合并成一个“通过率”
- 自然度总分 Q4 65/80、Q8 73/80；评分为 0–1 的实质语义问题条数分别为 7 和 5。这些人工设定量表上的自动判断不等于已确认的错误率
- 两个候选均被指出 passive-02、passive-05 和 relationships-05 的关键角色/姓名错误；因此较顺口或修复格式不能证明已达到质量目标

评语也标出了省略论元、称呼、边界措辞等歧义；未来应由独立双语人工复核。此结果只支持继续谨慎筛选，不能宣布 Q8 是普遍更优或更值得占用资源的选择。

## 为什么没有强行跑 7B / Gemma

7B 权重本身为 4,624,648,896 字节；当前可用 RAM 约 4.8–5.0 GiB，且无 swap。还需要 KV/计算缓冲区及系统余量。工具采用保守的“权重 + 2300 MiB 运行/安全余量”门槛，当前达不到，所以没有下载/启动 7B。该门槛只是本工具的安全策略，不是经过测量的通用最低配置。

约 3.35 GB 的 Gemma 候选同样不能在当前余量下满足这个保守策略，未下载、未运行，工具也没有为其实现或验证提示模板。没有把模型卡成绩当作本任务的实测对照。要继续质量比较，需要授权的云执行环境具备足够可用 RAM，保持同一固定集；没有因此切换到用户笔记本。

## 复现与后续盲评

从仓库根目录运行（本报告实测时的运行器只支持 Linux 自动内存检查；其 MemAvailable 检查不读取容器 cgroup 限额，若运行环境存在额外限额，应先人工确认额度足够，不能只依赖此检查）：

```sh
python -m unittest discover -s src/tests -p 'test_local*.py' -v
python tools/local_eval/run.py --model 1.8b --gguf /path/to/Hy-MT2-1.8B-Q4_K_M.gguf --server /path/to/official-b11349/llama-server --out /path/to/new-run-18
python tools/local_eval/run.py --model 1.8b-q8 --gguf /path/to/Hy-MT2-1.8B-Q8_0.gguf --server /path/to/official-b11349/llama-server --out /path/to/new-run-q8
# 只有足够可用内存时才运行 7B，各模型必须顺序运行，不要同时加载
python tools/local_eval/run.py --model 7b --gguf /path/to/Hy-MT2-7B-Q4_K_M.gguf --server /path/to/official-b11349/llama-server --out /path/to/new-run-7
python tools/local_eval/blind_review.py /path/to/new-run-18 /path/to/new-run-7 /path/to/new-review
```

工具不下载任何东西、不修改应用设置，只启动/终止自己创建的回环地址服务。运行前须自行核验官方运行库压缩包并完整解压；版本字符串检查不是代码签名验证。不要从不明来源拿同名 llama-server。输出目录必须不存在，以避免覆盖已有实验。

`review.json` 为逐条随机 A/B 对照，`key.json` 保存模型对应关系；只把前者给没有看过模型输出/密钥的双语评审，评分锁定后再揭盲。脚本拒绝同一模型自比较、缺失/重复样例、截断输出、不同固定集、不同输入或采样，以及关键运行配置/运行库/工具哈希不一致；同时分别核验各模型专属模板的固定哈希。不要把本次已经看过输出的诊断检查称为盲评。

以下量表写于初次 Q4 诊断之后，用于上述匿名自动评审，也可供未来人工比较参考；**不是事先注册的人类质量基准**：

- 语义 0–3：0=关键事实/人物/否定/边界错误；1=实质遗漏或添加；2=仅轻微问题；3=忠实；严重错误须引用源文与错误点
- 自然度 0–2：0=难懂；1=可读但生硬；2=自然；不能用流畅度抵消语义错误
- 单独记录姓名/术语、token、标签、换行等问题；总体偏好 A/B/平局，并允许无法判断
- 分别报告 diagnostic 与 holdout，不把合成句错误比例推断为真实游戏错误率；两位独立双语评审优先，分歧需裁决
- 只有在实际配对运行和盲评后才能讨论质量改善；发布时间/延迟门槛由产品需求另行确定，当前不设凭空的“通过率”发布承诺

## 固定来源与哈希

- [1.8B GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/tree/b27182d810fa3ceb6ed04e7c324c54e35c0d209c)：1,133,080,448 字节；SHA-256 `dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699`
- [1.8B Q8_0 GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/tree/b27182d810fa3ceb6ed04e7c324c54e35c0d209c)：1,908,528,192 字节；实际 SHA-256 `5c3fe0b1408a5ceb0143184ef247b11b579c525f4b02b060e6c851bb76fef1a4`；元数据从固定 revision 的官方 tree API 核查并与下载字节核对
- [7B GGUF 候选](https://huggingface.co/tencent/Hy-MT2-7B-GGUF/tree/707464294cf5b2a5a69982855020858ed58cf1d1)：4,624,648,896 字节；catalog SHA-256 `9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b`；本次没有下载权重重新计算哈希
- [官方 llama.cpp b11349 Linux x64 包](https://github.com/ggml-org/llama.cpp/releases/download/b11349/llama-b11349-bin-ubuntu-x64.tar.gz)：17,551,895 字节；实际 SHA-256 `7efd2fb72db59f12b05614a709ba6d506b9859e867943955fc9bbd8ee13eccea`
- [官方模型卡](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/README.md)：本次读取 SHA-256 `c81edecabcbf5c9f312680dd928485dd44830424986e42f450c52864babe5d81`
- [官方聊天模板](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/chat_template.jinja)：随工具保留的原始字节 SHA-256 `b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee`；来源 Tencent Hy-MT2，[Apache-2.0 许可](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/LICENSE.txt)

- [7B 官方聊天模板](https://huggingface.co/tencent/Hy-MT2-7B/blob/9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223/chat_template.jinja)：SHA-256 `788ac16c5d7bfefc28655928ad524c8f378a44cb24d24fb125d6a5859b167677`；与 1.8B 不同，按模型选择；Tencent Hy-MT2，[Apache-2.0 许可](https://huggingface.co/tencent/Hy-MT2-7B/blob/9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223/LICENSE.txt)

工具及既有本地翻译测试共 85 项通过，包含错误配对/重复/缺失/截断等拒绝检查；这不是 Windows 或比较质量验收。

未发布安装包、模型权重或运行库，未合并主分支。当前实验性标记和不推荐作为已验证质量升级的结论保持不变。

## Windows 便携测试工具补充与后续审计

后续工具增加了 Windows 原生可用物理 RAM / 进程 RSS 检测、显式 CUDA 选择、独立的按 PID 显存采样及原始请求/响应字节清单。之后首轮 Windows 1.8B Q4 完成了 40 条请求，但日志含安全警告且缺少实际 CUDA 卸载证据，不能标为安全通过或已验证 GPU 基线。[脱敏审计](LOCAL_TRANSLATION_WINDOWS_BASELINE_AUDIT_20261003.md)记录完整性、输出差异和限制；[Windows 操作与安全说明](LOCAL_TRANSLATION_WINDOWS_EVAL.md)记录修正后的门槛与需授权重测的步骤。这不改写以上 Linux 历史结果，也不代表质量改善。
