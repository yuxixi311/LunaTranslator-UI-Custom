# License and Attribution / 许可证与归因

## Base application / 基础软件

- **LunaTranslator** — Copyright © HIllya51 and contributors.
- Upstream repository: <https://github.com/HIllya51/LunaTranslator>
- Upstream baseline used for this fork: `c7d00f7320e872f8717385e173a0d76f891aa9e9`.
- LunaTranslator UI Optimized Custom Edition is an unofficial modified version. It is not endorsed by or affiliated with the upstream author.
- The combined modified work is distributed under **GNU General Public License version 3 (`GPL-3.0-only`)**. The complete license is preserved in [`LICENSE`](LICENSE).

LunaTranslator 原始代码的版权属于 HIllya51 及各贡献者。本项目是非官方修改版，不代表原作者立场，也不构成官方合作或背书。整体修改版本继续依据 GPLv3 发布。

## Fork modifications / 改版内容

The UI, learning workflow, Hook state repair, manual Japanese reading controls, TTS pause/rate behavior, settings aggregation, GiNZA integration, learner-facing syntax grouping, tests, and release tooling added by this fork are described in [`MODIFICATIONS.md`](MODIFICATIONS.md). No proprietary relicensing has occurred.

## Design reference / 设计参考

- `apple-design-skill` — Copyright © 2026 naplesblue, MIT License.
- Portions of its `motion.md` are adapted from `emilkowalski/skills`, Copyright © 2026 Emil Kowalski, MIT License.
- Lucide line-icon geometry is under the ISC License, Copyright © Lucide Contributors.
- Reference repositories: <https://github.com/naplesblue/apple-design-skill>, <https://github.com/emilkowalski/skills>, and <https://github.com/lucide-icons/lucide>.
- The combined MIT and ISC notices used by this project are preserved in [`LICENSES/LICENSE.apple-design-skill`](LICENSES/LICENSE.apple-design-skill).

No Apple proprietary font, SF Symbols asset, screenshot, interface file, or Apple trademark is bundled. The interface uses ordinary design properties and Windows system fonts.

## Bundled offline Japanese syntax runtime / 内置离线日语句法运行时

Release archives include a CPython x64 bundle under `files/plugins/ginza`. Direct components include:

| Component | Version | License |
|---|---:|---|
| GiNZA / ja_ginza | 5.2.0 | MIT |
| spaCy | 3.8.15 | MIT |
| SudachiPy | 0.6.11 | Apache-2.0 |
| SudachiDict-core | 20260723 | Apache-2.0 |
| NumPy | 2.5.2 | BSD-3-Clause and bundled compatible notices |

Package metadata and license files remain in their respective `.dist-info` directories. Exact direct versions are locked in [`src/scripts/ginza-requirements.txt`](src/scripts/ginza-requirements.txt), and source locations are recorded in [`THIRD_PARTY_SOURCE.md`](THIRD_PARTY_SOURCE.md).

## Binary distribution notices / 二进制分发声明

- Release archives preserve the upstream runtime license collection under `LICENSES/`.
- The root archive includes `LICENSE`, `LICENSE_AND_ATTRIBUTION.md`, and the design-reference notice.
- Personal `userconfig`, caches, translation records, and credentials are excluded from releases.
- The customized Windows launchers are unsigned because the upstream private signing certificate is unavailable. This does not remove the GPLv3 rights or obligations.

All copyright and license notices found in the upstream source are preserved. Any future bundled asset or dependency must be recorded here before release.

## Optional local translation models / 可选本地翻译模型

- **Tencent Hy-MT2 1.8B and 7B** — Copyright (C) 2026 Tencent. Apache License, Version 2.0.
- Official licenses: [1.8B](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/LICENSE.txt), [7B](https://huggingface.co/tencent/Hy-MT2-7B/blob/9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223/LICENSE.txt).
- The new preset contains only pinned download metadata; model weights and llama.cpp executables are not included by this feature. Exact official revisions, byte sizes and SHA-256 values are documented in [local setup](docs/LOCAL_TRANSLATION.md).
- llama.cpp is an existing upstream integration; users select a separately obtained official runtime. Any future bundled runtime/model must retain its complete applicable license and NOTICE material.
- Apache-2.0 model licensing does not change this application's GPL-3.0-only license or corresponding-source obligations. No noncommercial GalTransl weights or extreme-quantization kernels are added to this preset.
