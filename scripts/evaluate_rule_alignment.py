"""How strict must "the answer nearly restates a source sentence" be for the polarity and meaning-shift rules?

Both rules compare an answer sentence only with source sentences it nearly restates (D-060, D-083: at least 65% of
its content words, source at most 2.5 times longer), and most edits in summaries fail that test. For looser settings
this counts, on RAGTruth train only: edits built from grounded train answers (opposite word, stronger quantifier, more
certainty; 150 each, one per source group) whose rule fires on the edited word after NLI confirmation, and natural
train answers (1,500) whose grounded ones get a confirmed finding (false alarms). The loosest setting per rule with
false alarms at or below 0.5% of grounded answers is chosen. Output: eval/results/rule_alignment_train.json
"""

import json
import random
from pathlib import Path

from truth_guardian import models, polarity, shifts
from truth_guardian.perturb import perturb
from truth_guardian.schema import read_jsonl
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
NATURAL = 1500
EDITS = 150
MAX_FALSE_ALARMS = 0.005
OVERLAPS = (0.65, 0.6, 0.55, 0.5, 0.45, 0.4)
RATIOS = (2.5, 4.0)
KIND_RULE = {"antonym": "polarity", "quantifier": "quantifier", "certainty": "certainty"}


def findings(sample, overlap: float, ratio: float) -> list[tuple[str, list[tuple[int, int]]]]:
    """Confirmed findings (rule, spans) for one answer under one alignment setting."""
    polarity.MIN_OVERLAP, polarity.MAX_LENGTH_RATIO = overlap, ratio
    shifts.MIN_OVERLAP = overlap
    shifts.MAX_LENGTH_RATIO = ratio
    sentences = split_sentences(sample.answer)
    out = [("polarity", c.antonym_spans + c.negation_spans) for c in polarity.check_sample(sample, sentences) if c.confirmed]
    out += [(c.kind, c.spans) for c in shifts.check_sample(sample, sentences) if c.confirmed and c.kind in ("quantifier", "certainty")]
    return out


def main() -> None:
    original = (polarity.MIN_OVERLAP, polarity.MAX_LENGTH_RATIO)
    train = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"]
    natural = random.Random("alignment-v1").sample(train, NATURAL)
    natural_ids = {s.id for s in natural}
    grounded = [s for s in train if s.labels.response == "grounded" and s.id not in natural_ids]
    random.Random("alignment-edits-v1").shuffle(grounded)
    edits = {}
    for kind in KIND_RULE:
        chosen, groups = [], set()
        for s in grounded:
            if len(chosen) >= EDITS:
                break
            if s.meta.group_id in groups:
                continue
            edited = perturb(s, kind, random.Random(f"alignment:{kind}:{s.id}"), None)
            if edited is not None:
                groups.add(s.meta.group_id)
                chosen.append(edited)
        edits[kind] = chosen

    n_grounded = sum(s.labels.response == "grounded" for s in natural)
    grid = []
    for ratio in RATIOS:
        for overlap in OVERLAPS:
            row = {"overlap": overlap, "length_ratio": ratio}
            alarms = {rule: 0 for rule in KIND_RULE.values()}
            hits = {rule: 0 for rule in KIND_RULE.values()}
            for s in natural:
                rules = {rule for rule, _ in findings(s, overlap, ratio)}
                for rule in rules:
                    if s.labels.response == "grounded":
                        alarms[rule] += 1
                    else:
                        hits[rule] += 1
            for kind, rule in KIND_RULE.items():
                found = 0
                for e in edits[kind]:
                    span = e.labels.spans[0]
                    found += any(r == rule and any(a < span.end and span.start < b for a, b in spans) for r, spans in findings(e, overlap, ratio))
                row[kind] = {"recall": found / len(edits[kind]), "false_alarms": alarms[rule] / n_grounded, "hallucinated_answers_hit": hits[rule]}
            grid.append(row)
            print(json.dumps(row), flush=True)
    polarity.MIN_OVERLAP, polarity.MAX_LENGTH_RATIO = original
    chosen = {}
    for kind in KIND_RULE:
        allowed = [g for g in grid if g[kind]["false_alarms"] <= MAX_FALSE_ALARMS]
        chosen[kind] = max(allowed, key=lambda g: (g[kind]["recall"], g["overlap"], -g["length_ratio"])) if allowed else None
    report = {"natural_answers": NATURAL, "grounded_answers": n_grounded, "edits_per_kind": EDITS, "max_false_alarms": MAX_FALSE_ALARMS, "chosen": chosen, "grid": grid}
    out = ROOT / "eval" / "results" / "rule_alignment_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
