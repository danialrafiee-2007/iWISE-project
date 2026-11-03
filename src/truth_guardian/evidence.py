"""Source sentences and their embeddings, computed once per unique document set and encoder (the last CACHED_SETS are kept)."""

from collections.abc import Callable
from functools import lru_cache
from typing import NamedTuple

import numpy as np

from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences

Encoder = Callable[[list[str]], np.ndarray]
CACHED_SETS = 64


class Evidence(NamedTuple):
    sentences: list[str]
    embeddings: np.ndarray


@lru_cache(maxsize=CACHED_SETS)
def _evidence(encode: Encoder, texts: tuple[str, ...]) -> Evidence:
    sentences = [s.text for t in texts for s in split_sentences(t)]
    return Evidence(sentences, encode(sentences) if sentences else np.zeros((0, 0)))


def evidence_for(sample: Sample, encode: Encoder) -> Evidence:
    return _evidence(encode, tuple(d.text for d in sample.documents))
