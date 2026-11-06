"""Choose the settings of the value check (values.py) on RAGTruth train only.

Recall, on two sets of edits built from grounded train answers, one per source group: "anywhere", where one number of a
sentence becomes another value of the same kind that the sources hold anywhere, and "same sentence", where it becomes
another value of a source sentence that holds the original one (the case of D-162: a value of the sentence the answer
restates, given to the wrong subject). An edit is caught when a confirmed finding lands on the edited number. False
alarms: 1,500 natural train answers, scored by the share of grounded answers with a confirmed finding. The setting with
the best recall on "same sentence" whose false alarms stay at or below 0.5% of grounded answers is chosen; NLI is run
once, at the loosest alignment (--cache keeps its readings for another grid). The dev suite is never used here.
Output: eval/results/values_train.json
"""

import argparse
import json
import pickle
import random
from pathlib import Path

from truth_guardian import values
from truth_guardian.schema import HallucinationType, Labels, Span, read_jsonl
from truth_guardian.text import Sentence, split_sentences

ROOT = Path(__file__).resolve().parents[1]
NATURAL = 1500
EDITS = 150
MAX_FALSE_ALARMS = 0.005
OVERLAPS = (0.3, 0.4, 0.5, 0.6, 0.7)
ENTAILMENTS = (0.7, 0.8, 0.9, 0.95)
CONTRADICTIONS = (0.5, 0.7, 0.8, 0.9, 0.95)
CONTRASTS = (None, 0.02, 0.05, 0.1, 0.2)
EDIT_KINDS = ("anywhere", "same sentence")


def edited(sample, rng: random.Random, kind: str = "anywhere"):
    """The answer with one number replaced by another value of the same kind from its sources, or None."""
    source_sentences = [values.values(s.text) for d in sample.documents for s in split_sentences(d.text)]
    in_sources = [v for found in source_sentences for v in found]
    known = frozenset().union(*(v.forms for v in in_sources)) if in_sources else frozenset()
    choices = []
    for sentence in split_sentences(sample.answer):
        held = values.values(sentence.text)
        for v in held:
            if not v.forms & known:
                continue
            pool = in_sources if kind == "anywhere" else [o for found in source_sentences if any(x.forms & v.forms for x in found) for o in found]
            others = sorted({o.text for o in pool if o.kind == v.kind and not o.forms & frozenset().union(*(h.forms for h in held))})
            choices += [(sentence.start + v.start, sentence.start + v.end, o) for o in others]
    if not choices:
        return None
    start, end, other = rng.choice(choices)
    answer = sample.answer[:start] + other + sample.answer[end:]
    span = Span(start=start, end=start + len(other), text=other, type=HallucinationType.CONTRADICTED, note=f"Original: {sample.answer[start:end]}")
    return sample.model_copy(update={"answer": answer, "labels": Labels(response="hallucinated", spans=[span])})


def measured(sample) -> list[tuple[int, int, list[values.Measured]]]:
    sentences = split_sentences(sample.answer)
    return [(s.start, s.end, m) for s, m in zip(sentences, values.measure(sample, sentences, min_overlap=min(OVERLAPS)))]


def findings(rows, overlap: float, entailment: float, contradiction: float, contrast: float | None) -> list[tuple[int, int]]:
    spans = []
    for start, end, found in rows:
        check = values.decide(Sentence(start, end, ""), [m for m in found if m.tried.overlap >= overlap], entailment, contradiction, contrast)
        if check.confirmed:
            spans.append(check.span)
    return spans



def edits(grounded, kind: str) -> list:
    out, groups = [], set()
    for s in grounded:
        if len(out) >= EDITS:
            break
        if s.meta.group_id in groups:
            continue
        e = edited(s, random.Random(f"values:{kind}:{s.id}"), kind)
        if e is not None:
            groups.add(s.meta.group_id)
            out.append((e.labels.spans[0], measured(e)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, help="keep NLI's readings here, to try another grid without reading again")
    args = parser.parse_args()
    if args.cache and args.cache.exists():
        natural_rows, edit_rows = pickle.loads(args.cache.read_bytes())
    else:
        train = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"]
        natural = random.Random("values-v1").sample(train, NATURAL)
        natural_ids = {s.id for s in natural}
        natural_rows = [(s.labels.response, s.labels.spans, measured(s)) for s in natural]
        print(f"natural: {len(natural_rows)} answers measured", flush=True)
        grounded = [s for s in train if s.labels.response == "grounded" and s.id not in natural_ids]
        random.Random("values-edits-v1").shuffle(grounded)
        edit_rows = {kind: edits(grounded, kind) for kind in EDIT_KINDS}
        print("edits:", {k: len(v) for k, v in edit_rows.items()}, flush=True)
        if args.cache:
            args.cache.write_bytes(pickle.dumps((natural_rows, edit_rows)))

    n_grounded = sum(label == "grounded" for label, _, _ in natural_rows)
    grid = []
    for overlap in OVERLAPS:
        for entailment in ENTAILMENTS:
            for contradiction in CONTRADICTIONS:
                for contrast in CONTRASTS:
                    setting = (overlap, entailment, contradiction, contrast)
                    alarms = hits = on_gold = 0
                    for label, gold, rows in natural_rows:
                        spans = findings(rows, *setting)
                        if not spans:
                            continue
                        if label == "grounded":
                            alarms += 1
                        else:
                            hits += 1
                            on_gold += any(a < g.end and g.start < b for a, b in spans for g in gold)
                    recall = {
                        kind: sum(any(a < span.end and span.start < b for a, b in findings(rows, *setting)) for span, rows in edit_rows[kind]) / len(edit_rows[kind])
                        for kind in EDIT_KINDS
                    }
                    grid.append({
                        "overlap": overlap, "entailment": entailment, "contradiction": contradiction, "contrast": contrast,
                        "recall": recall, "false_alarms": alarms / n_grounded, "hallucinated_answers_hit": hits, "hits_on_gold_spans": on_gold,
                    })
    allowed = [g for g in grid if g["false_alarms"] <= MAX_FALSE_ALARMS]
    best = lambda g: (g["recall"]["same sentence"], g["recall"]["anywhere"], -g["false_alarms"], g["entailment"], g["contradiction"])
    chosen = max(allowed, key=best) if allowed else None
    shipped = {"overlap": values.MIN_OVERLAP, "entailment": values.CONFIRM_ENTAILMENT, "contradiction": values.CONFIRM_CONTRADICTION, "contrast": values.CONFIRM_CONTRAST}
    report = {
        "natural_answers": NATURAL, "grounded_answers": n_grounded, "edits": {k: len(v) for k, v in edit_rows.items()},
        "max_false_alarms": MAX_FALSE_ALARMS, "shipped": next(g for g in grid if all(g[k] == v for k, v in shipped.items())),
        "chosen": chosen, "grid": grid,
    }
    print(json.dumps({"chosen": chosen, "shipped": report["shipped"]}, indent=1))
    out = ROOT / "eval" / "results" / "values_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
