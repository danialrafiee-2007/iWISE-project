"""Score any hallucination detector on TG-Bench, or produce Truth Guardian's own predictions to compare against.

Predictions are JSONL lines {"id": ..., "score": risk in [0, 1], "spans": [[start, end], ...]} for the
Fool-the-Guardian part (spans optional) and {"id": ..., "score": ..., "step": suspected step} for TG-Agent (step
optional). Reported per edit kind: AUROC against the unedited controls and, with spans, how often the edited words
are hit; for TG-Agent: detection AUROC and exact / within-one step accuracy on hallucinated runs.
--ours writes this project's predictions (fusion model with overrides; learned tracer) and scores them.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "benchmark"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_fool(labels: list[dict], predictions: dict[str, dict]) -> dict:
    controls = [predictions[r["id"]]["score"] for r in labels if r["kind"] == "control" and r["id"] in predictions]
    by_kind = defaultdict(list)
    for r in labels:
        if r["kind"] != "control" and r["id"] in predictions:
            by_kind[r["kind"]].append((r, predictions[r["id"]]))
    out = {"controls": len(controls)}
    for kind, rows in sorted(by_kind.items()):
        scores = [p["score"] for _, p in rows]
        result = {"n": len(rows), "auroc_vs_controls": float(roc_auc_score([1] * len(scores) + [0] * len(controls), scores + controls))}
        if all("spans" in p for _, p in rows):
            hit = [any(a < s["end"] and s["start"] < b for a, b in p["spans"] for s in r["spans"]) for r, p in rows]
            result["edit_located"] = float(np.mean(hit))
        out[kind] = result
    return out


def score_agent(labels: list[dict], predictions: dict[str, dict]) -> dict:
    rows = [(r, predictions[r["id"]]) for r in labels if r["id"] in predictions]
    y = [r["response"] == "hallucinated" for r, _ in rows]
    out = {"n": len(rows), "detection_auroc": float(roc_auc_score(y, [p["score"] for _, p in rows]))}
    stepped = [(r, p) for r, p in rows if r["responsible_step"] is not None and "step" in p]
    if stepped:
        out["step_exact"] = float(np.mean([p["step"] == r["responsible_step"] for r, p in stepped]))
        out["step_within_one"] = float(np.mean([abs(p["step"] - r["responsible_step"]) <= 1 for r, p in stepped]))
    return out


def our_predictions(out_dir: Path) -> tuple[Path, Path]:
    from truth_guardian import fusion
    from truth_guardian.overrides import cached_predictions
    from truth_guardian.schema import read_jsonl

    model, _ = fusion.load(ROOT / "models" / "fusion")
    samples, predictions = cached_predictions(model, ROOT / "data/processed/perturb_dev.jsonl", ROOT / "data" / "features")
    fool = out_dir / "truth_guardian.fool_the_guardian.jsonl"
    with fool.open("w", encoding="utf-8", newline="\n") as f:
        for s in samples:
            p = predictions[s.id]
            spans = [[x.start, x.end] for x in p.sentences if x.score >= model.thresholds["sentence"]]
            f.write(json.dumps({"id": s.id, "score": p.score, "spans": spans}) + "\n")
    tracer, _ = fusion.load(ROOT / "models" / "tracer")
    agent = out_dir / "truth_guardian.tg_agent.jsonl"
    with agent.open("w", encoding="utf-8", newline="\n") as f:
        for s in read_jsonl(ROOT / "data/processed/tg_agent_dev.jsonl"):
            traces, probs, risk = tracer.analyse(s)
            step = max(zip(probs, traces), key=lambda pt: (pt[0], -pt[1].step))[1].step if traces else None
            f.write(json.dumps({"id": s.id, "score": float(risk), **({"step": step} if step is not None else {})}) + "\n")
    return fool, agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fool", type=Path, help="predictions for the Fool-the-Guardian part")
    parser.add_argument("--agent", type=Path, help="predictions for TG-Agent")
    parser.add_argument("--ours", action="store_true")
    args = parser.parse_args()
    if args.ours:
        args.fool, args.agent = our_predictions(RELEASE)
    report = {}
    if args.fool:
        report["fool_the_guardian"] = score_fool(read(RELEASE / "fool_the_guardian.labels.jsonl"), {p["id"]: p for p in read(args.fool)})
    if args.agent:
        report["tg_agent"] = score_agent(read(RELEASE / "tg_agent.labels.jsonl"), {p["id"]: p for p in read(args.agent)})
    print(json.dumps(report, indent=1))
    if args.ours:
        (RELEASE / "truth_guardian.scores.json").write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
