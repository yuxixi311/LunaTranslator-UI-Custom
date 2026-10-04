# Public lexical feasibility design snapshot

Status: **NOT EXECUTED; source preparation only**. This restates the technical proposal without machine-specific metadata. It grants no package download, installation, analyzer or model execution authority.

## Fixed mechanism

Use SudachiPy 0.6.11 with SudachiDict-core 20260723, SplitMode.C and surface projection. Retain the six-entry `canon.json`. For every literal occurrence of a canon key, require a token with exactly the same Unicode-code-point span and original source slice, `is_oov=false`, `dictionary_id=0`, and the first three POS fields `名詞`, `固有名詞`, `人名`. Admit the entire key only if all its occurrences pass. Ordinary, mixed, embedded or unknown occurrences withhold that key. A source with no admitted key remains a baseline-policy input.

No source normalization, alias addition, user dictionary, mode change, output replacement, case-ID rule or expected label is part of activation. Source-sense labels are consulted only in assessment. POS does not prove semantic sense or repair grammar and role assignment.

## Fixed diagnostic population

Use 16 public illustrative synthetic cases: four explicit-person, four ordinary-word, four same-key mixed-sense, two embedded-key and two no-match controls. Intended assessment decisions and occurrence offsets were authored before any analyzer output. They are mechanism diagnostics, not translation holdout evidence. Include all 32 already-public seen source regressions, retaining their order. Exactly 48 tokenizer calls are planned, one per source, with no warmups, retries, alternate modes or output-dependent exclusions.

Require complete technical evidence and exact intended entry decisions on all 16 diagnostic cases. Report failures by category. A mismatch rejects this fixed mechanism; do not tune it on these examples. A complete match is not proof of semantic or translation improvement. A later semantic experiment needs a separate predeclared design and new held-out cases; seen cases remain regressions.

## Dependency and resource boundaries

The target is CPython 3.12.14 on Linux x86_64 with glibc >= 2.17. Exact official wheel URL, byte count and SHA-256 are in `PYPI_PINS.json`; no source distribution, build hook, dependency resolution or fallback is proposed. The two wheels total 73,904,174 compressed bytes under a 100 MiB cap. Require 2 GiB free disk and 2 GiB MemAvailable before transfer.

After a separately authorized transfer, verify all archive members and RECORD hashes before extraction, reject traversal, links, duplicate members, startup hooks and relocations, and require the dictionary's exact target bytes. Aggregate uncompressed and installed payload must each stay <= 512 MiB. Setup uses an isolated virtual environment and offline installation without dependencies or extras. Preserve upstream notices.

Owned lifecycle limits are 240 seconds for both downloads together and 60 seconds each for setup, parse and assessment. Parser CPU limit is 15 seconds, address-space limit 1 GiB and output-file limit 4 MiB. Address space is not measured peak RSS. The controller reserves cleanup time and signals only its owned process group. Failure or uncertain cleanup is terminal; keep the claim and do not repeat a consumed stage.

Python socket audit hooks apply after download; they are not an OS network sandbox and do not prove a native extension cannot network. No Luna startup, spaCy/GiNZA import, translation model, GPU workload or Windows performance claim is part of this source snapshot.
