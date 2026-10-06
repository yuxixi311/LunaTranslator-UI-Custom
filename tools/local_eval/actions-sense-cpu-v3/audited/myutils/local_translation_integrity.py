"""Deterministic output checks, not a semantic-quality score or a repair rule.

Only the opt-in local provider uses this. No model call, prompt growth, glossary
guessing, or substitution of one translated name for another is performed.
"""

from collections import Counter
import re

from myutils.local_translation import LocalTranslationError

# Intentionally bounded syntax: brace placeholders, printf conversions, and
# ordinary angle-bracket tags. This is not a parser for every game script.
_BRACE_PLACEHOLDER = re.compile(r"\{\{[^{}\r\n]+\}\}|\$?\{[^{}\r\n]+\}")
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:_-]*(?:[ \t][^<>\r\n]*)?/?>")


def printf_tokens(text):
    """Linear scanner: consume escaped %% pairs and avoid regex backtracking.

    Return (literal, sequential) pairs. Bounded syntax omits dynamic '*' widths
    and ASCII word suffixes; this is deliberately not a full printf parser.
    """
    tokens = []
    i, size = 0, len(text)
    while i < size:
        if text[i] != "%":
            i += 1
            continue
        start = i
        i += 1
        if i < size and text[i] == "%":
            i += 1
            continue
        positioned = False
        j = i
        while j < size and text[j] in "0123456789":
            j += 1
        if j > i and j < size and text[j] == "$":
            positioned, i = True, j + 1
        elif i < size and text[i] == "(":
            j = i + 1
            if j < size and (text[j] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"):
                j += 1
                while j < size and text[j] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789":
                    j += 1
                if j < size and text[j] == ")":
                    positioned, i = True, j + 1
                else:
                    i = j
                    continue
            else:
                i = j
                continue
        while i < size and text[i] in "-+ #0":
            i += 1
        while i < size and text[i] in "0123456789":
            i += 1
        if i < size and text[i] == ".":
            i += 1
            while i < size and text[i] in "0123456789":
                i += 1
        if i < size and text[i] in "sdif":
            i += 1
            if i == size or text[i] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789":
                tokens.append((text[start:i], not positioned))
    return tokens


def needs_integrity_check(source):
    return bool(_BRACE_PLACEHOLDER.search(source) or printf_tokens(source) or _TAG.search(source) or "\n" in source)


def validate_integrity(source, translated):
    """Reject changed protected structure; never silently fix or guess output."""
    source_printf, target_printf = printf_tokens(source), printf_tokens(translated)
    source_tokens = _BRACE_PLACEHOLDER.findall(source) + [token for token, _ in source_printf]
    target_tokens = _BRACE_PLACEHOLDER.findall(translated) + [token for token, _ in target_printf]
    if Counter(source_tokens) != Counter(target_tokens):
        raise LocalTranslationError("本地译文改变了占位符，已拒绝显示；请对照原文")
    # Unlike named/numbered placeholders, ordinary printf conversions consume
    # arguments sequentially. Reordering them can bind the wrong value/type.
    if [t for t, sequential in source_printf if sequential] != [t for t, sequential in target_printf if sequential]:
        raise LocalTranslationError("本地译文改变了顺序占位符的顺序，已拒绝显示；请对照原文")
    if _TAG.findall(source) != _TAG.findall(translated):
        raise LocalTranslationError("本地译文改变了标签或标签顺序，已拒绝显示；请对照原文")
    if source.count("\n") != translated.count("\n"):
        raise LocalTranslationError("本地译文改变了换行数量，已拒绝显示；请对照原文")
    return translated


def collect_translation(chunks, limit=4 * 1024 * 1024):
    """Buffer Sakura's delta/reset protocol until protected output can be checked."""
    parts = []
    total = 0
    for chunk in chunks:
        if not isinstance(chunk, str):
            raise LocalTranslationError("本地翻译响应格式错误")
        # Count all received text, including reset messages, to bound retention.
        total += len(chunk)
        if total > limit:
            raise LocalTranslationError("本地翻译响应过大")
        if chunk == "\0":
            parts.clear()
        else:
            parts.append(chunk)
    return "".join(parts)
