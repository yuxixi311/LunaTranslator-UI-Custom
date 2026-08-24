"""Offline GiNZA syntax analysis layered on top of the existing MeCab output.

The heavy third-party runtime is imported lazily from ``files/plugins/ginza``.
This module itself remains importable when the optional bundle is absent so the
application can always fall back to MeCab.
"""

import copy
import os
import sys
import threading
from traceback import print_exc

from sometypes import WordSegResult


ROLE_LABELS = {
    "subject": "主语",
    "object": "宾语",
    "predicate": "谓语",
    "modifier": "修饰语",
}

_SUBJECT_DEPS = {"nsubj", "csubj"}
_OBJECT_DEPS = {"obj", "iobj"}
_MODIFIER_DEPS = {"acl", "advcl", "advmod", "amod"}
_LEARNING_ATTACH_DEPS = {"obj", "iobj", "obl", "nmod"}


def dependency_role(dep):
    """Map a Universal Dependencies label to a conservative learning hint."""
    normalized = (dep or "").replace("_bunsetu", "")
    if normalized.lower() == "root":
        return "predicate"
    if normalized in _SUBJECT_DEPS:
        return "subject"
    if normalized in _OBJECT_DEPS:
        return "object"
    if normalized in _MODIFIER_DEPS:
        return "modifier"
    return None


def bundle_path():
    override = os.environ.get("LUNA_GINZA_PATH")
    if override:
        return os.path.abspath(override)
    return os.path.abspath(os.path.join("files", "plugins", "ginza"))


def bundle_available():
    path = bundle_path()
    return os.path.isdir(os.path.join(path, "ginza")) and os.path.isdir(
        os.path.join(path, "ja_ginza")
    )


def _segment_offsets(text, words):
    """Return original-text offsets without changing MeCab token boundaries."""
    cursor = 0
    result = []
    for word in words:
        value = word.word or ""
        if not value:
            result.append((cursor, cursor))
            continue
        start = text.find(value, cursor)
        if start < 0:
            start = cursor
        end = min(len(text), start + len(value))
        result.append((start, end))
        cursor = end
    return result


def _overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def build_learning_units(bunsetu):
    """Merge a short case/object phrase with its immediately following head.

    GiNZA correctly splits Japanese bunsetsu, but raw bunsetsu are often too
    technical for a learner.  This conservative second layer makes structures
    such as ``役に`` -> ``立ってたなら`` readable as one learning unit without
    pretending that they are one morphological word.
    """
    units = []
    index = 0
    while index < len(bunsetu):
        members = [bunsetu[index]]
        current = bunsetu[index]
        if index + 1 < len(bunsetu):
            following = bunsetu[index + 1]
            dep = (current.get("dep") or "").replace("_bunsetu", "")
            head_start = current.get("head_start", -1)
            attaches_to_following = following["start"] <= head_start < following["end"]
            if dep in _LEARNING_ATTACH_DEPS and attaches_to_following:
                members.append(following)
                index += 1
        tail = members[-1]
        units.append(
            {
                "id": len(units),
                "text": "".join(member["text"] for member in members),
                "start": members[0]["start"],
                "end": tail["end"],
                "role": tail.get("role") or members[0].get("role"),
                "dep": tail.get("dep") or members[0].get("dep"),
                "head": tail.get("head") or members[0].get("head"),
                "bunsetu_ids": [member["id"] for member in members],
            }
        )
        index += 1
    return units


