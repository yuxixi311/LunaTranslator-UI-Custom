# v1.0.1 portable popup hotfix: packaging and verification

This release is rooted at the previously released `v1.0.0` commit
`87d125adc2cc528b5781d87d5610c2615f68efe2`. It does not release the experimental
local-translation branch. Only the seven popup runtime paths in
`src/scripts/package_popup_hotfix.py` are changed, plus their existing digest
slots in the two customized launchers and release notices.

## Complete package

- Filename: `LunaTranslator-UI-Custom-v1.0.1-x64.zip`
- Size: 243,563,643 bytes
- SHA-256: `68ac9892c7776482288c6c1ec01ec315aa70bbfdb202edecbf7980a09e20400b`
- Members: 4,923
- The old package has 4,921 members. 4,909 remain byte-identical; 12 change
  (seven runtime sources, two launchers, three notices). Two files are added:
  `RELEASE_NOTES.md` and `BUILD_INFO.json`
- Existing GiNZA, OCR, Python/Qt and other third-party/runtime files are retained
  byte-for-byte. There are no new dependencies or generator model weights
- The smaller ZIP size comes from compression settings, not model reduction

Both launchers have exactly six changed Python digest slots. A second refresh
dry-run reports zero stale digests. All other executable bytes remain unchanged
apart from the permitted PE checksum/signature-directory fields; the launchers
remain unsigned custom binaries. HTML is verified separately by its file hash.

The machine-readable packaging record is
[`release/POPUP_PACKAGE_VERIFICATION.json`](../release/POPUP_PACKAGE_VERIFICATION.json).
The public package contains no user configuration, caches, translation records,
private workspace data or unfinished local-translation provider files. A scan of
3,387 text members found no credential patterns after distinguishing an unchanged
SPDX license identifier from an API-key prefix.

## Reproduction

Obtain the exact v1.0.0 asset from this repository's
[v1.0.0 release](https://github.com/yuxixi311/LunaTranslator-UI-Custom/releases/tag/v1.0.0).
The builder requires its exact 251,214,174-byte size and SHA-256
`aafdbcadee8f75054ea3aa6783f6efb18b5cc0697690cdf9311a311f4115d19a`.
From the v1.0.1 source checkout, with Python 3.10+:

```sh
python src/scripts/package_popup_hotfix.py \
  --base-archive /path/to/Luna-Translate-UI-x64.zip \
  --output /path/to/LunaTranslator-UI-Custom-v1.0.1-x64.zip \
  --report /path/to/POPUP_PACKAGE_VERIFICATION.json
```

Output paths must not already exist. The builder performs no downloads and runs
no native binary. It checks the pinned input, paths, complete inventory and CRC,
requires each modified Python file to have an existing digest slot in both
launchers, updates those digests, and verifies the final member-by-member content.
The archived runtime is reused rather than rebuilt from moving dependencies.
ZIP compression can differ across zlib versions; content manifests identify the
payload independently of compression.

## Tests and limits

- 39 popup/renderer Python regressions and 6 JavaScript bridge scenarios passed
- 10 package-input safety tests passed
- Existing headless audio pause (3), Japanese reading shortcut (8), and learning
  segmentation (7) tests passed, along with design-token and text-source checks
- Changed Python compilation, nine inline-JavaScript syntax checks, source diff
  whitespace checks, archive CRC/hash/inventory, launcher digest checks and
  sensitive-content checks passed
- Native Windows GUI/focus and game-compatibility regression testing was not run
  for this hotfix. This limitation is also disclosed in the downloadable package
  and release notes; package integrity is not a native GUI pass

See the focused [native checklist](LOOKUP_POPUP_TOGGLE.md#remaining-native-acceptance)
for additional validation. Extract the portable release into a new writable
directory and back up existing configuration before evaluating it. No automatic
local installation/update is performed.
