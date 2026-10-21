"""B3: each answer sentence is checked by an NLI model against its top-k most similar source sentences.

Sources are longer than the NLI model's 512-token limit, so embeddings only pick the premise;
the score is 1 - P(entailment), so both contradicted and unsupported sentences score high.
"""

from collections.abc import Callable

import numpy as np

from truth_guardian import models
from truth_guardian.evaluation import Prediction, SentenceScore
from truth_guardian.evidence import Encoder, Evidence, evidence_for
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences

TOP_K = 5
ENTAILMENT = models.NLI_LABELS.index("entailment")

Classifier = Callable[[list[tuple[str, str]]], np.ndarray]


def build_premise(sentence_embedding: np.ndarray, evidence: Evidence, k: int = TOP_K) -> str:
    """The k most similar source sentences, kept in their original order."""
    similarities = evidence.embeddings @ sentence_embedding
    top = sorted(np.argsort(-similarities)[:k])
    return " ".join(evidence.sentences[i] for i in top)


def predict(sample: Sample, encode: Encoder = models.encode, classify: Classifier = models.nli_probabilities) -> Prediction:
    sentences = split_sentences(sample.answer)
    if not sentences:
        return Prediction(id=sample.id, score=0.0)
    evidence = evidence_for(sample, encode)
    if evidence.sentences:
        answer = encode([s.text for s in sentences])
        pairs = [(build_premise(e, evidence), s.text) for e, s in zip(answer, sentences)]
        scores = 1 - classify(pairs)[:, ENTAILMENT]
    else:
        scores = np.ones(len(sentences))
    return Prediction(
        id=sample.id,
        score=float(scores.max()),
        sentences=[SentenceScore(start=s.start, end=s.end, score=float(v)) for s, v in zip(sentences, scores)],
    )
