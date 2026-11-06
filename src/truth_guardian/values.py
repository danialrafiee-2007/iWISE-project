"""A value the sources give, attached to the wrong subject: "HHEM reaches 0.83" when the sources give 0.83 to the
fusion model and 0.78 to HHEM.

Every number of such an answer is in the sources, so the symbolic check passes it, and HHEM, which the fusion model
leans on, hardly reads which value goes with which subject (D-162: a risk of 0.03). NLI on the one source sentence
does, so the rule proposes and NLI decides, as in the polarity check. For each number of an answer sentence that the
sources hold, every other value of the same kind in a source sentence the answer sentence is about is put in its place.
The finding is confirmed when NLI finds that source sentence contradicting the answer as written and either entailing it
with the other value or, if CONFIRM_CONTRAST is set, not contradicting it with that value; and no source sentence holding
the answer's own value entails it. When the other value is entailed it is the fix.
"""

import re
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.correct import Suggestion, _singular
from truth_guardian.polarity import _index
from truth_guardian.schema import Sample
from truth_guardian.symbolic import _SCALE, _numbers_in, number_forms
from truth_guardian.text import Sentence, content_words

CANDIDATES = 5
MIN_OVERLAP = 0.5
MAX_TRIES = 6
MAX_HOLDING = 3
CONFIRM_ENTAILMENT = 0.9
CONFIRM_CONTRADICTION = 0.8
CONFIRM_CONTRAST: float | None = None
HOLDING_ENTAILMENT = 0.5
_CURRENCY = set("$€£¥")
_PERCENT = re.compile(r"\s*(?:%|per\s?cent\b)", re.IGNORECASE)
_YEAR = re.compile(r"1[5-9]\d\d|20\d\d")


class Value(NamedTuple):
    start: int
    end: int
    text: str
    forms: frozenset[str]
    kind: str


class Try(NamedTuple):
    value: Value
    other: Value
    source: str
    overlap: float
    rewritten: str


class Measured(NamedTuple):
    tried: Try
    rewritten_entailment: float
    rewritten_contradiction: float
    given_contradiction: float
    holding_entailment: float


class ValueCheck(NamedTuple):
    tries: int
    span: tuple[int, int] | None = None
    original: str = ""
    replacement: str = ""
    evidence: str = ""
    contradiction: float = 0.0
    entailment: float = 0.0

    @property
    def confirmed(self) -> bool:
        return self.span is not None


def _kind(text: str, m: re.Match, scaled: bool) -> str:
    if ":" in m.group():
        return "time"
    if text[m.start() - 1 : m.start()] in _CURRENCY:
        return "money"
    if _PERCENT.match(text, m.end()):
        return "percent"
    if not scaled and _YEAR.fullmatch(m.group()):
        return "year"
    return "amount"


def values(text: str) -> list[Value]:
    """Numbers with their scale word ("2.1 million"), positions within text."""
    found = []
    for m in _numbers_in(text):
        scale = _SCALE.match(text, m.end())
        end = scale.end() if scale else m.end()
        found.append(Value(m.start(), end, text[m.start() : end], frozenset(number_forms(text, m)), _kind(text, m, bool(scale))))
    return found


def _words(text: str) -> set[str]:
    return {w for w in content_words(_singular(text)) if not any(c.isdigit() for c in w)}


