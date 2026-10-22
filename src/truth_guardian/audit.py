"""Audit a whole RAG system from a log of its answers.

Every answer runs through the guardian; the summary is the system's health: the estimated share of hallucinated
answers (the mean calibrated risk, with a bootstrap interval), verdicts, grades and triage lanes, who is most often
to blame (retriever, generator or conflicting sources), the commonest error types and cautions, the source documents
most often behind flagged claims, and the worst answers to read first. When the log carries labels, the true share
is reported beside the estimate.
"""

from collections import Counter
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel

from truth_guardian.report import Report
from truth_guardian.schema import Sample

FLAGGED = ("contradicted", "unsupported", "insufficient_evidence")
BOOTSTRAP = 1000
WORST = 10


class WorstAnswer(BaseModel):
    id: str
    risk: float
    grade: str
    claim: str
    explanation: str


class AuditSummary(BaseModel):
    answers: int
    estimated_hallucination_rate: float
    estimate_interval: tuple[float, float]
    true_hallucination_rate: float | None = None
    verdicts: dict[str, int]
    grades: dict[str, int]
    lanes: dict[str, int]
    blame: dict[str, int]
    error_types: dict[str, int]
    cautions: dict[str, int]
    flagged_documents: dict[str, int]
    worst: list[WorstAnswer]


def _risk(report: Report) -> float:
    return report.domain.calibrated_risk if report.domain else report.risk


def _cautions(report: Report) -> Counter:
    found = Counter()
    for claim in report.claims:
        for caution in claim.cautions:
            found["overclaim" if caution.startswith("overclaim") else "wrong citation"] += 1
        found["contested by the sources"] += claim.status == "contested"
    found["dropped caveat"] += len(report.completeness.omitted_caveats) if report.completeness else 0
    return found


def summarize(samples: list[Sample], reports: list[Report], seed: int = 0) -> AuditSummary:
    risks = np.array([_risk(r) for r in reports])
    rng = np.random.default_rng(seed)
    means = [rng.choice(risks, len(risks)).mean() for _ in range(BOOTSTRAP)]
    labelled = [s.labels.response == "hallucinated" for s in samples if s.labels is not None]
    cautions, documents, errors = Counter(), Counter(), Counter()
    for report in reports:
        cautions += _cautions(report)
        for claim in report.claims:
            if claim.status in FLAGGED:
                errors[str(claim.type or claim.status)] += 1
                if claim.evidence and claim.evidence.document_id:
                    documents[claim.evidence.document_id] += 1
    worst = []
    for report in sorted(reports, key=_risk, reverse=True)[:WORST]:
        flagged = next((c for c in report.claims if c.status in FLAGGED), None)
        worst.append(WorstAnswer(
            id=report.id, risk=_risk(report), grade=report.card.grade if report.card else "?",
            claim=flagged.text[:200] if flagged else "", explanation=flagged.explanation if flagged else "risk spread over the answer",
        ))
    return AuditSummary(
        answers=len(reports),
        estimated_hallucination_rate=float(risks.mean()),
        estimate_interval=(float(np.percentile(means, 5)), float(np.percentile(means, 95))),
        true_hallucination_rate=float(np.mean(labelled)) if len(labelled) == len(samples) and samples else None,
        verdicts=dict(Counter(r.verdict for r in reports)),
        grades=dict(sorted(Counter(r.card.grade for r in reports if r.card).items())),
        lanes=dict(Counter(r.triage.lane for r in reports if r.triage)),
        blame=dict(Counter(r.diagnosis.blame for r in reports if r.diagnosis).most_common()),
        error_types=dict(errors.most_common()),
        cautions=dict(cautions.most_common()),
        flagged_documents=dict(documents.most_common(10)),
        worst=worst,
    )


def audit(samples: list[Sample], analyze: Callable[[Sample], Report], progress: Callable[[int, int], None] | None = None) -> tuple[AuditSummary, list[Report]]:
    reports = []
    for i, sample in enumerate(samples, 1):
        reports.append(analyze(sample))
        if progress:
            progress(i, len(samples))
    return summarize(samples, reports), reports
