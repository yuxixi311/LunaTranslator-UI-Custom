"""Inert, standard-library-only source preparation for one frozen experiment.

No I/O, tokenizer, inference, runtime adapter, output repair, or app imports.
Call prepare_candidate before complete-chat counting, then apply_token_gate.
The actual counting/receipt binding and unchanged output guard belong to the
separately reviewed execution harness. This module does not authorize execution.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Optional

from _integrity_guard import needs_integrity_check


POLICY_VERSION = "usage-example-prefix-v1"
BASELINE_TEMPLATE = (
    "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{}"
)
PREFIX_TEMPLATE = "译例：{source_ja}→{target_zh}\n\n"
FROZEN_BANK_SHA256 = "9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a"
FROZEN_BANK_ID = "luna-zh-wikibooks-usage-v1-20261006"
FROZEN_BANK_STATUS = "source_bank_frozen"
MAX_BANK_BYTES = 16 * 1024
BANK_RECORD_COUNT = 8
MAX_SOURCE_CHARS = 4096
MAX_PROMPT_TOKENS = 384
MAX_ADDED_TOKENS = 16
_TOP_KEYS = {"schema_version", "bank_id", "status", "records"}
_ENTRY_KEYS = {"id", "source_ja", "target_zh", "contextual_anchor", "designated_focus"}
_CONTROL_SYNTAX = ("{", "}", "<", ">", "%", "`", "\\", "→", "译例：")


class PolicyError(ValueError):
    """Terminal preparation error; never convert this into row abstention."""


class BankValidationError(PolicyError):
    pass


class TokenCountError(PolicyError):
    pass


@dataclass(frozen=True)
class Entry:
    id: str
    source_ja: str
    target_zh: str
    contextual_anchor: str
    designated_focus: str


@dataclass(frozen=True)
class Bank:
    entries: tuple[Entry, ...]
    digest: str


@dataclass(frozen=True)
class CandidatePlan:
    # For every surface abstention, messages IS baseline, even if out of scope.
    baseline: Any
    messages: Any
    raw_source: str
    surface_eligible: bool
    reason: str
    record_id: Optional[str] = None
    anchor_span: Optional[tuple[int, int]] = None
    baseline_snapshot: Optional[bytes] = None
    candidate_snapshot: Optional[bytes] = None


@dataclass(frozen=True)
class Decision:
    # For every abstention, messages IS the caller's original baseline object.
    messages: Any
    raw_source: str
    example_active: bool
    reason: str
    record_id: Optional[str]
    baseline_tokens: int
    # Prospective candidate count; a fallback actually sends baseline_tokens.
    candidate_tokens: int


def baseline_messages(raw_source: str) -> list[dict[str, str]]:
    """Evaluation copy of the pinned context-free, no-glossary baseline."""
    if type(raw_source) is not str:
        raise PolicyError("raw_source must be a plain str")
    return [{"role": "user", "content": BASELINE_TEMPLATE.format(raw_source)}]


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BankValidationError("duplicate JSON key")
        result[key] = value
    return result


def _safe_text(value, maximum):
    return (
        type(value) is str
        and 0 < len(value) <= maximum
        and value.isprintable()
        and value == value.strip()
        and not any(marker in value for marker in _CONTROL_SYNTAX)
    )


def _decode_reviewed_bank(raw_bytes, reviewed_sha256, bank_id, status):
    """Internal schema checker; public admission always uses frozen constants."""
    if type(raw_bytes) is not bytes or not 0 < len(raw_bytes) <= MAX_BANK_BYTES:
        raise BankValidationError("bank byte cap/type")
    if type(reviewed_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", reviewed_sha256) is None:
        raise BankValidationError("missing valid freeze digest")
    if sha256(raw_bytes).hexdigest() != reviewed_sha256:
        raise BankValidationError("bank digest mismatch")
    try:
        data = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        if type(data) is not dict or set(data) != _TOP_KEYS:
            raise BankValidationError("bank schema")
        if data["schema_version"] != "1.0" or data["bank_id"] != bank_id or data["status"] != status:
            raise BankValidationError("bank metadata")
        records = data["records"]
        if type(records) is not list or len(records) != BANK_RECORD_COUNT:
            raise BankValidationError("exactly eight records required; no pruning")
        entries, seen = [], set()
        for item in records:
            if type(item) is not dict or set(item) != _ENTRY_KEYS:
                raise BankValidationError("record schema")
            record_id = item["id"]
            if type(record_id) is not str or re.fullmatch(r"wb[0-9]{2}", record_id) is None or record_id in seen:
                raise BankValidationError("invalid or duplicate record id")
            if not _safe_text(item["source_ja"], 16) or not _safe_text(item["target_zh"], 12):
                raise BankValidationError("complete example text cap/control syntax")
            anchor, focus = item["contextual_anchor"], item["designated_focus"]
            if not _safe_text(anchor, 16) or not _safe_text(focus, 16):
                raise BankValidationError("cue cap/control syntax")
            if anchor not in item["source_ja"] or focus not in anchor or anchor == focus:
                raise BankValidationError("anchor/focus containment or headword-only anchor")
            seen.add(record_id)
            entries.append(Entry(**item))
        return Bank(tuple(entries), reviewed_sha256)
    except (UnicodeError, TypeError, RecursionError, ValueError) as exc:
        if isinstance(exc, BankValidationError):
            raise
        raise BankValidationError("invalid bank JSON/schema") from exc


def load_frozen_bank(raw_bytes: bytes) -> Bank:
    """Verify the entire exact reviewed inventory; never accept caller pins."""
    return _decode_reviewed_bank(raw_bytes, FROZEN_BANK_SHA256, FROZEN_BANK_ID, FROZEN_BANK_STATUS)


def _literal_spans(source: str, key: str) -> tuple[tuple[int, int], ...]:
    """Exact case-sensitive Unicode substrings; count overlapping positions."""
    spans, start = [], 0
    while True:
        index = source.find(key, start)
        if index < 0:
            return tuple(spans)
        spans.append((index, index + len(key)))
        start = index + 1


def _select_entry(raw_source: str, entries: tuple[Entry, ...]):
    matches = [(entry, _literal_spans(raw_source, entry.contextual_anchor)) for entry in entries]
    matches = [(entry, spans) for entry, spans in matches if spans]
    if not matches:
        return None, None, "no_match"
    if len(matches) != 1:
        return None, None, "competing_full_anchors"
    entry, spans = matches[0]
    if len(spans) != 1:
        return entry, None, "repeated_anchor"
    anchor_span = spans[0]
    # Only THIS record's focus is checked. Do not scan all bank focuses.
    if any(start < anchor_span[0] or end > anchor_span[1]
           for start, end in _literal_spans(raw_source, entry.designated_focus)):
        return entry, anchor_span, "selected_focus_outside_anchor"
    return entry, anchor_span, "surface_eligible"


def _is_baseline(raw_source, baseline):
    return (
        type(baseline) is list and len(baseline) == 1
        and type(baseline[0]) is dict and set(baseline[0]) == {"role", "content"}
        and type(baseline[0]["role"]) is str and baseline[0]["role"] == "user"
        and type(baseline[0]["content"]) is str
        and baseline[0]["content"] == BASELINE_TEMPLATE.format(raw_source)
    )


def _snapshot(messages):
    return json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def prepare_candidate(raw_source: str, baseline: Any, bank_bytes: bytes, *, baseline_in_scope: bool) -> CandidatePlan:
    """Prepare countable messages without admitting any example for generation.

    baseline_in_scope is an explicit caller assertion of the pinned model,
    configuration, sampling, context-free/no-glossary mode and output guard.
    This pure module additionally verifies the exact baseline message shape.
    Every call validates all frozen bank bytes, even for a surface abstention.
    """
    bank = load_frozen_bank(bank_bytes)
    if type(raw_source) is not str or type(baseline_in_scope) is not bool:
        raise PolicyError("raw_source/baseline_in_scope type")

    def abstain(reason, entry=None, span=None):
        return CandidatePlan(baseline, baseline, raw_source, False, reason,
                             entry.id if entry else None, span)

    if len(raw_source) > MAX_SOURCE_CHARS:
        return abstain("source_over_4096_chars")
    if not baseline_in_scope or not _is_baseline(raw_source, baseline):
        return abstain("baseline_out_of_scope")
    if needs_integrity_check(raw_source):
        return abstain("protected_structure")
    entry, span, reason = _select_entry(raw_source, bank.entries)
    if reason != "surface_eligible":
        return abstain(reason, entry, span)
    prefix = PREFIX_TEMPLATE.format(source_ja=entry.source_ja, target_zh=entry.target_zh)
    candidate = [{"role": "user", "content": prefix + baseline[0]["content"]}]
    return CandidatePlan(baseline, candidate, raw_source, True, reason, entry.id, span,
                         _snapshot(baseline), _snapshot(candidate))


def apply_token_gate(plan: CandidatePlan, *, baseline_tokens: int, candidate_tokens: int) -> Decision:
    """Use actual COMPLETE chat counts, including wrappers/generation markers.

    Invalid/missing counts and count errors are terminal, never fallback. The
    caller must bind both receipts to these exact messages and the frozen chat
    template/tokenizer. A surface-ineligible row still needs two real equivalent
    counts. Positive counts with an inadmissible upper delta produce abstention;
    tokenizer counts are not assumed monotonic. candidate_tokens retains the
    prospective C on a budget fallback: actual generation then sends B tokens.
    """
    if type(plan) is not CandidatePlan:
        raise PolicyError("expected CandidatePlan")
    if any(type(count) is not int or count < 1 for count in (baseline_tokens, candidate_tokens)):
        raise TokenCountError("whole-chat counts must be positive plain integers")
    if baseline_tokens > MAX_PROMPT_TOKENS:
        raise TokenCountError("baseline exceeds 384 whole-chat tokens")
    if not plan.surface_eligible and candidate_tokens != baseline_tokens:
        raise TokenCountError("surface-abstention counts must be baseline-equivalent")
    if plan.surface_eligible:
        try:
            if _snapshot(plan.baseline) != plan.baseline_snapshot or _snapshot(plan.messages) != plan.candidate_snapshot:
                raise PolicyError("prepared request changed before token admission")
        except (TypeError, UnicodeError, RecursionError) as exc:
            raise PolicyError("prepared request changed before token admission") from exc
    delta = candidate_tokens - baseline_tokens
    allowed_delta = min(MAX_ADDED_TOKENS, (2 * baseline_tokens) // 5)
    active = plan.surface_eligible and candidate_tokens <= MAX_PROMPT_TOKENS and delta <= allowed_delta
    reason = "example_admitted" if active else ("token_budget" if plan.surface_eligible else plan.reason)
    return Decision(plan.messages if active else plan.baseline, plan.raw_source, active, reason,
                    plan.record_id, baseline_tokens, candidate_tokens)
