import pytest

from truth_guardian.schema import Sample
from truth_guardian.signals import SIGNALS, lexical, spans_per_sentence, symbolic
from truth_guardian.text import Sentence, split_sentences


def make_sample(answer: str, document: str) -> Sample:
    return Sample.model_validate({
        "id": "x",
        "documents": [{"id": "d", "text": document}],
        "answer": answer,
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def test_spans_per_sentence_coverage_and_confidence():
    sentences = [Sentence(0, 10, "a" * 10), Sentence(11, 21, "b" * 10)]
    rows = spans_per_sentence([{"start": 5, "end": 15, "confidence": 0.8}], sentences)
    assert rows[0] == {"cover": 0.5, "max_confidence": 0.8}
    assert rows[1] == {"cover": pytest.approx(0.4), "max_confidence": 0.8}


def test_spans_per_sentence_without_spans():
    assert spans_per_sentence([], [Sentence(0, 4, "abcd")]) == [{"cover": 0.0, "max_confidence": 0.0}]


def test_cheap_signals_align_with_sentences():
    sample = make_sample("The cafe is in Paris. It opened in 2022.", "The cafe is in Paris. It opened in 1945.")
    sentences = split_sentences(sample.answer)
    lex = lexical(sample, sentences)
    sym = symbolic(sample, sentences)
    assert len(lex) == len(sym) == 2
    assert lex[0]["lex_unsupported"] == 0.0 and lex[1]["lex_unsupported"] > 0
    assert sym[1]["sym_numbers_unmatched"] == 1 and sym[1]["sym_spans"] == [[35, 39]]


def test_every_signal_has_a_version():
    assert all(version for version, _ in SIGNALS.values())
