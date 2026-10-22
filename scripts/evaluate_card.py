"""Check what the reliability card's grades mean: the observed hallucination rate per grade.

Grades come from the saved model's calibrated risk (with overrides), on RAGTruth dev and HaluEval external dev.
A useful grade scale is monotonic: each grade's hallucination rate is higher than the one before.
Output: eval/results/card.json
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from truth_guardian import fusion
from truth_guardian.card import GRADES, grade
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
DATASETS = ("ragtruth_dev", "xdev_halueval_qa", "xdev_halueval_dialogue", "xdev_halueval_summary")


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    report = {"model_version": manifest["version"], "grades": {g: limit for g, limit in GRADES}}
    for name in DATASETS:
        samples, predictions = cached_predictions(model, ROOT / "data/processed" / f"{name}.jsonl", FEATURES)
        by_grade = defaultdict(list)
        for s in samples:
            risk = predictions[s.id].score
            by_grade[grade(risk)].append((risk, s.labels.response == "hallucinated"))
        rows = {
            g: {"n": len(v), "share": len(v) / len(samples), "mean_risk": float(np.mean([r for r, _ in v])), "hallucination_rate": float(np.mean([h for _, h in v]))}
            for g in "ABCDF" if (v := by_grade[g])
        }
        rates = [m["hallucination_rate"] for m in rows.values()]
        report[name] = {"by_grade": rows, "monotonic": all(a <= b for a, b in zip(rates, rates[1:]))}
        print(name, "monotonic" if report[name]["monotonic"] else "NOT monotonic")
        for g, m in rows.items():
            print(f"  {g}: n={m['n']:4} ({m['share']:.0%})  mean risk {m['mean_risk']:.2f}  hallucinated {m['hallucination_rate']:.2f}")
    out = ROOT / "eval" / "results" / "card.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
