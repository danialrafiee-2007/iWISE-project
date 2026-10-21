"""Deterministic, group-aware splitting: all samples of one group always land in the same split."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable

from truth_guardian.schema import Sample

TRAIN_SUBSET_SEED = "tg-train-subset-v1"


def _rank(seed: str, group_id: str) -> str:
    return hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()


def assign_dev(samples: Iterable[Sample], fraction: float = 0.1, seed: str = "tg-dev-v1") -> list[Sample]:
    """Move a task-stratified fraction of train groups to dev."""
    samples = list(samples)
    groups_by_task: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        if s.meta.split == "train":
            groups_by_task[s.meta.task].add(s.meta.group_id)
    dev_groups: set[str] = set()
    for groups in groups_by_task.values():
        ranked = sorted(groups, key=lambda g: _rank(seed, g))
        dev_groups.update(ranked[: round(len(ranked) * fraction)])
    return [
        s.model_copy(update={"meta": s.meta.model_copy(update={"split": "dev"})}) if s.meta.group_id in dev_groups else s
        for s in samples
    ]


def sample_groups(samples: Iterable[Sample], n_groups: int, seed: str = "tg-subset-v1", offset: int = 0) -> list[Sample]:
    """Keep n whole groups, chosen deterministically; the same seed with a larger offset gives disjoint groups."""
    samples = list(samples)
    groups = sorted({s.meta.group_id for s in samples}, key=lambda g: _rank(seed, g))
    keep = set(groups[offset : offset + n_groups])
    return [s for s in samples if s.meta.group_id in keep]


def check_no_group_leak(samples: Iterable[Sample]) -> None:
    splits_by_group: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        splits_by_group[s.meta.group_id].add(s.meta.split)
    leaked = [g for g, splits in splits_by_group.items() if len(splits) > 1]
    if leaked:
        raise ValueError(f"{len(leaked)} groups appear in more than one split, e.g. {leaked[:3]}")
