"""Who is to blame for a hallucination: the retriever or the generator?

Retrieval relevance measures how well the documents address the question: the best embedding match between the
question and any source sentence, averaged with the share of the question's content words found in the sources.
A hallucinated answer over low-relevance documents points to retrieval (the model filled a gap); over relevant
documents it points to generation (the model departed from good evidence). Without a question, retrieval
cannot be judged. The relevance threshold is set on RAGTruth train with swapped (irrelevant) documents.
"""

from typing import Literal, NamedTuple

import numpy as np

from truth_guardian import models
from truth_guardian.evidence import Encoder, evidence_for
from truth_guardian.schema import Sample
from truth_guardian.text import content_words

RELEVANCE_THRESHOLD = 0.43

Blame = Literal["retrieval", "generation", "weak_sources", "none", "unknown"]

MESSAGES = {
    "retrieval": "The sources barely address the question, so the model filled the gap: fix retrieval first.",
    "generation": "The sources address the question, but the answer departs from them: the generator is at fault.",
    "weak_sources": "The answer matches the sources, but the sources barely address the question: check they are the right documents.",
    "none": "The sources address the question and the answer stays with them.",
    "unknown": "No question was given, so retrieval quality cannot be judged.",
}


class Diagnosis(NamedTuple):
    relevance: float | None
    question_similarity: float | None
    question_coverage: float | None
    blame: Blame
    message: str


def relevance(sample: Sample, encode: Encoder = models.encode) -> tuple[float, float, float] | None:
    """(score, best question-sentence similarity, question word coverage), or None without a question."""
    if not sample.question:
        return None
    evidence = evidence_for(sample, encode)
    similarity = float((evidence.embeddings @ encode([sample.question])[0]).max()) if evidence.sentences else 0.0
    question_words = content_words(sample.question)
    source_words = content_words(" ".join(d.text for d in sample.documents))
    coverage = len(question_words & source_words) / len(question_words) if question_words else 0.0
    return float(np.mean([max(similarity, 0.0), coverage])), similarity, coverage


def judge(scored: tuple[float, float, float] | None, hallucinated: bool, threshold: float = RELEVANCE_THRESHOLD) -> Diagnosis:
    """Blame from relevance() output and the verdict."""
    if scored is None:
        return Diagnosis(None, None, None, "unknown", MESSAGES["unknown"])
    score, similarity, coverage = scored
    relevant = score >= threshold
    blame: Blame = ("generation" if relevant else "retrieval") if hallucinated else ("none" if relevant else "weak_sources")
    return Diagnosis(score, similarity, coverage, blame, MESSAGES[blame])


def diagnose(sample: Sample, hallucinated: bool, encode: Encoder = models.encode, threshold: float = RELEVANCE_THRESHOLD) -> Diagnosis:
    return judge(relevance(sample, encode), hallucinated, threshold)
