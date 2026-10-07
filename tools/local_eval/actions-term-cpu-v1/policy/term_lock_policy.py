"""Pure source-only terminology experiment policy. No I/O or inference.

The caller must bind the complete frozen glossary to its source scope before
calling prepare(). Independent source authors cannot add per-row eligibility.
The required output guard is the existing verified local Hy integrity helper.
"""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
import unicodedata


POLICY_ID = "luna-term-lock-v1"
SCOPE_ID = "luna-fictional-terminology-v1"
DECLARATIONS_SHA256 = "f7d849ae54ec36d8247aeaadedd633523de92df35313c7bebb3a2073baeccd3b"
MAX_SOURCE_CHARS = 4096
MAX_GLOSSARY_ENTRIES = 16
MAX_FIELD_CHARS = 64
MAX_FULL_PROMPT_TOKENS = 384
MARKER = "{LT0}"
NAMESPACE = re.compile(r"\{LT[0-9]+\}")
ORDINARY = "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n"
QUOTES = frozenset('"\'「」『』')
# A deliberately conservative source-only exclusion, not a general parser.
PROTECTED_SOURCE_CHARS = frozenset("\r\n{}<>%")


class PolicyError(ValueError):
    pass


class StructuralFailure(PolicyError):
    pass


@dataclass(frozen=True)
class Entry:
    src: str
    dst: str


@dataclass(frozen=True)
class Plan:
    source: str
    scope_id: str
    glossary_digest: str
    baseline_prompt: str
    provisional_prompt: str
    masked_source: str
    eligible: bool
    reason: str
    entry_id: str | None = None
    destination: str | None = None


@dataclass(frozen=True)
class Decision:
    plan: Plan
    active: bool
    reason: str
    prompt: str
    baseline_tokens: int
    provisional_tokens: int


def _require(condition, message):
    if not condition:
        raise PolicyError(message)


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _field(text):
    return (
        type(text) is str
        and 1 <= len(text) <= MAX_FIELD_CHARS
        and not any(unicodedata.category(c).startswith("C") for c in text)
        and not any(c in PROTECTED_SOURCE_CHARS for c in text)
    )


def load_declarations(raw):
    _require(type(raw) is bytes and len(raw) <= 8192, "declaration byte bound")
    _require(sha256(raw).hexdigest() == DECLARATIONS_SHA256, "declaration hash mismatch")
    try:
        document = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PolicyError("invalid declarations") from exc
    _require(type(document) is dict and set(document) == {
        "schema_version", "policy_id", "scope_id", "source_language",
        "target_language", "declaration", "entries",
    }, "declaration schema")
    _require(document["schema_version"] == 1 and document["policy_id"] == POLICY_ID
             and document["scope_id"] == SCOPE_ID
             and document["source_language"] == "ja"
             and document["target_language"] == "zh-Hans", "declaration identity")
    rows = document["entries"]
    _require(type(rows) is list and len(rows) == 7, "six safe terms plus one unsafe term")
    for row in rows:
        _require(type(row) is dict and set(row) == {"id", "src", "dst", "kind", "lock_safe"}, "entry schema")
        _require(_field(row["src"]) and _field(row["dst"]), "entry field")
        _require(type(row["lock_safe"]) is bool, "safe declaration must be boolean")
        _require(row["kind"] in ("proper_name", "domain_term", "ambiguous_surface"), "entry kind")
        _require(row["lock_safe"] == (row["kind"] != "ambiguous_surface"), "unsafe entry cannot become safe")
    _require(len({r["id"] for r in rows}) == 7 and len({r["src"] for r in rows}) == 7, "duplicate declarations")
    _require(sum(r["lock_safe"] for r in rows) == 6, "six globally safe entries")
    return document


def _glossary(rows):
    _require(type(rows) in (list, tuple) and len(rows) <= MAX_GLOSSARY_ENTRIES, "glossary size")
    result = []
    for row in rows:
        _require(type(row) is dict and set(row) == {"src", "dst"}, "only explicit src/dst glossary fields")
        _require(_field(row["src"]) and _field(row["dst"]), "glossary field")
        result.append(Entry(row["src"], row["dst"]))
    _require(len({e.src for e in result}) == len(result), "duplicate/conflicting glossary source")
    return tuple(result)


def _occurrences(source, entries):
    found = []
    for index, entry in enumerate(entries):
        start = 0
        while True:
            start = source.find(entry.src, start)
            if start < 0:
                break
            found.append((start, start + len(entry.src), index))
            start += 1  # Include overlapping occurrences.
    return tuple(sorted(found))


def _prompt(source, entries, occurrences):
    matched = {index for _, _, index in occurrences}
    block = "\n".join(e.src + "翻译成" + e.dst for i, e in enumerate(entries) if i in matched)
    return (("参考下面的翻译：\n" + block + "\n") if block else "") + ORDINARY + source