def enrich_word_segments(text, words, analysis):
    """Attach GiNZA fields to a copy of the MeCab ``WordSegResult`` list."""
    enriched = [WordSegResult.from_dict(copy.deepcopy(word.as_dict())) for word in words]
    bunsetu = analysis.get("bunsetu", [])
    learning_units = analysis.get("learning_units", [])
    tokens = analysis.get("tokens", [])
    for word, (start, end) in zip(enriched, _segment_offsets(text, enriched)):
        candidates = [
            span
            for span in bunsetu
            if _overlap(start, end, span["start"], span["end"]) > 0
        ]
        if candidates:
            span = max(
                candidates,
                key=lambda item: _overlap(start, end, item["start"], item["end"]),
            )
            word.bunsetu_id = span["id"]
            word.bunsetu_text = span["text"]
            word.bunsetu_start = start <= span["start"] < end or start == span["start"]
            word.bunsetu_end = start < span["end"] <= end or end == span["end"]
            word.grammar_role = span.get("role")
            word.grammar_dep = span.get("dep")
            word.grammar_head = span.get("head")
        unit_candidates = [
            unit
            for unit in learning_units
            if _overlap(start, end, unit["start"], unit["end"]) > 0
        ]
        if unit_candidates:
            unit = max(
                unit_candidates,
                key=lambda item: _overlap(start, end, item["start"], item["end"]),
            )
            word.learning_unit_id = unit["id"]
            word.learning_unit_text = unit["text"]
            word.learning_unit_start = start <= unit["start"] < end or start == unit["start"]
            word.learning_unit_end = start < unit["end"] <= end or end == unit["end"]
        token_candidates = [
            token
            for token in tokens
            if _overlap(start, end, token["start"], token["end"]) > 0
        ]
        if token_candidates and not word.grammar_dep:
            token = max(
                token_candidates,
                key=lambda item: _overlap(start, end, item["start"], item["end"]),
            )
            word.grammar_dep = token.get("dep")
            word.grammar_head = token.get("head")
    return enriched


class GinzaAnalyzer:
    """Thread-safe, lazy singleton-style wrapper around the bundled model."""

    def __init__(self):
        self._nlp = None
        self._ginza = None
        self._load_lock = threading.Lock()
        self._analysis_lock = threading.Lock()

    def _load(self):
        if self._nlp is not None:
            return
        with self._load_lock:
            if self._nlp is not None:
                return
            path = bundle_path()
            if not bundle_available():
                raise FileNotFoundError("GiNZA offline bundle is missing: " + path)
            if path not in sys.path:
                sys.path.insert(0, path)
            import ginza
            import spacy

            # GiNZA 5.2 declares this option as nullable, while spaCy 3.8's
            # stricter validation rejects the model's null value. C is the
            # tokenizer's native split mode and avoids modifying vendor files.
            self._nlp = spacy.load(
                "ja_ginza",
                exclude=["ner"],
                config={
                    "components": {"compound_splitter": {"split_mode": "C"}}
                },
            )
            self._ginza = ginza

    def analyze(self, text):
        self._load()
        with self._analysis_lock:
            doc = self._nlp(text)
        tokens = [
            {
                "text": token.text,
                "start": token.idx,
                "end": token.idx + len(token.text),
                "dep": token.dep_,
                "head": token.head.text,
            }
            for token in doc
        ]
        spans = []
        for index, span in enumerate(self._ginza.bunsetu_spans(doc)):
            heads = list(self._ginza.bunsetu_head_tokens(span))
            head = heads[0] if heads else span.root
            spans.append(
                {
                    "id": index,
                    "text": span.text,
                    "start": span.start_char,
                    "end": span.end_char,
                    "dep": head.dep_,
                    "head": head.head.text,
                    "head_start": head.head.idx,
                    "role": dependency_role(head.dep_),
                }
            )
        return {
            "tokens": tokens,
            "bunsetu": spans,
            "learning_units": build_learning_units(spans),
        }


_analyzer = GinzaAnalyzer()


class GinzaAnalysisWorker:
    """One daemon worker with latest-request-wins queue semantics."""

    def __init__(self, callback):
        self._callback = callback
        self._condition = threading.Condition()
        self._pending = None
        self._thread = threading.Thread(
            target=self._run, name="LunaGiNZA", daemon=True
        )
        self._thread.start()

    def submit(self, request_id, text, words):
        snapshot = [WordSegResult.from_dict(word.as_dict()) for word in words]
        with self._condition:
            self._pending = (request_id, text, snapshot)
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                while self._pending is None:
                    self._condition.wait()
                request_id, text, words = self._pending
                self._pending = None
            try:
                analysis = _analyzer.analyze(text)
                result = enrich_word_segments(text, words, analysis)
                self._callback(request_id, text, result, "")
            except Exception as error:
                print_exc()
                self._callback(request_id, text, [], str(error))
