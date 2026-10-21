"""Hybrid evidence retrieval: BM25 and embedding rankings fused with Reciprocal Rank Fusion."""

import math
from collections import Counter

import numpy as np

from truth_guardian.evidence import Evidence
from truth_guardian.text import tokens

RRF_K = 60


class Bm25:
    """Okapi BM25 over the source sentences of one sample."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(d)) for d in documents]
        self.lengths = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg_length = self.lengths.mean() if len(self.docs) else 0.0
        df = Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        self.idf = {term: math.log((n - f + 0.5) / (f + 0.5) + 1) for term, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        result = np.zeros(len(self.docs))
        norm = self.k1 * (1 - self.b + self.b * self.lengths / max(self.avg_length, 1e-9))
        for term in set(tokens(query)):
            if term not in self.idf:
                continue
            tf = np.array([d[term] for d in self.docs], dtype=float)
            result += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
        return result


def _ranks(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


def rrf_scores(*score_lists: np.ndarray) -> np.ndarray:
    return sum(1.0 / (RRF_K + _ranks(s)) for s in score_lists)


def retrieve(query: str, query_embedding: np.ndarray, evidence: Evidence, bm25: Bm25, k: int) -> list[int]:
    """Indices of the top-k source sentences by fused rank, returned in source order."""
    if not evidence.sentences:
        return []
    fused = rrf_scores(evidence.embeddings @ query_embedding, bm25.scores(query))
    return sorted(np.argsort(-fused, kind="stable")[:k].tolist())
