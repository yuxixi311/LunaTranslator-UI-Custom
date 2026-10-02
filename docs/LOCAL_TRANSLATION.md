# 实验性本地翻译快速设置 / Experimental local translation quick setup

> 实验性开发分支功能。Windows x64 / PyQt 真机验收仍未完成；Linux/CPU 的有限真实模型初测发现语义错误，尚未证明优于既有在线翻译。这不是已验证的二进制发布。

## 使用方式

1. 备份现有 `userconfig`，使用单独的开发测试目录。
2. 在“常用设置 → 本地翻译 → 配置本地翻译…”打开新入口。初始选项是 **实验性 Hy-MT2 1.8B Q4_K_M + CPU**，不代表推荐其翻译质量；7B Q4_K_M 为可选较大模型。
3. 从 [llama.cpp 官方 Releases](https://github.com/ggml-org/llama.cpp/releases) 获取适合 Windows x64 的运行库，解压并保留同目录 DLL，然后在此选择 `llama-server.exe`。也可继续用原来的 llama.cpp Launcher 获取运行库。此入口不自动安装、执行下载脚本或更改旧 Launcher 配置。
4. 点击“下载并校验模型”，先确认体积和许可证，再从腾讯官方 Hugging Face 固定版本下载。网络不可用时，先在其他电脑取得下表的相同文件，再“导入同版本 GGUF…”。导入只引用原文件，不复制或删除它。任意 GGUF / 同名文件不会被直接当作受支持模型；大小和真实 SHA-256 都必须吻合。
5. 选择 CPU 或 GPU / 自动。使用 GPU 需对应 CUDA / Vulkan 运行库和可用驱动；显存不足可停止后改 CPU。端口默认 `18080`，只绑定 `127.0.0.1`。不会关闭占用端口的其他程序。
6. 点击“启动并启用实验性本地翻译”。每次启动会重新校验模型，启动自己持有的进程，确认 `/health` 与本次随机模型别名均匹配后，才启用新接口。首次请求已明确使用 `Hy-MT2` 提示词。
7. “停止本地翻译”只停止本入口启动的进程并关闭新接口。关闭设置窗口会取消未完成操作；已就绪的进程继续工作，退出应用时结束。重开应用后需手动启动，无自动下载或启动。

### 原有接口与离线范围

- 所有原有翻译接口、API Key、开关、模型目录和 llama.cpp Launcher 参数保持原样。新增接口默认关闭，配置独立保存在 `local_translation` / `local_hymt` 项。
- **其他已开启的在线接口仍可能发送原文。** 要只使用离线翻译，请自行到翻译设置关闭这些接口。在线朗读、在线词典等功能也不因此变成离线。
- 新预设的翻译请求仅能发往其当前本机端口，禁用代理和 HTTP 重定向；连接失败会报错，不会切换到 Google、DeepSeek 或其他云端 API。
- 原来的高级配置入口与模型目录仍可使用；任意模型、其他量化版本或远程服务器继续通过原有功能配置。此预设只承诺验证下面两个固定文件。

## 模型与资源

| 预设 | 下载字节数 | 短上下文资源规划参考 |
|---|---:|---|
| Hy-MT2 1.8B Q4_K_M（实验性初始选项） | 1,133,080,448 | 建议约 3–4 GB 可用内存；CPU 可运行，当前电脑速度待验证（已有 Linux 初测） |
| Hy-MT2 7B Q4_K_M（实验性可选） | 4,624,648,896 | 建议约 6–7 GB 可用显存并留足系统内存；CPU 也可尝试，速度待测 |

以上内存/显存为规划估计，**不是本程序实测最低配置或速度保证**。文件大小不等于运行内存。游戏、OCR、句法模型和其他应用同时占用资源时，可能不足。默认上下文 `2048`、并发 `1`、输出上限 `512`（高级设置可到 `1024`）；上下文历史默认关闭，启用时最多保留 3 组历史；避免同时加载多个大模型。原有术语表处理继续复用 Sakura/Hy-MT2 实现。先使用小模型，再自行比较较大模型。

### 官方参数与质量边界

新快速预设固定采用[腾讯官方 1.8B / 7B 模型卡](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/README.md)的四项采样值：`temperature=0.7`、`top_p=0.6`、`top_k=20`、重复惩罚 `1.05`。发给 llama.cpp 时使用其有效字段 `repeat_penalty`，不依赖会被忽略的 `repetition_penalty`。中文指令使用“简体中文 / 繁体中文”等中文语言全名；不添加默认 system prompt。这些修正仅用于新预设，原有 Sakura/Hy-MT2 接口不变。

采样值由此快速预设固定管理，旧开发版本保存的 `.6/.8/1` 值不会影响实际请求，原有保存内容不被改写。高级自定义采样仍可使用原来的独立接口。本预设有意保留 `2048` 上下文和默认 `512` 输出上限，以控制资源占用；没有声称复现官方 `4096` 输出上限的全部部署设置。官方卡未指定的参数仍可能取决于 llama.cpp 版本，例如 b11349 的 `min_p=0.05`；复现实测时应同时记录这些有效参数。

Linux/CPU 合成文本初测及官方参数修正后的复测仍出现使役/被动关系丢失、把道歉译成感谢、条件边界改变等实质语义问题；另外 8 条事先固定的新样本还出现语义错误与占位符破坏。见[实测摘要](LOCAL_TRANSLATION_SMOKE_RESULT.md)。对齐官方参数是配置修正，**没有消除这些已观察到的质量问题**。轻量模型的优点目标是低资源、无 API 费用和离线可用性，不能据此称为已验证的“更高翻译质量”选择。7B 的质量优势也尚未在此应用中验证。重要剧情、人物关系或关键句请对照原文、术语表和其他可靠来源复核。

下载需要模型大小外加至少 16 MiB 可用空间；重新下载损坏文件时，旧文件在成功前仍占空间。独立 `.part` 文件在同一目录写入，完整大小与 SHA-256 校验、刷新磁盘后原子替换。错误或取消清理本次临时文件，旧文件不受影响。重试从头下载，不支持断点续传。取消最多需等待当前网络读超时（30 秒）；强制结束应用可能留下 `.part`，可在应用退出后自行删除。

### 固定来源与完整性

元数据于 2026-10-02 对照腾讯官方 Hugging Face LFS 指针核查；不是 Xet 存储哈希。

- [1.8B 官方固定提交](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/commit/b27182d810fa3ceb6ed04e7c324c54e35c0d209c)
  - revision: `b27182d810fa3ceb6ed04e7c324c54e35c0d209c`
  - filename: `Hy-MT2-1.8B-Q4_K_M.gguf`
  - SHA-256: `dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699`
- [7B 官方固定提交](https://huggingface.co/tencent/Hy-MT2-7B-GGUF/commit/707464294cf5b2a5a69982855020858ed58cf1d1)
  - revision: `707464294cf5b2a5a69982855020858ed58cf1d1`
  - filename: `Hy-MT2-7B-Q4_K_M.gguf`
  - SHA-256: `9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b`

## 许可证和分发边界

Tencent Hy-MT2 模型版权归 Tencent，依据 Apache-2.0 提供。官方许可证：[1.8B](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/LICENSE.txt)、[7B](https://huggingface.co/tencent/Hy-MT2-7B/blob/9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223/LICENSE.txt)。本分支只包含下载元数据、设置、源码与合成测试文本，**不捆绑模型权重**。下载模型与应用许可是两件事；LunaTranslator 修改版仍为 GPL-3.0-only，分发二进制仍需履行对应源码等义务。未来若捆绑运行库或模型，须保留相应完整许可证、归因与适用 NOTICE，记录准确版本。不会因采用 Apache 模型而改变应用许可证。

本快速设置没有包含 GalTransl 的非商业权重或尚依赖特殊内核的极低位量化。没有改动原有模型目录的许可与兼容性承诺。

## 故障排查

- 无法下载：检查到 Hugging Face 的连接、磁盘空间和证书；可用离线导入。不要绕过 TLS 证书错误。下载采用标准库系统代理，翻译与健康检查始终不走代理。
- 校验失败：确认选择的模型/量化完全相同，重新取得固定版本文件。不要将页面的 Xet hash 当作 SHA-256。
- 启动失败 / 缺 DLL：检查官方运行库是否完整、CPU/GPU 架构是否匹配、驱动和可用 RAM/VRAM；查看“打开本地服务日志”。
- 端口占用：停止本预设后更换端口。不按进程名查杀，也不连接不明的现有服务。
- 超时：180 秒仍未返回正确健康状态与模型别名会停止本次进程并报错。检查日志，改小模型/CPU 或换兼容运行库。
- 日志：`cache/local-translation-server.log` 来自本地运行库，可能包含路径或运行库自身输出；发布 bug 报告前检查和删去个人内容。不要上传 `userconfig`、翻译记录或模型文件。

## English summary

Open Common Settings → Local translation and explicitly select a trusted official Windows x64 `llama-server.exe`. Choose the default Hy-MT2 1.8B Q4_K_M or optional 7B Q4_K_M, confirm the first-use download, or import the exact pinned GGUF. Imports and starts verify actual SHA-256 and byte size. Downloads are temporary, cancellable and atomically installed after validation.

The experimental, disabled-by-default provider is isolated from all existing providers, API keys and advanced launcher settings. It uses the existing llama.cpp/Sakura implementation, a loopback-only owned server and an explicit Hy-MT2 prompt. No cloud fallback is added. Existing enabled online providers stay enabled: switch them off yourself for offline-only translation. Separate limited Linux/CPU checks, including a corrected-protocol rerun and fresh held-out synthetic cases, still found substantive semantic and placeholder errors. See the [smoke-test findings](LOCAL_TRANSLATION_SMOKE_RESULT.md). The correction does not establish superiority over online translation. Windows application behavior and broader quality/performance still require the [acceptance plan](LOCAL_TRANSLATION_TEST_PLAN.md).
