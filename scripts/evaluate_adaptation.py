"""Does a small labelled sample restore the guarantees and calibration on a new domain?

HaluEval QA, dialogue and summary stand in for new domains. For k labelled answers (k = 20, 50, 100), repeated over
random draws: fit a domain profile on the k answers, then measure on the domain's remaining answers the miss rate
under the catch threshold and the false-alarm rate under the alarm threshold at alpha 0.1, and the calibration error
(ECE) of the recalibrated risk. Compared with using the RAGTruth calibration as is.
Output: eval/results/adaptation.json
"""

import json
import random
from pathlib import Path

import numpy as np

from truth_guardian import adapt, conformal, fusion
from truth_guardian.evaluation import expected_calibration_error
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


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    ragtruth = conformal.load(ROOT / "models" / "fusion" / manifest["version"], manifest["version"])
    rng = random.Random("adaptation-v1")
    report = {"model_version": manifest["version"], "alpha": ALPHA, "draws": DRAWS, "domains": {}}
    for domain in DOMAINS:
        samples, predictions = cached_predictions(model, ROOT / "data/processed" / f"xdev_halueval_{domain}.jsonl", FEATURES)
        risks = np.array([predictions[s.id].score for s in samples])
        labels = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
        miss, alarm, catch_cost, alarm_cost = rates(risks, labels, ragtruth.get(ALPHA))
        result = {"answers": len(samples), "hallucinated_share": float(labels.mean()),
                  "ragtruth_calibration": {"miss_rate": miss, "false_alarm_rate": alarm, "false_alarms_when_catching": catch_cost,
                                           "misses_when_alarming": alarm_cost, "ece": expected_calibration_error(labels, risks)}}
        for k in SIZES:
            misses, alarms, catch_costs, alarm_costs, eces = [], [], [], [], []
            for _ in range(DRAWS):
                chosen = np.array(rng.sample(range(len(samples)), k))
                rest = np.setdiff1d(np.arange(len(samples)), chosen)
                profile = adapt.fit(domain, risks[chosen], labels[chosen], manifest["version"])
                t = next(x for x in profile.thresholds if np.isclose(x.alpha, ALPHA))
                m, a, cc, ac = rates(risks[rest], labels[rest], t)
                misses.append(m)
                alarms.append(a)
                catch_costs.append(cc)
                alarm_costs.append(ac)
                eces.append(expected_calibration_error(labels[rest], np.array([profile.calibrated(r) for r in risks[rest]])))
            result[f"k={k}"] = {
                "miss_rate": float(np.mean(misses)), "miss_rate_within_alpha": float(np.mean([m <= ALPHA for m in misses])),
                "false_alarm_rate": float(np.mean(alarms)), "false_alarm_within_alpha": float(np.mean([a <= ALPHA for a in alarms])),
                "false_alarms_when_catching": float(np.mean(catch_costs)), "misses_when_alarming": float(np.mean(alarm_costs)),
                "ece": float(np.mean(eces)),
            }
        report["domains"][domain] = result
        r = result["ragtruth_calibration"]
        print(f"{domain}: RAGTruth calibration miss {r['miss_rate']:.3f} (costs {r['false_alarms_when_catching']:.2f} false alarms)  false alarm {r['false_alarm_rate']:.3f} (costs {r['misses_when_alarming']:.2f} misses)  ECE {r['ece']:.3f}")
        for k in SIZES:
            m = result[f"k={k}"]
            print(f"  k={k:3}: miss {m['miss_rate']:.3f} (costs {m['false_alarms_when_catching']:.2f})  false alarm {m['false_alarm_rate']:.3f} (costs {m['misses_when_alarming']:.2f})  ECE {m['ece']:.3f}")
    out = ROOT / "eval" / "results" / "adaptation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
