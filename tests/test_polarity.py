import numpy as np

from truth_guardian.models import NLI_LABELS
from truth_guardian.polarity import antonyms, check_sample
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def fake_nli(contradiction: float):
    def classify(pairs):
        probs = np.zeros((len(pairs), len(NLI_LABELS)))
        probs[:, NLI_LABELS.index("contradiction")] = contradiction
        return probs

    return classify


def make_sample(answer: str, source: str) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "documents": [{"id": "d", "text": source}],
        "answer": answer,
        "meta": {"dataset": "unit", "task": "summary", "split": "dev", "group_id": "g"},
    })


def first(sample: Sample, contradiction: float = 0.9):
    return check_sample(sample, split_sentences(sample.answer), classify=fake_nli(contradiction))[0]


def test_wordnet_antonyms_are_general():
    assert "decrease" in antonyms("increased")
    assert "expensive" in antonyms("cheap")


def test_negation_added_to_a_matching_statement_is_flagged():
    sample = make_sample("The police were not notified of the alarm.", "The police were notified of the alarm at 3 am.")
    result = first(sample)
    assert result.negation_mismatch
    assert [sample.answer[a:b] for a, b in result.negation_spans] == ["not"]


def test_contraction_counts_as_negation():
    assert first(make_sample("The museum isn't open on Mondays.", "The museum is open on Mondays.")).negation_mismatch


def test_antonym_against_the_source_is_flagged_with_its_span():
    sample = make_sample("Ticket sales decreased sharply last year.", "Ticket sales increased sharply last year.")
    result = first(sample)
    assert [sample.answer[a:b] for a, b in result.antonym_spans] == ["decreased"]


def test_same_polarity_is_clean():
    result = first(make_sample("The police were notified of the alarm.", "The police were notified of the alarm at 3 am."))
    assert not result.negation_mismatch and result.antonym_spans == []


def test_unrelated_sentence_is_not_compared():
    result = first(make_sample("Bananas are not blue.", "The police were notified of the alarm."))
    assert not result.negation_mismatch and result.overlap == 0.0


def test_matching_restatement_elsewhere_in_the_source_wins():
    source = "Fold the longer end of the bow tie horizontally. Then fold the shorter end of the bow tie horizontally."
    assert not first(make_sample("Fold the shorter end of the bow tie horizontally.", source)).candidate


def test_candidate_needs_nli_confirmation():
    sample = make_sample("The police were not notified of the alarm.", "The police were notified of the alarm at 3 am.")
    assert first(sample, contradiction=0.9).confirmed
    weak = first(sample, contradiction=0.2)
    assert weak.candidate and not weak.confirmed
