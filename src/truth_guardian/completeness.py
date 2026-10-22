"""Omission check: which key evidence did the answer leave out?

Key evidence = the source sentences most relevant to the question (embedding similarity fused with BM25).
A key sentence counts as covered when some answer sentence is close to it in meaning, or repeats most of its
content words. Uncovered key sentences are reported, and those carrying a caveat ("however", "except",
"only if", "not") are singled out, since dropping a condition can change what the answer means.
Only questions are checked: without one, "key" evidence is undefined.
"""

import re
from typing import NamedTuple

import numpy as np

from truth_guardian import models
from truth_guardian.evidence import Encoder, evidence_for
from truth_guardian.retrieval import Bm25, rrf_scores
from truth_guardian.schema import Sample
from truth_guardian.text import content_words, split_sentences

KEY_SENTENCES = 3
COVER_SIMILARITY = 0.75
COVER_WORDS = 0.7
CAVEAT = re.compile(r"\b(however|but|except|unless|only if|although|though|not|never|avoid|warning|caution|instead)\b", re.IGNORECASE)


class Completeness(NamedTuple):
    score: float | None
    key_evidence: list[str]
    missing: list[str]
    omitted_caveats: list[str]


def key_evidence(sample: Sample, encode: Encoder, k: int = KEY_SENTENCES) -> tuple[list[str], np.ndarray]:
    evidence = evidence_for(sample, encode)
    if not evidence.sentences or not sample.question:
        return [], np.zeros((0, 0))
    fused = rrf_scores(evidence.embeddings @ encode([sample.question])[0], Bm25(evidence.sentences).scores(sample.question))
    top = np.argsort(-fused, kind="stable")[:k]
    return [evidence.sentences[i] for i in top], evidence.embeddings[top]


class Coverage(NamedTuple):
    keys: list[str]
    similarity: np.ndarray
    words: np.ndarray


def coverage(sample: Sample, encode: Encoder = models.encode) -> Coverage | None:
    """Per key sentence: best similarity to an answer sentence, and the share of its content words the answer repeats."""
    if not sample.question:
        return None
    keys, key_embeddings = key_evidence(sample, encode)
    answer_sentences = [s.text for s in split_sentences(sample.answer)]
    if not keys or not answer_sentences:
        return Coverage(keys, np.zeros(0), np.zeros(0))
    answer_words = content_words(sample.answer)
    word_cover = [len(content_words(k) & answer_words) / len(content_words(k)) if content_words(k) else 1.0 for k in keys]
    return Coverage(keys, (key_embeddings @ encode(answer_sentences).T).max(axis=1), np.array(word_cover))


def judge(c: Coverage | None, similarity: float, words: float) -> Completeness:
    if c is None:
        return Completeness(None, [], [], [])
    if not len(c.similarity):
        return Completeness(None, c.keys, [], [])
    covered = (c.similarity >= similarity) | (c.words >= words)
    missing = [k for k, ok in zip(c.keys, covered) if not ok]
    return Completeness(float(covered.mean()), c.keys, missing, [m for m in missing if CAVEAT.search(m)])


def check(sample: Sample, encode: Encoder = models.encode) -> Completeness:
    return judge(coverage(sample, encode), COVER_SIMILARITY, COVER_WORDS)
