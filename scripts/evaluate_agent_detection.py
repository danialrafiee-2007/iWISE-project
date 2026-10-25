"""Can the guardian tell hallucinating agent runs from faithful ones? AgentHallu dev only, every score out of fold.

Three scores per trajectory: the tracer's run risk (the shipped configuration, content features, refit on each fold's
training trajectories), the fusion model's risk for the final answer checked against the tool outputs (as the app's
answer check does; overrides applied), and both stacked by a logistic regression. Folds are grouped by source
question (5), so no trajectory is scored by a model that saw it or a sibling run of its question. The trajectories
are capped as the app caps an agent's steps (5,000 characters per step and tool output; some AgentHallu tool outputs
exceed a megabyte). Answer signals must be cached first (extract_features.py).
Output: eval/results/agent_detection__<data>.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.adapt import _logit
from truth_guardian.overrides import cached_predictions
from truth_guardian.tracer import combined_features, fit_tracer, trace, trajectory_features

ROOT = Path(__file__).resolve().parents[1]
FOLDS = 5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/processed/agenthallu_dev_capped.jsonl")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts:
        parser.error("this study runs on dev only")

    model = fusion.load(ROOT / "models" / "fusion")[0]
    samples, predictions = cached_predictions(model, args.data, ROOT / "data" / "features")
    y = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
    fold_of = fusion.group_folds([s.meta.group_id for s in samples], FOLDS)
    features = {s.id: (traces, *combined_features(s, traces, None)) for s in samples for traces in [trace(s)]}
    run = np.zeros(len(samples))
    for k in range(FOLDS):
        tracer = fit_tracer([s for s in samples if fold_of[s.meta.group_id] != k], features, False, True)
        for i, s in enumerate(samples):
            if fold_of[s.meta.group_id] == k:
                _, matrix, answer = features[s.id]
                run[i] = float(tracer.detector.predict_proba(trajectory_features(matrix[:, tracer.columns], answer).reshape(1, -1))[:, 1][0])
    answer_risk = np.array([predictions[s.id].score for s in samples])
    stacked_inputs = np.column_stack([_logit(run), _logit(answer_risk)])
    stacked = np.zeros(len(samples))
    for k in range(FOLDS):
        train = np.array([fold_of[s.meta.group_id] != k for s in samples])
        stacked[~train] = LogisticRegression(C=1.0).fit(stacked_inputs[train], y[train]).predict_proba(stacked_inputs[~train])[:, 1]
    scores = {"tracer_run_risk": run, "answer_risk": answer_risk, "stacked": stacked}
    report = {
        "data": args.data.name, "trajectories": len(samples), "hallucinated": int(y.sum()), "folds": FOLDS,
        "auroc": {k: float(roc_auc_score(y, v)) for k, v in scores.items()},
        "by_category": {},
    }
    grounded = y == 0
    for c in sorted({s.labels.category for s in samples if s.labels.category}):
        mask = np.array([s.labels.category == c for s in samples]) | grounded
        report["by_category"][c] = {"n": int((mask & ~grounded).sum()), **{k: float(roc_auc_score(y[mask], v[mask])) for k, v in scores.items()}}
    out = ROOT / "eval" / "results" / f"agent_detection__{args.data.stem}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
