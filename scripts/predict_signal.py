"""Predictions from one cached signal used on its own, for external reference models such as LettuceDetect.

The answer's score is the highest sentence value of --key, and each sentence keeps its own value, so
scripts/evaluate.py can score it like any detector. Locked test data needs --final.
"""

import argparse
import json
from pathlib import Path

from truth_guardian.evaluation import Prediction, SentenceScore, write_predictions
from truth_guardian.features import load_rows
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--signal", required=True)
    parser.add_argument("--key", required=True, help="the per-sentence value to score with, e.g. lettuce_max")
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    samples = list(read_jsonl(args.data))
    rows = load_rows([args.signal], args.data, ROOT / "data" / "features")[args.signal]
    predictions = []
    for s in samples:
        sentences = [SentenceScore(start=r["start"], end=r["end"], score=float(r[args.key])) for r in rows[s.id]]
        predictions.append(Prediction(id=s.id, score=max((x.score for x in sentences), default=0.0), sentences=sentences))
    out = ROOT / "eval" / "predictions" / f"{args.signal}__{args.data.stem}.jsonl"
    write_predictions(predictions, out)
    print(json.dumps({"samples": len(predictions), "predictions": out.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
