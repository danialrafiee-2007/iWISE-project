"""Evaluate the provenance tracer on AgentHallu: does it find the step where the hallucination started?

Reports exact, +/-1 and top-3 step accuracy on hallucinated trajectories, detection AUROC, and the same
for simple baselines (always step 1, always the last step, a random step). Dev only unless --final.
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.schema import read_jsonl
from truth_guardian.tracer import trace

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/processed/agenthallu_dev.jsonl")
    parser.add_argument("--learned", action="store_true", help="use the saved learned tracer (models/tracer) instead of v0")
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.data.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    learned = fusion.load(ROOT / "models" / "tracer")[0] if args.learned else None
    samples = list(read_jsonl(args.data))
    started = time.perf_counter()
    hits = defaultdict(lambda: defaultdict(list))
    y, scores, lengths = [], [], []
    for s in samples:
        if learned is not None:
            traces, probs, risk = learned.analyse(s)
            step_scores = [float(p) for p in probs]
        else:
            traces = trace(s)
            step_scores = [t.score for t in traces]
            risk = max(step_scores, default=0.0)
        y.append(int(s.labels.response == "hallucinated"))
        scores.append(risk)
        lengths.append(len(s.agent_log or []))
        if s.labels.responsible_step is None or not traces:
            continue
        gold = s.labels.responsible_step
        ranked = [t.step for score, t in sorted(zip(step_scores, traces), key=lambda st: (-st[0], st[1].step))]
        steps = [t.step for t in traces]
        groups = ("all", f"category: {s.labels.category}", f"framework: {s.id.split('-')[1]}", f"domain: {s.meta.task}")
        for g in groups:
            h = hits[g]
            h["tracer_exact"].append(ranked[0] == gold)
            h["tracer_within_1"].append(abs(ranked[0] - gold) <= 1)
            h["tracer_top3"].append(gold in ranked[:3])
            h["baseline_first_step"].append(steps[0] == gold)
            h["baseline_last_step"].append(steps[-1] == gold)
            h["baseline_random"].append(1 / len(steps))

    report = {
        "data": args.data.name,
        "trajectories": len(samples),
        "seconds_per_trajectory": (time.perf_counter() - started) / len(samples),
        "detection_auroc": float(roc_auc_score(y, scores)),
        "detection_auroc_length_only": float(roc_auc_score(y, lengths)),
        "localization": {g: {k: float(np.mean(v)) for k, v in h.items()} | {"n": len(h["tracer_exact"])} for g, h in sorted(hits.items())},
    }
    out = ROOT / "eval" / "results" / f"tracer{'_learned' if args.learned else ''}__{args.data.stem}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"{report['trajectories']} trajectories, {report['seconds_per_trajectory']:.2f} s each; detection AUROC {report['detection_auroc']:.3f} (length only {report['detection_auroc_length_only']:.3f})")
    print(f"{'group':48} {'n':>4} {'exact':>6} {'+-1':>6} {'top3':>6} | {'first':>6} {'last':>6} {'random':>6}")
    for g, m in report["localization"].items():
        print(f"{g:48} {m['n']:>4} {m['tracer_exact']:>6.2f} {m['tracer_within_1']:>6.2f} {m['tracer_top3']:>6.2f} | {m['baseline_first_step']:>6.2f} {m['baseline_last_step']:>6.2f} {m['baseline_random']:>6.2f}")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
