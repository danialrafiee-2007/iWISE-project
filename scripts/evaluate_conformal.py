"""Check the conformal guarantees of the saved model, then save its calibration next to it.

Repeated 50/50 splits of RAGTruth dev by source group: calibrate on one half, measure on the other. For each alpha,
the guaranteed rate (miss rate under the catch threshold, false-alarm rate under the alarm threshold) should average
at most alpha; the cost side (false alarms when guaranteeing catches, and the reverse) is reported too. Pooled
thresholds are compared with per-task (Mondrian) ones within each task. Shift test: thresholds calibrated on all of
RAGTruth dev applied to HaluEval. Final calibration = all of RAGTruth dev, saved as conformal.json in the model folder.
Output: eval/results/conformal.json
"""

import json
import random
from pathlib import Path

import numpy as np

from truth_guardian import conformal, fusion
from truth_guardian.overrides import cached_predictions

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
SPLITS = 200
XDEV = ("qa", "dialogue", "summary")


def scored(model, name: str) -> tuple[np.ndarray, np.ndarray, list]:
    """Risks (with the polarity and role-swap overrides), labels and samples of a processed dataset."""
    samples, predictions = cached_predictions(model, ROOT / "data/processed" / f"{name}.jsonl", FEATURES)
    risks = np.array([predictions[s.id].score for s in samples])
    labels = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
    return risks, labels, samples


def rates(risks, labels, t: conformal.Thresholds) -> dict[str, float]:
    hallucinated, grounded = risks[labels == 1], risks[labels == 0]
    return {
        "miss_rate_catch": float(np.mean(hallucinated < t.catch)),
        "false_alarm_rate_catch": float(np.mean(grounded >= t.catch)),
        "false_alarm_rate_alarm": float(np.mean(grounded > t.alarm)),
        "miss_rate_alarm": float(np.mean(hallucinated <= t.alarm)),
    }


def summary(runs: list[dict], alpha: float) -> dict:
    out = {k: float(np.mean([r[k] for r in runs])) for k in runs[0]}
    for key in ("miss_rate_catch", "false_alarm_rate_alarm"):
        values = [r[key] for r in runs]
        out[f"{key}_p90"] = float(np.quantile(values, 0.9))
        out[f"{key}_within_alpha"] = float(np.mean([v <= alpha for v in values]))
    return out


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    risks, labels, samples = scored(model, "ragtruth_dev")
    tasks = np.array([s.meta.task for s in samples])
    groups = sorted({s.meta.group_id for s in samples})
    group_of = np.array([s.meta.group_id for s in samples])
    rng = random.Random("conformal-v1")

    pooled_runs = {a: [] for a in conformal.ALPHAS}
    task_runs = {(task, kind, a): [] for task in set(tasks) for kind in ("pooled", "per_task") for a in conformal.ALPHAS}
    for _ in range(SPLITS):
        calibration = set(rng.sample(groups, len(groups) // 2))
        cal = np.isin(group_of, list(calibration))
        test = ~cal
        for t in conformal.calibrate(risks[cal], labels[cal]):
            pooled_runs[t.alpha].append(rates(risks[test], labels[test], t))
            for task in set(tasks):
                mask = test & (tasks == task)
                task_runs[(task, "pooled", t.alpha)].append(rates(risks[mask], labels[mask], t))
        for task in set(tasks):
            mask = cal & (tasks == task)
            for t in conformal.calibrate(risks[mask], labels[mask]):
                test_mask = test & (tasks == task)
                task_runs[(task, "per_task", t.alpha)].append(rates(risks[test_mask], labels[test_mask], t))

    final = conformal.Calibration(
        model_version=manifest["version"],
        data="ragtruth_dev.jsonl",
        pooled=conformal.calibrate(risks, labels),
        by_task={task: conformal.calibrate(risks[tasks == task], labels[tasks == task]) for task in sorted(set(tasks))},
    )
    shift = {}
    for name in XDEV:
        x_risks, x_labels, _ = scored(model, f"xdev_halueval_{name}")
        shift[name] = {str(t.alpha): rates(x_risks, x_labels, t) for t in final.pooled}

    report = {
        "model_version": manifest["version"],
        "splits": SPLITS,
        "pooled": {str(a): summary(runs, a) for a, runs in pooled_runs.items()},
        "by_task": {f"{task}/{kind}/{a}": summary(runs, a) for (task, kind, a), runs in sorted(task_runs.items())},
        "halueval_shift": shift,
        "final_calibration": final.model_dump(),
    }
    saved = final.save(ROOT / "models" / "fusion" / manifest["version"])
    out = ROOT / "eval" / "results" / "conformal.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    for a, m in report["pooled"].items():
        print(f"alpha {a}: miss {m['miss_rate_catch']:.3f} (p90 {m['miss_rate_catch_p90']:.3f}, within {m['miss_rate_catch_within_alpha']:.2f}) costs false alarms {m['false_alarm_rate_catch']:.3f} | "
              f"false alarm {m['false_alarm_rate_alarm']:.3f} (p90 {m['false_alarm_rate_alarm_p90']:.3f}) costs misses {m['miss_rate_alarm']:.3f}")
    for key, m in report["by_task"].items():
        if key.endswith("/0.1"):
            print(f"  {key:28} miss {m['miss_rate_catch']:.3f}  false alarm {m['false_alarm_rate_alarm']:.3f}")
    for name, by_alpha in shift.items():
        m = by_alpha["0.1"]
        print(f"  HaluEval {name:9} alpha 0.1: miss {m['miss_rate_catch']:.3f}  false alarm {m['false_alarm_rate_alarm']:.3f}")
    print(f"saved {out.relative_to(ROOT).as_posix()} and {saved.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
