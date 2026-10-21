"""Signal study: how much each signal helps (AUROC) versus what it costs (seconds per sample).

Runs on a task-stratified subset of RAGTruth dev and of the external HaluEval dev. Features are cached,
so the study can be interrupted and resumed, and later reused by the fusion model.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian.data.splits import sample_groups
from truth_guardian.features import FeatureStore, extract
from truth_guardian.labels import sentence_labels
from truth_guardian.schema import Sample, read_jsonl
from truth_guardian.signals import SIGNALS
from truth_guardian.text import Sentence

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"

# Each signal's per-sentence "how hallucinated" value; higher = more suspicious.
SCORES = {
    "lexical": {"lexical": lambda r: r["lex_unsupported"]},
    "dense": {"dense": lambda r: -r["dense_max"]},
    "symbolic": {"symbolic": lambda r: len(r["sym_spans"])},
    "nli": {"nli 1-entail": lambda r: 1 - r["nli_entailment"], "nli contradiction": lambda r: r["nli_contradiction"]},
    "nli_large": {"nli-large 1-entail": lambda r: 1 - r["nlil_entailment"], "nli-large contradiction": lambda r: r["nlil_contradiction"]},
    "hhem": {"hhem": lambda r: 1 - r["hhem_consistency"]},
    "lettuce": {"lettuce": lambda r: r["lettuce_max"]},
}


def stratified_subset(path: Path, groups_per_task: int) -> list[Sample]:
    samples = list(read_jsonl(path))
    subset = []
    for task in sorted({s.meta.task for s in samples}):
        subset += sample_groups([s for s in samples if s.meta.task == task], groups_per_task, seed="tg-study-v1")
    return subset


def auroc(y: list[int], scores: list[float]) -> float | None:
    return float(roc_auc_score(y, scores)) if 0 < sum(y) < len(y) else None


def evaluate_signal(samples: list[Sample], rows: dict[str, list[dict]], score) -> dict:
    y_resp, s_resp, y_sent, s_sent = [], [], [], []
    for sample in samples:
        values = [score(r) for r in rows[sample.id]]
        y_resp.append(int(sample.labels.response == "hallucinated"))
        s_resp.append(max(values, default=0.0))
        if sample.labels.spans or sample.meta.dataset == "ragtruth":
            sentences = [Sentence(r["start"], r["end"], "") for r in rows[sample.id]]
            y_sent += sentence_labels(sample, sentences)
            s_sent += values
    return {"response_auroc": auroc(y_resp, s_resp), "sentence_auroc": auroc(y_sent, s_sent) if y_sent else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", nargs="+", default=list(SIGNALS), choices=list(SIGNALS))
    parser.add_argument("--groups-per-task", type=int, default=17)
    args = parser.parse_args()

    subsets = {
        "study_ragtruth_dev": stratified_subset(ROOT / "data/processed/ragtruth_dev.jsonl", args.groups_per_task),
        "study_halueval_xdev": [
            s
            for task in ("qa", "dialogue", "summary")
            for s in sample_groups(read_jsonl(ROOT / f"data/processed/xdev_halueval_{task}.jsonl"), 50, seed="tg-study-v1")
        ],
    }
    results_path = ROOT / "eval" / "results" / "signal_study.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else {}

    for signal in args.signals:
        version, fn = SIGNALS[signal]
        for name, samples in subsets.items():
            store = FeatureStore(FEATURES / signal / f"{name}.jsonl", signal, version)
            started = time.perf_counter()
            computed = extract(samples, store, fn)
            entry = results.setdefault(signal, {}).setdefault(name, {"n": len(samples)})
            if computed:
                entry["seconds_per_sample"] = (time.perf_counter() - started) / computed
            rows = store.load()
            for label, score in SCORES[signal].items():
                entry[label] = evaluate_signal(samples, rows, score)
            results_path.write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
            print(f"{signal} / {name}: {json.dumps(entry)}", flush=True)


if __name__ == "__main__":
    main()
