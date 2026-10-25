"""Reliability card: one grade per answer, with the dimensions behind it.

The grade depends only on the calibrated risk (the model's probability that the answer contains a hallucination;
with a domain profile, the risk recalibrated on that domain), so it means the same thing everywhere: A below 0.1,
B below 0.25, C below 0.4, D below 0.7, F above;
scripts/evaluate_card.py reports the observed hallucination rate per grade. The other dimensions (claims supported,
source relevance, completeness, certainty, source agreement, citations, agent trajectory) are shown beside the
grade, not mixed into it: how much each should weigh against the risk cannot be learned from the labels available.
"""

from truth_guardian.report import Card, Dimension, Report
from truth_guardian.schema import HallucinationType

GRADES = (("A", 0.1), ("B", 0.25), ("C", 0.4), ("D", 0.7))


def grade(risk: float) -> str:
    return next((g for g, limit in GRADES if risk < limit), "F")


def _share(count: int, total: int) -> float | None:
    return 1 - count / total if total else None


def build_card(report: Report) -> Card:
    claims = report.claims
    supported = sum(c.status == "supported" for c in claims)
    overclaims = sum(c.type == HallucinationType.OVERCLAIM for c in claims)
    contested = sum(c.status == "contested" for c in claims)
    citing = [c for c in claims if c.citation is not None]
    wrong = sum(not c.citation.supported for c in citing)
    risk = report.domain.calibrated_risk if report.domain else report.risk
    dimensions = [
        Dimension(name="grounding", score=1 - risk, note="probability that the answer contains no hallucination"),
        Dimension(name="claims supported", score=supported / len(claims) if claims else None, note=f"{supported} of {len(claims)} claims are supported by the sources"),
        Dimension(
            name="source relevance",
            score=report.diagnosis.relevance if report.diagnosis else None,
            note=report.diagnosis.message if report.diagnosis else "not judged",
        ),
        Dimension(
            name="completeness",
            score=report.completeness.score if report.completeness else None,
            note=f"{len(report.completeness.missing)} key source sentences not covered" if report.completeness else "needs a question",
        ),
        Dimension(name="certainty", score=_share(overclaims, len(claims)), note=f"{overclaims} claims state more certainty or generality than the sources"),
        Dimension(name="source agreement", score=_share(contested, len(claims)), note=f"{contested} claims rest on facts the sources disagree about"),
        Dimension(name="citations", score=_share(wrong, len(citing)), note=f"{wrong} of {len(citing)} citations point to a passage that does not support the claim" if citing else "no citations"),
    ]
    if report.agent is not None:
        stop = report.agent.guardian_stop
        dimensions.append(Dimension(
            name="agent trajectory", score=1 - report.agent.risk,
            note=f"the live guardian would have stopped the agent at step {stop}" if stop is not None else "the live guardian would not have stopped the agent",
        ))
    return Card(grade=grade(risk), risk=risk, dimensions=dimensions)
