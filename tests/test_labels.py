from truth_guardian.labels import sentence_labels, sentence_types
from truth_guardian.schema import HallucinationType, Sample
from truth_guardian.text import split_sentences

ANSWER = "The cafe is in Paris. It opened in 1990. It has 3 floors."


def make_sample(spans: list[dict]) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "documents": [{"id": "d", "text": "doc"}],
        "answer": ANSWER,
        "labels": {"response": "hallucinated" if spans else "grounded", "spans": spans},
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def span(text: str, type_: str) -> dict:
    start = ANSWER.index(text)
    return {"start": start, "end": start + len(text), "text": text, "type": type_}


def test_sentence_overlapping_a_span_is_positive():
    sample = make_sample([span("1990", "contradicted")])
    assert sentence_labels(sample, split_sentences(ANSWER)) == [0, 1, 0]


def test_span_crossing_sentences_marks_both():
    sample = make_sample([span("1990. It has", "unsupported")])
    assert sentence_labels(sample, split_sentences(ANSWER)) == [0, 1, 1]


def test_grounded_sample_has_no_positive_sentences():
    assert sentence_labels(make_sample([]), split_sentences(ANSWER)) == [0, 0, 0]


def test_contradiction_wins_over_unsupported():
    sample = make_sample([span("opened", "unsupported"), span("1990", "contradicted")])
    types = sentence_types(sample, split_sentences(ANSWER))
    assert types == [None, HallucinationType.CONTRADICTED, None]
