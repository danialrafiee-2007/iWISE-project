import hashlib

import numpy as np

from truth_guardian.completeness import check
from truth_guardian.schema import Sample

SOURCE = (
    "Ghee is made by simmering butter until the milk solids separate. "
    "However, the solids burn quickly if the heat is too high. "
    "Ghee keeps for months without refrigeration."
)


def fake_encode(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 64))
    for row, text in enumerate(texts):
        for word in text.lower().replace(".", "").replace(",", "").replace("?", "").split():
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def make_sample(answer: str, question: str | None = "How is ghee made and what can go wrong with the heat?") -> Sample:
    return Sample.model_validate({
        "id": "x", "question": question, "documents": [{"id": "d", "text": SOURCE}], "answer": answer,
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def test_complete_answer_covers_key_evidence():
    result = check(make_sample("Ghee is made by simmering butter until the milk solids separate. The solids burn quickly if the heat is too high."), fake_encode)
    assert result.score >= 2 / 3 and not result.omitted_caveats


def test_dropped_caveat_is_reported():
    result = check(make_sample("Ghee is made by simmering butter until the milk solids separate."), fake_encode)
    assert result.score < 1.0
    assert result.omitted_caveats == ["However, the solids burn quickly if the heat is too high."]


def test_without_a_question_completeness_is_not_judged():
    assert check(make_sample("Anything.", question=None), fake_encode).score is None
