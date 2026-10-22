"""Choose the healing contribution floor on RAGTruth train (dev stays for evaluate_healing.py).

The same per-task sample design as on dev, drawn from train. For each floor, the character-level F1 of the edits
over hallucinated and grounded answers together: precision = annotated hallucinated characters edited / all
characters edited (edits to grounded answers count against it), recall = annotated characters edited / all
annotated characters. Output: eval/results/healing_train.json
"""

import json
from pathlib import Path

from evaluate_healing import choose, edited_characters

from truth_guardian import fusion
from truth_guardian.pipeline import heal

ROOT = Path(__file__).resolve().parents[1]
FLOORS = (0.03, 0.05, 0.1, 0.15, 0.2)


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    chosen = choose(ROOT / "data/processed/ragtruth_train.jsonl", "healing-train-v1")
    report = {"model_version": manifest["version"], "samples": len(chosen), "floors": {}}
    for floor in FLOORS:
        edited = edited_gold = gold = grounded_after = flagged = 0
        for s in chosen:
            healing = heal(s, model, strategy={"min_contribution": floor}, model_version=manifest["version"])
            spans = {j for sp in s.labels.spans for j in range(sp.start, sp.end)}
            changed = edited_characters(s.answer, healing.answer)
            edited, edited_gold, gold = edited + len(changed), edited_gold + len(changed & spans), gold + len(spans)
            if s.labels.response == "hallucinated" and healing.reports[0].verdict != "grounded":
                flagged += 1
                grounded_after += healing.reports[-1].verdict == "grounded"
        precision, recall = edited_gold / max(edited, 1), edited_gold / max(gold, 1)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        report["floors"][str(floor)] = {"precision": precision, "recall": recall, "f1": f1, "grounded_after_among_flagged": grounded_after / max(flagged, 1)}
        print(f"floor {floor}: precision {precision:.3f} recall {recall:.3f} F1 {f1:.3f} grounded after {grounded_after / max(flagged, 1):.2f}", flush=True)
    report["chosen"] = float(max(report["floors"], key=lambda k: report["floors"][k]["f1"]))
    out = ROOT / "eval" / "results" / "healing_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"chosen floor {report['chosen']}; saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
