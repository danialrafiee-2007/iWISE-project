"""Does a small labelled sample restore the guarantees, the calibration and the ranking on a new domain?

HaluEval QA, dialogue and summary (the external dev sets, never the locked ones) stand in for new domains. For k
labelled answers (k = 20, 50, 100), repeated over random draws: fit a domain profile on the k answers, then measure on
the domain's remaining answers the miss rate under the catch threshold and the false-alarm rate under the alarm
threshold at alpha 0.1, the calibration error (ECE) of the domain's risk, its AUROC, and the verdict's F1 and accuracy.
Two profiles: "calibration" (Platt scaling and thresholds only) and "reweighted" (also re-weighting the model's risk
and three length-free evidence signals). Compared with the RAGTruth calibration as is. The AUROC of answer length
alone is reported per domain, since on HaluEval it separates the labels by itself and a fair detector must not use it.
Output: eval/results/adaptation.json
"""

import json
import random
from pathlib import Path

import numpy as np

from sklearn.metrics import f1_score, roc_auc_score

from truth_guardian import adapt, conformal, fusion
from truth_guardian.evaluation import expected_calibration_error
from truth_guardian.features import load_rows
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
DOMAINS = ("qa", "dialogue", "summary")
SIZES = (20, 50, 100)
DRAWS = 200
ALPHA = 0.1


def rates(risks, labels, t: conformal.Thresholds) -> tuple[float, float, float, float]:
    """(miss rate under the catch threshold, false-alarm rate under the alarm threshold, and the cost of each:
    false alarms when flagging at the catch threshold, misses when flagging only above the alarm threshold)."""
    hallucinated, grounded = risks[labels == 1], risks[labels == 0]
    return (float(np.mean(hallucinated < t.catch)), float(np.mean(grounded > t.alarm)),
            float(np.mean(grounded >= t.catch)), float(np.mean(hallucinated <= t.alarm)))


def held_out(profile, risks, features, labels, threshold_risk) -> dict:
    """Measures of one fitted profile on the answers it did not see."""
    domain = np.array([profile.domain_risk(r, f.tolist()) for r, f in zip(risks, features)])
    t = next(x for x in profile.thresholds if np.isclose(x.alpha, ALPHA))
    miss, alarm, catch_cost, alarm_cost = rates(domain, labels, t)
    verdicts = (domain >= profile.decision).astype(int)
    return {
        "miss_rate": miss, "false_alarm_rate": alarm, "false_alarms_when_catching": catch_cost, "misses_when_alarming": alarm_cost,
        "ece": expected_calibration_error(labels, domain), "auroc": float(roc_auc_score(labels, domain)),
        "verdict_f1": float(f1_score(labels, verdicts)), "verdict_accuracy": float(np.mean(verdicts == labels)),
    }


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    ragtruth = conformal.load(ROOT / "models" / "fusion" / manifest["version"], manifest["version"])
    rng = random.Random("adaptation-v2")
    report = {"model_version": manifest["version"], "alpha": ALPHA, "draws": DRAWS, "features": list(adapt.FEATURES), "domains": {}}
    for domain in DOMAINS:
        path = ROOT / "data/processed" / f"xdev_halueval_{domain}.jsonl"
        samples, predictions = cached_predictions(model, path, FEATURES)
        rows = load_rows(["lexical", "dense", "hhem"], path, FEATURES)
        risks = np.array([predictions[s.id].score for s in samples])
        merged = lambda sid: [{**a, **b, **c} for a, b, c in zip(rows["lexical"][sid], rows["dense"][sid], rows["hhem"][sid])]
        features = np.array([adapt.domain_features(predictions[s.id].score, merged(s.id)) for s in samples])
        labels = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
        miss, alarm, catch_cost, alarm_cost = rates(risks, labels, ragtruth.get(ALPHA))
        verdicts = (risks >= model.thresholds["response"]).astype(int)
        result = {
            "answers": len(samples), "hallucinated_share": float(labels.mean()),
            "answer_length_alone_auroc": float(roc_auc_score(labels, [len(s.answer.split()) for s in samples])),
            "ragtruth_calibration": {
                "miss_rate": miss, "false_alarm_rate": alarm, "false_alarms_when_catching": catch_cost, "misses_when_alarming": alarm_cost,
                "ece": expected_calibration_error(labels, risks), "auroc": float(roc_auc_score(labels, risks)),
                "verdict_f1": float(f1_score(labels, verdicts)), "verdict_accuracy": float(np.mean(verdicts == labels)),
            },
        }
        for k in SIZES:
            runs = {"calibration": [], "reweighted": []}
            for _ in range(DRAWS):
                chosen = np.array(rng.sample(range(len(samples)), k))
                rest = np.setdiff1d(np.arange(len(samples)), chosen)
                if len(set(labels[chosen].tolist())) < 2:
                    continue
                for kind, feats in (("calibration", None), ("reweighted", features[chosen])):
                    profile = adapt.fit(domain, risks[chosen], labels[chosen], manifest["version"], features=feats)
                    runs[kind].append(held_out(profile, risks[rest], features[rest], labels[rest], model.thresholds["response"]))
            result[f"k={k}"] = {
                kind: {
                    **{key: float(np.mean([r[key] for r in values])) for key in values[0]},
                    "miss_rate_within_alpha": float(np.mean([r["miss_rate"] <= ALPHA for r in values])),
                    "false_alarm_within_alpha": float(np.mean([r["false_alarm_rate"] <= ALPHA for r in values])),
                    "draws": len(values),
                }
                for kind, values in runs.items()
            }
        report["domains"][domain] = result
        r = result["ragtruth_calibration"]
        print(f"{domain}: length alone AUROC {result['answer_length_alone_auroc']:.3f}; RAGTruth: AUROC {r['auroc']:.3f} F1 {r['verdict_f1']:.3f} miss {r['miss_rate']:.3f} false alarm {r['false_alarm_rate']:.3f} ECE {r['ece']:.3f}")
        for k in SIZES:
            for kind, m in result[f"k={k}"].items():
                print(f"  k={k:3} {kind:11}: AUROC {m['auroc']:.3f} F1 {m['verdict_f1']:.3f} acc {m['verdict_accuracy']:.3f} miss {m['miss_rate']:.3f} false alarm {m['false_alarm_rate']:.3f} ECE {m['ece']:.3f}")
    out = ROOT / "eval" / "results" / "adaptation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
