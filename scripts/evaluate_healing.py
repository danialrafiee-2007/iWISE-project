"""Evaluate self-healing on RAGTruth dev: does correcting an answer from its own report make it grounded?

A fixed sample of hallucinated and grounded answers (per task) runs through the full live pipeline, gets corrected
and is checked again, with two strategies: "basic" (flagged claims only, whole sentences, 2 rounds) and "full"
(clause-level removal, then leave-one-out attribution when no claim is flagged, up to 4 rounds). For hallucinated
answers: share judged grounded and share below the decision threshold afterwards, and, at the character level,
how much of the removed or replaced text was annotated as hallucinated (edit precision, against the chance rate of
annotated text in those answers) and how much annotated text was removed (edit recall). For grounded answers: how
often and how much they are changed (the cost of false alarms). Per-answer details are kept for error analysis.
Output: eval/results/healing.json
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
STRATEGIES = {"basic": {"max_rounds": 2, "attribute": False, "clauses": False}, "full": {}}


def edited_characters(before: str, after: str) -> set[int]:
    """Positions in `before` that were deleted or replaced on the way to `after`."""
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return {i for op, a, b, _, _ in matcher.get_opcodes() if op in ("delete", "replace") for i in range(a, b)}


def run(model, manifest, chosen, strategy: dict) -> tuple[dict, list[dict]]:
    rows, details = {"hallucinated": [], "grounded": []}, []
    for i, s in enumerate(chosen, 1):
        healing = heal(s, model, strategy=strategy, model_version=manifest["version"])
        first, last = healing.reports[0], healing.reports[-1]
        gold = {j for sp in s.labels.spans for j in range(sp.start, sp.end)}
        edited = edited_characters(s.answer, healing.answer)
        rows[s.labels.response].append({
            "flagged": first.verdict != "grounded",
            "changed": healing.answer != s.answer,
            "grounded_after": last.verdict == "grounded",
            "below_threshold_after": last.risk < last.response_threshold,
            "risk_before": first.risk,
            "risk_after": last.risk,
            "edited": len(edited),
            "edited_gold": len(edited & gold),
            "gold": len(gold),
            "length": len(s.answer),
        })
        details.append({
            "id": s.id, "task": s.meta.task, "label": s.labels.response,
            "verdicts": [r.verdict for r in healing.reports], "risks": [round(r.risk, 3) for r in healing.reports],
            "changes": [[c.reason.split(":")[0] for c in round_] for round_ in healing.changes],
            "after": healing.answer[:600] if healing.answer != s.answer else None,
        })
        print(f"{i}/{len(chosen)} {s.labels.response:12} risk {first.risk:.2f} -> {last.risk:.2f}  verdict {first.verdict} -> {last.verdict}", flush=True)
    return rows, details


def summary(items: list[dict]) -> dict:
    flagged = [r for r in items if r["flagged"]]
    mean = lambda key, rows: float(np.mean([r[key] for r in rows])) if rows else None
    edited, gold = sum(r["edited"] for r in items), sum(r["gold"] for r in items)
    return {
        "n": len(items),
        "flagged": len(flagged) / len(items),
        "changed": mean("changed", items),
        "grounded_after_among_flagged": mean("grounded_after", flagged),
        "below_threshold_after_among_flagged": mean("below_threshold_after", flagged),
        "mean_risk_before": mean("risk_before", items),
        "mean_risk_after": mean("risk_after", items),
        "text_edited": edited / sum(r["length"] for r in items),
        "edit_precision": sum(r["edited_gold"] for r in items) / edited if edited else None,
        "chance_precision": gold / sum(r["length"] for r in items),
        "edit_recall": sum(r["edited_gold"] for r in items) / gold if gold else None,
    }


def choose(path: Path, seed: str) -> list:
    """A fixed sample per label and task, as in PER_TASK."""
    samples = [s for s in read_jsonl(path) if s.meta.quality == "good"]
    rng, chosen = random.Random(seed), []
    for label, n in PER_TASK.items():
        for task in ("qa", "summary", "data2text"):
            pool = [s for s in samples if s.labels.response == label and s.meta.task == task]
            chosen += rng.sample(pool, min(n, len(pool)))
    return chosen


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    chosen = choose(ROOT / "data/processed/ragtruth_dev.jsonl", "healing-v1")

    report = {"model_version": manifest["version"], "strategies": {}}
    for name, strategy in STRATEGIES.items():
        rows, details = run(model, manifest, chosen, strategy)
        report["strategies"][name] = {**{label: summary(items) for label, items in rows.items()}, "details": details}
    out = ROOT / "eval" / "results" / "healing.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    for name, result in report["strategies"].items():
        print(name, json.dumps({k: v for k, v in result.items() if k != "details"}, indent=1))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
