"""Set and test the retrieval-relevance threshold: each question with its own documents vs with another question's documents.

The threshold maximises balanced accuracy on RAGTruth train; dev and the external HaluEval dev only measure it.
Also reports how natural hallucinated QA answers in dev split between retrieval and generation blame.
"""

import json
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian.diagnosis import diagnose, relevance
from truth_guardian.schema import Sample, read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def one_per_group(samples: list[Sample]) -> list[Sample]:
    seen, out = set(), []
    for s in samples:
        if s.question and s.meta.group_id not in seen:
            seen.add(s.meta.group_id)
            out.append(s)
    return out


def pairs(samples: list[Sample], seed: int) -> tuple[list[float], list[int]]:
    """Relevance with the sample's own documents (label 1) and with a different sample's documents (label 0)."""
    rng = random.Random(seed)
    scores, labels = [], []
    for i, s in enumerate(samples):
        other = samples[(i + rng.randint(1, len(samples) - 1)) % len(samples)]
        swapped = s.model_copy(update={"documents": other.documents})
        scores += [relevance(s)[0], relevance(swapped)[0]]
        labels += [1, 0]
    return scores, labels


def balanced_accuracy(scores: list[float], labels: list[int], threshold: float) -> float:
    predicted = np.array(scores) >= threshold
    y = np.array(labels, dtype=bool)
    return float((predicted[y].mean() + (~predicted[~y]).mean()) / 2)


def main() -> None:
    load = lambda name: one_per_group([s for s in read_jsonl(ROOT / f"data/processed/{name}.jsonl") if s.meta.task in ("qa", "dialogue")])
    train, dev, xdev = load("ragtruth_train"), load("ragtruth_dev"), load("xdev_halueval_qa")

    train_scores, train_labels = pairs(train, 0)
    grid = np.unique(np.round(train_scores, 3))
    threshold = float(max(grid, key=lambda t: balanced_accuracy(train_scores, train_labels, t)))
    report = {"threshold": threshold, "train_balanced_accuracy": balanced_accuracy(train_scores, train_labels, threshold)}
    for name, samples in (("ragtruth_dev", dev), ("halueval_xdev_qa", xdev)):
        scores, labels = pairs(samples, 1)
        report[name] = {"pairs": len(labels), "auroc": float(roc_auc_score(labels, scores)), "balanced_accuracy": balanced_accuracy(scores, labels, threshold)}

    natural = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl") if s.meta.task == "qa" and s.labels.response == "hallucinated"]
    blames = [diagnose(s, True, threshold=threshold).blame for s in natural]
    report["natural_dev_hallucinations"] = {"n": len(blames), "retrieval": blames.count("retrieval") / len(blames), "generation": blames.count("generation") / len(blames)}
    out = ROOT / "eval" / "results" / "diagnosis.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
