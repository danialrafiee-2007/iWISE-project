"""Evaluate a predictions file against a processed dataset and save a JSON report to eval/results."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from truth_guardian.evaluation import best_span_threshold, best_threshold, evaluate, read_predictions
from truth_guardian.provenance import git_commit
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
LOCKED_LOG = ROOT / "eval" / "locked_runs.log"


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def print_summary(report: dict) -> None:
    r, ci = report["response"], report["ci95"]
    print(f"{report['name']} on {report['data']}  (threshold {report['threshold']:.4f}, n={r['n']})")
    print(f"  F1 {r['f1']:.3f} {ci['f1']}  P {r['precision']:.3f}  R {r['recall']:.3f}  (flag-everything F1 {r['f1_flag_everything']:.3f})")
    print(f"  AUROC {r.get('auroc', float('nan')):.3f} {ci['auroc']}  PR-AUC {r.get('pr_auc', float('nan')):.3f}")
    if "ece" in r:
        print(f"  Brier {r['brier']:.3f}  ECE {r['ece']:.3f}")
    if report["span"]:
        s = report["span"]
        print(f"  span F1 {s['f1']:.3f}  P {s['precision']:.3f}  R {s['recall']:.3f}  (sentence threshold {report['sentence_threshold']:.4f})")
    for task, m in report["breakdown"].get("task", {}).items():
        print(f"  [{task}] F1 {m['f1']:.3f} (flag-everything {m['f1_flag_everything']:.3f})  AUROC {m.get('auroc', float('nan')):.3f}  n={m['n']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--pred", required=True, type=Path)
    parser.add_argument("--name", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--threshold", type=float)
    mode.add_argument("--tune", action="store_true", help="pick F1-optimal response and span thresholds on this data (dev only)")
    parser.add_argument("--sentence-threshold", type=float, help="with --threshold: span threshold from dev")
    parser.add_argument("--final", action="store_true", help="required for locked test data; every run is logged")
    args = parser.parse_args()

    locked = "locked" in args.data.resolve().parts
    if locked and not args.final:
        parser.error("locked test data needs --final; evaluate on dev while developing")
    if locked and args.tune:
        parser.error("never tune a threshold on locked test data; pass the dev threshold")

    samples = list(read_jsonl(args.data))
    predictions = read_predictions(args.pred)
    threshold, sentence_threshold = args.threshold, args.sentence_threshold
    if args.tune:
        y = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
        threshold = best_threshold(y, np.array([predictions[s.id].score for s in samples]))
        if any(s.labels.spans for s in samples):
            sentence_threshold = best_span_threshold(samples, predictions)

    report = {
        "name": args.name,
        "data": relative(args.data),
        "predictions": relative(args.pred),
        "commit": git_commit(ROOT),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **evaluate(samples, predictions, threshold, sentence_threshold),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{args.name}__{args.data.stem}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    if locked:
        with LOCKED_LOG.open("a", encoding="utf-8", newline="\n") as log:
            log.write(f"{report['timestamp']}\t{report['commit']}\t{report['name']}\t{report['data']}\t{report['predictions']}\n")
    print_summary(report)
    print(f"saved {relative(out)}")


if __name__ == "__main__":
    main()
