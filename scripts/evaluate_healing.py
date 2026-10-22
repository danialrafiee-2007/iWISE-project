"""Evaluate self-healing on RAGTruth dev: does correcting an answer from its own report make it grounded?

A fixed sample of hallucinated and grounded answers (per task) runs through the full live pipeline, gets corrected
and is checked again. For hallucinated answers: how many are flagged, how many end up judged grounded, whether the
annotated hallucinated text is gone, and how much of the answer survives. For grounded answers: how often they are
changed at all (the cost of false alarms). Output: eval/results/healing.json
"""

import difflib
import json
import random
from pathlib import Path

import numpy as np

from truth_guardian import fusion
from truth_guardian.pipeline import heal
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
PER_TASK = {"hallucinated": 20, "grounded": 8}


def kept(before: str, after: str) -> float:
    return difflib.SequenceMatcher(None, before, after, autojunk=False).ratio()


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    dev = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl") if s.meta.quality == "good"]
    rng = random.Random("healing-v1")
    chosen = []
    for label, n in PER_TASK.items():
        for task in ("qa", "summary", "data2text"):
            pool = [s for s in dev if s.labels.response == label and s.meta.task == task]
            chosen += rng.sample(pool, min(n, len(pool)))

    rows, examples = {"hallucinated": [], "grounded": []}, []
    for i, s in enumerate(chosen, 1):
        healing = heal(s, model, model_version=manifest["version"])
        first, last = healing.reports[0], healing.reports[-1]
        gold = [s.answer[sp.start : sp.end] for sp in s.labels.spans]
        rows[s.labels.response].append({
            "flagged": first.verdict != "grounded",
            "changed": healing.answer != s.answer,
            "grounded_after": last.verdict == "grounded",
            "risk_before": first.risk,
            "risk_after": last.risk,
            "gold_removed": float(np.mean([g not in healing.answer for g in gold])) if gold else None,
            "kept": kept(s.answer, healing.answer),
            "rounds": len(healing.changes),
        })
        if healing.answer != s.answer and len(examples) < 12:
            examples.append({"id": s.id, "label": s.labels.response, "before": s.answer[:600], "after": healing.answer[:600], "risk": [round(first.risk, 3), round(last.risk, 3)]})
        print(f"{i}/{len(chosen)} {s.labels.response:12} risk {first.risk:.2f} -> {last.risk:.2f}  verdict {first.verdict} -> {last.verdict}", flush=True)

    def summary(items: list[dict]) -> dict:
        flagged = [r for r in items if r["flagged"]]
        gold = [r["gold_removed"] for r in flagged if r["gold_removed"] is not None]
        return {
            "n": len(items),
            "flagged": len(flagged) / len(items),
            "changed": float(np.mean([r["changed"] for r in items])),
            "grounded_after_among_flagged": float(np.mean([r["grounded_after"] for r in flagged])) if flagged else None,
            "mean_risk_before": float(np.mean([r["risk_before"] for r in items])),
            "mean_risk_after": float(np.mean([r["risk_after"] for r in items])),
            "gold_text_removed_among_flagged": float(np.mean(gold)) if gold else None,
            "text_kept": float(np.mean([r["kept"] for r in items])),
        }

    report = {"model_version": manifest["version"], **{label: summary(items) for label, items in rows.items()}, "examples": examples}
    out = ROOT / "eval" / "results" / "healing.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
