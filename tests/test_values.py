import numpy as np
import pytest

from test_report_and_pipeline import SIGNAL_FNS, fake_encode, trained_model
from truth_guardian.models import NLI_LABELS
from truth_guardian.pipeline import analyze, make_sample
from truth_guardian.text import split_sentences
from truth_guardian.values import check_sample, decide, fixes, measure, values

SOURCE = "Paris has 2.1 million people, and Lyon has 520,000 people."


def fake_nli(entailed: set[str]):
    """Entails the hypotheses named, contradicts every other."""
    def classify(pairs):
        probs = np.zeros((len(pairs), len(NLI_LABELS)))
        for row, (_, hypothesis) in enumerate(pairs):
            probs[row, NLI_LABELS.index("entailment" if hypothesis in entailed else "contradiction")] = 0.99
        return probs

    return classify


def never(pairs):
    raise AssertionError("NLI should not be asked")


def first(answer: str, sources: list[str], classify):
    sample = make_sample(answer, sources)
    return check_sample(sample, split_sentences(sample.answer), classify=classify)[0]


def test_values_keep_their_scale_word_and_kind():
    found = {v.text: v.kind for v in values("In 1903 it earned $5 million, 45% of 2.1 million sales, at 10:30.")}
    assert found == {"1903": "year", "5 million": "money", "45": "percent", "2.1 million": "amount", "10:30": "time"}


def test_a_value_of_the_sources_on_the_wrong_subject_is_found_with_the_right_one():
    answer = "Lyon has 2.1 million people."
    check = first(answer, [SOURCE], fake_nli({"Lyon has 520,000 people."}))
    assert check.confirmed and answer[slice(*check.span)] == "2.1 million"
    assert (check.replacement, check.evidence) == ("520,000", SOURCE)


def test_a_right_value_is_left_alone():
    assert not first("Lyon has 520,000 people.", [SOURCE], fake_nli({"Lyon has 520,000 people."})).confirmed


def test_a_value_the_sources_lack_is_left_to_the_symbolic_check():
    check = first("Lyon has 700,000 people.", [SOURCE], never)
    assert not check.confirmed and check.tries == 0


def test_only_values_of_the_same_kind_are_tried():
    check = first("The shop opened in 1990.", ["The shop opened in 1990 and has 1,200 staff."], never)
    assert check.tries == 0


def test_a_sentence_without_any_try_needs_no_model_even_when_its_value_is_in_the_sources():
    check = first("With a 4.5-star rating, this eatery is a great choice.", ["business_stars: 4.5"], never)
    assert not check.confirmed


def test_a_value_supported_by_another_source_sentence_is_not_a_finding():
    sources = ["The Nile is 6,650 km long. The Amazon is 6,400 km long.", "Some measure the Amazon at 6,650 km."]
    check = first("The Amazon is 6,650 km long.", sources, fake_nli({"The Amazon is 6,400 km long.", "The Amazon is 6,650 km long."}))
    assert not check.confirmed


def test_a_confirmed_value_swap_is_contradicted_with_its_fix_and_evidence():
    def swapped(sample, sentences):
        return [{"val_tries": 1, "val_confirmed": 1, "val_contradiction": 0.97, "val_entailment": 0.99, "val_spans": [[9, 20]],
                 "val_original": "2.1 million", "val_replacement": "520,000", "val_evidence": SOURCE} for _ in sentences]

    report = analyze(make_sample("Lyon has 2.1 million people.", [SOURCE]), trained_model(), use_polarity=False,
                     signal_fns={**SIGNAL_FNS, "values": swapped}, encode=fake_encode)
    (claim,) = report.claims
    assert claim.status == "contradicted" and claim.risk == pytest.approx(0.97) and "wrong subject" in claim.explanation
    assert claim.evidence.text == SOURCE and [(f.original, f.replacement) for f in claim.fixes] == [("2.1 million", "520,000")]


def test_without_an_entailed_value_the_contrast_finds_the_swap_but_proposes_no_fix():
    def classify(pairs):
        probs = np.zeros((len(pairs), len(NLI_LABELS)))
        for row, (_, hypothesis) in enumerate(pairs):
            probs[row, NLI_LABELS.index("contradiction" if "2.1 million" in hypothesis else "neutral")] = 0.99
        return probs

    sample = make_sample("Lyon has 2.1 million people.", [SOURCE])
    sentences = split_sentences(sample.answer)
    (measured,) = measure(sample, sentences, classify)
    assert not decide(sentences[0], measured, contrast=None).confirmed
    check = decide(sentences[0], measured, contrast=0.05)
    assert check.confirmed and check.replacement == ""
    row = {"val_confirmed": 1, "val_spans": [list(check.span)], "val_original": check.original, "val_replacement": check.replacement,
           "val_evidence": check.evidence, "val_entailment": check.entailment}
    (fix,) = fixes(row)
    assert fix.replacement is None and fix.original == "2.1 million"
