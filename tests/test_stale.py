import numpy as np

from truth_guardian import stale
from truth_guardian.pipeline import make_sample
from truth_guardian.text import split_sentences

STEPS = [
    {"step": 1, "kind": "action", "content": "search('Ostby population')", "observation": "Ostby had a population of 8,900 at the 2011 census."},
    {"step": 2, "kind": "action", "content": "search('Ostby 2021 census')", "observation": "At the 2021 census, Ostby had grown to 10,400 residents."},
]


def judge(pairs):
    """Stand-in NLI: the 2011 sentence entails "8,900", the 2021 sentence contradicts it."""
    rows = []
    for premise, hypothesis in pairs:
        if "8,900" in hypothesis:
            rows.append([0.05, 0.9, 0.05] if "8,900" in premise else [0.9, 0.05, 0.05])
        else:
            rows.append([0.05, 0.9, 0.05] if "10,400" in premise else [0.6, 0.1, 0.3])
    return np.array(rows)


def run(answer: str):
    s = make_sample(answer, [], "How many people live in Ostby?", STEPS)
    return stale.check_sample(s, split_sentences(s.answer), judge)


def test_an_answer_kept_from_an_earlier_tool_result_is_outdated():
    (check,) = run("Ostby has a population of 8,900.")
    assert check.stale and (check.earlier_step, check.later_step) == (1, 2) and "10,400" in check.later_text


def test_the_newest_value_is_not_outdated():
    (check,) = run("Ostby has 10,400 residents.")
    assert not check.stale


def test_runs_with_one_tool_output_are_not_checked():
    s = make_sample("Ostby has a population of 8,900.", [], "How many?", STEPS[:1])
    (check,) = stale.check_sample(s, split_sentences(s.answer), judge)
    assert not check.stale
