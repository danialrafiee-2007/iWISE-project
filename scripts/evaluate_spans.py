"""Exact words: narrow each flagged sentence to the tokens the trained detector marks. RAGTruth dev only.

The final model (with its overrides) decides which sentences are flagged, as before; inside them the detector's
tokens at or above a word threshold become the predicted span, and a flagged sentence with no marked token keeps its
whole range. The word threshold is chosen on one half of dev (split by source group) and measured on the other, both
ways round, so the reported span F1 is not tuned on the answers it is measured on; the threshold the app ships is then
chosen on all of dev. Detector rows must be cached first (extract_features.py --signals detector).
Output: eval/results/spans.json
"""

import hashlib
import json
from pathlib import Path

from truth_guardian import detector, fusion
from truth_guardian.evaluation import span_f1
from truth_guardian.features import load_rows
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/ragtruth_dev.jsonl"
GRID = [round(0.05 * i, 2) for i in range(2, 19)]


def half(group_id: str) -> int:
    return int(hashlib.sha256(f"spans-v1:{group_id}".encode()).hexdigest(), 16) % 2


def narrowed(predictions: dict, rows: dict, threshold: float) -> dict:
    return {
        sid: p.model_copy(update={"spans": [sp for r in rows[sid] for sp in detector.merged([tuple(t) for t in r["det_tokens"]], threshold)]})
        for sid, p in predictions.items()
    }


def main() -> None:
    model = fusion.load(ROOT / "models" / "fusion")[0]
    samples, predictions = cached_predictions(model, DATA, ROOT / "data" / "features")
    predictions = {k: p.model_copy(update={"spans": None}) for k, p in predictions.items()}
    rows = load_rows(["detector"], DATA, ROOT / "data" / "features")["detector"]
    sentence = model.thresholds["sentence"]
    halves = [[s for s in samples if half(s.meta.group_id) == h] for h in (0, 1)]

    def score(subset, threshold=None) -> dict:
        chosen = predictions if threshold is None else narrowed(predictions, rows, threshold)
        return span_f1(subset, chosen, sentence)

    cross = []
    for tune, test in ((halves[0], halves[1]), (halves[1], halves[0])):
        best = max(GRID, key=lambda t: score(tune, t)["f1"])
        cross.append({"threshold": best, "sentences": score(test), "narrowed": score(test, best)})
    chosen = max(GRID, key=lambda t: score(samples, t)["f1"])
    report = {
        "answers": len(samples), "detector": detector.fingerprint(), "sentence_threshold": sentence,
        "cross_fitted": cross,
        "cross_fitted_f1": {"sentences": sum(c["sentences"]["f1"] for c in cross) / 2, "narrowed": sum(c["narrowed"]["f1"] for c in cross) / 2},
        "shipped_threshold": chosen,
        "all_dev": {"sentences": score(samples), "narrowed": score(samples, chosen)},
        "grid": {str(t): score(samples, t) for t in GRID},
    }
    out = ROOT / "eval" / "results" / "spans.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("cross_fitted_f1", "shipped_threshold", "all_dev")}, indent=1))


if __name__ == "__main__":
    main()
