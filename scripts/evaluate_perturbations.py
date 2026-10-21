"""Score the "Fool the Guardian" suite: per edit kind, is it detected, located, and correctly fixed?

The fusion model is trained on train with the given signals and thresholds are tuned on RAGTruth dev,
then applied unchanged to the suite. Output: eval/results/perturbations__<name>.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.correct import suggest
from truth_guardian.evaluation import best_span_threshold, best_threshold
from truth_guardian.features import load_rows, usable
from truth_guardian.perturb import KINDS
from truth_guardian.schema import read_jsonl
from truth_guardian.symbolic import normalize_number
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"


def same_value(a: str, b: str) -> bool:
    if any(c.isdigit() for c in a) and any(c.isdigit() for c in b):
        return bool(normalize_number(a) & normalize_number(b))
    return a.strip().lower() == b.strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", nargs="+", required=True)
    parser.add_argument("--kind", choices=["logreg", "hgb", "ensemble"], default="hgb")
    parser.add_argument("--no-structure", action="store_true", help="drop position, length and count features")
    args = parser.parse_args()
    structure = not args.no_structure

    def load(name: str, good_only: bool = False):
        path = ROOT / f"data/processed/{name}.jsonl"
        rows = load_rows(args.signals, path, FEATURES)
        return usable([s for s in read_jsonl(path) if not good_only or s.meta.quality == "good"], rows), rows

    train, train_rows = load("ragtruth_train", good_only=True)
    dev, dev_rows = load("ragtruth_dev")
    suite, suite_rows = load("perturb_dev")
    model, _, _ = fusion.fit(train, fusion.build_table(train, train_rows, args.signals, structure), args.signals, args.kind)

    dev_predictions = {p.id: p for p in model.predictions(dev, fusion.build_table(dev, dev_rows, args.signals, structure))}
    y_dev = np.array([s.labels.response == "hallucinated" for s in dev], dtype=int)
    threshold = best_threshold(y_dev, np.array([dev_predictions[s.id].score for s in dev]))
    sentence_threshold = best_span_threshold(dev, dev_predictions)
    predictions = {p.id: p for p in model.predictions(suite, fusion.build_table(suite, suite_rows, args.signals, structure))}

    def kind_of(sample_id: str) -> str:
        return sample_id.split("-")[1]

    scores = defaultdict(list)
    located, fixable, fixed = defaultdict(int), defaultdict(int), defaultdict(int)
    for s in suite:
        kind = kind_of(s.id)
        p = predictions[s.id]
        scores[kind].append(p.score)
        if kind == "control":
            continue
        span = s.labels.spans[0]
        flagged = [(x.start, x.end) for x in p.sentences if x.score >= sentence_threshold]
        located[kind] += any(a < span.end and span.start < b for a, b in flagged)
        if kind in {"number", "entity"}:
            fixable[kind] += 1
            original = span.note.removeprefix("Original: ")
            sentence = next(x for x in split_sentences(s.answer) if x.start <= span.start < x.end)
            fixed[kind] += any(
                g.replacement is not None and g.start < span.end and span.start < g.end and same_value(g.replacement, original)
                for g in suggest(s, sentence)
            )

    controls = scores["control"]
    report = {
        "signals": args.signals,
        "kind": args.kind,
        "structure": structure,
        "train_samples": len(train),
        "response_threshold": threshold,
        "sentence_threshold": sentence_threshold,
        "control_false_alarm_rate": float(np.mean(np.array(controls) >= threshold)),
        "by_edit": {},
    }
    for kind in KINDS:
        values = scores[kind]
        report["by_edit"][kind] = {
            "n": len(values),
            "detected": float(np.mean(np.array(values) >= threshold)),
            "auroc_vs_controls": float(roc_auc_score([1] * len(values) + [0] * len(controls), values + controls)),
            "located": located[kind] / len(values),
            **({"fixed_exactly": fixed[kind] / fixable[kind]} if fixable[kind] else {}),
        }
    name = f"{args.kind}-{'+'.join(args.signals)}" + ("" if structure else "-nostructure")
    out = ROOT / "eval" / "results" / f"perturbations__{name}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"{name}: control false alarms {report['control_false_alarm_rate']:.2f}")
    for kind, m in report["by_edit"].items():
        fix = f"  fixed {m['fixed_exactly']:.2f}" if "fixed_exactly" in m else ""
        print(f"  {kind:9} n={m['n']:3}  detected {m['detected']:.2f}  AUROC {m['auroc_vs_controls']:.3f}  located {m['located']:.2f}{fix}")


if __name__ == "__main__":
    main()
