# Third-Party Source Reference

This document identifies the principal third-party source packages bundled in the `v1.0.0` Windows release. It supplements, and does not replace, the license texts and package metadata included in the archive.

| Component | Version | Source / project page | License |
|---|---:|---|---|
| LunaTranslator | baseline `c7d00f7` plus this repository's modifications | <https://github.com/HIllya51/LunaTranslator> and this repository | GPL-3.0-only |
| GiNZA / ja_ginza | 5.2.0 | <https://github.com/megagonlabs/ginza> | MIT |
| spaCy | 3.8.15 | <https://github.com/explosion/spaCy> | MIT |
| SudachiPy | 0.6.11 | <https://github.com/WorksApplications/SudachiPy> | Apache-2.0 |
| SudachiDict-core | 20260723 | <https://pypi.org/project/SudachiDict-core/> | Apache-2.0 |
| NumPy | 2.5.2 | <https://github.com/numpy/numpy> | BSD-3-Clause and bundled notices |

The exact direct Python requirements are in [`src/scripts/ginza-requirements.txt`](src/scripts/ginza-requirements.txt). Transitive packages retain their package metadata and license files inside the release's `files/plugins/ginza` directory. The upstream application runtime's own license collection is preserved under `LICENSES/` in the release archive.

The preferred form for modifying LunaTranslator UI Optimized Custom Edition is this Git repository. Release tags, packaging scripts, dependency locks, and launcher-refresh tooling are included so a recipient can inspect and rebuild the modified portions.
