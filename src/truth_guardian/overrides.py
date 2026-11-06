"""High-precision rules that can override the fusion model's scores.

A confirmed polarity contradiction (an answer sentence that restates a source sentence with the opposite
meaning, confirmed by NLI) is rare in natural answers but almost always a real error, so it is applied
after the learned model rather than learned from data that barely contains it. A role swap found by the parse
(shifts.py) is treated the same way, with a fixed score, since NLI largely ignores word order. A value of the sources
put on the wrong subject (values.py) raises its sentence to NLI's contradiction, as a polarity finding does. A confirmed flip
(flips.py) raises the sentence to the entailment of its flipped version when the word was turned into its opposite,
and to a fixed overclaim score when the answer was stronger or more certain than the sources.
"""

from pathlib import Path

from truth_guardian.evaluation import Prediction

ROLE_SWAP_SCORE = 0.9
OVERCLAIM_SCORE = 0.6


def apply_polarity(prediction: Prediction, polarity_rows: list[dict]) -> Prediction:
    """Raise a sentence's score to the NLI contradiction probability when the rule confirms it, and the response with it."""
    return _raise(prediction, {(r["start"], r["end"]): r["pol_contradiction"] for r in polarity_rows if r.get("pol_confirmed")})


def apply_shifts(prediction: Prediction, shift_rows: list[dict]) -> Prediction:
    """Raise sentences with a confirmed role swap to a fixed contradiction score, and a confirmed stronger quantifier
    or dropped hedge to the overclaim score."""
    return _raise(prediction, {
        (r["start"], r["end"]): ROLE_SWAP_SCORE if r.get("shift_overrides") else OVERCLAIM_SCORE
        for r in shift_rows if r.get("shift_confirmed")
    })


def apply_values(prediction: Prediction, value_rows: list[dict]) -> Prediction:
    """Raise a sentence to NLI's contradiction when another value of its source sentence makes the source entail it."""
    return _raise(prediction, {(r["start"], r["end"]): r["val_contradiction"] for r in value_rows if r.get("val_confirmed")})


def apply_flips(prediction: Prediction, flip_rows: list[dict]) -> Prediction:
    """Raise sentences with a confirmed flip: an opposite word to its flipped entailment, an overclaim to OVERCLAIM_SCORE."""
    return _raise(prediction, {
        (r["start"], r["end"]): r["flip_flipped"] if r["flip_kind"] == "antonym" else OVERCLAIM_SCORE
        for r in flip_rows if r.get("flip_confirmed")
    })


def with_words(prediction: Prediction, detector_rows: list[dict]) -> Prediction:
    """The detector's marked words (at its shipped word threshold), used to narrow flagged sentences to exact words."""
    from truth_guardian.detector import WORD_THRESHOLD, merged

    return prediction.model_copy(update={"spans": [sp for r in detector_rows for sp in merged([tuple(t) for t in r.get("det_tokens", [])], WORD_THRESHOLD)]})


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
    for signal, apply in (("polarity", apply_polarity), ("shifts", apply_shifts), ("flips", apply_flips), ("values", apply_values)):
        if (features_dir / signal / f"{dataset.stem}.jsonl").exists():
            extra = load_rows([signal], dataset, features_dir)[signal]
            predictions = {k: apply(p, extra[k]) for k, p in predictions.items()}
    if (features_dir / "detector" / f"{dataset.stem}.jsonl").exists():
        words = load_rows(["detector"], dataset, features_dir)["detector"]
        predictions = {k: with_words(p, words[k]) for k, p in predictions.items()}
    return samples, predictions
