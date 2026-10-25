"""Choose the outdated-value check's settings (stale.py) on faithful agent runs, and see what it catches.

For every final answer of AgentHallu dev (capped as the app caps steps) and TG-Agent dev, records the NLI entailment
of each answer sentence by every tool output and its contradiction by every later one. For each pair of cutoffs it
counts faithful runs that would be flagged (false alarms) and hallucinating runs flagged. The loosest setting with at
most 1% false alarms on the faithful runs of both sets is chosen. Output: eval/results/stale_dev.json
"""

import json
from pathlib import Path

from truth_guardian import models, stale
from truth_guardian.schema import read_jsonl
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
SETS = ("agenthallu_dev_capped", "tg_agent_dev")
CUTOFFS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
MAX_FALSE_ALARMS = 0.01


def flagged(rows: list[tuple[int, int, float, float]], entail: float, contra: float) -> bool:
    """rows: (sentence, step, entailment, contradiction)."""
    for i in {r[0] for r in rows}:
        ordered = sorted(r[1:] for r in rows if r[0] == i)
        for a, (_, e, _) in enumerate(ordered):
            if e >= entail and any(c >= contra for _, _, c in ordered[a + 1 :]):
                return True
    return False


def measured(sample) -> list[tuple[int, int, float, float]]:
    sentences = split_sentences(sample.answer)
    rows = []

    def classify(pairs):
        probs = models.nli_probabilities(pairs)
        for (premise, hypothesis), p in zip(pairs, probs):
            i = next(k for k, s in enumerate(sentences) if s.text == hypothesis)
            step = next(st for st, texts in stale._observations(sample) if premise in texts)
            rows.append((i, step, float(p[models.NLI_LABELS.index("entailment")]), float(p[models.NLI_LABELS.index("contradiction")])))
        return probs

    stale.check_sample(sample, sentences, classify)
    return rows


def main() -> None:
    runs = []
    for name in SETS:
        for s in read_jsonl(ROOT / "data/processed" / f"{name}.jsonl"):
            runs.append((name, s.labels.response, measured(s)))
        print(f"{name}: measured", flush=True)
    grid = []
    for entail in CUTOFFS:
        for contra in CUTOFFS:
            row = {"entailment": entail, "contradiction": contra}
            for name in SETS:
                faithful = [r for n, label, r in runs if n == name and label == "grounded"]
                wrong = [r for n, label, r in runs if n == name and label == "hallucinated"]
                row[f"{name}_false_alarms"] = sum(flagged(r, entail, contra) for r in faithful) / max(len(faithful), 1)
                row[f"{name}_hallucinated_flagged"] = sum(flagged(r, entail, contra) for r in wrong) / max(len(wrong), 1)
            grid.append(row)
    allowed = [g for g in grid if all(g[f"{n}_false_alarms"] <= MAX_FALSE_ALARMS for n in SETS)]
    chosen = max(allowed, key=lambda g: (sum(g[f"{n}_hallucinated_flagged"] for n in SETS), -g["entailment"], -g["contradiction"])) if allowed else None
    report = {"sets": list(SETS), "max_false_alarms": MAX_FALSE_ALARMS, "chosen": chosen, "grid": grid}
    out = ROOT / "eval" / "results" / "stale_dev.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(chosen, indent=1))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
