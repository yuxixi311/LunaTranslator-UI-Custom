"""Preparation-only, source-only entry policy; no model loading or execution.

This module consumes supplied entity spans. It has no access to case IDs,
strata, destination aliases, dictionary POS, OOV flags, or confidence scores.
Only an exact raw-source span with the exact label ``Person`` is positive
evidence. All literal occurrences of an entry must qualify before admission.

The general 256-codepoint source cap, 256-span cap, and 64-codepoint label cap
below are explicit PROPOSED input-schema limits, pending protocol review.
The draft's separate 80-codepoint fresh-source limit and fresh-case quotas
belong to population validation, not this shared old/new entry policy.

Canon keys are literal data supplied by the caller. No concrete canon or
evaluation source/criteria is embedded here. The same syntactic validation
applies to the old single-character keys and newly authored keys. Semantic
authoring requirements (including absence of instructions) require review;
this module intentionally has no word-specific or semantic blacklist.
"""

from dataclasses import dataclass
import re
import unicodedata


PROPOSED_MAX_SOURCE_CODEPOINTS = 256
PROPOSED_MAX_ENTITY_SPANS = 256
PROPOSED_MAX_LABEL_CODEPOINTS = 64
MAX_CANON_KEYS = 6
MAX_KEY_CODEPOINTS = 8


@dataclass(frozen=True, slots=True)
class EntitySpan:
    """Half-open Python string/codepoint offsets into the unmodified source.

    Missing label evidence is represented by None or an empty string. It is
    unknown, not positive evidence and not evidence of an ordinary-noun use.
    """

    start: int
    end: int
    text: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class OccurrenceDecision:
    start: int
    end: int
    exact_person: bool


@dataclass(frozen=True, slots=True)
class EntryDecision:
    key: str
    occurrences: tuple[OccurrenceDecision, ...]
    admitted: bool


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Per-entry evidence in caller canon order; admitted_keys is a set.

    An entry with no literal occurrences is never admitted. A withheld entry
    conveys insufficient qualifying evidence, not a semantic classification.
    """

    entries: tuple[EntryDecision, ...]

    @property
    def admitted_keys(self) -> frozenset[str]:
        return frozenset(entry.key for entry in self.entries if entry.admitted)


def _bounded_sequence(value: object, limit: int, name: str) -> None:
    # Reject iterators rather than consuming an unbounded or side-effectful one.
    if type(value) not in (list, tuple) or len(value) > limit:
        raise ValueError(f"{name} must be a list or tuple of at most {limit} items")


def _has_control_or_whitespace(value: str) -> bool:
    # Reviewed format clarification: reject control/format/surrogate codepoints.
    # This classifies codepoints without normalizing or rewriting literal keys.
    return any(char.isspace() or unicodedata.category(char) in {"Cc", "Cf", "Cs"}
               for char in value)


def validate_canon_keys(keys: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Validate the shared literal format, including non-overlapping scans.

    Empty canons are allowed for the fixed smoke. Requiring exactly six keys,
    at least two multi-character fresh keys, old/new disjointness, aliases and
    semantic authoring constraints belongs to the frozen population data.
    """
    _bounded_sequence(keys, MAX_CANON_KEYS, "canon keys")
    for key in keys:
        if type(key) is not str or not 1 <= len(key) <= MAX_KEY_CODEPOINTS:
            raise ValueError("each canon key must contain 1 to 8 codepoints")
        if _has_control_or_whitespace(key):
            raise ValueError("canon keys cannot contain whitespace or Unicode Cc/Cf/Cs codepoints")
        if any(key[:size] == key[-size:] for size in range(1, len(key))):
            raise ValueError("canon keys cannot have a proper prefix/suffix overlap")

    for index, left in enumerate(keys):
        for right in keys[index + 1:]:
            if left in right or right in left:
                raise ValueError("canon keys must be unique and cannot contain each other")
            for size in range(1, min(len(left), len(right))):
                if left[-size:] == right[:size] or right[-size:] == left[:size]:
                    raise ValueError("canon keys cannot overlap by a proper prefix/suffix")
    return tuple(keys)


def _validate_spans(source: str, spans: list[EntitySpan] | tuple[EntitySpan, ...]
                    ) -> tuple[EntitySpan, ...]:
    _bounded_sequence(spans, PROPOSED_MAX_ENTITY_SPANS, "entity spans")
    for span in spans:
        if type(span) is not EntitySpan:
            raise ValueError("each entity record must be an EntitySpan")
        # bool is an int subclass, but is not a valid offset in this schema.
        if type(span.start) is not int or type(span.end) is not int:
            raise ValueError("entity offsets must be integer codepoint offsets")
        if not 0 <= span.start < span.end <= len(source):
            raise ValueError("entity offsets must bound a nonempty source slice")
        if type(span.text) is not str or span.text != source[span.start:span.end]:
            raise ValueError("entity text must exactly equal its raw source slice")
        if span.label is not None and (
                type(span.label) is not str
                or len(span.label) > PROPOSED_MAX_LABEL_CODEPOINTS):
            raise ValueError("entity labels must be None or strings of at most 64 codepoints")

    ordered = tuple(sorted(spans, key=lambda span: (span.start, span.end)))
    for left, right in zip(ordered, ordered[1:]):
        if right.start < left.end:
            # This includes duplicates, conflicting labels and nested spans.
            raise ValueError("entity spans must be distinct and globally non-overlapping")
    return ordered


def evaluate_entries(source: str, keys: list[str] | tuple[str, ...],
                     spans: list[EntitySpan] | tuple[EntitySpan, ...]) -> PolicyDecision:
    """Apply exact Person evidence to every escaped, non-overlapping occurrence.

    Integrity errors anywhere in the supplied evidence raise ValueError, even
    when unrelated to a canon occurrence or when the canon is empty. Callers
    must terminate a probe on this exception, not convert it to abstention.
    Ordinary missing/non-Person/containing/partial evidence merely withholds.
    """
    if type(source) is not str or len(source) > PROPOSED_MAX_SOURCE_CODEPOINTS:
        raise ValueError("source must be a string of at most 256 codepoints")
    canon = validate_canon_keys(keys)
    entities = _validate_spans(source, spans)
    by_bounds = {(span.start, span.end): span for span in entities}
    decisions = []
    for key in canon:
        occurrences = []
        for match in re.finditer(re.escape(key), source):
            span = by_bounds.get((match.start(), match.end()))
            occurrences.append(OccurrenceDecision(
                start=match.start(), end=match.end(),
                exact_person=span is not None and span.label == "Person",
            ))
        decisions.append(EntryDecision(
            key=key,
            occurrences=tuple(occurrences),
            admitted=bool(occurrences) and all(item.exact_person for item in occurrences),
        ))
    return PolicyDecision(entries=tuple(decisions))
