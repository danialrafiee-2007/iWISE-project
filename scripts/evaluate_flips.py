"""Choose the flip-test settings (flips.py) on RAGTruth train only.

Recall: edits of each kind (opposite word, stronger quantifier, more certainty) built from grounded train answers, one
per source group, scored by whether a confirmed flip lands on the edited word. False alarms: 1,500 natural train
answers, scored by the share of grounded answers with a confirmed flip of that kind. For each kind, the setting with the
best recall whose false alarms stay at or below 0.5% of grounded answers is chosen. The dev suite is never used here.
Output: eval/results/flips_train.json
"""

import json
import random
from collections import defaultdict
from pathlib import Path

from truth_guardian import flips, models
from truth_guardian.perturb import perturb
from truth_guardian.schema import read_jsonl
from truth_guardian.signals import premises
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
NATURAL = 1500
EDITS = 150
MAX_FALSE_ALARMS = 0.005
FLIPPED = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95)
GAINS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)


def measured(sample) -> list[list[tuple]]:
    """Per sentence: (kind, start, end, original entailment, flipped entailment) for every candidate."""
    sentences = split_sentences(sample.answer)
    found = [[] for _ in sentences]
    for i, (sentence, premise) in enumerate(zip(sentences, premises(sample, sentences))):
        candidates = flips.candidates(sentence, flips.KINDS) if premise else []
        if not candidates:
            continue
        probs = models.nli_probabilities([(premise, sentence.text)] + [(premise, flips._swap(sentence, f)) for f in candidates])
        entail = [float(p[models.NLI_LABELS.index("entailment")]) for p in probs]
        found[i] = [(f.kind, f.start, f.end, entail[0], e) for f, e in zip(candidates, entail[1:])]
    return found


def confirmed(row: tuple, flipped: float, gain: float) -> bool:
    _, _, _, e0, e1 = row
    return e1 >= flipped and e1 - e0 >= gain


def main() -> None:
    train = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"]
    natural = random.Random("flips-v1").sample(train, NATURAL)
    natural_rows = [(s.labels.response, measured(s)) for s in natural]
    print(f"natural: {len(natural_rows)} answers measured", flush=True)

    grounded = [s for s in train if s.labels.response == "grounded"]
    random.Random("flips-edits-v1").shuffle(grounded)
    edit_rows = defaultdict(list)
    for kind in flips.KINDS:
        groups = set()
        for s in grounded:
            if len(edit_rows[kind]) >= EDITS:
                break
            if s.meta.group_id in groups or s in natural:
                continue
            edited = perturb(s, kind, random.Random(f"flips:{kind}:{s.id}"), None)
            if edited is None:
                continue
            groups.add(s.meta.group_id)
            span = edited.labels.spans[0]
            rows = [r for sentence in measured(edited) for r in sentence]
            edit_rows[kind].append([r for r in rows if r[0] == kind and r[1] < span.end and span.start < r[2]])
        print(f"{kind}: {len(edit_rows[kind])} edits measured", flush=True)

    n_grounded = sum(label == "grounded" for label, _ in natural_rows)
    grid, chosen = {}, {}
    for kind in flips.KINDS:
        grid[kind] = []
        for flipped in FLIPPED:
            for gain in GAINS:
                ok = lambda r: r[0] == kind and confirmed(r, flipped, gain)
                false_alarms = sum(label == "grounded" and any(ok(r) for s in rows for r in s) for label, rows in natural_rows) / n_grounded
                natural_hits = sum(label == "hallucinated" and any(ok(r) for s in rows for r in s) for label, rows in natural_rows)
                recall = sum(any(confirmed(r, flipped, gain) for r in rows) for rows in edit_rows[kind]) / len(edit_rows[kind])
                grid[kind].append({"flipped": flipped, "gain": gain, "recall": recall, "false_alarms": false_alarms, "hallucinated_answers_hit": natural_hits})
        allowed = [g for g in grid[kind] if g["false_alarms"] <= MAX_FALSE_ALARMS]
        chosen[kind] = max(allowed, key=lambda g: (g["recall"], -g["false_alarms"], -g["flipped"], -g["gain"])) if allowed else None
        print(kind, chosen[kind], flush=True)
    report = {
        "natural_answers": len(natural_rows), "grounded_answers": n_grounded, "edits_per_kind": EDITS,
        "max_false_alarms": MAX_FALSE_ALARMS, "chosen": chosen, "grid": grid,
        "candidate_on_edit": {k: sum(bool(rows) for rows in v) / len(v) for k, v in edit_rows.items()},
    }
    out = ROOT / "eval" / "results" / "flips_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
