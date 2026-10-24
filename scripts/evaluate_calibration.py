"""Reliability diagram data: in each band of predicted risk, how often were the answers really hallucinated?

Reads the final model's saved predictions (no model is run) for RAGTruth dev, the locked RAGTruth test and the locked
HaluEval sets (pooled), and bins them as the reported ECE does (10 equal-width bins). Locked data needs --final and the
read is logged. Output: eval/results/calibration.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from truth_guardian.evaluation import expected_calibration_error, read_predictions
from truth_guardian.provenance import git_commit
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
BINS = 10
SETS = {
    "ragtruth_dev": ["data/processed/ragtruth_dev.jsonl"],
    "ragtruth_test": ["data/processed/locked/ragtruth_test.jsonl"],
    "halueval": [f"data/processed/locked/halueval_{t}.jsonl" for t in ("qa", "dialogue", "summary")],
}


def reliability(y: np.ndarray, scores: np.ndarray, bins: int = BINS) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    index = np.clip(np.digitize(scores, edges[1:-1]), 0, bins - 1)
    return [
        {"low": float(edges[b]), "high": float(edges[b + 1]), "n": int(mask.sum()), "mean_risk": float(scores[mask].mean()), "observed": float(y[mask].mean())}
        for b in range(bins) if (mask := index == b).any()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="required: the locked test predictions are read")
    args = parser.parse_args()
    if not args.final:
        parser.error("this reads locked test predictions; pass --final")

    report = {"model": "final", "bins": BINS, "sets": {}}
    for name, paths in SETS.items():
        y, scores = [], []
        for path in map(Path, paths):
            predictions = read_predictions(ROOT / "eval" / "predictions" / f"final__{path.stem}.jsonl")
            for s in read_jsonl(ROOT / path):
                y.append(s.labels.response == "hallucinated")
                scores.append(predictions[s.id].score)
        y, scores = np.array(y, dtype=float), np.array(scores)
        report["sets"][name] = {
            "data": paths, "answers": len(y), "hallucinated_share": float(y.mean()),
            "ece": expected_calibration_error(y, scores, BINS), "bins": reliability(y, scores),
        }
    out = ROOT / "eval" / "results" / "calibration.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with (ROOT / "eval" / "locked_runs.log").open("a", encoding="utf-8", newline="\n") as log:
        for path in SETS["ragtruth_test"] + SETS["halueval"]:
            log.write(f"{stamp}\t{git_commit(ROOT)}\tcalibration (saved predictions re-read, no model run)\t{path}\t{out.relative_to(ROOT).as_posix()}\n")
    for name, s in report["sets"].items():
        print(f"{name}: {s['answers']} answers, ECE {s['ece']:.3f}, bins " + " ".join(f"{b['mean_risk']:.2f}->{b['observed']:.2f}({b['n']})" for b in s["bins"]))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
