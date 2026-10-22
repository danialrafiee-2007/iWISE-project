"""Symbolic checks: numbers, times and named entities in the answer must appear in the sources (or the question).

For Yelp-style structured data, mentioning an attribute whose value is "not specified" is also flagged,
unless a review mentions it. Unmatched items come back as exact character spans for word-level highlighting.
Matching tolerates surface variation (v2): accents, dotted acronyms, hyphenation, possessives, number words
("three", "twenty-first"), scale words ("1.5 million"), numeric dates, acronyms and their expansions, and
WordNet demonym links ("French" and "France"). References to passages or to the answer's own steps are not claims.
"""

import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple

from spacy.lang.en.stop_words import STOP_WORDS

from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, tokens

_NUMBER = re.compile(r"\d{1,2}:\d{1,2}(?::\d{2})?(?:\.\d+)?|\d+(?:[.,]\d+)*")
_LIST_MARKER = re.compile(r"(?:^|\n)\s*$")
_PASSAGE_REF = re.compile(r"passages?\s*(?:\d+\s*(?:,|and|&)\s*)*$", re.IGNORECASE)
_STEP_REF = re.compile(r"\b(?:steps?|items?|points?|stages?)\s*(?:\d+\s*(?:,|and|&|or|to|-)\s*)*$", re.IGNORECASE)
_PASSAGE_ENTITY = re.compile(r"passages?\s*\d+(?:\s*(?:,|and|&)\s*\d+)*", re.IGNORECASE)
_WORD_COUNT = re.compile(r"\s*words\b", re.IGNORECASE)
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
ENTITY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "NORP", "FAC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "LANGUAGE", "DATE"}
_GENERIC_KEY_WORDS = {"attributes", "business", "restaurants", "good", "for", "ambience", "hours"}
NULL_VALUE = "not specified"

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_CALENDAR_WORDS = set(_MONTHS) | {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
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
_OTHER_EQUIVALENTS = {
    "f": "fahrenheit", "c": "celsius", "america": "united states", "usa": "united states",
    "uk": "united kingdom", "britain": "united kingdom",
}
_EQUIVALENTS = {**_US_STATES, **_STREET_WORDS, **_OTHER_EQUIVALENTS}

_UNIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
               "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TEN_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
    "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30, "fortieth": 40,
    "fiftieth": 50, "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90, "hundredth": 100,
}
_SIMPLE_NUMBERS = {w: i for i, w in enumerate(_UNIT_WORDS)} | _ORDINAL_WORDS | {"dozen": 12}
_DIGIT_WORDS = "|".join(_UNIT_WORDS[1:10] + [w for w, v in _ORDINAL_WORDS.items() if v < 10])
_NUMBER_WORD = re.compile(
    rf"\b(?:({'|'.join(_TEN_WORDS)})(?:[- ]({_DIGIT_WORDS}))?|({'|'.join(_SIMPLE_NUMBERS)}))\b"
    r"(?:\s+(hundred|thousand|million|billion|trillion)\b)?",
    re.IGNORECASE,
)
_SCALE = re.compile(r"\s*(hundred|thousand|million|billion|trillion)\b", re.IGNORECASE)
_SCALES = {"hundred": 10**2, "thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
_ISO_DATE = re.compile(r"\b\d{4}-(\d{1,2})-\d{1,2}\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/\d{1,2}/\d{2,4}\b")
_DOTTED_ACRONYM = re.compile(r"\b(?:[A-Za-z]\.){2,}")
_CAPS = re.compile(r"\b[A-Z]{2,6}(?=s?\b)")
_ROMAN = re.compile(r"[IVX]{1,4}")
_CONNECTORS = {"of", "the", "and", "for", "on", "de"}
_POSSESSIVE = re.compile(r"['’]s\b")
_CHUNK = re.compile(r"\w+(?:-\w+)*")


class Atom(NamedTuple):
    """One unmatched item in the answer: character offsets, text, kind and (for entities) the NER label."""

    start: int
    end: int
    text: str
    kind: str
    label: str = ""


class SentenceChecks(NamedTuple):
    numbers: int
    numbers_unmatched: int
    entities: int
    entities_unmatched: int
    null_mentions: int
    spans: list[tuple[int, int]]
    atoms: list[Atom] = []


@lru_cache(maxsize=1)
def _ner():
    import spacy

    return spacy.load("en_core_web_sm", exclude=["tagger", "attribute_ruler", "lemmatizer", "parser"])


def normalize_number(text: str) -> set[str]:
    """Canonical forms of a number or clock time; times also yield 12-hour variants."""
    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            return {text}
        hour, minute = int(parts[0]), int(parts[1])
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


def _scaled(value: float, scale: str) -> str:
    return normalize_number(f"{value * _SCALES[scale.lower()]:.6f}").pop()


def number_forms(text: str, m: re.Match) -> set[str]:
    """Forms of the number matched in `text`, plus its value when a scale word follows ("1.5 million")."""
    forms = normalize_number(m.group())
    scale = _SCALE.match(text, m.end())
    if scale and ":" not in m.group():
        forms.add(_scaled(float(m.group().replace(",", "")), scale.group(1)))
    return forms


def _word_number_forms(text: str) -> set[str]:
    """Digit forms of spelled-out numbers ("three", "twenty-first", "two million")."""
    forms = set()
    for m in _NUMBER_WORD.finditer(text):
        if m.group(1):
            value = _TEN_WORDS[m.group(1).lower()] + (_SIMPLE_NUMBERS[m.group(2).lower()] if m.group(2) else 0)
        else:
            value = _SIMPLE_NUMBERS[m.group(3).lower()]
        forms.add(str(value))
        if m.group(4):
            forms.add(_scaled(value, m.group(4)))
    return forms


def _is_reference(text: str, m: re.Match) -> bool:
    """List markers, "Passage 2" citations, "steps 1-3" and "in 200 words" statements are not factual claims."""
    before, after = text[: m.start()], text[m.end() :]
    list_marker = _LIST_MARKER.search(before) and after[:1] in {".", ")"}
    return bool(list_marker or _PASSAGE_REF.search(before) or _STEP_REF.search(before) or _WORD_COUNT.match(after))


def _numbers_in(text: str) -> list[re.Match]:
    return [m for m in _NUMBER.finditer(text) if not _is_reference(text, m)]


def fold(text: str) -> str:
    """Strip accents and the dots of acronyms ("café" -> "cafe", "U.S." -> "US"), for matching only."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return _DOTTED_ACRONYM.sub(lambda m: m.group().replace(".", ""), text)


def _initials(run: list[str]) -> set[str]:
    letters = [w.lower() if _ROMAN.fullmatch(w) else w[0].lower() for w in run[:8]]
    return {"".join(letters[i:j]) for i in range(len(letters)) for j in range(i + 2, len(letters) + 1)}


def _acronyms(text: str) -> tuple[set[str], set[str]]:
    """(all-caps words, initials of runs of capitalised words such as "United Nations" -> "un")."""
    caps = {m.group().lower() for m in _CAPS.finditer(text)}
    initials, run = set(), []
    for w in re.findall(r"[A-Za-z]+", text):
        if (w[0].isupper() and w[1:].islower()) or _ROMAN.fullmatch(w):
            run.append(w)
        elif run and w.lower() in _CONNECTORS:
            continue
        else:
            initials |= _initials(run)
            run = []
    return caps, initials | _initials(run)


def _numeric_date_months(text: str) -> set[str]:
    months = {int(m.group(1)) for m in _ISO_DATE.finditer(text)} | {int(m.group(1)) for m in _SLASH_DATE.finditer(text)}
    return {_MONTHS[m - 1] for m in months if 1 <= m <= 12}


@lru_cache(maxsize=50_000)
def related_forms(word: str) -> frozenset[str]:
    """The word, its WordNet base forms, pertainyms and derivational links ("french" -> "france", "americans" -> "america")."""
    if len(word) < 3 or not word.isalpha():
        return frozenset({word})
    from truth_guardian.polarity import _wordnet

    wn = _wordnet()
    forms = {word} | {m for pos in ("n", "a") if (m := wn.morphy(word, pos))}
    related = set(forms)
    for lemma in forms:
        for synset in wn.synsets(lemma):
            for l in synset.lemmas():
                if l.name().lower() == lemma:
                    related |= {p.name().lower() for p in l.pertainyms() + l.derivationally_related_forms()}
    return frozenset(related)


def _expand(words: set[str], raw_words: set[str]) -> set[str]:
    """Add known equivalents (US states, street types, units, country names); raw words keep abbreviations like "ca"."""
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


MAX_NER_CHARS = 5_000
_CAPITALISED = re.compile(r"\b[A-Z][a-z]")


class EvidenceIndex:
    """Numbers and words seen so far; grows step by step so a trajectory's evidence is never re-read."""

    def __init__(self, text: str = ""):
        self.numbers: set[str] = set()
        self.words: set[str] = set()
        self.raw_words: set[str] = set()
        self.caps: set[str] = set()
        self.initials: set[str] = set()
        self.proper: set[str] = set()
        self._expanded: set[str] | None = None
        self.add(text)

    def add(self, text: str) -> None:
        if not text:
            return
        text = fold(text)
        self.numbers |= {form for m in _numbers_in(text) for form in number_forms(text, m)} | _word_number_forms(text)
        self.words |= set(tokens(text)) | {c.replace("-", "") for c in _CHUNK.findall(text.lower()) if "-" in c}
        self.words |= _numeric_date_months(text)
        self.raw_words |= set(re.findall(r"\w+", text.lower()))
        caps, initials = _acronyms(text)
        self.caps |= caps
        self.initials |= initials
        self.proper |= {w.lower() for w in re.findall(r"\b[A-Z][a-z]{2,}\b", text)}
        self._expanded = None

    @property
    def expanded(self) -> set[str]:
        if self._expanded is None:
            related = {f for w in self.proper for f in related_forms(w)}
            self._expanded = _expand(self.words, self.raw_words) | self.caps | self.initials | related
        return self._expanded

    def number_known(self, text: str, m: re.Match) -> bool:
        return bool(number_forms(text, m) & self.numbers)

    def entity_known(self, text: str, label: str) -> bool | None:
        """Whether every checkable word of an entity is in the evidence; None when nothing is checkable."""
        text = _POSSESSIVE.sub("", fold(text))
        if _PASSAGE_ENTITY.fullmatch(text.strip()):
            return None
        known, checked, unknown = self.expanded, False, False
        for chunk in _CHUNK.findall(text):
            parts = [p.lower() for p in chunk.split("-") if not p.isdigit() and (p.lower() not in STOP_WORDS or (p.isupper() and len(p) > 1))]
            if label == "DATE":
                parts = [p for p in parts if p.rstrip("s") in _CALENDAR_WORDS]
            if not parts:
                continue
            checked = True
            if chunk.lower().replace("-", "") in known:
                continue
            if not all(_word_known(p, known) or related_forms(p) & known for p in parts):
                unknown = True
        if not checked:
            return None
        if not unknown:
            return True
        capitals = [w for w in re.findall(r"[A-Za-z]+", text) if w[0].isupper() and w.lower() not in _CONNECTORS]
        return len(capitals) >= 2 and "".join(w[0] for w in capitals).lower() in self.caps

    def atoms(self, text: str) -> list[Atom]:
        """Numbers, times and names in `text` that the evidence does not contain (offsets relative to `text`)."""
        atoms = [Atom(m.start(), m.end(), m.group(), "number") for m in _numbers_in(text) if not self.number_known(text, m)]
        if not _CAPITALISED.search(text):
            return atoms
        for e in _ner()(text[:MAX_NER_CHARS]).ents:
            if e.label_ in ENTITY_LABELS and self.entity_known(e.text, e.label_) is False:
                atoms.append(Atom(e.start_char, e.end_char, e.text, "entity", e.label_))
        return atoms


def unmatched_atoms(text: str, evidence: str) -> list[Atom]:
    """Numbers, times and names in `text` that `evidence` does not contain (offsets relative to `text`)."""
    return EvidenceIndex(evidence).atoms(text)


def check_sample(sample: Sample, sentences: list[Sentence]) -> list[SentenceChecks]:
    index = EvidenceIndex(" ".join([sample.question or "", *(d.text for d in sample.documents)]))
    null_terms = _null_terms(sample)
    entities = [e for e in _ner()(sample.answer).ents if e.label_ in ENTITY_LABELS]

    results = []
    for s in sentences:
        atoms: list[Atom] = []
        numbers = _numbers_in(s.text)
        unmatched_numbers = [m for m in numbers if not index.number_known(s.text, m)]
        atoms += [Atom(s.start + m.start(), s.start + m.end(), m.group(), "number") for m in unmatched_numbers]

        checked = unmatched_entities = 0
        for e in entities:
            if not (s.start <= e.start_char and e.end_char <= s.end):
                continue
            known = index.entity_known(e.text, e.label_)
            if known is None:
                continue
            checked += 1
            if not known:
                unmatched_entities += 1
                atoms.append(Atom(e.start_char, e.end_char, e.text, "entity", e.label_))

        null_mentions = 0
        for m in re.finditer(r"\w+", s.text):
            if _word_known(m.group().lower(), null_terms):
                null_mentions += 1
                atoms.append(Atom(s.start + m.start(), s.start + m.end(), m.group(), "null"))

        spans = sorted({(a.start, a.end) for a in atoms})
        results.append(SentenceChecks(len(numbers), len(unmatched_numbers), checked, unmatched_entities, null_mentions, spans, atoms))
    return results
