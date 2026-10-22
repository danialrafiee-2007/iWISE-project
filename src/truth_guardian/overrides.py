"""High-precision rules that can override the fusion model's scores.

A confirmed polarity contradiction (an answer sentence that restates a source sentence with the opposite
meaning, confirmed by NLI) is rare in natural answers but almost always a real error, so it is applied
after the learned model rather than learned from data that barely contains it. A role swap found by the parse
(shifts.py) is treated the same way, with a fixed score, since NLI largely ignores word order.
"""

from pathlib import Path

from truth_guardian.evaluation import Prediction

ROLE_SWAP_SCORE = 0.9


def apply_polarity(prediction: Prediction, polarity_rows: list[dict]) -> Prediction:
    """Raise a sentence's score to the NLI contradiction probability when the rule confirms it, and the response with it."""
    return _raise(prediction, {(r["start"], r["end"]): r["pol_contradiction"] for r in polarity_rows if r.get("pol_confirmed")})


def apply_shifts(prediction: Prediction, shift_rows: list[dict]) -> Prediction:
    """Raise sentences with a confirmed role swap to a fixed contradiction score; advisory shifts change nothing."""
    return _raise(prediction, {(r["start"], r["end"]): ROLE_SWAP_SCORE for r in shift_rows if r.get("shift_overrides")})


def _raise(prediction: Prediction, confirmed: dict[tuple[int, int], float]) -> Prediction:
    if not confirmed:
        return prediction
    sentences = [s.model_copy(update={"score": max(s.score, confirmed.get((s.start, s.end), 0.0))}) for s in prediction.sentences]
    return prediction.model_copy(update={"sentences": sentences, "score": max(prediction.score, max(confirmed.values()))})


def cached_predictions(model, dataset: Path, features_dir: Path) -> tuple[list, dict[str, Prediction]]:
    """A saved model's predictions from cached signals, with the polarity and role-swap overrides where cached."""
    from truth_guardian import fusion
    from truth_guardian.features import load_rows
    from truth_guardian.schema import read_jsonl

    samples = list(read_jsonl(dataset))
    rows = load_rows(model.signals, dataset, features_dir)
    predictions = {p.id: p for p in model.predictions(samples, fusion.build_table(samples, rows, model.signals, model.structure))}
    for signal, apply in (("polarity", apply_polarity), ("shifts", apply_shifts)):
        if (features_dir / signal / f"{dataset.stem}.jsonl").exists():
            extra = load_rows([signal], dataset, features_dir)[signal]
            predictions = {k: apply(p, extra[k]) for k, p in predictions.items()}
    return samples, predictions
