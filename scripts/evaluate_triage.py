"""Evaluate the triage lanes on RAGTruth dev, then save the policy next to the model.

200 splits of dev by source group: thresholds chosen on one half, lanes measured on the other (share of answers per
lane, hallucinations among passed answers, grounded answers blocked). Also a risk-coverage table: if the
lowest-risk X% of answers pass unchecked, how many of them are hallucinated. The saved policy uses all of dev;
on HaluEval it is reported as is, since triage, like the guarantees, holds only for data like its calibration.
Output: eval/results/triage.json and triage.json in the model folder.
"""

import json
import random
from pathlib import Path

import numpy as np

from truth_guardian import fusion, triage
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
SPLITS = 200
COVERAGES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)


def scored(model, name: str):
    samples, predictions = cached_predictions(model, ROOT / "data/processed" / f"{name}.jsonl", FEATURES)
    return samples, np.array([predictions[s.id].score for s in samples]), np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    samples, risks, labels = scored(model, "ragtruth_dev")
    groups = sorted({s.meta.group_id for s in samples})
    group_of = np.array([s.meta.group_id for s in samples])
    rng = random.Random("triage-v1")
    runs = []
    for _ in range(SPLITS):
        calibration = np.isin(group_of, rng.sample(groups, len(groups) // 2))
        policy = triage.fit(risks[calibration], labels[calibration], manifest["version"], "split")
        runs.append(triage.workload(risks[~calibration], labels[~calibration], policy))
    held_out = {k: float(np.mean([r[k] for r in runs if r[k] is not None])) for k in runs[0]}
    held_out["passed_within_target"] = float(np.mean([r["hallucinated_among_passed"] <= triage.PASS_ERROR for r in runs if r["hallucinated_among_passed"] is not None]))
    held_out["blocked_within_target"] = float(np.mean([r["grounded_blocked"] <= triage.BLOCK_FALSE_ALARM for r in runs]))

    order = np.argsort(risks)
    coverage = {f"{c:.0%}": float(labels[order[: max(1, int(c * len(labels)))]].mean()) for c in COVERAGES}
    final = triage.fit(risks, labels, manifest["version"], "ragtruth_dev.jsonl")
    shift = {}
    for domain in ("qa", "dialogue", "summary"):
        _, x_risks, x_labels = scored(model, f"xdev_halueval_{domain}")
        shift[domain] = triage.workload(x_risks, x_labels, final)

    report = {"model_version": manifest["version"], "pass_error": triage.PASS_ERROR, "block_false_alarm": triage.BLOCK_FALSE_ALARM, "confidence": triage.CONFIDENCE,
              "held_out": held_out, "risk_coverage": coverage, "base_rate": float(labels.mean()), "final_policy": final.model_dump(), "halueval": shift}
    saved = final.save(ROOT / "models" / "fusion" / manifest["version"])
    out = ROOT / "eval" / "results" / "triage.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    h = held_out
    print(f"held out: pass {h['pass']:.2f} review {h['review']:.2f} block {h['block']:.2f}; hallucinated among passed {h['hallucinated_among_passed']:.3f} "
          f"(within target in {h["passed_within_target"]:.0%} of splits); among blocked {h["hallucinated_among_blocked"]:.3f}; grounded blocked {h["grounded_blocked"]:.3f} (within target in {h["blocked_within_target"]:.0%}); hallucinations not passed {h['hallucinations_caught']:.3f}")
    print("risk-coverage:", coverage, "base rate", round(report["base_rate"], 3))
    print(f"final policy: pass below {final.pass_below:.3f}, block from {final.block_from:.3f}")
    for d, w in shift.items():
        print(f"  HaluEval {d}: pass {w['pass']:.2f} review {w['review']:.2f} block {w['block']:.2f}; among passed {w['hallucinated_among_passed']}; among blocked {w['hallucinated_among_blocked']}; grounded blocked {w['grounded_blocked']}")
    print(f"saved {out.relative_to(ROOT).as_posix()} and {saved.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
