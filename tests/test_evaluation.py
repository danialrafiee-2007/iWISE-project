import numpy as np
import pytest

from truth_guardian.evaluation import (
    Prediction,
    best_threshold,
    evaluate,
    expected_calibration_error,
    read_predictions,
    span_counts,
    write_predictions,
)
from truth_guardian.schema import Sample

ANSWER = "First sentence here. Second one is false."


def sample(i: int, hallucinated: bool, task: str = "qa") -> Sample:
    labels = {"response": "hallucinated" if hallucinated else "grounded"}
    if hallucinated:
        labels["spans"] = [{"start": 21, "end": 41, "text": "Second one is false."}]
    return Sample.model_validate({
        "id": f"s{i}",
        "documents": [{"id": "d", "text": "doc"}],
        "answer": ANSWER,
        "labels": labels,
        "meta": {"dataset": "unit", "task": task, "split": "dev", "group_id": f"g{i}"},
    })


def test_hand_computed_response_metrics():
    samples = [sample(0, True), sample(1, True), sample(2, False), sample(3, False)]
    preds = {f"s{i}": Prediction(id=f"s{i}", score=s) for i, s in enumerate([0.9, 0.4, 0.6, 0.1])}
    report = evaluate(samples, preds, threshold=0.5, bootstrap_rounds=10)
    r = report["response"]
    assert (r["precision"], r["recall"], r["f1"]) == (0.5, 0.5, 0.5)
    assert r["auroc"] == pytest.approx(0.75)


def test_perfect_predictions():
    samples = [sample(i, i % 2 == 0) for i in range(6)]
    preds = {s.id: Prediction(id=s.id, score=1.0 if s.labels.response == "hallucinated" else 0.0) for s in samples}
    r = evaluate(samples, preds, threshold=0.5, bootstrap_rounds=10)["response"]
    assert r["f1"] == 1.0 and r["auroc"] == 1.0 and r["ece"] == 0.0


def test_span_counts_character_overlap():
    assert span_counts([(0, 10)], [(5, 15)]) == (5, 10, 10)
    assert span_counts([], [(0, 3)]) == (0, 3, 0)


def test_span_metrics_use_sentence_scores_above_threshold():
    samples = [sample(0, True)]
    pred = Prediction(id="s0", score=0.9, sentences=[{"start": 0, "end": 20, "score": 0.1}, {"start": 21, "end": 41, "score": 0.9}])
    span = evaluate(samples, {"s0": pred}, threshold=0.5, bootstrap_rounds=10)["span"]
    assert span == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_missing_prediction_raises():
    with pytest.raises(ValueError, match="no prediction"):
        evaluate([sample(0, True)], {}, threshold=0.5)


def test_best_threshold_maximizes_f1():
    y = np.array([1, 1, 0, 0])
    scores = np.array([0.9, 0.7, 0.6, 0.1])
    assert best_threshold(y, scores) == pytest.approx(0.7)


def test_ece_zero_when_calibrated():
    y = np.array([1, 1, 1, 1, 0])
    assert expected_calibration_error(y, np.full(5, 0.8)) == pytest.approx(0.0)


def test_breakdown_by_task():
    samples = [sample(0, True, "qa"), sample(1, False, "qa"), sample(2, True, "summary"), sample(3, False, "summary")]
    preds = {s.id: Prediction(id=s.id, score=0.5) for s in samples}
    report = evaluate(samples, preds, threshold=0.5, bootstrap_rounds=10)
    assert set(report["breakdown"]["task"]) == {"qa", "summary"}


def test_predictions_round_trip(tmp_path):
    preds = [Prediction(id="a", score=0.3, sentences=[{"start": 0, "end": 4, "score": 0.3}])]
    path = tmp_path / "p.jsonl"
    assert write_predictions(preds, path) == 1
    assert read_predictions(path) == {"a": preds[0]}
