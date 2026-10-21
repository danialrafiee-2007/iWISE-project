"""High-precision rules that can override the fusion model's scores.

A confirmed polarity contradiction (an answer sentence that restates a source sentence with the opposite
meaning, confirmed by NLI) is rare in natural answers but almost always a real error, so it is applied
after the learned model rather than learned from data that barely contains it.
"""

from truth_guardian.evaluation import Prediction


def apply_polarity(prediction: Prediction, polarity_rows: list[dict]) -> Prediction:
    """Raise a sentence's score to the NLI contradiction probability when the rule confirms it, and the response with it."""
    confirmed = {(r["start"], r["end"]): r["pol_contradiction"] for r in polarity_rows if r.get("pol_confirmed")}
    if not confirmed:
        return prediction
    sentences = [s.model_copy(update={"score": max(s.score, confirmed.get((s.start, s.end), 0.0))}) for s in prediction.sentences]
    return prediction.model_copy(update={"sentences": sentences, "score": max(prediction.score, max(confirmed.values()))})
