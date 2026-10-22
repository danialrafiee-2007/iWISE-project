import random

import pytest

from truth_guardian.perturb import KINDS, perturb
from truth_guardian.schema import Sample

SOURCE = "Anne Frank died in 1945 in Bergen-Belsen. The museum is open and attendance increased. Otto Frank thanked Miep Gies. Some visitors may return."
ANSWER = "Anne Frank died in 1945 in Bergen-Belsen. The museum is open, and attendance increased. Otto Frank thanked Miep Gies. Some visitors may return."


def base() -> Sample:
    return Sample.model_validate({
        "id": "b1",
        "documents": [{"id": "d", "text": SOURCE}],
        "answer": ANSWER,
        "labels": {"response": "grounded"},
        "meta": {"dataset": "ragtruth", "task": "summary", "split": "dev", "group_id": "g1"},
    })


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_produces_a_valid_hallucinated_sample(kind):
    pool = {"PERSON": ["Marie Curie"], "GPE": ["Paris"], "ORG": [], "NORP": [], "LOC": []}
    result = perturb(base(), kind, random.Random(0), pool)
    assert result is not None
    (span,) = result.labels.spans
    assert result.labels.response == "hallucinated" and result.answer[span.start : span.end] == span.text
    assert result.id == f"perturb-{kind}-b1" and result.meta.synthetic and result.meta.group_id == "g1"
    assert span.note.startswith("Original: ") and span.source_label == f"perturb:{kind}"
    assert result.answer != ANSWER


def test_number_edit_avoids_numbers_in_the_source():
    result = perturb(base(), "number", random.Random(1))
    assert result.labels.spans[0].note == "Original: 1945"
    assert result.labels.spans[0].text not in SOURCE


def test_negation_and_antonym_change_meaning():
    negated = perturb(base(), "negation", random.Random(0))
    assert " not" in negated.answer
    flipped = perturb(base(), "antonym", random.Random(0))
    assert any(w in flipped.answer for w in ("closed", "decreased"))


def test_inapplicable_edit_returns_none():
    sample = base().model_copy(update={"answer": "Nothing to see here"})
    assert perturb(sample, "number", random.Random(0)) is None
    assert perturb(sample, "entity", random.Random(0), {}) is None


def test_edits_are_deterministic_for_a_seed():
    first = perturb(base(), "addition", random.Random(7))
    assert first.answer == perturb(base(), "addition", random.Random(7)).answer


def test_meaning_shift_edits():
    swapped = perturb(base(), "role_swap", random.Random(0))
    assert "Miep Gies thanked Otto Frank" in swapped.answer
    assert "All visitors" in perturb(base(), "quantifier", random.Random(0)).answer
    assert "will return" in perturb(base(), "certainty", random.Random(0)).answer
