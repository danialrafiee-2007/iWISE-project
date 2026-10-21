"""Response-level, span-level and calibration metrics with group-aware bootstrap confidence intervals."""

from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
)

from truth_guardian.schema import Sample


class SentenceScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int
    end: int
    score: float


class Prediction(BaseModel):
    """Hallucination score for one response (higher = more likely hallucinated), plus per-sentence scores."""

    model_config = ConfigDict(extra="forbid")
    id: str
    score: float
    sentences: list[SentenceScore] = Field(default_factory=list)


def write_predictions(predictions: Iterable[Prediction], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for p in predictions:
            f.write(p.model_dump_json() + "\n")
            count += 1
    return count


def read_predictions(path: str | Path) -> dict[str, Prediction]:
    with Path(path).open(encoding="utf-8") as f:
        predictions = [Prediction.model_validate_json(line) for line in f if line.strip()]
    return {p.id: p for p in predictions}


def predicted_spans(prediction: Prediction, threshold: float) -> list[tuple[int, int]]:
    return [(s.start, s.end) for s in prediction.sentences if s.score >= threshold]


def span_counts(gold: Sequence[tuple[int, int]], predicted: Sequence[tuple[int, int]]) -> tuple[int, int, int]:
    """Character-level (overlap, predicted, gold) counts."""
    gold_chars = {i for start, end in gold for i in range(start, end)}
    pred_chars = {i for start, end in predicted for i in range(start, end)}
    return len(gold_chars & pred_chars), len(pred_chars), len(gold_chars)


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def expected_calibration_error(y: np.ndarray, scores: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    index = np.clip(np.digitize(scores, edges[1:-1]), 0, bins - 1)
    error = 0.0
    for b in range(bins):
        mask = index == b
        if mask.any():
            error += mask.mean() * abs(y[mask].mean() - scores[mask].mean())
    return float(error)


def best_threshold(y: np.ndarray, scores: np.ndarray) -> float:
    """Threshold that maximizes F1 for the hallucinated class."""
    precision, recall, thresholds = precision_recall_curve(y, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    return float(thresholds[int(np.argmax(f1))])


def span_f1(samples: Sequence[Sample], predictions: dict[str, Prediction], sentence_threshold: float) -> dict:
    overlap = n_pred = n_gold = 0
    for s in samples:
        o, p, g = span_counts([(sp.start, sp.end) for sp in s.labels.spans], predicted_spans(predictions[s.id], sentence_threshold))
        overlap, n_pred, n_gold = overlap + o, n_pred + p, n_gold + g
    precision = overlap / n_pred if n_pred else 0.0
    recall = overlap / n_gold if n_gold else 0.0
    return {"precision": precision, "recall": recall, "f1": _f1(precision, recall)}


def best_span_threshold(samples: Sequence[Sample], predictions: dict[str, Prediction], candidates: int = 50) -> float:
    """Sentence threshold that maximizes character-level span F1."""
    scores = np.array([sc.score for s in samples for sc in predictions[s.id].sentences])
    if len(scores) == 0:
        return 0.5
    grid = np.unique(np.quantile(scores, np.linspace(0, 1, candidates), method="nearest"))
    return float(max(grid, key=lambda t: span_f1(samples, predictions, t)["f1"]))


def _response_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    predicted = (scores >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, average="binary", zero_division=0)
    metrics = {
        "n": int(len(y)),
        "hallucinated_rate": float(y.mean()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "f1_flag_everything": _f1(float(y.mean()), 1.0),
        "accuracy": float((predicted == y).mean()),
    }
    if 0 < y.sum() < len(y):
        metrics["auroc"] = float(roc_auc_score(y, scores))
        metrics["pr_auc"] = float(average_precision_score(y, scores))
    if scores.min() >= 0 and scores.max() <= 1:
        metrics["brier"] = float(brier_score_loss(y, scores))
        metrics["ece"] = expected_calibration_error(y, scores)
    return metrics


def _bootstrap(y: np.ndarray, scores: np.ndarray, groups: list[str], threshold: float, rounds: int, seed: int) -> dict:
    """95% intervals resampling whole groups, since responses sharing a source are correlated."""
    rng = np.random.default_rng(seed)
    by_group: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    members = list(by_group.values())
    f1s, aurocs = [], []
    for _ in range(rounds):
        idx = np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])
        yb, sb = y[idx], scores[idx]
        _, _, f1, _ = precision_recall_fscore_support(yb, (sb >= threshold).astype(int), average="binary", zero_division=0)
        f1s.append(f1)
        if 0 < yb.sum() < len(yb):
            aurocs.append(roc_auc_score(yb, sb))
    interval = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v else None
    return {"f1": interval(f1s), "auroc": interval(aurocs)}


def evaluate(
    samples: Sequence[Sample],
    predictions: dict[str, Prediction],
    threshold: float,
    sentence_threshold: float | None = None,
    bootstrap_rounds: int = 1000,
    seed: int = 0,
) -> dict:
    """sentence_threshold decides which sentences count as predicted spans; defaults to threshold."""
    missing = [s.id for s in samples if s.id not in predictions]
    if missing:
        raise ValueError(f"{len(missing)} samples have no prediction, e.g. {missing[:3]}")
    y = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
    scores = np.array([predictions[s.id].score for s in samples], dtype=float)
    sentence_threshold = threshold if sentence_threshold is None else sentence_threshold
    has_spans = any(s.labels.spans for s in samples)

    report = {
        "threshold": threshold,
        "sentence_threshold": sentence_threshold,
        "response": _response_metrics(y, scores, threshold),
        "span": span_f1(samples, predictions, sentence_threshold) if has_spans else None,
        "ci95": _bootstrap(y, scores, [s.meta.group_id for s in samples], threshold, bootstrap_rounds, seed),
        "breakdown": {},
    }
    for field in ("task", "generator", "quality"):
        values = [getattr(s.meta, field) for s in samples]
        if len(set(values)) > 1:
            report["breakdown"][field] = {
                value: _response_metrics(y[mask], scores[mask], threshold)
                for value in sorted(set(values), key=str)
                for mask in [np.array([v == value for v in values])]
            }
    return report
