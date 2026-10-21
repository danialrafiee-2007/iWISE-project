"""Symbolic checks: numbers, times and named entities in the answer must appear in the sources (or the question).

For Yelp-style structured data, mentioning an attribute whose value is "not specified" is also flagged,
unless a review mentions it. Unmatched items come back as exact character spans for word-level highlighting.
"""

import re
from functools import lru_cache
from typing import NamedTuple

from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, tokens

_NUMBER = re.compile(r"\d{1,2}:\d{1,2}|\d+(?:[.,]\d+)*")
_LIST_MARKER = re.compile(r"(?:^|\n)\s*$")
_PASSAGE_REF = re.compile(r"passages?\s*(?:\d+\s*(?:,|and|&)\s*)*$", re.IGNORECASE)
_WORD_COUNT = re.compile(r"\s*words\b", re.IGNORECASE)
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
ENTITY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "NORP", "FAC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE", "DATE"}
_GENERIC_KEY_WORDS = {"attributes", "business", "restaurants", "good", "for", "ambience", "hours"}
NULL_VALUE = "not specified"

_CALENDAR_WORDS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
_US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "ia": "iowa", "ks": "kansas", "ky": "kentucky", "la": "louisiana", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi", "mo": "missouri",
    "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire", "nj": "new jersey",
    "nm": "new mexico", "ny": "new york", "nc": "north carolina", "nd": "north dakota", "oh": "ohio",
    "ok": "oklahoma", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina", "sd": "south dakota",
    "tn": "tennessee", "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming",
}
_STREET_WORDS = {
    "rd": "road", "st": "street", "ave": "avenue", "blvd": "boulevard", "dr": "drive", "ln": "lane",
    "hwy": "highway", "ste": "suite", "pkwy": "parkway", "ct": "court", "pl": "place",
}
_EQUIVALENTS = {**_US_STATES, **_STREET_WORDS}


class SentenceChecks(NamedTuple):
    numbers: int
    numbers_unmatched: int
    entities: int
    entities_unmatched: int
    null_mentions: int
    spans: list[tuple[int, int]]


@lru_cache(maxsize=1)
def _ner():
    import spacy

    return spacy.load("en_core_web_sm", exclude=["tagger", "attribute_ruler", "lemmatizer", "parser"])


def normalize_number(text: str) -> set[str]:
    """Canonical forms of a number or clock time; times also yield 12-hour variants."""
    if ":" in text:
        hour, minute = (int(p) for p in text.split(":"))
        forms = set()
        for h in {hour, hour % 12 or 12}:
            forms.add(f"{h}:{minute:02d}")
            if minute == 0:
                forms.add(str(h))
        return forms
    value = text.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return {value.lstrip("0") or "0"}


def _is_reference(text: str, m: re.Match) -> bool:
    """List markers, "Passage 2" citations and "in 200 words" statements are not factual claims."""
    before, after = text[: m.start()], text[m.end() :]
    list_marker = _LIST_MARKER.search(before) and after[:1] in {".", ")"}
    return bool(list_marker or _PASSAGE_REF.search(before) or _WORD_COUNT.match(after))


def _numbers_in(text: str) -> list[re.Match]:
    return [m for m in _NUMBER.finditer(text) if not _is_reference(text, m)]


def _expand(words: set[str], raw_words: set[str]) -> set[str]:
    """Add known equivalents (US states, street types); raw words keep abbreviations like "ca" that are stop words."""
    expanded = set(words)
    for short, full in _EQUIVALENTS.items():
        full_words = set(full.split())
        if short in raw_words:
            expanded |= full_words
        if full_words <= raw_words:
            expanded.add(short)
    return expanded


def _word_known(word: str, known: set[str]) -> bool:
    return word in known or word.rstrip("s") in known or f"{word}s" in known


def _null_terms(sample: Sample) -> set[str]:
    terms: set[str] = set()
    for doc in sample.documents:
        if doc.id != "business":
            continue
        for line in doc.text.splitlines():
            key, _, value = line.rpartition(": ")
            if value != NULL_VALUE or not key:
                continue
            last = key.split()[-1]
            parts = {p.lower() for p in _CAMEL.findall(last)} | {last.lower()}
            terms |= {p for p in parts if len(p) >= 4 and p not in _GENERIC_KEY_WORDS}
    reviews = set(tokens(" ".join(d.text for d in sample.documents if d.id.startswith("review"))))
    return {t for t in terms if not _word_known(t, reviews)}


def check_sample(sample: Sample, sentences: list[Sentence]) -> list[SentenceChecks]:
    source = " ".join([sample.question or "", *(d.text for d in sample.documents)])
    source_numbers = {form for m in _numbers_in(source) for form in normalize_number(m.group())}
    source_words = _expand(set(tokens(source)), set(re.findall(r"\w+", source.lower())))
    null_terms = _null_terms(sample)
    entities = [e for e in _ner()(sample.answer).ents if e.label_ in ENTITY_LABELS]

    results = []
    for s in sentences:
        spans: list[tuple[int, int]] = []
        numbers = _numbers_in(s.text)
        unmatched_numbers = [m for m in numbers if not normalize_number(m.group()) & source_numbers]
        spans += [(s.start + m.start(), s.start + m.end()) for m in unmatched_numbers]

        checked = unmatched_entities = 0
        for e in entities:
            if not (s.start <= e.start_char and e.end_char <= s.end):
                continue
            words = [w for w in tokens(e.text) if not w.isdigit()]
            if e.label_ == "DATE":
                words = [w for w in words if w.rstrip("s") in _CALENDAR_WORDS]
            if not words:
                continue
            checked += 1
            if not all(_word_known(w, source_words) for w in words):
                unmatched_entities += 1
                spans.append((e.start_char, e.end_char))

        null_mentions = 0
        for m in re.finditer(r"\w+", s.text):
            if _word_known(m.group().lower(), null_terms):
                null_mentions += 1
                spans.append((s.start + m.start(), s.start + m.end()))

        results.append(SentenceChecks(len(numbers), len(unmatched_numbers), checked, unmatched_entities, null_mentions, sorted(set(spans))))
    return results
