"""Meaning shifts that keep the words but change the claim: swapped roles, stronger quantifiers, inflated certainty.

Like the polarity check, each rule compares an answer sentence with a source sentence it nearly restates:
- role swap: the same verb with its two participants exchanged ("Germany beat Brazil" vs "Brazil beat Germany",
  passive voice normalised, participants matched by head word). Word overlap and embeddings cannot see it; the
  parse decides. Since a swap keeps every word, a looser restatement criterion is used. A confirmed swap is a
  contradiction and overrides the model's score.
- quantifier: the answer uses a stronger quantifier than the source for the same thing ("some people" -> "most people").
- certainty: the source hedges a statement ("may reduce", "allegedly traveled") and the answer states it as fact.
Quantifier and certainty shifts are advisory cautions: RAGTruth annotators rarely count them as hallucinations, so
they are reported next to the verdict instead of changing it. They need NLI to find that the source sentence does
not entail the answer sentence. Word classes are closed linguistic categories (quantifiers, modal and epistemic
hedges); settings come from RAGTruth train (scripts/evaluate_shifts.py).
"""

import re
from functools import lru_cache
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.correct import _singular
from truth_guardian.polarity import CANDIDATES, MAX_LENGTH_RATIO, MIN_OVERLAP, _index, lemmas
from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, content_words

QUANTIFIER_STRENGTH = {
    **dict.fromkeys(["some", "several", "certain", "sometimes", "occasionally", "partly", "partially"], 1),
    **dict.fromkeys(["many", "most", "majority", "often", "usually", "frequently", "generally", "typically", "mostly", "largely", "mainly", "commonly"], 2),
    **dict.fromkeys(["all", "every", "each", "always", "entire", "entirely", "whole", "completely", "totally", "universally", "everyone", "everybody", "everything", "everywhere", "invariably"], 3),
}
HEDGE = re.compile(
    r"\b(?:may(?!\s+(?:want|wish|need|be\s+required))|might|possibly|perhaps|probably|likely|unlikely|apparently|presumably|"
    r"reportedly|allegedly|alleged|supposedly|potentially|seemingly|arguably|suggests?|suggested|suggesting|preliminary|"
    r"tentative(?:ly)?|unconfirmed|speculated|suspected|rumou?red)\b|\b(?:appears?|appeared|seems?|seemed|believed|thought|said|reported)\s+to\b",
    re.IGNORECASE,
)
BOOSTERS = {
    "definitely", "certainly", "clearly", "undoubtedly", "conclusively", "prove", "proves", "proved", "proven",
    "confirms", "confirmed", "guaranteed", "guarantees", "will", "surely", "obviously",
}
SYMMETRIC_VERBS = {
    "meet", "marry", "wed", "date", "play", "tie", "draw", "face", "collaborate", "partner", "merge", "border",
    "resemble", "fight", "battle", "clash", "debate", "negotiate", "talk", "speak", "chat", "compete", "equal", "match",
    "share", "trade", "exchange", "join", "accompany", "befriend", "divorce", "kiss", "hug", "contact", "know",
}
CONFIRM_ENTAILMENT = {"role_swap": 1.01, "quantifier": 0.5, "certainty": 0.5}
OVERRIDE_KINDS = {"role_swap"}
KINDS = tuple(CONFIRM_ENTAILMENT)
QUANTIFIER_WINDOW = 2
ROLE_SWAP_OVERLAP = 0.5
_WORD = re.compile(r"[A-Za-z]+")


class ShiftCheck(NamedTuple):
    kind: str | None
    spans: list[tuple[int, int]]
    evidence: str
    detail: str
    entailment: float | None = None

    @property
    def candidate(self) -> bool:
        return self.kind is not None

    @property
    def confirmed(self) -> bool:
        return self.candidate and self.entailment is not None and self.entailment < CONFIRM_ENTAILMENT[self.kind]

    @property
    def overrides(self) -> bool:
        return self.confirmed and self.kind in OVERRIDE_KINDS


NO_SHIFT = ShiftCheck(None, [], "", "")


class Role(NamedTuple):
    verbs: frozenset[str]
    agent: str
    patient: str
    agent_span: tuple[int, int]
    patient_span: tuple[int, int]
    proper: bool
    agent_head: str
    patient_head: str


@lru_cache(maxsize=1)
def _parser():
    import spacy

    return spacy.load("en_core_web_sm", exclude=["ner", "lemmatizer"])


def _aligned(sentence: Sentence, source_texts: tuple[str, ...], ignore: set[str], min_overlap: float = MIN_OVERLAP) -> list[str]:
    """Source sentences the answer sentence nearly restates (by default the polarity check's criteria)."""
    sources, bm25 = _index(source_texts)
    if not sources:
        return []
    words = content_words(sentence.text) - ignore
    scores = bm25.scores(_singular(sentence.text))
    out = []
    for i in sorted(range(len(sources)), key=lambda i: -scores[i])[:CANDIDATES]:
        source_words = content_words(sources[i]) - ignore
        overlap = len(words & source_words) / max(len(words), 1)
        if scores[i] > 0 and overlap >= min_overlap and len(source_words) <= MAX_LENGTH_RATIO * max(len(words), 1):
            out.append(sources[i])
    return out


def _phrase(token) -> tuple[int, int]:
    """Character range of a participant: its compound and proper-noun modifiers plus the head."""
    left = [c for c in token.lefts if c.dep_ in {"compound", "amod", "poss"} and c.pos_ in {"PROPN", "NOUN", "ADJ"}]
    start = min([token] + left, key=lambda t: t.i)
    return start.idx, token.idx + len(token.text)


