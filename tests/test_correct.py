from truth_guardian.correct import _format_like, apply, suggest
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def make_sample(answer: str, documents: list[tuple[str, str]]) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "documents": [{"id": i, "text": t} for i, t in documents],
        "answer": answer,
        "meta": {"dataset": "unit", "task": "summary", "split": "dev", "group_id": "g"},
    })


def first_sentence_suggestions(sample: Sample):
    return suggest(sample, split_sentences(sample.answer)[0])


def test_wrong_year_is_replaced_from_matching_source_sentence():
    sample = make_sample(
        "Anne Frank died in 2022 in Bergen-Belsen.",
        [("article", "The museum opened in 1960. Anne Frank died in 1945 in Bergen-Belsen, weeks before liberation.")],
    )
    (s,) = first_sentence_suggestions(sample)
    assert (s.original, s.replacement, s.kind) == ("2022", "1945", "number")
    assert "Bergen-Belsen" in s.evidence
    assert apply(sample.answer, [s]) == "Anne Frank died in 1945 in Bergen-Belsen."


def test_number_with_matching_context_is_preferred():
    sample = make_sample("The cafe has 5 stars from 120 reviews.", [("business", "business_stars: 4.5\nreview_count: 87\nThe cafe has 3 stars on another site.")])
    suggestions = {s.original: s.replacement for s in first_sentence_suggestions(sample)}
    assert suggestions["5"] == "3"


def test_closing_time_keeps_answer_style():
    assert _format_like("10", "21:0") == "9"
    assert _format_like("9:45", "21:30") == "9:30"
    assert _format_like("21:45", "21:30") == "21:30"
    sample = make_sample("It closes at 10 pm on Fridays.", [("business", "hours Friday: 8:0-21:0")])
    (s,) = first_sentence_suggestions(sample)
    assert s.replacement == "9"
    sample = make_sample("It opens at 7 am on Fridays.", [("business", "hours Friday: 8:0-21:0")])
    (s,) = first_sentence_suggestions(sample)
    assert s.replacement == "8"


def test_wrong_person_replaced_by_same_entity_type():
    sample = make_sample(
        "Robert Downey Jr. starred in Zodiac with Tom Hanks.",
        [("k", "Robert Downey Jr. starred in Zodiac with Jake Gyllenhaal.")],
    )
    by_original = {s.original: s for s in first_sentence_suggestions(sample)}
    assert by_original["Tom Hanks"].replacement == "Jake Gyllenhaal"


def test_unspecified_attribute_suggests_removal_with_source_line():
    sample = make_sample("The cafe offers free parking.", [("business", "name: Cafe\nattributes BusinessParking: not specified")])
    (s,) = first_sentence_suggestions(sample)
    assert s.replacement is None and s.kind == "null"
    assert s.evidence == "attributes BusinessParking: not specified"


def test_clean_sentence_has_no_suggestions():
    sample = make_sample("Paris is the capital of France.", [("d", "Paris is the capital of France.")])
    assert first_sentence_suggestions(sample) == []
