import numpy as np

from truth_guardian.evidence import Evidence
from truth_guardian.retrieval import Bm25, retrieve, rrf_scores

SENTENCES = ["The cafe opened in 1945.", "It serves Italian food.", "Parking is free on weekends."]


def test_bm25_prefers_sentence_with_rare_query_terms():
    scores = Bm25(SENTENCES).scores("When did the cafe open in 1945?")
    assert int(np.argmax(scores)) == 0
    assert scores[2] == 0.0


def test_bm25_unknown_terms_score_zero():
    assert Bm25(SENTENCES).scores("zebra").tolist() == [0.0, 0.0, 0.0]


def test_rrf_rewards_agreement_between_rankings():
    fused = rrf_scores(np.array([0.9, 0.5, 0.1]), np.array([3.0, 0.0, 2.0]))
    assert int(np.argmax(fused)) == 0


def test_retrieve_returns_top_k_in_source_order():
    evidence = Evidence(SENTENCES, np.eye(3))
    query_embedding = np.array([0.2, 0.0, 1.0])
    assert retrieve("free parking in 1945", query_embedding, evidence, Bm25(SENTENCES), k=2) == [0, 2]


def test_retrieve_without_evidence():
    assert retrieve("q", np.zeros(3), Evidence([], np.zeros((0, 0))), Bm25([]), k=3) == []
