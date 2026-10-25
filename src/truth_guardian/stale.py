"""Outdated values in agent runs: the answer repeats an earlier tool result that a later tool result revised.

An agent can find a figure, find a newer one later, and still answer with the first. Every claim is then supported by
some tool output, so the evidence checks pass. Here each answer sentence is compared by NLI with the closest sentence
of every tool output, in step order: it is outdated when an earlier output entails it and a later one contradicts it.
Studied, not used: on faithful runs of AgentHallu dev and TG-Agent dev it fires 9-13% of the time at every setting
(their tool outputs often disagree with each other), far above the 1% allowed (scripts/evaluate_stale.py, D-116).
"""

from typing import NamedTuple

from truth_guardian import models
from truth_guardian.correct import _singular
from truth_guardian.retrieval import Bm25
from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, split_sentences

MIN_ENTAILMENT = 0.8
MIN_CONTRADICTION = 0.8


class StaleCheck(NamedTuple):
    stale: bool
    earlier_step: int | None = None
    later_step: int | None = None
    later_text: str = ""
    contradiction: float = 0.0


NOT_STALE = StaleCheck(False)


def _observations(sample: Sample) -> list[tuple[int, list[str]]]:
    return [(s.step, [x.text for x in split_sentences(s.observation)]) for s in sample.agent_log or [] if s.observation]


def check_sample(sample: Sample, sentences: list[Sentence], classify=models.nli_probabilities) -> list[StaleCheck]:
    observations = [(step, texts) for step, texts in _observations(sample) if texts]
    if len(observations) < 2:
        return [NOT_STALE for _ in sentences]
    pairs, owners = [], []
    for i, sentence in enumerate(sentences):
        for step, texts in observations:
            scores = Bm25([_singular(t) for t in texts]).scores(_singular(sentence.text))
            best = max(range(len(texts)), key=lambda k: scores[k])
            if scores[best] > 0:
                pairs.append((texts[best], sentence.text))
                owners.append((i, step))
    if not pairs:
        return [NOT_STALE for _ in sentences]
    probs = classify(pairs)
    by_sentence: dict[int, list[tuple[int, str, float, float]]] = {}
    for (i, step), (premise, _), row in zip(owners, pairs, probs):
        by_sentence.setdefault(i, []).append((step, premise, float(row[models.NLI_LABELS.index("entailment")]), float(row[models.NLI_LABELS.index("contradiction")])))
    checks = []
    for i in range(len(sentences)):
        found = NOT_STALE
        rows = sorted(by_sentence.get(i, []))
        for a, (step_a, _, entail_a, _) in enumerate(rows):
            if entail_a < MIN_ENTAILMENT:
                continue
            later = [r for r in rows[a + 1 :] if r[3] >= MIN_CONTRADICTION]
            if later:
                step_b, text_b, _, contra_b = max(later, key=lambda r: r[3])
                found = StaleCheck(True, step_a, step_b, text_b, contra_b)
                break
        checks.append(found)
    return checks
