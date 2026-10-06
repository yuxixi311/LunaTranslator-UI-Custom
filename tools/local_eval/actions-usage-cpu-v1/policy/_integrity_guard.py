"""Exact production guard excerpt; source and excerpt hashes are in SOURCE_MANIFEST.json.

Only standard-library re is imported. No application or Qt imports.
"""

import re

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

