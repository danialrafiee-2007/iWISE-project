import pytest

from truth_guardian.data.splits import assign_dev, check_no_group_leak, sample_groups
from truth_guardian.schema import Sample


def sample(i: int, group: str, task: str = "qa", split: str = "train") -> Sample:
    return Sample.model_validate({
        "id": f"s{i}",
        "documents": [{"id": "d", "text": "doc"}],
        "answer": "answer",
        "meta": {"dataset": "unit", "task": task, "split": split, "group_id": group},
    })


def corpus() -> list[Sample]:
    samples = [sample(i * 6 + j, f"g{i}", task="qa" if i % 2 else "summary") for i in range(40) for j in range(6)]
    return samples + [sample(1000 + i, f"t{i}", split="test") for i in range(5)]


def test_dev_takes_fraction_of_groups_per_task():
    result = assign_dev(corpus(), fraction=0.1)
    for task in ("qa", "summary"):
        dev_groups = {s.meta.group_id for s in result if s.meta.split == "dev" and s.meta.task == task}
        assert len(dev_groups) == 2


def test_groups_stay_together_and_test_untouched():
    result = assign_dev(corpus(), fraction=0.25)
    check_no_group_leak(result)
    assert all(s.meta.split == "test" for s in result if s.meta.group_id.startswith("t"))


def test_assignment_is_deterministic():
    first = [s.meta.split for s in assign_dev(corpus())]
    assert first == [s.meta.split for s in assign_dev(corpus())]


def test_leak_detected():
    with pytest.raises(ValueError, match="more than one split"):
        check_no_group_leak([sample(1, "g", split="train"), sample(2, "g", split="dev")])


def test_sample_groups_keeps_whole_groups():
    kept = sample_groups(corpus(), n_groups=3)
    groups = {s.meta.group_id for s in kept}
    assert len(groups) == 3
    assert all(sum(s.meta.group_id == g for s in kept) == sum(s.meta.group_id == g for s in corpus()) for g in groups)
