"""Conflicting sources: two documents give different numbers or names for the same fact.

Two sentences from different documents conflict when they nearly restate each other (most content words shared,
numbers aside), differ in exactly one number or one name of the same kind, and NLI finds them
contradictory. Parts of one uploaded document (same `origin`) are one document; at most MAX_CANDIDATES pairs, the
closest restatements first, go to NLI. An answer sentence that repeats one side of a conflict is "contested": the model did not invent
the value, but the sources do not settle it, so the reader must check which source is right.
"""

import re
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.schema import Sample
from truth_guardian.symbolic import ENTITY_LABELS, _ner, _numbers_in, fold, normalize_number, number_forms
from truth_guardian.text import Sentence, content_words, split_sentences

PAIR_OVERLAP = 0.6
MIN_SHARED_WORDS = 4
MAX_CANDIDATES = 400
CONFIRM_CONTRADICTION = 0.5
CLAIM_OVERLAP = 0.5
_ENUMERATOR = re.compile(r"^\s*\d{1,3}[.)]?\s+(?=[A-Z])")


class Conflict(NamedTuple):
    first: str
    first_document: str
    second: str
    second_document: str
    first_value: str
    second_value: str
    contradiction: float


class _Fact(NamedTuple):
    text: str
    document: str
    origin: str
    words: set[str]
    numbers: dict[str, str]
    names: dict[str, tuple[str, str]]


def _fact(text: str, document: str, origin: str | None = None) -> _Fact:
    """A source sentence's words, numbers and names; a leading list number ("4  Let cool") is not a fact."""
    text = _ENUMERATOR.sub("", text)
    numbers = {min(number_forms(text, m)): m.group() for m in _numbers_in(text)}
    names = {fold(e.text).lower(): (e.label_, e.text) for e in _ner()(text).ents if e.label_ in ENTITY_LABELS - {"DATE"}}
    words = {w for w in content_words(fold(text)) if not w.isdigit()}
    return _Fact(text, document, origin or document, words, numbers, names)


def _difference(a: _Fact, b: _Fact) -> tuple[str, str] | None:
    """The single number, or single name of one kind, on which two near-restatements differ."""
    only_a, only_b = a.numbers.keys() - b.numbers.keys(), b.numbers.keys() - a.numbers.keys()
    if len(only_a) == 1 and len(only_b) == 1:
        return a.numbers[next(iter(only_a))], b.numbers[next(iter(only_b))]
    if only_a or only_b:
        return None
    names_a, names_b = a.names.keys() - b.names.keys(), b.names.keys() - a.names.keys()
    if len(names_a) == 1 and len(names_b) == 1:
        (label_a, text_a), (label_b, text_b) = a.names[next(iter(names_a))], b.names[next(iter(names_b))]
        if label_a == label_b:
            return text_a, text_b
    return None


def find_conflicts(sample: Sample, classify=models.nli_probabilities) -> list[Conflict]:
    documents = [d for d in sample.documents if d.text.strip()]
    if len(documents) < 2:
        return []
    facts = [_fact(s.text, d.id, d.origin) for d in documents for s in split_sentences(d.text)]
    candidates = []
    for i, a in enumerate(facts):
        for b in facts[i + 1 :]:
            if a.origin == b.origin:
                continue
            shared = len(a.words & b.words)
            overlap = shared / max(min(len(a.words), len(b.words)), 1)
            if shared < MIN_SHARED_WORDS or overlap < PAIR_OVERLAP:
                continue
            values = _difference(a, b)
            if values:
                candidates.append((overlap, a, b, values))
    if not candidates:
        return []
    # Long uploaded documents can produce thousands of look-alike pairs; NLI checks only the closest restatements.
    candidates = [c[1:] for c in sorted(candidates, key=lambda c: -c[0])[:MAX_CANDIDATES]]
    probs = classify([(a.text, b.text) for a, b, _ in candidates])
    index = models.NLI_LABELS.index("contradiction")
    return [
        Conflict(a.text, a.document, b.text, b.document, va, vb, float(p[index]))
        for (a, b, (va, vb)), p in zip(candidates, probs)
        if p[index] >= CONFIRM_CONTRADICTION
    ]


def _mentions(text: str, value: str) -> bool:
    if any(ch.isdigit() for ch in value):
        return bool(normalize_number(value) & {f for m in _numbers_in(text) for f in number_forms(text, m)})
    return re.search(rf"\b{re.escape(fold(value).lower())}\b", fold(text).lower()) is not None


def contested(sentence: Sentence, conflicts: list[Conflict]) -> tuple[Conflict, str] | None:
    """The conflict an answer sentence takes a side in, and which document it follows."""
    words = content_words(fold(sentence.text))
    for c in conflicts:
        for side_text, value, document in ((c.first, c.first_value, c.first_document), (c.second, c.second_value, c.second_document)):
            overlap = len(words & content_words(fold(side_text))) / max(len(words), 1)
            if overlap >= CLAIM_OVERLAP and _mentions(sentence.text, value):
                return c, document
    return None