def prepare(source, scope_id, glossary_rows, declaration_bytes):
    """No case ID, expected sense, gold answer or per-record safe flag accepted.

    Count all exact literal occurrences across ALL supplied glossary entries,
    including unsafe and undeclared entries, before deciding lock eligibility.
    Build the shared glossary once from the ORIGINAL source and preserve its
    order and bytes in both prompts. No normalization or substring repair.
    """
    _require(type(source) is str and type(scope_id) is str, "source/scope types")
    # Reject before scans, declaration work or prompt rendering. An unbounded
    # original request is not constructed merely to return a nominal fallback.
    _require(1 <= len(source) <= MAX_SOURCE_CHARS, "source character bound")
    _require(len(scope_id) <= 128, "scope identifier bound")
    declarations = load_declarations(declaration_bytes)
    entries = _glossary(glossary_rows)
    canonical_glossary = json.dumps(glossary_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    occurrences = _occurrences(source, entries)
    baseline = _prompt(source, entries, occurrences)
    plan = Plan(source, scope_id, sha256(canonical_glossary).hexdigest(), baseline, baseline,
                source, False, "not_evaluated")
    def abstain(reason):
        return replace(plan, reason=reason)
    if scope_id != SCOPE_ID:
        return abstain("scope_not_declared")
    # A same-scope run must use the complete frozen glossary, not a subset chosen
    # separately for each record to make an unsafe/multiple match disappear.
    complete = tuple(Entry(r["src"], r["dst"]) for r in declarations["entries"])
    if entries != complete:
        return abstain("scope_glossary_mismatch")
    if any(NAMESPACE.search(text) for text in (source, *(e.src for e in entries), *(e.dst for e in entries))):
        return abstain("marker_namespace_collision")
    if any(c in PROTECTED_SOURCE_CHARS for c in source):
        return abstain("protected_source")
    if any(c in QUOTES or unicodedata.category(c) in ("Pi", "Pf") for c in source):
        return abstain("quoted_source")
    if not occurrences:
        return abstain("no_match")
    if any(left[1] > right[0] for left, right in zip(occurrences, occurrences[1:])):
        return abstain("overlapping_matches")
    if len(occurrences) != 1:
        return abstain("multiple_matches")
    start, end, index = occurrences[0]
    declaration = declarations["entries"][index]
    if not declaration["lock_safe"]:
        return abstain("globally_unsafe_entry")
    adjacent = ((source[start - 1],) if start else ()) + ((source[end],) if end < len(source) else ())
    if any(unicodedata.category(c)[0] in "LMN" for c in adjacent):
        return abstain("unproven_boundary")
    masked = source[:start] + MARKER + source[end:]
    # Replace target span only. Glossary is derived from original occurrences.
    candidate = _prompt(masked, entries, occurrences)
    return replace(plan, provisional_prompt=candidate, masked_source=masked,
                   eligible=True, reason="eligible", entry_id=declaration["id"],
                   destination=declaration["dst"])


def apply_token_gate(plan, baseline_tokens, provisional_tokens):
    _require(type(plan) is Plan, "plan type")
    _require(all(type(n) is int and n > 0 for n in (baseline_tokens, provisional_tokens)), "positive real full-template counts required")
    _require(baseline_tokens <= MAX_FULL_PROMPT_TOKENS, "baseline over prompt limit")
    if not plan.eligible:
        _require(plan.provisional_prompt == plan.baseline_prompt and baseline_tokens == provisional_tokens, "abstention identity/count mismatch")
        return Decision(plan, False, plan.reason, plan.baseline_prompt, baseline_tokens, provisional_tokens)
    delta_bound = min(16, (2 * baseline_tokens) // 5)
    active = provisional_tokens <= MAX_FULL_PROMPT_TOKENS and provisional_tokens - baseline_tokens <= delta_bound
    return Decision(plan, active, "active" if active else "token_budget",
                    plan.provisional_prompt if active else plan.baseline_prompt,
                    baseline_tokens, provisional_tokens)


def restore(decision, output, validate_integrity):
    """Call only after buffering the complete output. Failures are never repaired.

    validate_integrity must be the source-bound existing local Hy output guard.
    Its return value is ignored: validation is not permission to rewrite output.
    This function has no model callback or baseline answer argument.
    """
    _require(type(decision) is Decision and type(output) is str, "decision/output types")
    _require(callable(validate_integrity), "existing integrity guard required")
    if not decision.active:
        validate_integrity(decision.plan.source, output)
        return output
    plan = decision.plan
    _require(plan.eligible and plan.destination is not None, "active plan invariant")
    if output.count(MARKER) != 1 or NAMESPACE.findall(output) != [MARKER]:
        raise StructuralFailure("missing, duplicated, altered or invented issued marker")
    validate_integrity(plan.masked_source, output)
    rendered = output.replace(MARKER, plan.destination, 1)
    if NAMESPACE.search(rendered):
        raise StructuralFailure("unresolved reserved marker")
    validate_integrity(plan.source, rendered)
    return rendered