def _key(token) -> str:
    return " ".join([t.text.lower() for t in token.lefts if t.dep_ == "compound"] + [token.text.lower()])


def roles(doc) -> list[Role]:
    """Each verb with both participants (passive voice normalised), keyed by head word and compounds."""
    found = []
    for verb in doc:
        if verb.pos_ not in {"VERB", "AUX"}:
            continue
        agent = patient = None
        for child in verb.children:
            if child.dep_ == "nsubj":
                agent = child
            elif child.dep_ in {"dobj", "nsubjpass"}:
                patient = child
            elif child.dep_ == "agent":
                agent = next((g for g in child.children if g.dep_ == "pobj"), agent)
        if agent is None or patient is None or agent.pos_ == "PRON" or patient.pos_ == "PRON":
            continue
        verb_lemmas = lemmas(verb.text)
        if verb_lemmas & SYMMETRIC_VERBS:
            continue
        found.append(Role(
            verb_lemmas, _key(agent), _key(patient), _phrase(agent), _phrase(patient), agent.pos_ == patient.pos_ == "PROPN",
            agent.text.lower(), patient.text.lower(),
        ))
    return found


def _role_swap(sentence: Sentence, source: str) -> ShiftCheck | None:
    answer_roles, source_roles = roles(_parser()(sentence.text)), roles(_parser()(source))
    for r in answer_roles:
        for s in source_roles:
            if r.verbs & s.verbs and r.agent_head != r.patient_head and r.agent_head == s.patient_head and r.patient_head == s.agent_head:
                spans = sorted((sentence.start + a, sentence.start + b) for a, b in (r.agent_span, r.patient_span))
                return ShiftCheck("role_swap", spans, source, f"the source has {s.agent} acting on {s.patient}, the answer the reverse")
    return None


def _words(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group().lower()) for m in _WORD.finditer(text)]


def _following(words: list[tuple[int, int, str]], i: int, window: int) -> set[str]:
    """Lemmas of the next content words after position i: what a quantifier or hedge applies to."""
    nearby = [w for _, _, w in words[i + 1 : i + 1 + window + 3] if w in content_words(w)][:window]
    return {l for w in nearby for l in lemmas(w)}


def _quantifier(sentence: Sentence, source: str) -> ShiftCheck | None:
    source_words, answer_words = _words(source), _words(sentence.text)
    for i, (a, b, word) in enumerate(answer_words):
        level = QUANTIFIER_STRENGTH.get(word, 0)
        if level < 2:
            continue
        target = _following(answer_words, i, QUANTIFIER_WINDOW)
        weaker = [w for j, (_, _, w) in enumerate(source_words) if 0 < QUANTIFIER_STRENGTH.get(w, 0) < level and _following(source_words, j, QUANTIFIER_WINDOW) & target]
        same_or_stronger = [w for j, (_, _, w) in enumerate(source_words) if QUANTIFIER_STRENGTH.get(w, 0) >= level and _following(source_words, j, QUANTIFIER_WINDOW) & target]
        if weaker and not same_or_stronger:
            return ShiftCheck("quantifier", [(sentence.start + a, sentence.start + b)], source, f'the source says "{weaker[0]}", the answer "{word}"')
    return None


def _certainty(sentence: Sentence, source: str) -> ShiftCheck | None:
    hedges = list(HEDGE.finditer(source))
    if not hedges or HEDGE.search(sentence.text):
        return None
    answer_words, source_words = _words(sentence.text), _words(source)
    for hedge in hedges:
        position = next((i for i, (a, _, _) in enumerate(source_words) if a >= hedge.end()), len(source_words)) - 1
        target = _following(source_words, position, 1)
        matched = [(a, b) for a, b, w in answer_words if lemmas(w) & target]
        if not matched:
            continue
        boosters = [(a, b) for a, b, w in answer_words if w in BOOSTERS]
        spans = [(sentence.start + a, sentence.start + b) for a, b in (boosters or matched[:1])]
        return ShiftCheck("certainty", spans, source, f'the source hedges with "{hedge.group().lower()}", the answer states it as fact')
    return None


def check_sentence(sentence: Sentence, source_texts: tuple[str, ...]) -> ShiftCheck:
    for source in _aligned(sentence, source_texts, set(), ROLE_SWAP_OVERLAP):
        found = _role_swap(sentence, source)
        if found:
            return found
    ignore = BOOSTERS | set(QUANTIFIER_STRENGTH) | {w for m in HEDGE.finditer(" ".join(source_texts)) for w in m.group().lower().split()}
    for source in _aligned(sentence, source_texts, ignore):
        for rule in (_quantifier, _certainty):
            found = rule(sentence, source)
            if found:
                return found
    return NO_SHIFT


def check_sample(sample: Sample, sentences: list[Sentence], classify=models.nli_probabilities) -> list[ShiftCheck]:
    """Rule candidates get one NLI call each on (source sentence, answer sentence)."""
    texts = tuple(d.text for d in sample.documents)
    checks = [check_sentence(s, texts) for s in sentences]
    pending = [i for i, c in enumerate(checks) if c.candidate]
    if pending:
        probs = classify([(checks[i].evidence, sentences[i].text) for i in pending])
        for i, row in zip(pending, probs):
            checks[i] = checks[i]._replace(entailment=float(row[models.NLI_LABELS.index("entailment")]))
    return checks
