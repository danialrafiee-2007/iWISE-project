"""Source sentences and their embeddings, computed once per unique document set and encoder."""

from collections.abc import Callable
from typing import NamedTuple

import numpy as np

from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences

Encoder = Callable[[list[str]], np.ndarray]


class Evidence(NamedTuple):
    sentences: list[str]
    embeddings: np.ndarray


_cache: dict[tuple, Evidence] = {}


def evidence_for(sample: Sample, encode: Encoder) -> Evidence:
    key = (encode, tuple(d.text for d in sample.documents))
    if key not in _cache:
        sentences = [s.text for d in sample.documents for s in split_sentences(d.text)]
        _cache[key] = Evidence(sentences, encode(sentences) if sentences else np.zeros((0, 0)))
    return _cache[key]
