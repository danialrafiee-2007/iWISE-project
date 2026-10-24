import numpy as np

from truth_guardian.conflicts import contested, find_conflicts
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def sample(*documents: str, answer: str = "x") -> Sample:
    return Sample.model_validate({
        "id": "x", "documents": [{"id": f"p{i}", "text": t} for i, t in enumerate(documents, 1)], "answer": answer,
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def contradiction(pairs):
    return np.tile([0.9, 0.05, 0.05], (len(pairs), 1))


def test_documents_disagreeing_on_one_number_conflict_and_the_answer_is_contested():
    s = sample("The Eiffel Tower is 324 metres tall, including its antennas.", "The Eiffel Tower is 300 metres tall, including its antennas.",
               answer="The Eiffel Tower is 300 metres tall.")
    (conflict,) = find_conflicts(s, contradiction)
    assert {conflict.first_value, conflict.second_value} == {"324", "300"}
    found, document = contested(split_sentences(s.answer)[0], [conflict])
    assert found == conflict and document == "p2"


def test_documents_disagreeing_on_a_name_conflict():
    s = sample("The chief executive of Acme is John Smith, the company said on Monday.", "The chief executive of Acme is Jane Doe, the company said on Monday.")
    (conflict,) = find_conflicts(s, contradiction)
    assert {conflict.first_value, conflict.second_value} == {"John Smith", "Jane Doe"}


def test_different_contexts_and_one_document_are_not_conflicts():
    assert find_conflicts(sample("In 2019 the ticket price was 5 dollars at the main shop.", "In 2020 the ticket price was 6 dollars at the main shop."), contradiction) == []
    assert find_conflicts(sample("The tower is 324 metres tall, including its antennas. The tower is 300 metres tall, including its antennas."), contradiction) == []


def test_nli_must_confirm():
    s = sample("The Eiffel Tower is 324 metres tall, including its antennas.", "The Eiffel Tower is 300 metres tall, including its antennas.")
    assert find_conflicts(s, lambda pairs: np.tile([0.1, 0.1, 0.8], (len(pairs), 1))) == []


def test_parts_of_one_uploaded_file_are_one_document():
    s = sample("The Eiffel Tower is 324 metres tall, including its antennas.", "The Eiffel Tower is 300 metres tall, including its antennas.")
    parts = s.model_copy(update={"documents": [d.model_copy(update={"origin": "guide.pdf"}) for d in s.documents]})
    assert find_conflicts(parts, contradiction) == []


def test_nli_sees_at_most_the_closest_candidate_pairs():
    from truth_guardian import conflicts

    seen = []
    first = " ".join(f"The museum holds exactly {i} paintings on the east wall today." for i in range(30))
    second = " ".join(f"The museum holds exactly {i + 100} paintings on the east wall today." for i in range(30))

    def count(pairs):
        seen.append(len(pairs))
        return np.tile([0.1, 0.8, 0.1], (len(pairs), 1))

    original = conflicts.MAX_CANDIDATES
    conflicts.MAX_CANDIDATES = 50
    try:
        find_conflicts(sample(first, second), count)
    finally:
        conflicts.MAX_CANDIDATES = original
    assert seen == [50]
