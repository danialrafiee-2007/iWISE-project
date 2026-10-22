"""Fix-it suggestions: for a number, time or name that the sources do not contain, propose what the sources say.

No language model is involved: the closest source sentence is found with BM25 (ignoring the wrong item),
and the replacement is the same kind of item there (a number with matching context, or an entity with
the same NER label). Unspecified attributes get a "remove" suggestion with the source line as evidence.
"""

import re
from functools import lru_cache
from typing import NamedTuple

from truth_guardian.retrieval import Bm25
from truth_guardian.schema import Sample
from truth_guardian.symbolic import NULL_VALUE, Atom, _ner, _numbers_in, check_sample, normalize_number
from truth_guardian.text import Sentence, content_words, split_sentences

CANDIDATE_SENTENCES = 3
_WORD = re.compile(r"\w+")


class Suggestion(NamedTuple):
    start: int
    end: int
    original: str
    replacement: str | None
    evidence: str
    kind: str
    confidence: float


def _singular(text: str) -> str:
    """Light plural folding for matching only ("Fridays" finds "Friday"); the shared retrieval is left unchanged."""
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in _WORD.findall(text.lower()))


@lru_cache(maxsize=256)
def _source_index(texts: tuple[str, ...]) -> tuple[list[str], Bm25]:
    sentences = [s.text for t in texts for s in split_sentences(t)]
    return sentences, Bm25([_singular(s) for s in sentences])


def _neighbours(text: str, start: int, end: int) -> tuple[str, str]:
    before = _WORD.findall(text[:start].lower())
    after = _WORD.findall(text[end:].lower())
    return (before[-1] if before else "", after[0] if after else "")


def _number_kind(text: str, next_word: str = "") -> str:
    if ":" in text or next_word in {"am", "pm"}:
        return "time"
    plain = text.replace(",", "")
    if "." in plain:
        return "decimal"
    if len(plain) == 4 and 1000 <= int(plain) <= 2100:
        return "year"
    return "integer"


def _format_like(original: str, value: str) -> str:
    """Keep the answer's style: "10 PM" against a source "21:0" becomes "9", "9:30" stays 12-hour."""
    if ":" not in value or not value.replace(":", "").isdigit() or value.count(":") != 1:
        return value
    hour, minute = (int(p) for p in value.split(":"))
    original_hour = int(original.split(":")[0]) if ":" in original else int(original.replace(",", "").split(".")[0])
    if original_hour <= 12 < hour:
        hour -= 12
    if ":" not in original and minute == 0:
        return str(hour)
    return f"{hour}:{minute:02d}"


_RANGE_END_WORDS = {"to", "until", "till"}
_CLOSING_WORDS = {"close", "closes", "closing", "closed", "until", "till", "ends", "end"}
_OPENING_WORDS = {"open", "opens", "opening", "from", "starts", "start"}


def _range_role(sentence_text: str, previous_word: str) -> str:
    """Whether a number in the answer refers to the start or the end of a range ("8:0-21:0")."""
    if previous_word == "from":
        return "start"
    if previous_word in _RANGE_END_WORDS:
        return "end"
    words = set(_WORD.findall(sentence_text.lower()))
    if words & _CLOSING_WORDS and not words & {"open", "opens", "opening"}:
        return "end"
    if words & _OPENING_WORDS:
        return "start"
    return ""


def _range_position(text: str, start: int, end: int) -> str:
    if text[end : end + 1] == "-":
        return "start"
    if start > 0 and text[start - 1] == "-":
        return "end"
    return ""


def _best_number(atom: Atom, sentence_text: str, candidates: list[str]) -> tuple[str, str, float] | None:
    """atom offsets are relative to sentence_text."""
    context = _neighbours(sentence_text, atom.start, atom.end)
    kind = _number_kind(atom.text, context[1])
    role = _range_role(sentence_text, context[0])
    answer_forms = {f for m in _numbers_in(sentence_text) for f in normalize_number(m.group())}
    best = None
    for rank, sentence in enumerate(candidates):
        for m in _numbers_in(sentence):
            if normalize_number(m.group()) & answer_forms or _number_kind(m.group(), _neighbours(sentence, m.start(), m.end())[1]) != kind:
                continue
            before, after = _neighbours(sentence, m.start(), m.end())
            score = (before == context[0] and before != "") + (after == context[1] and after != "") - 0.25 * rank
            score += bool(role) and role == _range_position(sentence, m.start(), m.end())
            if best is None or score > best[2]:
                best = (_format_like(atom.text, m.group()), sentence, score)
    if best is None:
        return None
    replacement, sentence, score = best
    return replacement, sentence, max(0.3, min(1.0, 0.5 + 0.25 * score))


MIN_ENTITY_CONTEXT = 0.5


def _best_entity(atom: Atom, answer_sentence: str, candidates: list[str]) -> tuple[str, str, float] | None:
    """Only from a source sentence that shares at least half of the claim's other content words."""
    lowered = answer_sentence.lower()
    claim_words = content_words(answer_sentence) - content_words(atom.text)
    for rank, sentence in enumerate(candidates):
        if not claim_words or len(claim_words & content_words(sentence)) / len(claim_words) < MIN_ENTITY_CONTEXT:
            continue
        for e in _ner()(sentence).ents:
            if e.label_ == atom.label and e.text.lower() not in lowered:
                return e.text, sentence, max(0.3, 0.8 - 0.2 * rank)
    return None


def _null_line(sample: Sample, word: str) -> str:
    for doc in sample.documents:
        for line in doc.text.splitlines():
            if line.endswith(NULL_VALUE) and word.lower() in line.lower().replace(" ", ""):
                return line
    return ""


def suggest(sample: Sample, sentence: Sentence) -> list[Suggestion]:
    (checks,) = check_sample(sample, [sentence])
    if not checks.atoms:
        return []
    source_sentences, bm25 = _source_index(tuple(d.text for d in sample.documents))
    suggestions = []
    for atom in checks.atoms:
        if atom.kind == "null":
            suggestions.append(Suggestion(atom.start, atom.end, atom.text, None, _null_line(sample, atom.text), "null", 0.9))
            continue
        local = (atom.start - sentence.start, atom.end - sentence.start)
        query = sentence.text[: local[0]] + " " + sentence.text[local[1] :]
        scores = bm25.scores(_singular(query))
        candidates = [source_sentences[i] for i in sorted(range(len(scores)), key=lambda i: -scores[i])[:CANDIDATE_SENTENCES] if scores[i] > 0]
        if atom.kind == "number":
            found = _best_number(Atom(local[0], local[1], atom.text, atom.kind), sentence.text, candidates)
        else:
            found = _best_entity(atom, sentence.text, candidates)
        if found:
            replacement, evidence, confidence = found
            suggestions.append(Suggestion(atom.start, atom.end, atom.text, replacement, evidence, atom.kind, confidence))
        else:
            suggestions.append(Suggestion(atom.start, atom.end, atom.text, None, candidates[0] if candidates else "", atom.kind, 0.3))
    return suggestions


def apply(answer: str, suggestions: list[Suggestion]) -> str:
    """The answer with every confident replacement applied (right to left so offsets stay valid)."""
    for s in sorted(suggestions, key=lambda s: -s.start):
        if s.replacement is not None:
            answer = answer[: s.start] + s.replacement + answer[s.end :]
    return answer
