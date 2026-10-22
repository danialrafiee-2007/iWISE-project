"""Build TG-Agent: scripted agent trajectories with one known injected error, from grounded RAGTruth dev QA answers.

Output: data/processed/tg_agent_dev.jsonl (never used for training; a controlled test of the tracer).
"""

import hashlib
import random
from collections import Counter
from pathlib import Path

from truth_guardian.data.agent_synth import build
from truth_guardian.data.splits import sample_groups
from truth_guardian.perturb import entity_pool
from truth_guardian.schema import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parents[1]
BASES = 60


def main() -> None:
    dev = list(read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl"))
    pool = entity_pool(dev)
    candidates = [s for s in dev if s.meta.task == "qa" and s.labels.response == "grounded" and s.meta.quality == "good" and len(s.documents) >= 2]
    trajectories, groups = [], set()
    for base in sample_groups(candidates, 10_000, seed="tg-agent-synth-v1"):
        if base.meta.group_id in groups or len(groups) >= BASES:
            continue
        built = build(base, random.Random(int(hashlib.sha256(base.id.encode()).hexdigest()[:8], 16)), pool)
        if built:
            groups.add(base.meta.group_id)
            trajectories += built
    out = ROOT / "data" / "processed" / "tg_agent_dev.jsonl"
    write_jsonl(trajectories, out)
    print(f"{len(groups)} bases -> {len(trajectories)} trajectories {dict(Counter(s.id.split('-')[1] for s in trajectories))} -> {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