def tries(sentence: Sentence, source_texts: tuple[str, ...], min_overlap: float = MIN_OVERLAP) -> tuple[list[Try], list[str]]:
    """The answer sentence with another value of a source sentence it is about in place of its own, and the source
    sentences that hold its own values."""
    sources, bm25 = _index(source_texts)
    if not sources:
        return [], []
    in_sources = [values(s) for s in sources]
    known = frozenset().union(*(v.forms for found in in_sources for v in found))
    own = [v for v in values(sentence.text) if v.forms & known]
    if not own:
        return [], []
    words = _words(sentence.text)
    scores = bm25.scores(_singular(sentence.text))
    ranked = [i for i in sorted(range(len(sources)), key=lambda i: -scores[i]) if scores[i] > 0]
    found, seen = [], set()
    for i in ranked[:CANDIDATES]:
        overlap = len(words & _words(sources[i])) / max(len(words), 1)
        if overlap < min_overlap:
            continue
        for value in own:
            for other in in_sources[i]:
                rewritten = sentence.text[: value.start] + other.text + sentence.text[value.end :]
                if other.kind == value.kind and not other.forms & value.forms and rewritten not in seen:
                    seen.add(rewritten)
                    found.append(Try(value, other, sources[i], overlap, rewritten))
    own_forms = frozenset().union(*(v.forms for v in own))
    holding = [sources[i] for i in ranked if any(v.forms & own_forms for v in in_sources[i])][:MAX_HOLDING]
    return found[:MAX_TRIES], holding


def measure(sample: Sample, sentences: list[Sentence], classify=models.nli_probabilities, min_overlap: float = MIN_OVERLAP) -> list[list[Measured]]:
    """Per sentence, NLI's reading of each try: one call for all the pairs of the answer."""
    texts = tuple(d.text for d in sample.documents)
    planned = [tries(s, texts, min_overlap) for s in sentences]
    pairs: dict[tuple[str, str], int] = {}
    for s, (found, holding) in zip(sentences, planned):
        for pair in [(t.source, t.rewritten) for t in found] + [(p, s.text) for p in [t.source for t in found] + (holding if found else [])]:
            pairs.setdefault(pair, len(pairs))
    probs = classify(list(pairs)) if pairs else []
    entailment, contradiction = models.NLI_LABELS.index("entailment"), models.NLI_LABELS.index("contradiction")
    out = []
    for s, (found, holding) in zip(sentences, planned):
        held = max((float(probs[pairs[(p, s.text)]][entailment]) for p in holding), default=0.0) if found else 0.0
        out.append([
            Measured(t, *(float(probs[pairs[(t.source, t.rewritten)]][k]) for k in (entailment, contradiction)), float(probs[pairs[(t.source, s.text)]][contradiction]), held)
            for t in found
        ])
    return out


def decide(
    sentence: Sentence, measured: list[Measured], entailment: float = CONFIRM_ENTAILMENT, contradiction: float = CONFIRM_CONTRADICTION,
    contrast: float | None = CONFIRM_CONTRAST,
) -> ValueCheck:
    entailed = lambda m: m.rewritten_entailment >= entailment
    confirmed = [
        m for m in measured
        if m.given_contradiction >= contradiction and m.holding_entailment < HOLDING_ENTAILMENT
        and (entailed(m) or (contrast is not None and m.rewritten_contradiction <= contrast))
    ]
    if not confirmed:
        return ValueCheck(len(measured))
    best = max(confirmed, key=lambda m: (entailed(m), round(m.rewritten_entailment + m.given_contradiction, 2), m.tried.value.kind != "year", m.tried.overlap))
    t = best.tried
    return ValueCheck(
        len(measured), (sentence.start + t.value.start, sentence.start + t.value.end), t.value.text, t.other.text if entailed(best) else "", t.source,
        best.given_contradiction, best.rewritten_entailment,
    )


def check_sample(sample: Sample, sentences: list[Sentence], classify=models.nli_probabilities) -> list[ValueCheck]:
    return [decide(s, m) for s, m in zip(sentences, measure(sample, sentences, classify))]


def fixes(row: dict) -> list[Suggestion]:
    """The confirmed finding of a sentence's signal row as a Fix-it replacement."""
    if not row.get("val_confirmed"):
        return []
    start, end = row["val_spans"][0]
    return [Suggestion(start, end, row["val_original"], row["val_replacement"] or None, row["val_evidence"], "number", row["val_entailment"])]
