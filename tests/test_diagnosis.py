import hashlib

import numpy as np

from truth_guardian.diagnosis import diagnose, relevance
from truth_guardian.schema import Sample


def fake_encode(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 64))
    for row, text in enumerate(texts):
        for word in text.lower().replace("?", "").replace(".", "").split():
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def make_sample(question: str | None, source: str) -> Sample:
    return Sample.model_validate({
        "id": "x", "question": question, "documents": [{"id": "d", "text": source}], "answer": "Some answer.",
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


RELEVANT = make_sample("When did Anne Frank die?", "Anne Frank died in 1945 in Bergen-Belsen.")
UNRELATED = make_sample("When did Anne Frank die?", "The cafe serves Italian food and offers free parking.")


def test_relevance_is_high_for_matching_sources_and_low_for_unrelated_ones():
    assert relevance(RELEVANT, fake_encode)[0] > 0.3 > relevance(UNRELATED, fake_encode)[0]


def test_blame_follows_relevance_and_hallucination():
    assert diagnose(RELEVANT, True, fake_encode, threshold=0.3).blame == "generation"
    assert diagnose(UNRELATED, True, fake_encode, threshold=0.3).blame == "retrieval"
    assert diagnose(UNRELATED, False, fake_encode, threshold=0.3).blame == "weak_sources"
    assert diagnose(RELEVANT, False, fake_encode, threshold=0.3).blame == "none"


def test_no_question_means_retrieval_cannot_be_judged():
    d = diagnose(make_sample(None, "Some article."), True, fake_encode)
    assert d.blame == "unknown" and d.relevance is None
