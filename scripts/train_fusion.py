"""Train the fusion model on cached signals, score dev, tune thresholds on dev, and save model + manifest.

Training uses every train sample that has all requested signals cached and normal quality (D-013),
so a nested --groups subset from extract_features.py trains on exactly that subset.
"""

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from truth_guardian import fusion
from truth_guardian.evaluation import best_span_threshold, best_threshold, evaluate, write_predictions
from truth_guardian.features import FeatureStore
from truth_guardian.schema import Sample, read_jsonl
from truth_guardian.signals import SIGNALS

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
MODELS = ROOT / "models" / "fusion"


def load_rows(signals: list[str], dataset: Path) -> dict[str, dict[str, list[dict]]]:
    rows = {}
    for signal in signals:
        path = FEATURES / signal / f"{dataset.stem}.jsonl"
        if not path.exists():
            raise SystemExit(f"no cached {signal} features for {dataset.name}; run scripts/extract_features.py first")
        rows[signal] = FeatureStore(path, signal, SIGNALS[signal][0]).load()
    return rows


def usable(samples: list[Sample], rows: dict[str, dict]) -> list[Sample]:
    return [s for s in samples if all(s.id in r for r in rows.values())]


def git_commit() -> str:
    run = lambda *cmd: subprocess.run(["git", *cmd], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = run("status", "--porcelain", "--", "src", "scripts", "pyproject.toml", "uv.lock")
    return run("rev-parse", "--short", "HEAD") + ("-dirty" if dirty else "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", nargs="+", required=True, choices=list(SIGNALS))
    parser.add_argument("--kind", choices=["logreg", "hgb"], default="hgb")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--train", type=Path, default=ROOT / "data/processed/ragtruth_train.jsonl")
    parser.add_argument("--dev", type=Path, default=ROOT / "data/processed/ragtruth_dev.jsonl")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    train_rows = load_rows(args.signals, args.train)
    all_train = list(read_jsonl(args.train))
    train = usable([s for s in all_train if s.meta.quality == "good"], train_rows)
    dev_rows = load_rows(args.signals, args.dev)
    all_dev = list(read_jsonl(args.dev))
    dev = usable(all_dev, dev_rows)
    if len(dev) != len(all_dev):
        raise SystemExit(f"dev features incomplete: {len(dev)} of {len(all_dev)} samples cached")

    model, report = fusion.fit(train, fusion.build_table(train, train_rows, args.signals), args.signals, args.kind, args.folds)
    print(f"trained on {report['samples']} samples / {report['groups']} groups / {report['sentences']} sentences")
    print(f"  out-of-fold AUROC: sentence {report['oof_sentence_auroc']:.3f}, response {report['oof_response_auroc']:.3f}")

    predictions = model.predictions(dev, fusion.build_table(dev, dev_rows, args.signals))
    by_id = {p.id: p for p in predictions}
    y = np.array([s.labels.response == "hallucinated" for s in dev], dtype=int)
    model.thresholds = {
        "response": best_threshold(y, np.array([by_id[s.id].score for s in dev])),
        "sentence": best_span_threshold(dev, by_id),
    }
    dev_report = evaluate(dev, by_id, model.thresholds["response"], model.thresholds["sentence"], bootstrap_rounds=200)

    name = f"fusion-{args.kind}-{'+'.join(args.signals)}"
    out = ROOT / "eval" / "predictions" / f"{name}__{args.dev.stem}.jsonl"
    write_predictions(predictions, out)
    r = dev_report["response"]
    print(f"  dev AUROC {r['auroc']:.3f}  F1 {r['f1']:.3f}  ECE {r['ece']:.3f}  span F1 {dev_report['span']['f1']:.3f}")
    print(f"  predictions -> {out.relative_to(ROOT).as_posix()}")

    if args.no_save:
        return
    created = datetime.now(timezone.utc)
    manifest = {
        "version": f"{created:%Y%m%d-%H%M%S}-{args.kind}",
        "name": name,
        "created": created.isoformat(timespec="seconds"),
        "commit": git_commit(),
        "kind": args.kind,
        "signals": model.signal_versions,
        "train": {"data": args.train.name, **report, "excluded_quality": sum(s.meta.quality != "good" for s in all_train)},
        "folds": args.folds,
        "thresholds": model.thresholds,
        "dev": {"data": args.dev.name, "n": len(dev), "auroc": r["auroc"], "f1": r["f1"], "ece": r["ece"], "span_f1": dev_report["span"]["f1"]},
    }
    folder = fusion.save(model, MODELS, manifest)
    print(f"  saved model -> {folder.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
