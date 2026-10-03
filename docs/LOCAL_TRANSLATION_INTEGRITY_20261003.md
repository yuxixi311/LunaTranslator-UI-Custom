# Existing 1.8B integrity investigation (2026-10-03)

## Outcome and limits

This change prevents some structurally invalid translations from being silently
displayed. It does **not** repair their meaning, make weights smaller, improve
the model's semantic score, or establish superiority over Google/online engines.
No bigger model, quantization change, new weight download, or new inference run
was performed. The experimental provider stays disabled by default; other
providers are unchanged.

The isolated local provider checks brace placeholders, common bounded printf
placeholders, literal angle-bracket tags (including attributes and order), and
logical LF newline count. Named/numbered placeholders may move for target-language
grammar, but their identities and multiplicities must match. Unnumbered printf
conversions must keep their original sequence to preserve argument binding.
CRLF versus LF is accepted.
This does not validate the position of a placeholder relative to meaning or
preserve all possible game scripting formats. Ambiguous prose, unsupported
format languages, character names, and semantic relationships are not inferred.
ASCII word suffixes after printf conversions are excluded to avoid treating
ordinary `%score` text as a placeholder; this bounded grammar can miss genuine
adjacent printf text. Escaping a real HTML-like tag changes rendering semantics
and is intentionally rejected; already escaped `&lt;b&gt;` is not treated as markup.

Protected input is buffered until the existing response finishes. Invalid
output raises a Chinese error identifying the changed placeholder/tag/newline
and telling the user to compare the source. It emits no invalid partial text,
does not save the rejected output to translation cache, and rolls back the
history pair before the next request. The normal provider error callback shows
the error; there is no silent success, fabricated repair, retry, or online
fallback. Source text is not embedded in the error. Ordinary single-line text
without recognized tokens retains streaming.

Cost: no added prompt tokens or model calls; one regex/count pass over the
source and result. Buffering delays the first displayed text until the existing
request completes for protected input. It uses bounded text memory, not extra
weights or model context. The underlying transport still caps the response at
4 MiB, and the collector caps total received characters, including resets.
No Windows/Qt UI or new inference latency measurement is claimed for this patch.

## Recorded-output replay

Command: `python tools/local_eval/replay_integrity.py <existing-results.jsonl>`.
The tool verifies all 40 unique frozen IDs, fixture SHA-256, and the baseline
request text before replaying. It does not rewrite the fixture or outputs.

| Existing outputs | Unprotected | Accepted structure | Rejected structure |
| --- | ---: | ---: | ---: |
| Strict Windows 1.8B Q4, CUDA | 35 | 4 | 1 |
| Linux 1.8B Q4 | 35 | 4 | 1 |
| Linux 1.8B Q8 | 35 | 5 | 0 |

The rejected Q4 case is `placeholders-05`: `{player}` was translated into
`{玩家}`. The guard is syntax-general and contains no case ID, source phrase,
target word, or language-specific replacement. These are retrospective replay
results, **not a newly held-out model-quality result**. Existing known semantic
failures remain; a structure pass must never be presented as a quality pass.

128 focused headless local tests passed, including protected streaming,
rollback, production cache collector, CRLF/LF, duplicate/reordered placeholders,
tag escaping, comparison prose, percent-escape parity, long malformed input,
and unchanged ordinary streaming. These tests
are not full application/Windows acceptance.

## Prompt, template, and tokenizer findings

- Current isolated Chinese default prompt matches the official full language
  name and no-extra-explanation structure. The glossary path uses the official
  terminology instruction. No new prompt is promoted without inference evidence.
- [Official 1.8B chat template](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/chat_template.jinja)
  matches the checked-in evaluation template text. Evaluation supplies that
  template explicitly; the application currently relies on GGUF metadata and
  its selected runtime. Evaluation is not proof of app-side template parity.
- [Official tokenizer config](https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/tokenizer_config.json)
  uses token 120020, `<｜hy_place▁holder▁no▁2｜>`, as EOS. The strict Windows log
  lists this same token as EOS and EOG after initialization.
- [Pinned llama.cpp source](https://github.com/ggml-org/llama.cpp/blob/fb4b2737a/src/llama-vocab.cpp#L2944-L2948)
  inserts a missing EOS token into the EOG set immediately before printing
  `special_eos_id is not in special_eog_ids`. This warning is not evidence that
  generation continued without its stop token. No unsupported tokenizer patch
  or claim that this warning explains role/meaning errors is justified.

## Lightweight distribution and next test

The code contains download metadata, not model weights. Model acquisition is
optional, explicit first-use download with size/license disclosure or verified
import; reopening the application does not download/start automatically. The
current Q4 file is still 1,133,080,448 bytes. Optional download is a distribution
benefit, not a reduction of model storage/RAM needs. There is no model-removal
UI yet. After stopping the owned service and exiting the application, a user
can remove an unneeded downloaded GGUF through their file manager; imported
files belong to the user and must never be silently deleted by the launcher.

A minimal general preservation instruction and bounded-context comparison
remain unrun. This cloud workspace has no usable model/runtime; direct access
to the official model source timed out. Do not send the task to the user's
desktop or download a larger model to work around this. When the existing
1.8B artifacts are available in the authorized cloud environment, preregister
one general candidate prompt before a single comparison, freeze sampling and
fixture, report exact outputs plus added prompt tokens/latency/RAM, and score
semantics separately from format. The now-inspected 24 holdout cases must be
described as a regression set, not fresh blind evidence; any promotion needs
new untouched validation data. Do not patch individual failed sentences.
