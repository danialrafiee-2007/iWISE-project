"""B2: a sentence is suspicious when no source sentence is close to it in meaning (cosine similarity)."""

import numpy as np

from truth_guardian import models
from truth_guardian.evaluation import Prediction, SentenceScore
from truth_guardian.evidence import Encoder, evidence_for
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def sentence_scores(similarities: np.ndarray) -> np.ndarray:
    """(answer sentences x source sentences) cosine matrix to scores in [0, 1]: (1 - best match) / 2."""
    if similarities.shape[1] == 0:
        return np.ones(similarities.shape[0])
    return (1 - similarities.max(axis=1)) / 2


def predict(sample: Sample, encode: Encoder = models.encode) -> Prediction:
    sentences = split_sentences(sample.answer)
    if not sentences:
        return Prediction(id=sample.id, score=0.0)
    evidence = evidence_for(sample, encode)
    answer = encode([s.text for s in sentences])
    similarities = answer @ evidence.embeddings.T if evidence.sentences else np.zeros((len(sentences), 0))
    scores = sentence_scores(similarities)
    return Prediction(
        id=sample.id,
        score=float(scores.max()),
        sentences=[SentenceScore(start=s.start, end=s.end, score=float(v)) for s, v in zip(sentences, scores)],
    )
