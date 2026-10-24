from collections import Counter
from pathlib import Path

import pytest

from truth_guardian.data.challenge_cases import case_of, load, unmark

SPEC = Path(__file__).resolve().parents[1] / "benchmark" / "challenge_cases.json"


def test_unmark_returns_the_marked_ranges():
    text, spans = unmark("It opened in [[1998]] and cost [[5 euros]].")
    assert text == "It opened in 1998 and cost 5 euros."
    assert [text[a:b] for a, b in spans] == ["1998", "5 euros"]
    with pytest.raises(ValueError):
        unmark("It opened in [[1998.")


def test_every_case_has_twenty_items_and_paired_controls():
    samples = load(SPEC)
    assert Counter(case_of(s) for s in samples) == {
        "control": 20, "mixed": 20, "unsupported": 20, "partial": 20, "weak": 20, "weakcontrol": 20, "agent": 20, "agentcontrol": 20,
    }
    assert len({s.id for s in samples}) == len(samples)


def test_labels_match_the_case():
    for s in load(SPEC):
        case = case_of(s)
        if case.endswith("control") or s.labels.category == "partial: omission":
            assert s.labels.response == "grounded" and not s.labels.spans
        else:
            assert s.labels.response == "hallucinated" and s.labels.spans
        if s.labels.category == "partial: omission":
            assert s.labels.reason in " ".join(d.text for d in s.documents)
        if case == "agent":
            answer_step = s.agent_log[-1]
            assert answer_step.kind == "answer" and answer_step.content == s.answer
            assert s.labels.responsible_step in {st.step for st in s.agent_log}
