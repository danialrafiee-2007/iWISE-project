import pytest

from truth_guardian.baselines.lexical import predict, sentence_score
from truth_guardian.schema import Sample
from truth_guardian.text import content_words, split_sentences


def test_split_sentences_keeps_offsets_across_lines():
    text = "name: Cafe\nwifi: yes\n\nDr. Lee came in 2020. He left."
    sentences = split_sentences(text)
    assert [s.text for s in sentences] == ["name: Cafe", "wifi: yes", "Dr. Lee came in 2020.", "He left."]
    assert all(text[s.start : s.end] == s.text for s in sentences)


def test_content_words_drop_stop_words():
    assert content_words("The cafe is in Paris") == {"cafe", "paris"}


def test_sentence_score_counts_unseen_words():
    assert sentence_score("The cafe opened in 1990", {"cafe", "opened"}) == pytest.approx(1 / 3)
    assert sentence_score("It is.", set()) == 0.0


def test_predict_flags_unsupported_sentence():
    sample = Sample.model_validate({
        "id": "x",
        "question": "Where is the cafe?",
        "documents": [{"id": "d", "text": "The cafe is in Paris."}],
        "answer": "The cafe is in Paris. It won a Michelin star.",
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })
    prediction = predict(sample)
    first, second = prediction.sentences
    assert first.score == 0.0 and second.score == 1.0
    assert prediction.score == 1.0
    assert sample.answer[second.start : second.end] == "It won a Michelin star."
