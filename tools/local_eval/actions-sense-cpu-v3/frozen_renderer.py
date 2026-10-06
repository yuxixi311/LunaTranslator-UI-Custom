"""Inert, standard-library-only evaluation renderer. No translator or I/O.

Only the exact ec749944 no-glossary, context-free local_hymt baseline is in
scope. A token counter is injected, never imported or downloaded here. Every
abstention returns the caller's ORIGINAL request, not a blank translation.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Callable, Optional


POLICY_VERSION = "sense-candidate-prefix-v1"
BASELINE_TEMPLATE = (
    "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{}"
)
# One frozen candidate. No alternate wording, inline tags, examples, or selector.
PREFIX_TEMPLATE = (
    "词义参考（非穷尽）：「{headword}」可能指{senses}。"
    "请按各处原文理解，不必限于这些词义。\n\n"
)
MAX_SIDECAR_BYTES = 8192
MAX_HEADWORDS = 6
MAX_SOURCE_CHARS = 4096
MAX_PROMPT_TOKENS = 384
MAX_HINT_DELTA_TOKENS = 64
_HEADWORD = re.compile(r"[A-Za-z0-9\u3041-\u3096\u30a1-\u30fa\u3400-\u4dbf\u4e00-\u9fff々ー]{1,16}\Z")
_SENSE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]{1,12}\Z")
# Deliberately conservative lexical-data gate, not a claim to solve injection.
# Independently reviewed and pinned bytes remain mandatory.
_INSTRUCTION_MARKERS = (
    "ignore", "instruction", "system", "assistant", "developer", "prompt",
    "忽略", "指令", "提示词", "系统消息", "输出", "回答", "翻译", "执行",
)


@dataclass(frozen=True)
class Entry:
    headword: str
    senses: tuple[str, ...]


@dataclass(frozen=True)
class Lexicon:
    entries: tuple[Entry, ...]
    digest: str


@dataclass(frozen=True)
class LexiconLoad:
    lexicon: Optional[Lexicon]
    reason: str


@dataclass(frozen=True)
class Decision:
    # NO_HINT preserves this object by identity as well as preserving its bytes.
    messages: list[dict[str, str]]
    hint_active: bool
    reason: str
    headword: Optional[str] = None
    occurrences: int = 0
    baseline_tokens: Optional[int] = None
    candidate_tokens: Optional[int] = None


def baseline_messages(raw_source: str) -> list[dict[str, str]]:
    """Evaluation copy of the pinned production baseline, not a product edit."""
    if type(raw_source) is not str:
        raise TypeError("raw_source must be str")
    return [{"role": "user", "content": BASELINE_TEMPLATE.format(raw_source)}]


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _safe_field(value, pattern):
    return (
        type(value) is str
        and pattern.fullmatch(value) is not None
        and not any(marker in value.casefold() for marker in _INSTRUCTION_MARKERS)
    )


def load_lexicon(raw_bytes: bytes, *, reviewed_sha256: Optional[str]) -> LexiconLoad:
    """Load only reviewed exact bytes; no filesystem/network or auto-repair.

    The review digest is supplied from the independent lexicon freeze, not
    trusted merely because it is stored alongside an arbitrary JSON payload.
    Validation rejects the entire inventory on any defect, never prunes it.
    """
    if type(raw_bytes) is not bytes or not 0 < len(raw_bytes) <= MAX_SIDECAR_BYTES:
        return LexiconLoad(None, "unreliable_lexicon")
    if type(reviewed_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", reviewed_sha256):
        return LexiconLoad(None, "unreviewed_lexicon")
    digest = sha256(raw_bytes).hexdigest()
    if digest != reviewed_sha256:
        return LexiconLoad(None, "lexicon_digest_mismatch")
    try:
        data = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        if type(data) is not dict or set(data) != {"version", "entries"}:
            raise ValueError("schema")
        if data["version"] != POLICY_VERSION:
            raise ValueError("version")
        items = data["entries"]
        if type(items) is not list or not 1 <= len(items) <= MAX_HEADWORDS:
            raise ValueError("entry count")
        entries = []
        seen = set()
        for item in items:
            if type(item) is not dict or set(item) != {"headword", "senses"}:
                raise ValueError("entry schema")
            key, senses = item["headword"], item["senses"]
            if not _safe_field(key, _HEADWORD) or key in seen:
                raise ValueError("headword")
            if type(senses) is not list or not 2 <= len(senses) <= 3:
                raise ValueError("sense count")
            if any(not _safe_field(sense, _SENSE) for sense in senses):
                raise ValueError("sense")
            if len(set(senses)) != len(senses):
                raise ValueError("duplicate sense")
            seen.add(key)
            entries.append(Entry(key, tuple(senses)))
        return LexiconLoad(Lexicon(tuple(entries), digest), "valid")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return LexiconLoad(None, "unreliable_lexicon")


def _literal_spans(source: str, key: str) -> list[tuple[int, int]]:
    """Case-sensitive substrings, deliberately NOT semantic word boundaries."""
    result = []
    start = 0
    while True:
        index = source.find(key, start)
        if index < 0:
            return result
        result.append((index, index + len(key)))
        start = index + 1  # Detect even overlapping occurrences of one key.


def render_candidate(
    raw_source: str,
    baseline: list[dict[str, str]],
    lexicon_bytes: bytes,
    *,
    reviewed_sha256: Optional[str] = None,
    count_prompt_tokens: Optional[Callable[[list[dict[str, str]]], int]] = None,
) -> Decision:
    """Add one candidate prefix or return the exact existing baseline request.

    The callback must count the full frozen chat template, including generation
    marker/BOS, using the execution tokenizer locally. Character counts and
    approximate tokenizers are not valid for a real evaluation. No execution
    adapter, generation, history, retry, cache, or decoding changes live here.
    """
    def no_hint(reason, **details):
        return Decision(baseline, False, reason, **details)

    if type(raw_source) is not str or len(raw_source) > MAX_SOURCE_CHARS:
        return no_hint("source_out_of_scope")
    if baseline != baseline_messages(raw_source):
        return no_hint("baseline_out_of_scope")
    # Bind every render to the reviewed raw bytes. Caller-created dataclasses
    # cannot bypass schema/digest validation or crash nested-object traversal.
    lexicon_load = load_lexicon(lexicon_bytes, reviewed_sha256=reviewed_sha256)
    if lexicon_load.lexicon is None:
        return no_hint("unreliable_lexicon")
    lexicon = lexicon_load.lexicon
    matches = [(entry, _literal_spans(raw_source, entry.headword)) for entry in lexicon.entries]
    matches = [(entry, spans) for entry, spans in matches if spans]
    if not matches:
        return no_hint("no_match")
    if len(matches) != 1:
        return no_hint("multiple_distinct_headwords")
    entry, spans = matches[0]
    details = {"headword": entry.headword, "occurrences": len(spans)}
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        return no_hint("overlapping_occurrences", **details)
    if count_prompt_tokens is None:
        return no_hint("token_counter_unavailable", **details)
    prefix = PREFIX_TEMPLATE.format(
        headword=entry.headword,
        senses="或".join("「" + sense + "」" for sense in entry.senses),
    )
    candidate = [{"role": "user", "content": prefix + baseline[0]["content"]}]
    try:
        # Copies isolate an accidental mutation by the external counting hook.
        base_tokens = count_prompt_tokens([dict(message) for message in baseline])
        candidate_tokens = count_prompt_tokens([dict(message) for message in candidate])
        if type(base_tokens) is not int or type(candidate_tokens) is not int:
            raise ValueError("token counter must return plain integer")
        if base_tokens < 1 or candidate_tokens < base_tokens:
            raise ValueError("invalid token counts")
    except Exception:
        return no_hint("token_counter_failed", **details)
    details.update(baseline_tokens=base_tokens, candidate_tokens=candidate_tokens)
    if candidate_tokens > MAX_PROMPT_TOKENS or candidate_tokens - base_tokens > MAX_HINT_DELTA_TOKENS:
        return no_hint("token_budget", **details)
    return Decision(candidate, True, "hint", **details)
