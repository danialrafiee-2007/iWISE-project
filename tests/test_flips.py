import numpy as np

from truth_guardian import flips
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences


def sample(answer: str) -> Sample:
    return Sample.model_validate({
        "id": "x", "documents": [{"id": "d", "text": "The supplement may reduce anxiety, the authors said."}], "answer": answer,
        "meta": {"dataset": "unit", "task": "summary", "split": "dev", "group_id": "g"},
    })


def entailed_when(supported: set[str]):
    """A stand-in NLI: entailment 0.95 for hypotheses in `supported`, 0.05 otherwise."""
    def classify(pairs):
        return np.array([[0.05, 0.95, 0.0] if hypothesis in supported else [0.6, 0.05, 0.35] for _, hypothesis in pairs])
    return classify


def run(answer: str, supported: set[str]):
    s = sample(answer)
    sentences = split_sentences(s.answer)
    return flips.check_sample(s, sentences, ["evidence"] * len(sentences), entailed_when(supported)), s


def test_candidates_turn_words_around_in_their_form():
    (sentence,) = split_sentences("Prices fell, the team won, and most guests will return.")
    found = {(f.kind, f.word, f.replacement) for f in flips.candidates(sentence, flips.KINDS)}
    assert {("antonym", "fell", "rose"), ("antonym", "won", "lost"), ("quantifier", "most", "some"), ("certainty", "will", "may")} <= found
    assert {f.kind for f in flips.candidates(sentence)} == set(flips.ACTIVE)


def test_more_certainty_than_the_sources_is_confirmed_when_the_hedged_flip_is_entailed():
    (check,), s = run("The supplement will reduce anxiety.", {"The supplement may reduce anxiety."})
    assert check.kind == "certainty" and check.confirmed and [s.answer[a:b] for a, b in check.spans] == ["will"]


def test_nothing_is_confirmed_when_the_original_is_already_entailed():
    (check,), _ = run("The supplement will reduce anxiety.", {"The supplement will reduce anxiety.", "The supplement may reduce anxiety."})
    assert not check.confirmed


def test_sentences_without_evidence_are_skipped():
    s = sample("The supplement will reduce anxiety.")
    sentences = split_sentences(s.answer)
    (check,) = flips.check_sample(s, sentences, [""], entailed_when(set()))
    assert check.kind is None
