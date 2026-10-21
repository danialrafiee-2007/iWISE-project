"""Compute and cache per-sentence signals for a processed dataset (resumable).

--groups N takes the first N source groups in a fixed ranking, so growing N later only adds new samples
(1,000 -> 2,000 -> 4,000 groups for a learning curve) and never recomputes what is cached.
"""

import argparse
import time
from pathlib import Path

from truth_guardian.data.splits import TRAIN_SUBSET_SEED, sample_groups
from truth_guardian.features import FeatureStore, extract
from truth_guardian.schema import read_jsonl
from truth_guardian.signals import SIGNALS

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--signals", nargs="+", required=True, choices=list(SIGNALS))
    parser.add_argument("--groups", type=int, help="only the first N source groups (nested across runs)")
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    samples = list(read_jsonl(args.data))
    if args.groups:
        samples = sample_groups(samples, args.groups, seed=TRAIN_SUBSET_SEED)
    print(f"{args.data.name}: {len(samples)} samples", flush=True)
    for signal in args.signals:
        version, fn = SIGNALS[signal]
        store = FeatureStore(FEATURES / signal / f"{args.data.stem}.jsonl", signal, version)
        started = time.perf_counter()
        computed = extract(samples, store, fn, report_every=500)
        print(f"{signal}: {computed} computed in {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
