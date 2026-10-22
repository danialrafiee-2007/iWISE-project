"""Choose the meaning-shift confirmation settings on natural RAGTruth train answers.

For each rule (role swap, quantifier, certainty) and each NLI entailment cutoff, counts confirmed sentences in
grounded answers (false alarms) and in hallucinated answers (on or off an annotated span). For rules that override
the verdict, the loosest cutoff with no false alarm on grounded answers is chosen, as for the polarity check (D-060);
for advisory rules the rate of cautions on grounded answers at their fixed setting is reported. Candidate examples
are saved for reading by hand. Output: eval/results/shifts_train.json
"""

import json
import random
from pathlib import Path

from truth_guardian import models
from truth_guardian.schema import read_jsonl
from truth_guardian.shifts import CONFIRM_ENTAILMENT, KINDS, OVERRIDE_KINDS, check_sentence
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SIZE = 1500
CUTOFFS = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01)


def main() -> None:
    good = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"]
    samples = random.Random("shifts-v1").sample(good, SAMPLE_SIZE)
    candidates = []
    for s in samples:
        texts = tuple(d.text for d in s.documents)
        gold = [(sp.start, sp.end) for sp in s.labels.spans]
        for sentence in split_sentences(s.answer):
            check = check_sentence(sentence, texts)
            if check.candidate:
                on_span = any(sentence.start < b and a < sentence.end for a, b in gold)
                candidates.append((s, sentence, check, on_span))
    entailment = models.nli_probabilities([(c.evidence, sentence.text) for _, sentence, c, _ in candidates]) if candidates else []
    index = models.NLI_LABELS.index("entailment")

    report = {"answers": len(samples), "grounded_answers": sum(s.labels.response == "grounded" for s in samples), "rules": {}}
    for kind in KINDS:
        rows = [(s, c, on_span, float(e[index])) for (s, _, c, on_span), e in zip(candidates, entailment) if c.kind == kind]
        grid = {}
        for cutoff in CUTOFFS:
            fired = [(s, on_span) for s, _, on_span, e in rows if e < cutoff]
            grid[str(cutoff)] = {
                "grounded_answers_flagged": len({s.id for s, _ in fired if s.labels.response == "grounded"}),
                "hallucinated_on_span": sum(on for s, on in fired if s.labels.response == "hallucinated"),
                "hallucinated_off_span": sum(not on for s, on in fired if s.labels.response == "hallucinated"),
            }
        safe = [c for c in CUTOFFS if grid[str(c)]["grounded_answers_flagged"] == 0]
        setting = grid[str(CONFIRM_ENTAILMENT[kind])]
        report["rules"][kind] = {
            "candidates": len(rows),
            "overrides_verdict": kind in OVERRIDE_KINDS,
            "loosest_cutoff_without_false_alarms": max(safe, default=0.0),
            "setting": CONFIRM_ENTAILMENT[kind],
            "grounded_answers_flagged_at_setting": setting["grounded_answers_flagged"],
            "grounded_rate_at_setting": setting["grounded_answers_flagged"] / report["grounded_answers"],
            "grid": grid,
            "examples": [
                {"label": s.labels.response, "on_span": on, "entailment": round(e, 3), "detail": c.detail, "evidence": c.evidence[:200]}
                for s, c, on, e in rows[:25]
            ],
        }
        r = report["rules"][kind]
        print(f"{kind}: {len(rows)} candidates, loosest safe cutoff {r['loosest_cutoff_without_false_alarms']}, setting {r['setting']}: grounded rate {r['grounded_rate_at_setting']:.3f}")
        for cutoff, g in grid.items():
            print(f"  entailment < {cutoff:>4}: grounded flagged {g['grounded_answers_flagged']:>3}, hallucinated on span {g['hallucinated_on_span']:>3}, off span {g['hallucinated_off_span']:>3}")
    out = ROOT / "eval" / "results" / "shifts_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
