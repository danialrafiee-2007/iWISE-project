"""Explanations for flagged sentences: hallucination type, word-level spans and a human-readable reason.

Types follow the project taxonomy; the evidence text shown to users is the retrieved premise.
"""

from typing import NamedTuple

from truth_guardian.schema import HallucinationType

WEAK_EVIDENCE_SIMILARITY = 0.3


class Explanation(NamedTuple):
    type: HallucinationType
    spans: list[tuple[int, int]]
    reason: str


def explain_sentence(row: dict, start: int, end: int) -> Explanation:
    """row holds one sentence's cached signals (symbolic, nli and dense keys are used when present)."""
    symbolic_spans = [tuple(span) for span in row.get("sym_spans", [])]
    if row.get("pol_confirmed", 0):
        spans = [tuple(span) for span in row.get("pol_spans", [])] or [(start, end)]
        return Explanation(HallucinationType.CONTRADICTED, spans, "it states the opposite of a source sentence it otherwise repeats")
    if row.get("shift_overrides", 0):
        spans = [tuple(span) for span in row.get("shift_spans", [])] or [(start, end)]
        return Explanation(HallucinationType.CONTRADICTED, spans, f"it swaps who did what: {row.get('shift_detail', '')}")
    if row.get("sym_numbers_unmatched", 0) or row.get("sym_entities_unmatched", 0):
        return Explanation(HallucinationType.NUMERIC_ENTITY_MISMATCH, symbolic_spans, "a number, date or name does not appear in the sources")
    if row.get("sym_null_mentions", 0):
        return Explanation(HallucinationType.UNSUPPORTED, symbolic_spans, "the sources leave this attribute unspecified")
    contradiction, entailment, neutral = (row.get(f"nli_{k}", 0.0) for k in ("contradiction", "entailment", "neutral"))
    if contradiction >= 0.5 and contradiction >= neutral:
        return Explanation(HallucinationType.CONTRADICTED, [(start, end)], "the closest source passage says otherwise")
    if row.get("dense_max", 1.0) < WEAK_EVIDENCE_SIMILARITY:
        return Explanation(HallucinationType.WEAK_EVIDENCE, [(start, end)], "no source passage is about this claim")
    return Explanation(HallucinationType.UNSUPPORTED, [(start, end)], "the sources do not support this claim")


def refine_spans(flagged: list[tuple[int, int]], rows: list[dict], starts: list[int], ends: list[int]) -> list[tuple[int, int]]:
    """Inside flagged sentences, prefer exact symbolic spans; otherwise keep the whole sentence."""
    spans: list[tuple[int, int]] = []
    for row, start, end in zip(rows, starts, ends):
        if (start, end) not in flagged:
            continue
        spans += explain_sentence(row, start, end).spans
    return spans
