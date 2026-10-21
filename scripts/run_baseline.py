"""Run a baseline over a processed dataset and write predictions to eval/predictions."""

import argparse
import importlib
import time
from pathlib import Path

from truth_guardian.evaluation import write_predictions
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
METHODS = {
    "lexical": "truth_guardian.baselines.lexical",
    "embedding": "truth_guardian.baselines.embedding",
    "nli": "truth_guardian.baselines.nli",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", required=True, choices=sorted(METHODS))
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--limit", type=int, help="only the first N samples, for quick checks")
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    predict = importlib.import_module(METHODS[args.method]).predict
    samples = list(read_jsonl(args.data))[: args.limit]
    started = time.perf_counter()
    predictions = [predict(s) for s in samples]
    elapsed = time.perf_counter() - started

    out = ROOT / "eval" / "predictions" / f"{args.method}__{args.data.stem}.jsonl"
    write_predictions(predictions, out)
    print(f"{len(predictions)} predictions in {elapsed:.1f}s ({1000 * elapsed / max(len(samples), 1):.1f} ms/sample) -> {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
