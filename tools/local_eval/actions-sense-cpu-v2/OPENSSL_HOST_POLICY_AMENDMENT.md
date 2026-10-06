# Separate exact OpenSSL host-library acceptance amendment

This source-only amendment adds exactly libssl.so.3 and libcrypto.so.3 to the
closed host-library SONAME list. It is an explicit operational acceptance change,
separate from diagnostics. It adds no wildcard, package install, extra download,
request, native probe, model call or retry. No actual run is authorized here.
The original failed run's initiating cause remains UNKNOWN.

The source evidence was independently reviewed at the exact pinned llama.cpp
commit fb4b2737a808a3fb7c2117a498f43815dc9be53e:

- The Linux x64 release uses Ubuntu22.04, installs libssl-dev and applies the
  frozen CPU release flags:
  https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/.github/workflows/release.yml#L149-L217
- LLAMA_OPENSSL defaults ON:
  https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/CMakeLists.txt#L144
- cpp-httplib finds a supported OpenSSL version and publicly links its SSL and
  Crypto targets:
  https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/vendor/cpp-httplib/CMakeLists.txt#L128-L151
- The server implementation links cpp-httplib and llama-server links that
  implementation:
  https://github.com/ggml-org/llama.cpp/blob/fb4b2737a808a3fb7c2117a498f43815dc9be53e/tools/server/CMakeLists.txt#L49-L66

This supports expected SSL/Crypto linkage. It does not establish the produced
archive's actual DT_NEEDED entries or prove that the original failure involved
OpenSSL. Both facts remain unobserved. Actual dependencies are checked only after
pinned acquisition and extraction, before the existing version/server execution.

The same rules apply to the two added names: exact supported cache format/flags,
no relevant hwcap or duplicate/ambiguous resolution, exact canonical system
library directory, observed hashes and ELF dependency closure, interpreter/cache/
symlink/hash rechecks, and rejection of unresolved post-extraction dependencies.
The preclaim cache policy now requires those exact entries along with the prior
closed list. Missing entries, old/different ABI names, alternate paths, ambiguous
candidates or unsupported binary facts stop. No unreviewed loader fallback exists.

Inert fixtures cover the exact positive cache/ELF closure, missing SSL/Crypto,
old libssl.so.1.1, ambiguous libcrypto.so.3, relevant SSL hwcaps and unresolved
post-extraction Crypto. They do not run or inspect real host libraries. All
scientific cases/model/sampling/quality/coverage/cost rules and request/resource/
time/byte limits remain unchanged.
