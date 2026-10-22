import numpy as np

from truth_guardian.schema import Sample
from truth_guardian.shifts import check_sample
from truth_guardian.text import split_sentences


def sample(answer: str, source: str) -> Sample:
    return Sample.model_validate({
        "id": "x", "documents": [{"id": "d", "text": source}], "answer": answer,
        "meta": {"dataset": "unit", "task": "summary", "split": "dev", "group_id": "g"},
    })


def not_entailed(pairs):
    return np.tile([0.1, 0.2, 0.7], (len(pairs), 1))


def run(answer: str, source: str):
    s = sample(answer, source)
    (check,) = check_sample(s, split_sentences(s.answer), not_entailed)
    return check, [s.answer[a:b] for a, b in check.spans]


def test_swapped_roles_are_caught_in_active_and_passive_voice():
    check, words = run("Brazil defeated Germany in the semi-final.", "Germany defeated Brazil in the semi-final.")
    assert check.kind == "role_swap" and check.confirmed and words == ["Brazil", "Germany"]
    check, _ = run("Germany was defeated by Brazil in the semi-final.", "Germany defeated Brazil in the semi-final.")
    assert check.kind == "role_swap"


def test_same_roles_in_passive_voice_and_symmetric_verbs_are_fine():
    assert run("Brazil was defeated by Germany in the semi-final.", "Germany defeated Brazil in the semi-final.")[0].kind is None
    assert run("Obama met Merkel in Berlin on Monday.", "Merkel met Obama in Berlin on Monday.")[0].kind is None


def test_stronger_quantifier_is_caught():
    check, words = run("All residents of the town were evacuated on Monday.", "Some residents of the town were evacuated on Monday.")
    assert check.kind == "quantifier" and words == ["All"] and check.detail == 'the source says "some", the answer "all"'
    assert run("Some residents of the town were evacuated on Monday.", "All residents of the town were evacuated on Monday.")[0].kind is None


def test_dropped_hedge_is_caught_and_kept_hedge_is_fine():
    check, words = run("Drinking coffee reduces the risk of diabetes.", "Drinking coffee may reduce the risk of diabetes.")
    assert check.kind == "certainty" and words == ["reduces"]
    check, words = run("Drinking coffee will reduce the risk of diabetes.", "Drinking coffee may reduce the risk of diabetes.")
    assert check.kind == "certainty" and words == ["will"]
    assert run("Drinking coffee might reduce the risk of diabetes.", "Drinking coffee may reduce the risk of diabetes.")[0].kind is None


def test_literal_senses_are_not_hedges():
    assert run("Biden spoke before the Senate on Tuesday about aid.", "Biden appeared before the Senate on Tuesday about aid.")[0].kind is None
    assert run("Apply an ice pack quickly to reduce swelling.", "Apply an ice pack as soon as possible to reduce swelling.")[0].kind is None


def test_only_role_swaps_override_the_verdict():
    assert run("Brazil defeated Germany in the semi-final.", "Germany defeated Brazil in the semi-final.")[0].overrides
    assert not run("All residents of the town were evacuated on Monday.", "Some residents of the town were evacuated on Monday.")[0].overrides


def test_entailed_candidate_is_not_confirmed():
    s = sample("All residents of the town were evacuated on Monday.", "Some residents of the town were evacuated on Monday.")
    (check,) = check_sample(s, split_sentences(s.answer), lambda pairs: np.tile([0.0, 0.9, 0.1], (len(pairs), 1)))
    assert check.candidate and not check.confirmed
