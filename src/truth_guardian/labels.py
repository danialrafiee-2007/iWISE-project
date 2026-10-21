"""Sentence-level training labels derived from gold character spans."""

from collections.abc import Sequence

from truth_guardian.schema import HallucinationType, Sample
from truth_guardian.text import Sentence


def _overlaps(sentence: Sentence, start: int, end: int) -> bool:
    return sentence.start < end and start < sentence.end


def sentence_labels(sample: Sample, sentences: Sequence[Sentence]) -> list[int]:
    """1 when the sentence overlaps any gold hallucinated span, else 0."""
    spans = sample.labels.spans if sample.labels else []
    return [int(any(_overlaps(s, sp.start, sp.end) for sp in spans)) for s in sentences]


def sentence_types(sample: Sample, sentences: Sequence[Sentence]) -> list[HallucinationType | None]:
    """Gold hallucination type per sentence; contradiction wins when a sentence has several spans."""
    spans = sample.labels.spans if sample.labels else []
    types = []
    for s in sentences:
        found = {sp.type for sp in spans if sp.type and _overlaps(s, sp.start, sp.end)}
        types.append(HallucinationType.CONTRADICTED if HallucinationType.CONTRADICTED in found else next(iter(found), None))
    return types
