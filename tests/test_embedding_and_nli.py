import hashlib

import numpy as np
import pytest

from truth_guardian.baselines import embedding, nli
from truth_guardian.evidence import Evidence
from truth_guardian.models import NLI_LABELS, canonical_columns
from truth_guardian.schema import Sample


def fake_encode(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-words vectors, unit length."""
    vectors = np.zeros((len(texts), 64))
    for row, text in enumerate(texts):
        for word in text.lower().strip(".").split():
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def make_sample(answer: str, documents: list[str]) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "documents": [{"id": f"d{i}", "text": t} for i, t in enumerate(documents)],
        "answer": answer,
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def test_embedding_scores_from_best_match():
    sims = np.array([[1.0, 0.2], [0.0, -1.0]])
    assert embedding.sentence_scores(sims).tolist() == [0.0, 0.5]
    assert embedding.sentence_scores(np.zeros((2, 0))).tolist() == [1.0, 1.0]


def test_embedding_predict_flags_unrelated_sentence():
    sample = make_sample("The cafe is in Paris. Dogs bark loudly.", ["The cafe is in Paris."])
    prediction = embedding.predict(sample, encode=fake_encode)
    first, second = prediction.sentences
    assert first.score == pytest.approx(0.0, abs=1e-9)
    assert second.score > first.score
    assert prediction.score == second.score


def test_build_premise_keeps_source_order():
    evidence = Evidence(["a", "b", "c"], np.eye(3))
    assert nli.build_premise(np.array([0.1, 0.0, 0.9]), evidence, k=2) == "a c"


def test_nli_predict_uses_one_minus_entailment():
    def classify(pairs):
        probs = np.zeros((len(pairs), len(NLI_LABELS)))
        probs[:, nli.ENTAILMENT] = [0.9, 0.2]
        return probs

    sample = make_sample("The cafe is in Paris. It opened in 1990.", ["The cafe is in Paris.", "It has a garden."])
    prediction = nli.predict(sample, encode=fake_encode, classify=classify)
    assert [s.score for s in prediction.sentences] == pytest.approx([0.1, 0.8])
    assert prediction.score == pytest.approx(0.8)


def test_nli_without_evidence_flags_everything():
    sample = make_sample("Something happened.", ["..."])
    assert nli.predict(sample, encode=fake_encode, classify=None).score == 1.0


def test_canonical_columns_handles_other_label_orders():
    assert canonical_columns({0: "entailment", 1: "neutral", 2: "contradiction"}) == [2, 0, 1]
    assert canonical_columns({0: "contradiction", 1: "entailment", 2: "neutral"}) == [0, 1, 2]
