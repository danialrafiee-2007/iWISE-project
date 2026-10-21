"""Analyse a fusion configuration: ablation, learning curve, train error analysis, cross-dataset, spans and types.

Error analysis uses out-of-fold scores on train (never dev), so dev stays an honest check.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.data.splits import TRAIN_SUBSET_SEED, sample_groups
from truth_guardian.evaluation import best_span_threshold, span_counts
from truth_guardian.explain import explain_sentence, refine_spans
from truth_guardian.features import load_rows, usable
from truth_guardian.labels import sentence_types
from truth_guardian.schema import HallucinationType, Sample, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"
XDEV = [ROOT / f"data/processed/xdev_halueval_{t}.jsonl" for t in ("qa", "dialogue", "summary")]


def auroc(y, s) -> float | None:
    return float(roc_auc_score(y, s)) if 0 < sum(y) < len(y) else None


def labels_of(samples: list[Sample]) -> np.ndarray:
    return np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)


def load(path: Path, signals: list[str], good_only: bool = False) -> tuple[list[Sample], dict]:
    rows = load_rows(signals, path, FEATURES)
    samples = [s for s in read_jsonl(path) if not good_only or s.meta.quality == "good"]
    return usable(samples, rows), rows


def fit_and_score(train, train_rows, evals: dict, signals: list[str], kind: str, structure: bool = True) -> tuple[fusion.FusionModel, dict, dict]:
    model, report, oof = fusion.fit(train, fusion.build_table(train, train_rows, signals, structure), signals, kind)
    scores = {"oof_response_auroc": report["oof_response_auroc"]}
    for name, (samples, rows) in evals.items():
        _, response_probs = model.score(fusion.build_table(samples, rows, signals, structure))
        scores[name] = auroc(labels_of(samples), response_probs)
    return model, scores, oof


def error_analysis(train: list[Sample], table: fusion.SentenceTable, oof: dict) -> dict:
    y = labels_of(train)
    result = {}
    for field in ("task", "generator"):
        values = np.array([getattr(s.meta, field) for s in train])
        result[f"response_auroc_by_{field}"] = {v: auroc(y[values == v], oof["response"][values == v]) for v in sorted(set(values))}
    negatives = oof["sentence"][table.labels == 0]
    by_label: dict[str, list[float]] = defaultdict(list)
    sentence_offset = 0
    for i, s in enumerate(train):
        sents = table.sentences[i]
        probs = oof["sentence"][sentence_offset : sentence_offset + len(sents)]
        sentence_offset += len(sents)
        for sent, p in zip(sents, probs):
            for sp in s.labels.spans:
                if sp.start < sent.end and sent.start < sp.end:
                    by_label[sp.source_label].append(p)
                    if sp.implicit_true:
                        by_label["implicit_true"].append(p)
                    if sp.due_to_null:
                        by_label["due_to_null"].append(p)
    result["sentence_auroc_vs_clean_sentences"] = {
        k: auroc([1] * len(v) + [0] * len(negatives), list(v) + list(negatives)) for k, v in sorted(by_label.items())
    }
    return result


def span_and_type_report(model: fusion.FusionModel, dev: list[Sample], rows: dict) -> dict:
    table = fusion.build_table(dev, {s: rows[s] for s in model.signals}, model.signals)
    predictions = {p.id: p for p in model.predictions(dev, table)}
    threshold = best_span_threshold(dev, predictions)
    whole, refined = [0, 0, 0], [0, 0, 0]
    confusion: Counter = Counter()
    for i, s in enumerate(dev):
        gold = [(sp.start, sp.end) for sp in s.labels.spans]
        flagged = [(sc.start, sc.end) for sc in predictions[s.id].sentences if sc.score >= threshold]
        merged = [{k: v for signal in model.signals for k, v in rows[signal][s.id][j].items()} for j in range(len(rows[model.signals[0]][s.id]))]
        starts = [r["start"] for r in merged]
        ends = [r["end"] for r in merged]
        for acc, spans in ((whole, flagged), (refined, refine_spans(flagged, merged, starts, ends))):
            o, p, g = span_counts(gold, spans)
            acc[0] += o; acc[1] += p; acc[2] += g
        gold_types = sentence_types(s, table.sentences[i])
        for row, gold_type in zip(merged, gold_types):
            if gold_type is not None and (row["start"], row["end"]) in flagged:
                predicted = explain_sentence(row, row["start"], row["end"]).type
                confusion[(gold_type.value, predicted.value)] += 1

    def prf(acc):
        precision, recall = (acc[0] / acc[1] if acc[1] else 0.0), (acc[0] / acc[2] if acc[2] else 0.0)
        return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}

    contradicted = [k for k in confusion if k[0] == HallucinationType.CONTRADICTED.value]
    total = sum(confusion.values())
    correct_binary = sum(n for (g, p), n in confusion.items() if (g == "contradicted") == (p == "contradicted"))
    majority = max(sum(confusion[k] for k in contradicted), total - sum(confusion[k] for k in contradicted))
    return {
        "sentence_threshold": threshold,
        "spans_whole_sentences": prf(whole),
        "spans_refined_with_symbolic": prf(refined),
        "type_confusion": {f"{g} -> {p}": n for (g, p), n in sorted(confusion.items())},
        "contradiction_vs_other_accuracy": correct_binary / total if total else None,
        "majority_baseline_accuracy": majority / total if total else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", nargs="+", required=True)
    parser.add_argument("--kind", choices=["logreg", "hgb"], default="hgb")
    parser.add_argument("--learning-curve", nargs="*", type=int, default=[], help="train group counts, e.g. 170 340 680")
    args = parser.parse_args()

    train, train_rows = load(ROOT / "data/processed/ragtruth_train.jsonl", args.signals, good_only=True)
    dev, dev_rows = load(ROOT / "data/processed/ragtruth_dev.jsonl", args.signals)
    evals = {"dev_auroc": (dev, dev_rows)}
    for path in XDEV:
        samples, rows = load(path, args.signals)
        if samples:
            evals[f"xdev_{path.stem.split('_')[-1]}_auroc"] = (samples, rows)
    name = f"{args.kind}-{'+'.join(args.signals)}"
    report = {"name": name, "train_samples": len(train), "dev_samples": len(dev), "xdev_samples": {k: len(v[0]) for k, v in evals.items() if k.startswith("xdev")}}

    model, report["full"], oof = fit_and_score(train, train_rows, evals, args.signals, args.kind)
    print(f"{name}: train {len(train)}  {report['full']}", flush=True)

    _, scores, _ = fit_and_score(train, train_rows, evals, args.signals, args.kind, structure=False)
    report["ablation"] = {"without structure (position, length, count)": scores}
    print(f"  without structure: {scores}", flush=True)
    for dropped in args.signals if len(args.signals) > 1 else []:
        kept = [s for s in args.signals if s != dropped]
        _, scores, _ = fit_and_score(train, train_rows, evals, kept, args.kind)
        report["ablation"][f"without {dropped}"] = scores
        print(f"  without {dropped}: {scores}", flush=True)

    report["learning_curve"] = {}
    for groups in args.learning_curve:
        ids = {s.id for s in sample_groups(train, groups, seed=TRAIN_SUBSET_SEED)}
        subset = [s for s in train if s.id in ids]
        _, scores, _ = fit_and_score(subset, train_rows, evals, args.signals, args.kind)
        report["learning_curve"][str(groups)] = {"samples": len(subset), **scores}
        print(f"  {groups} groups ({len(subset)} samples): {scores}", flush=True)

    report["train_errors"] = error_analysis(train, fusion.build_table(train, train_rows, args.signals), oof)
    report["dev_spans_and_types"] = span_and_type_report(model, dev, dev_rows)
    print(json.dumps({k: report[k] for k in ("train_errors", "dev_spans_and_types")}, indent=1), flush=True)

    out = ROOT / "eval" / "results" / f"analysis__{name}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
