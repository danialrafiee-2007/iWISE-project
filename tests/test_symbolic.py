from truth_guardian.schema import Sample
from truth_guardian.symbolic import check_sample, normalize_number
from truth_guardian.text import split_sentences


def make_sample(answer: str, documents: list[tuple[str, str]], question: str | None = None) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "question": question,
        "documents": [{"id": i, "text": t} for i, t in documents],
        "answer": answer,
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def check(sample: Sample):
    return check_sample(sample, split_sentences(sample.answer))


def test_normalize_number_forms():
    assert normalize_number("2,000") == {"2000"}
    assert normalize_number("4.50") == {"4.5"}
    assert normalize_number("21:0") == {"21:00", "21", "9:00", "9"}
    assert normalize_number("16:30") == {"16:30", "4:30"}


def test_changed_year_is_flagged_with_exact_span():
    sample = make_sample("The camp was liberated in 2022.", [("article", "The camp was liberated in 1945.")])
    (result,) = check(sample)
    assert (result.numbers, result.numbers_unmatched) == (1, 1)
    assert [sample.answer[a:b] for a, b in result.spans] == ["2022"]


def test_twelve_hour_time_matches_24_hour_source():
    sample = make_sample("It opens at 4:30 PM and closes at 9 PM.", [("business", "hours Tuesday: 16:30-21:0")])
    (result,) = check(sample)
    assert result.numbers == 2 and result.numbers_unmatched == 0


def test_list_markers_are_ignored():
    sample = make_sample("1. The cafe is in Paris.", [("d", "The cafe is in Paris.")])
    assert all(r.numbers_unmatched == 0 for r in check(sample))


def test_citations_and_word_counts_are_not_claims():
    sample = make_sample(
        "Here is a summary in 85 words: the cafe is in Paris (Passage 2, Passage 3).",
        [("d", "The cafe is in Paris.")],
    )
    assert all(r.numbers == 0 for r in check(sample))


def test_state_and_street_abbreviations_match():
    sample = make_sample("It is at 12 Coast Village Road in Santa Barbara, California.", [("business", "address: 12 Coast Village Rd\ncity: Santa Barbara\nstate: CA")])
    (result,) = check(sample)
    assert result.spans == []


def test_generic_date_phrases_are_skipped_but_weekdays_checked():
    sample = make_sample("It is open every day of the week, except Mondays.", [("business", "hours Tuesday: 9:00-17:00")])
    (result,) = check(sample)
    assert [sample.answer[a:b] for a, b in result.spans] == ["Mondays"]


def test_unknown_person_is_flagged():
    sample = make_sample("Robert Downey Jr. starred in Zodiac with Tom Hanks.", [("k", "Robert Downey Jr. starred in Zodiac with Jake Gyllenhaal.")])
    (result,) = check(sample)
    assert result.entities_unmatched >= 1
    assert "Tom Hanks" in [sample.answer[a:b] for a, b in result.spans]


def test_null_attribute_mention_flagged_unless_reviews_cover_it():
    business = ("business", "name: Cafe\nattributes BusinessParking: not specified\nattributes WiFi: not specified")
    flagged = make_sample("The cafe offers free parking.", [business])
    assert check(flagged)[0].null_mentions == 1
    covered = make_sample("The cafe offers free parking.", [business, ("review1", "Review 1 (5 stars, 2022): Easy parking nearby.")])
    assert check(covered)[0].null_mentions == 0


def test_supported_sentence_is_clean():
    sample = make_sample("Paris is the capital of France.", [("d", "Paris is the capital of France.")])
    (result,) = check(sample)
    assert result.spans == [] and result.numbers_unmatched == result.entities_unmatched == result.null_mentions == 0


def spans_of(answer: str, source: str, question: str | None = None) -> list[str]:
    sample = make_sample(answer, [("d", source)], question)
    return [sample.answer[a:b] for r in check(sample) for a, b in r.spans]


def test_surface_variants_are_not_flagged():
    assert spans_of("Three people and 2 dogs were rescued.", "Three people and two dogs were rescued.") == []
    assert spans_of("It was the 21st meeting.", "It was the twenty-first meeting.") == []
    assert spans_of("The city has 1,500,000 residents.", "The city has 1.5 million residents.") == []
    assert spans_of("The UN Security Council met.", "The United Nations Security Council met.") == []
    assert spans_of("Officials in the United States agreed.", "U.S. officials agreed.") == []
    assert spans_of("Mexican officials and French police met.", "Officials from Mexico met police in France.") == []
    assert spans_of("The café offers Wi-Fi.", "The cafe offers WiFi.") == []
    assert spans_of("Set it to 350 Fahrenheit.", "Bake at 350 F.") == []
    assert spans_of("A review from January 2015 praised it.", "date: 2015-01-12, stars: 5, text: Great.") == []
    assert spans_of("Kossuth High School's team won.", "The Kossuth High School team won.") == []


def test_references_are_not_claims():
    assert spans_of("Repeat steps 1-3 as described in Passage 1.", "Mix the flour.") == []


def test_race_time_is_one_number():
    assert spans_of("He finished in 1:39.87.", "He finished in 1:39.87.") == []
    assert spans_of("He finished in 1:41.20.", "He finished in 1:39.87.") == ["1:41.20"]


def test_real_mismatches_still_flagged():
    assert spans_of("Four people were rescued.", "Three people were rescued.") == []
    assert spans_of("The city has 2,500,000 residents.", "The city has 1.5 million residents.") == ["2,500,000"]
    assert spans_of("German officials agreed.", "French officials agreed.") == ["German"]
