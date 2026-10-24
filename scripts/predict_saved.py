"""Predictions of the saved final model on a dataset whose signals are cached (scripts/extract_features.py first).

Applies the polarity and swapped-role overrides where their signals are cached, exactly as the live pipeline does,
and writes eval/predictions/<name>__<dataset>.jsonl; scripts/evaluate.py then scores it with the model's own
thresholds (chosen on dev when the model was trained). Locked test data needs --final.
"""

import argparse
import json
from pathlib import Path

from truth_guardian import fusion
from truth_guardian.evaluation import write_predictions
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--name", default="final")
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    model, manifest = fusion.load(ROOT / "models" / "fusion")
    samples, predictions = cached_predictions(model, args.data, ROOT / "data" / "features")
    missing = [s.id for s in samples if s.id not in predictions]
    if missing:
        raise SystemExit(f"{len(missing)} samples have no prediction (signals not cached?)")
    out = ROOT / "eval" / "predictions" / f"{args.name}__{args.data.stem}.jsonl"
    write_predictions([predictions[s.id] for s in samples], out)
    print(json.dumps({"model": manifest["version"], "samples": len(samples), "thresholds": model.thresholds, "predictions": out.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
