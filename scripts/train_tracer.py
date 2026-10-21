"""Train the learned provenance tracer on AgentHallu dev and compare it with tracer v0 and simple baselines.

Scores are out-of-fold (5 folds grouped by question), so every number comes from trajectories the model
did not train on. The final model is then fit on all of dev and saved; the locked test is not touched.
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.provenance import git_commit
from truth_guardian.schema import read_jsonl
from truth_guardian.tracer import fit_tracer, step_features, suspected_step, trace, trajectory_features

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "tracer"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    samples = list(read_jsonl(ROOT / "data/processed/agenthallu_dev.jsonl"))
    features = {s.id: (traces, step_features(s, traces)) for s in samples for traces in [trace(s)]}
    fold_of = fusion.group_folds([s.meta.group_id for s in samples], args.folds)

    hits = defaultdict(lambda: defaultdict(list))
    risk = {}
    for k in range(args.folds):
        train = [s for s in samples if fold_of[s.meta.group_id] != k]
        model = fit_tracer(train, features)
        for s in (s for s in samples if fold_of[s.meta.group_id] == k):
            traces, matrix = features[s.id]
            risk[s.id] = float(model.detector.predict_proba(trajectory_features(matrix).reshape(1, -1))[:, 1][0])
            if s.labels.responsible_step is None or not traces:
                continue
            probs = model.step_model.predict_proba(matrix)[:, 1]
            ranked = [t.step for _, t in sorted(zip(probs, traces), key=lambda pt: (-pt[0], pt[1].step))]
            gold, steps = s.labels.responsible_step, [t.step for t in traces]
            v0 = suspected_step(traces).step
            for g in ("all", f"category: {s.labels.category}"):
                h = hits[g]
                h["learned_exact"].append(ranked[0] == gold)
                h["learned_within_1"].append(abs(ranked[0] - gold) <= 1)
                h["learned_top3"].append(gold in ranked[:3])
                h["v0_exact"].append(v0 == gold)
                h["first_step"].append(steps[0] == gold)
                h["random"].append(1 / len(steps))

    y = [int(s.labels.response == "hallucinated") for s in samples]
    v0_risk = [max((t.score for t in features[s.id][0]), default=0.0) for s in samples]
    report = {
        "trajectories": len(samples),
        "folds": args.folds,
        "detection_auroc_learned": float(roc_auc_score(y, [risk[s.id] for s in samples])),
        "detection_auroc_v0": float(roc_auc_score(y, v0_risk)),
        "localization": {g: {k: float(np.mean(v)) for k, v in h.items()} | {"n": len(h["learned_exact"])} for g, h in sorted(hits.items())},
    }
    out = ROOT / "eval" / "results" / "tracer_learned__agenthallu_dev.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"detection AUROC: learned {report['detection_auroc_learned']:.3f}, v0 {report['detection_auroc_v0']:.3f}")
    print(f"{'group':42} {'n':>4} {'exact':>6} {'+-1':>6} {'top3':>6} | {'v0':>6} {'first':>6} {'random':>6}")
    for g, m in report["localization"].items():
        print(f"{g:42} {m['n']:>4} {m['learned_exact']:>6.2f} {m['learned_within_1']:>6.2f} {m['learned_top3']:>6.2f} | {m['v0_exact']:>6.2f} {m['first_step']:>6.2f} {m['random']:>6.2f}")

    if args.no_save:
        return
    model = fit_tracer(samples, features)
    created = datetime.now(timezone.utc)
    manifest = {
        "version": f"{created:%Y%m%d-%H%M%S}-tracer",
        "created": created.isoformat(timespec="seconds"),
        "commit": git_commit(ROOT),
        "train": {"data": "agenthallu_dev.jsonl", "trajectories": len(samples)},
        "cross_validation": {"folds": args.folds, "exact": report["localization"]["all"]["learned_exact"], "detection_auroc": report["detection_auroc_learned"]},
    }
    folder = fusion.save(model, MODELS, manifest)
    print(f"saved {folder.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
