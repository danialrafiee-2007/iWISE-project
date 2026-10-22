from truth_guardian.citations import check_sample, cite, cited_documents
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def sample(answer: str) -> Sample:
    return Sample.model_validate({
        "id": "x", "answer": answer, "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
        "documents": [{"id": "passage1", "text": "Ghee keeps for months without a fridge."}, {"id": "passage2", "text": "Anne Frank died in 1945 in Bergen-Belsen."}],
    })


def word_overlap(pairs):
    return [len(set(p.lower().split()) & set(h.lower().split())) / max(len(h.split()), 1) for p, h in pairs]


def test_citation_forms_are_parsed():
    assert cited_documents("It lasts long (Passages 1 & 2).", 3) == [1, 2]
    assert cited_documents("According to Passage 3, yes.", 3) == [3]
    assert cited_documents("It is true [2].", 3) == [2]
    assert cited_documents("See Passage 7.", 3) == []


def test_wrong_citation_is_caught_and_right_one_passes():
    wrong = sample("Anne Frank died in 1945 in Bergen-Belsen (Passage 1).")
    (check,) = check_sample(wrong, split_sentences(wrong.answer), word_overlap)
    assert check.wrong and check.cited == [1] and check.best_other == 2
    right = sample("Anne Frank died in 1945 in Bergen-Belsen (Passage 2).")
    (check,) = check_sample(right, split_sentences(right.answer), word_overlap)
    assert not check.wrong


def test_sentences_without_citations_are_skipped():
    s = sample("Anne Frank died in 1945.")
    assert check_sample(s, split_sentences(s.answer), word_overlap) == [None]


def test_cite_adds_markers_before_the_full_stop():
    assert cite("Ghee keeps. Frank died.", [(0, 11, 1), (12, 23, 2)]) == "Ghee keeps [1]. Frank died [2]."
