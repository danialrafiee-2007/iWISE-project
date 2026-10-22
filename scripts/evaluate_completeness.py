"""Test omission detection: full grounded answers vs the same answers with the sentence that covers the top key evidence removed.

Coverage thresholds are chosen on RAGTruth train by AUROC; dev only measures them. Also reports how often a removed
sentence that carried a caveat shows up in `omitted_caveats`.
"""

import json
from itertools import product
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

import truth_guardian.completeness as completeness
from truth_guardian import models
from truth_guardian.schema import Sample, read_jsonl
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]


def bases(path: Path, limit: int) -> list[Sample]:
    seen, out = set(), []
    for s in read_jsonl(path):
        if s.meta.task == "qa" and s.labels.response == "grounded" and s.meta.quality == "good" and s.meta.group_id not in seen and len(split_sentences(s.answer)) >= 2:
            seen.add(s.meta.group_id)
            out.append(s)
    return out[:limit]


def reduced(sample: Sample) -> tuple[Sample, str] | None:
    """The answer without the sentence closest to the top key evidence sentence."""
    keys, key_embeddings = completeness.key_evidence(sample, models.encode)
    sentences = split_sentences(sample.answer)
    if not keys:
        return None
    best = int(np.argmax(models.encode([s.text for s in sentences]) @ key_embeddings[0]))
    kept = " ".join(s.text for i, s in enumerate(sentences) if i != best)
    return sample.model_copy(update={"answer": kept}), keys[0]


def coverages(samples: list[Sample]) -> tuple[list, list[int], list[tuple[Sample, str]]]:
    """Coverage of each full answer and of its reduced copy, computed once and judged under every threshold pair."""
    covers, labels, removed = [], [], []
    for s in samples:
        r = reduced(s)
        if r is None:
            continue
        covers += [completeness.coverage(s), completeness.coverage(r[0])]
        labels += [1, 0]
        removed.append(r)
    return covers, labels, removed


def scores(covers: list, similarity: float, words: float) -> list[float]:
    return [completeness.judge(c, similarity, words).score for c in covers]


def main() -> None:
    train, dev = bases(ROOT / "data/processed/ragtruth_train.jsonl", 300), bases(ROOT / "data/processed/ragtruth_dev.jsonl", 300)
    train_covers, train_labels, _ = coverages(train)
    grid = [
        (roc_auc_score(train_labels, scores(train_covers, similarity, words)), similarity, words)
        for similarity, words in product(np.arange(0.5, 0.951, 0.05).round(2), np.arange(0.4, 1.01, 0.1).round(1))
    ]
    best = max(grid)
    _, similarity, words = best
    dev_covers, labels, removed = coverages(dev)
    values = scores(dev_covers, similarity, words)
    caveat_cases = [(c, key) for c, (_, key) in zip(dev_covers[1::2], removed) if completeness.CAVEAT.search(key)]
    caught = sum(key in completeness.judge(c, similarity, words).omitted_caveats for c, key in caveat_cases)
    report = {
        "cover_similarity": float(similarity),
        "cover_words": float(words),
        "train_auroc": best[0],
        "train_grid": {f"{s:.2f}/{w:.1f}": round(a, 4) for a, s, w in grid},
        "dev_pairs": len(labels),
        "dev_auroc": float(roc_auc_score(labels, values)),
        "dev_mean_score_full": float(np.mean(values[0::2])),
        "dev_mean_score_reduced": float(np.mean(values[1::2])),
        "dev_caveat_omissions": len(caveat_cases),
        "dev_caveat_omissions_reported": caught,
    }
    out = ROOT / "eval" / "results" / "completeness.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
