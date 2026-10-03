"""Isolated experimental prompt policy. No inference, I/O transport or default switch."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from production_adapter import production_pair, SOURCE_HASHES

CANON_SHA256 = '7cc5bdb3626dd4e781070dca708428c0ef81048d72b067a71f9e15c795814337'
ORDINARY = '将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n'
CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]+\Z')

class PreflightError(ValueError):
    pass

@dataclass(frozen=True)
class Entry:
    src: str
    dst: str

@dataclass(frozen=True)
class Pair:
    source: str
    matched: tuple[Entry, ...]
    a: str
    b: str

    @property
    def matched_count(self):
        return len(self.matched)

    def messages(self, arm):
        if arm not in ('A', 'B'):
            raise PreflightError('arm must be A or B')
        return [{'role': 'user', 'content': self.a if arm == 'A' else self.b}]

def _no_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PreflightError('duplicate JSON field')
        result[key] = value
    return result

def validate_canon(document):
    """Structural check; execution entry point is load_canon with pinned byte identity."""
    if not isinstance(document, dict) or set(document) != {'project_description', 'entries'}:
        raise PreflightError('unexpected canon fields')
    description = document['project_description']
    if not isinstance(description, str) or not description or any(unicodedata.category(c).startswith('C') or c in '\r\n\u2028\u2029' for c in description):
        raise PreflightError('invalid description')
    rows = document['entries']
    if not isinstance(rows, list) or len(rows) != 6:
        raise PreflightError('canon must contain six entries')
    entries = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'src', 'dst'}:
            raise PreflightError('unexpected entry fields')
        if any(not isinstance(row[k], str) or not CJK.fullmatch(row[k]) for k in ('src', 'dst')):
            raise PreflightError('entries must be nonempty literal CJK strings')
        entries.append(Entry(row['src'], row['dst']))
    if len({e.src for e in entries}) != 6 or len({e.dst for e in entries}) != 6:
        raise PreflightError('duplicate source or destination')
    if any(a.src in b.src for a in entries for b in entries if a is not b):
        raise PreflightError('overlapping keys')
    return tuple(entries)

def load_canon(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CANON_SHA256:
        raise PreflightError('canon byte identity mismatch')
    try:
        return validate_canon(json.loads(raw, object_pairs_hook=_no_duplicate_fields))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError('invalid canon JSON') from exc

def prepare_pair(raw_source, canon_path):
    """Always match original source; never accept a rewritten placeholder intermediate."""
    entries = load_canon(canon_path)
    if not isinstance(raw_source, str) or not raw_source or len(raw_source) > 200:
        raise PreflightError('source must contain 1 to 200 characters')
    if any(unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in raw_source):
        raise PreflightError('source must be a single line without controls')
    try:
        actual_matched, actual_a, actual_b = production_pair(raw_source, entries)
    except (OSError, ValueError) as exc:
        raise PreflightError("production source or adapter preflight failed") from exc
    matched = tuple(Entry(e["src"], e["dst"]) for e in actual_matched)
    if len(matched) > 4:
        raise PreflightError('more than four matched entries; do not trim or fall back')
    a = ORDINARY + raw_source
    b = ('参考下面的翻译：\n' + '\n'.join(e.src + '翻译成' + e.dst for e in matched) + '\n' + a) if matched else a
    if actual_a != [{"role": "user", "content": a}] or actual_b != [{"role": "user", "content": b}]:
        raise PreflightError("production prompt differs from frozen rendering")
    return Pair(raw_source, matched, actual_a[0]["content"], actual_b[0]["content"])

def check_applied_token_counts(a_tokens, b_tokens):
    """Pass actual full applied-template counts, including generation prefix.

    This pure check cannot establish provenance. The execution harness must obtain
    these counts from its tokenizer probes; estimates/user-content-only counts are
    not valid inputs. A failure stops preflight, never clips or changes the pair.
    """
    if any(type(n) is not int or n <= 0 for n in (a_tokens, b_tokens)):
        raise PreflightError('actual counts must be positive integers')
    if max(a_tokens, b_tokens) > 384 or b_tokens - a_tokens > 64:
        raise PreflightError('applied prompt token budget exceeded')
    return {'a_tokens': a_tokens, 'b_tokens': b_tokens, 'b_minus_a': b_tokens - a_tokens}
