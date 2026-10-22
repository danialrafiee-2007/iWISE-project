"""Build the "Fool the Guardian" suite: grounded dev answers, each edited once per kind, plus unedited controls.

Bases come from dev (never train), one answer per source group, so the suite tests the trained model
on edits it has never seen. Edit kinds that apply to few of the 60 bases (role swaps, hedges, quantifiers) are
topped up from further grounded dev answers, one per unused group, up to MIN_PER_KIND edits.
Output: data/processed/perturb_dev.jsonl
"""

import hashlib
import random
from collections import Counter
from pathlib import Path

from truth_guardian.data.splits import sample_groups
from truth_guardian.perturb import KINDS, entity_pool, perturb
from truth_guardian.schema import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parents[1]
BASES_PER_TASK = 20
MIN_PER_KIND = 30
TOP_UP_KINDS = ("role_swap", "quantifier", "certainty")


def main() -> None:
    dev = list(read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl"))
    grounded = [s for s in dev if s.labels.response == "grounded" and s.meta.quality == "good"]
    bases = []
    for task in ("qa", "summary", "data2text"):
        seen_groups = set()
        for s in sample_groups([x for x in grounded if x.meta.task == task], 10_000, seed="tg-perturb-v1"):
            if s.meta.group_id not in seen_groups and len(seen_groups) < BASES_PER_TASK:
                seen_groups.add(s.meta.group_id)
                bases.append(s)

    pool = entity_pool(dev)
    suite, counts = [], Counter()
    for base in bases:
        control = base.model_copy(update={"id": f"perturb-control-{base.id}", "meta": base.meta.model_copy(update={"dataset": "tg_perturb"})})
        suite.append(control)
        counts["control"] += 1
        for kind in KINDS:
            seed = int(hashlib.sha256(f"{base.id}:{kind}".encode()).hexdigest()[:8], 16)
            edited = perturb(base, kind, random.Random(seed), pool)
            if edited is not None:
                suite.append(edited)
                counts[kind] += 1

    used = {b.meta.group_id for b in bases}
    for s in sample_groups(grounded, 10_000, seed="tg-perturb-topup-v1"):
        if s.meta.group_id in used:
            continue
        used.add(s.meta.group_id)
        for kind in TOP_UP_KINDS:
            if counts[kind] >= MIN_PER_KIND:
                continue
            seed = int(hashlib.sha256(f"{s.id}:{kind}".encode()).hexdigest()[:8], 16)
            edited = perturb(s, kind, random.Random(seed), pool)
            if edited is not None:
                suite.append(edited)
                counts[kind] += 1

    out = ROOT / "data" / "processed" / "perturb_dev.jsonl"
    write_jsonl(suite, out)
    print(f"{len(bases)} bases -> {len(suite)} samples {dict(counts)} -> {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
