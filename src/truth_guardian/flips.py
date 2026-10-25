"""Flip test: does a sentence fit its evidence better with one word turned around?

An answer that states the opposite of its source ("fell" for "rose"), a stronger quantifier ("all" for "some") or
more certainty ("will" for "may") often has no source sentence close enough for the polarity and shift rules, which
need a near-restatement. Here the suspect word is replaced by its counterpart: a WordNet antonym, the weak member of
the quantifier scale shifts.py already uses, a hedge for a booster. If NLI finds the flipped sentence entailed by the
sentence's evidence (the same retrieved premises as the NLI signal) and the original much less so, the original says
the opposite of, or more than, the sources. Settings come from RAGTruth train (scripts/evaluate_flips.py): edits built
from grounded train answers for recall, natural train answers for false alarms. Only the certainty flip passed the
bar of 0.5% false alarms on grounded answers (13% of certainty edits found at 0.4%); with the base NLI model the
antonym and quantifier flips flag 3-20% of grounded answers at any useful setting, so they are studied, not used.
"""

import re
from functools import lru_cache
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.polarity import _wordnet, antonyms, lemmas
from truth_guardian.schema import Sample
from truth_guardian.shifts import BOOSTERS, QUANTIFIER_STRENGTH
from truth_guardian.text import STOP_WORDS, Sentence

KINDS = ("antonym", "quantifier", "certainty")
ACTIVE = ("certainty",)
MIN_FLIPPED_ENTAILMENT = {"antonym": 0.9, "quantifier": 0.9, "certainty": 0.5}
MIN_GAIN = {"antonym": 0.6, "quantifier": 0.6, "certainty": 0.6}
MAX_FLIPS = 6
ANTONYMS_PER_WORD = 2
FREQUENCY = {"always", "usually", "often", "frequently", "generally", "typically", "commonly", "invariably"}
WEAKER = {"frequency": "sometimes", "degree": "partly", "quantity": "some"}
DEGREE = {"mostly", "largely", "mainly", "entirely", "completely", "totally", "universally"}
HEDGED = {
    "will": "may", "definitely": "possibly", "certainly": "possibly", "clearly": "possibly", "undoubtedly": "possibly",
    "conclusively": "possibly", "surely": "possibly", "obviously": "possibly", "prove": "suggest", "proves": "suggests",
    "proved": "suggested", "proven": "suggested", "confirms": "suggests", "confirmed": "suggested", "guaranteed": "likely",
    "guarantees": "suggests",
}
_WORD = re.compile(r"[A-Za-z]+")


class Flip(NamedTuple):
    kind: str
    start: int
    end: int
    word: str
    replacement: str


class FlipCheck(NamedTuple):
    kind: str | None
    spans: list[tuple[int, int]]
    detail: str
    original_entailment: float | None = None
    flipped_entailment: float | None = None

    @property
    def confirmed(self) -> bool:
        return (
            self.kind is not None and self.flipped_entailment is not None
            and self.flipped_entailment >= MIN_FLIPPED_ENTAILMENT[self.kind]
            and self.flipped_entailment - self.original_entailment >= MIN_GAIN[self.kind]
        )


NO_FLIP = FlipCheck(None, [], "")


def _cased(word: str, replacement: str) -> str:
    return replacement.capitalize() if word[0].isupper() else replacement


@lru_cache(maxsize=1)
def _irregular() -> dict[str, list[str]]:
    """Verb lemma -> its irregular forms, from WordNet's own exception list ("fall" -> "fallen", "fell")."""
    forms: dict[str, list[str]] = {}
    for form, bases in _wordnet()._exception_map["v"].items():
        for base in bases:
            forms.setdefault(base, []).append(form)
    return forms


def _bases(word: str) -> frozenset[str]:
    """The word's lemmas plus the verbs it is an irregular form of ("fell" is also "fall", not only "to fell")."""
    return lemmas(word) | frozenset(_wordnet()._exception_map["v"].get(word.lower(), []))


def _inflect(word: str, lemma: str, target: str) -> str:
    """Carry the word's form over to the replacement: "increased" -> "decreased", "rose" -> "fell", "won" -> "lost"."""
    low = word.lower()
    if low != lemma and low in _wordnet()._exception_map["v"]:
        if irregular := _irregular().get(target):
            participle = low.endswith("n")
            target = min([f for f in irregular if f.endswith("n") == participle] or irregular, key=len)
    elif low.startswith(lemma) and len(low) > len(lemma):
        target = target + low[len(lemma):]
    elif low.endswith("ed") and lemma.endswith("e") and low[:-1] == lemma:
        target = target + "d"
    return _cased(word, target)


def _weaker(word: str) -> str | None:
    w = word.lower()
    if QUANTIFIER_STRENGTH.get(w, 0) < 2:
        return None
    return WEAKER["frequency" if w in FREQUENCY else "degree" if w in DEGREE else "quantity"]


def candidates(sentence: Sentence, kinds: tuple[str, ...] = ACTIVE) -> list[Flip]:
    """The words worth flipping, in order of appearance, at most MAX_FLIPS, of the given kinds."""
    flips = []
    for m in _WORD.finditer(sentence.text):
        word, low = m.group(), m.group().lower()
        if len(low) < 3 or low in STOP_WORDS and low not in QUANTIFIER_STRENGTH and low not in HEDGED:
            continue
        start, end = sentence.start + m.start(), sentence.start + m.end()
        if low in HEDGED:
            flips.append(Flip("certainty", start, end, word, _cased(word, HEDGED[low])))
        elif (weak := _weaker(word)) is not None:
            flips.append(Flip("quantifier", start, end, word, _cased(word, weak)))
        else:
            bases = _bases(word)
            lemma = min(bases - {low}, key=len, default=low)
            opposites = sorted({(a, b == low) for b in bases for a in antonyms(b) if " " not in a})
            replacements = list(dict.fromkeys(_cased(word, a) if same_form else _inflect(word, lemma, a) for a, same_form in opposites))
            flips += [Flip("antonym", start, end, word, r) for r in replacements[:ANTONYMS_PER_WORD]]
    return [f for f in flips if f.kind in kinds][:MAX_FLIPS]


def _swap(sentence: Sentence, flip: Flip) -> str:
    a, b = flip.start - sentence.start, flip.end - sentence.start
    return sentence.text[:a] + flip.replacement + sentence.text[b:]


def check_sample(sample: Sample, sentences: list[Sentence], premises: list[str], classify=models.nli_probabilities) -> list[FlipCheck]:
    """One NLI call per sentence with candidates (original) and one per candidate (flipped), against its premises."""
    pairs, owners = [], []
    for i, (sentence, premise) in enumerate(zip(sentences, premises)):
        flips = candidates(sentence) if premise else []
        if flips:
            pairs.append((premise, sentence.text))
            owners.append((i, None))
            for f in flips:
                pairs.append((premise, _swap(sentence, f)))
                owners.append((i, f))
    if not pairs:
        return [NO_FLIP for _ in sentences]
    entail = [float(row[models.NLI_LABELS.index("entailment")]) for row in classify(pairs)]
    original = {i: e for (i, f), e in zip(owners, entail) if f is None}
    checks = [NO_FLIP for _ in sentences]
    for (i, f), e in zip(owners, entail):
        if f is None:
            continue
        found = FlipCheck(f.kind, [(f.start, f.end)], f'with "{f.replacement}" for "{f.word}" the sources support it', original[i], e)
        best = checks[i]
        if best.kind is None or (found.confirmed and not best.confirmed) or (found.confirmed == best.confirmed and e - original[i] > best.flipped_entailment - best.original_entailment):
            checks[i] = found
    return checks
