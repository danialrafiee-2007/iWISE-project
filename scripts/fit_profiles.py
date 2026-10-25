"""Fit the domain profiles the app ships: HaluEval QA, dialogue and summary, 50 labelled answers each.

The 50 answers are drawn at random from each domain's external dev set (never the locked test); the profile
(recalibration, re-weighting and conformal thresholds, adapt.py) is saved to models/profiles/, and checked on the
domain's other 450 answers against the model with its RAGTruth calibration. Output: eval/results/profiles.json
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian import adapt, fusion
from truth_guardian.evaluation import expected_calibration_error
from truth_guardian.features import load_rows
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
DOMAINS = {"qa": "HaluEval QA", "dialogue": "HaluEval dialogue", "summary": "HaluEval summary"}


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    folder = ROOT / "models" / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    report = {"model_version": manifest["version"], "labelled": adapt.SHIPPED_LABELLED, "profiles": {}}
    for domain, title in DOMAINS.items():
        path = ROOT / "data/processed" / f"xdev_halueval_{domain}.jsonl"
        samples, predictions = cached_predictions(model, path, FEATURES)
        rows = load_rows(["lexical", "dense", "hhem"], path, FEATURES)
        risks = np.array([predictions[s.id].score for s in samples])
        features = np.array([
            adapt.domain_features(predictions[s.id].score, [{**a, **b, **c} for a, b, c in zip(rows["lexical"][s.id], rows["dense"][s.id], rows["hhem"][s.id])])
            for s in samples
        ])
        labels = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
        chosen = np.array(adapt.labelled_choice(len(samples), domain))
        rest = np.setdiff1d(np.arange(len(samples)), chosen)
        profile = adapt.fit(title, risks[chosen], labels[chosen], manifest["version"], features=features[chosen])
        name = f"halueval-{domain}"
        profile.save(folder / f"{name}.json")
        domain_risk = np.array([profile.domain_risk(r, f.tolist()) for r, f in zip(risks[rest], features[rest])])
        base_verdict = risks[rest] >= model.thresholds["response"]
        report["profiles"][name] = {
            "title": title, "labelled": {"hallucinated": profile.hallucinated, "grounded": profile.grounded},
            "held_out_answers": len(rest),
            "auroc": {"model": float(roc_auc_score(labels[rest], risks[rest])), "profile": float(roc_auc_score(labels[rest], domain_risk))},
            "ece": {"model": expected_calibration_error(labels[rest], risks[rest]), "profile": expected_calibration_error(labels[rest], domain_risk)},
            "verdict_accuracy": {"model": float(np.mean(base_verdict == labels[rest])), "profile": float(np.mean((domain_risk >= profile.decision) == labels[rest]))},
            "weights": dict(zip(profile.ranking.features, profile.ranking.coef)) if profile.ranking else None,
        }
        r = report["profiles"][name]
        print(f"{name}: AUROC {r['auroc']['model']:.3f} -> {r['auroc']['profile']:.3f}, ECE {r['ece']['model']:.3f} -> {r['ece']['profile']:.3f}, verdict accuracy {r['verdict_accuracy']['model']:.3f} -> {r['verdict_accuracy']['profile']:.3f}")
    out = ROOT / "eval" / "results" / "profiles.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
