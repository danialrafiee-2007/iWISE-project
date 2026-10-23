"""The report contract: what every interface (web app, API, batch file) receives for one checked answer.

Per claim (sentence): status, risk, error type, exact words, evidence, a plain-language explanation,
a suggested action, Fix-it replacements, the atomic claim that carries the error, cautions (overclaims, wrong
citations) and whether the sources disagree about it. Per answer: verdict, calibrated risk, who is to blame
(retriever, generator or conflicting sources), which key evidence it leaves out, conflicts between sources, the
conformal guarantee, the reliability card and warnings. "Insufficient evidence" and "contested" are kept apart from
"contradicted" and "unsupported", and an answer whose risk sits close to the decision threshold is reported as
"uncertain" instead of forcing a verdict.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from truth_guardian.citations import CitationCheck, cite
from truth_guardian.completeness import Completeness
from truth_guardian.conflicts import Conflict
from truth_guardian.conformal import Calibration
from truth_guardian.correct import Suggestion as FixSuggestion
from truth_guardian.correct import _source_index, _singular
from truth_guardian.diagnosis import MESSAGES, Blame, Diagnosis
from truth_guardian.evaluation import Prediction
from truth_guardian.explain import explain_sentence
from truth_guardian.guardian import Alert
from truth_guardian.schema import HallucinationType, Sample
from truth_guardian.text import Sentence

UNCERTAIN_BAND = 0.1
SPREAD_RISK_CONTRIBUTION = 0.05

Status = Literal["supported", "contradicted", "unsupported", "insufficient_evidence", "contested"]
Action = Literal["keep", "replace", "remove", "verify"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(_Strict):
    text: str
    document_id: str | None = None


class Fix(_Strict):
    start: int
    end: int
    original: str
    replacement: str | None
    confidence: float


class CitationReport(_Strict):
    cited: list[int]
    supported: bool
    better_document: int | None = None


class ClaimReport(_Strict):
    start: int
    end: int
    text: str
    status: Status
    risk: float
    type: HallucinationType | None = None
    spans: list[tuple[int, int]] = Field(default_factory=list)
    focus: list[tuple[int, int]] = Field(default_factory=list)
    evidence: Evidence | None = None
    explanation: str
    action: Action
    fixes: list[Fix] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    citation: CitationReport | None = None
    contribution: float | None = None


class AgentStepReport(_Strict):
    step: int
    kind: str
    role: str | None = None
    suspicion: float
    reason: str
    unsupported: list[str] = Field(default_factory=list)
    tool_error: bool = False


class AgentAlert(_Strict):
    step: int
    level: Literal["warning", "stop"]
    reason: str


class AgentReport(_Strict):
    """Timeline of an agent trajectory: how suspicious each step is, where the hallucination most likely began,
    and where the live guardian would have warned or stopped the agent."""

    risk: float
    suspected_step: int | None
    steps: list[AgentStepReport]
    alerts: list[AgentAlert] = Field(default_factory=list)
    guardian_stop: int | None = None


class DiagnosisReport(_Strict):
    """Who is to blame: the retriever (sources miss the question) or the generator (answer departs from good sources)."""

    blame: Blame
    message: str
    relevance: float | None = None
    question_similarity: float | None = None
    question_coverage: float | None = None


class CompletenessReport(_Strict):
    """Key evidence for the question that the answer leaves out; dropped caveats are singled out."""

    score: float | None
    key_evidence: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    omitted_caveats: list[str] = Field(default_factory=list)


class ConflictReport(_Strict):
    first: str
    first_document: str
    second: str
    second_document: str
    first_value: str
    second_value: str


class GuaranteeReport(_Strict):
    """Split-conformal thresholds: flagging at `catch_threshold` misses at most alpha of hallucinated answers, flagging
    above `alarm_threshold` raises at most alpha false alarms, for answers like the calibration data."""

    alpha: float
    catch_threshold: float
    alarm_threshold: float
    flagged_with_catch_guarantee: bool
    flagged_with_alarm_guarantee: bool
    calibrated_on: str


class TriageReport(_Strict):
    """Which lane the answer goes to: out unchecked, to a person, or blocked, and why."""

    lane: Literal["pass", "review", "block"]
    reason: str


class DomainReport(_Strict):
    """The answer seen through a domain profile: the risk recalibrated on that domain's labelled answers."""

    name: str
    examples: int
    calibrated_risk: float


class Dimension(_Strict):
    name: str
    score: float | None
    note: str


class Card(_Strict):
    """Reliability card: a grade from the calibrated risk alone, with the other dimensions shown beside it."""

    grade: Literal["A", "B", "C", "D", "F"]
    risk: float
    dimensions: list[Dimension]


class Report(_Strict):
    id: str
    verdict: Literal["grounded", "hallucinated", "uncertain"]
    risk: float
    response_threshold: float
    sentence_threshold: float
    claims: list[ClaimReport]
    agent: AgentReport | None = None
    diagnosis: DiagnosisReport | None = None
    completeness: CompletenessReport | None = None
    conflicts: list[ConflictReport] = Field(default_factory=list)
    guarantee: GuaranteeReport | None = None
    domain: DomainReport | None = None
    triage: TriageReport | None = None
    card: Card | None = None
    cited_answer: str | None = None
    warnings: list[str] = Field(default_factory=list)
    model_version: str | None = None


_STATUS = {
    HallucinationType.CONTRADICTED: "contradicted",
    HallucinationType.NUMERIC_ENTITY_MISMATCH: "contradicted",
    HallucinationType.PARTIAL: "unsupported",
    HallucinationType.UNSUPPORTED: "unsupported",
    HallucinationType.WEAK_EVIDENCE: "insufficient_evidence",
    HallucinationType.AGENT_INTRODUCED: "unsupported",
    HallucinationType.OVERCLAIM: "unsupported",
}


def best_evidence(sample: Sample, sentence: Sentence) -> Evidence | None:
    """The source sentence closest to the claim (BM25 with plural folding over the sentences of every document, so
    scores from different documents are comparable), with the document it came from."""
    sentences, bm25 = _source_index(tuple(d.text for d in sample.documents))
    if not sentences:
        return None
    owners = [d.id for d in sample.documents for _ in _source_index((d.text,))[0]]
    scores = bm25.scores(_singular(sentence.text))
    i = int(scores.argmax())
    return Evidence(text=sentences[i], document_id=owners[i]) if scores[i] > 0 else None


def _cautions(row: dict, citation: CitationCheck | None) -> list[str]:
    cautions = []
    if row.get("shift_confirmed") and not row.get("shift_overrides"):
        cautions.append(f"overclaim: {row['shift_detail']}")
    if citation is not None and citation.wrong:
        cited = ", ".join(str(n) for n in citation.cited)
        cautions.append(f"cites document {cited}, but the passage that matches this claim is in document {citation.best_other}")
    return cautions


def claim_report(
    sample: Sample,
    sentence: Sentence,
    risk: float,
    threshold: float,
    row: dict,
    fixes: list[FixSuggestion],
    focus: list[tuple[int, int]] | None = None,
    side: tuple[Conflict, str] | None = None,
    citation: CitationCheck | None = None,
    contribution: float | None = None,
) -> ClaimReport:
    """focus: the claim spans that carry the error, kept only when narrower than the whole sentence; side: the source
    conflict this claim takes a side in and the document it follows; citation: the check of its cited documents;
    contribution: how much the answer's risk falls without this claim."""
    extras = {
        "contribution": contribution,
        "cautions": _cautions(row, citation),
        "citation": CitationReport(cited=citation.cited, supported=not citation.wrong, better_document=citation.best_other if citation.wrong else None) if citation else None,
    }
    if side is not None:
        conflict, document = side
        followed = conflict.first if document == conflict.first_document else conflict.second
        explanation = f'the sources disagree: {conflict.first_document} says "{conflict.first_value}", {conflict.second_document} says "{conflict.second_value}"; the answer follows {document}'
        return ClaimReport(
            start=sentence.start, end=sentence.end, text=sentence.text, status="contested", risk=risk,
            evidence=Evidence(text=followed, document_id=document), explanation=explanation, action="verify", **extras,
        )
    if row.get("pol_confirmed") and row.get("pol_evidence"):
        evidence = Evidence(text=row["pol_evidence"])
    elif row.get("shift_overrides") and row.get("shift_evidence"):
        evidence = Evidence(text=row["shift_evidence"])
    else:
        evidence = best_evidence(sample, sentence)
    if risk < threshold and not row.get("pol_confirmed"):
        return ClaimReport(start=sentence.start, end=sentence.end, text=sentence.text, status="supported", risk=risk, evidence=evidence, explanation="the sources support this claim", action="keep", **extras)
    explanation = explain_sentence(row, sentence.start, sentence.end)
    status: Status = _STATUS[explanation.type]
    replacements = [Fix(start=f.start, end=f.end, original=f.original, replacement=f.replacement, confidence=f.confidence) for f in fixes]
    if any(f.replacement for f in replacements):
        action: Action = "replace"
    elif status == "insufficient_evidence" or status == "contradicted":
        action = "verify"
    else:
        action = "remove"
    return ClaimReport(
        start=sentence.start, end=sentence.end, text=sentence.text, status=status, risk=risk,
        type=explanation.type, spans=explanation.spans, evidence=evidence,
        focus=[f for f in focus or [] if f != (sentence.start, sentence.end)],
        explanation=explanation.reason, action=action, fixes=replacements, **extras,
    )


def verdict(risk: float, threshold: float, claims: list[ClaimReport]) -> Literal["grounded", "hallucinated", "uncertain"]:
    if any(c.status == "contradicted" for c in claims) and risk >= threshold:
        return "hallucinated"
    if abs(risk - threshold) < UNCERTAIN_BAND:
        return "uncertain"
    flagged = [c for c in claims if c.status != "supported"]
    if flagged and all(c.status in ("insufficient_evidence", "contested") for c in flagged):
        return "uncertain"
    return "hallucinated" if risk >= threshold else "grounded"


def agent_report(sample: Sample, traces: list, probabilities, risk: float, alerts: list[Alert] = ()) -> AgentReport:
    """traces and probabilities come from LearnedTracer.analyse, in step order; alerts from guardian.replay."""
    steps = [
        AgentStepReport(
            step=t.step, kind=s.kind, role=s.role, suspicion=float(p), reason=t.reason(),
            unsupported=sorted({a.text for a in t.unsupported})[:5], tool_error=t.tool_error,
        )
        for s, t, p in zip(sample.agent_log or [], traces, probabilities)
    ]
    suspected = max(steps, key=lambda s: (s.suspicion, -s.step)).step if steps else None
    stop = next((a.step for a in alerts if a.level == "stop"), None)
    return AgentReport(
        risk=risk, suspected_step=suspected, steps=steps,
        alerts=[AgentAlert(step=a.step, level=a.level, reason=a.reason) for a in alerts], guardian_stop=stop,
    )


def completeness_report(c: Completeness) -> CompletenessReport | None:
    if c.score is None and not c.key_evidence:
        return None
    return CompletenessReport(score=c.score, key_evidence=c.key_evidence, missing=c.missing, omitted_caveats=c.omitted_caveats)


def with_diagnosis(report: Report, d: Diagnosis) -> Report:
    """Diagnosis needs the verdict, so it is attached after the report is built; doubtful sources also become a warning.
    When every flagged claim is contested, the sources themselves are to blame."""
    flagged = [c for c in report.claims if c.status != "supported"]
    if flagged and all(c.status == "contested" for c in flagged):
        d = d._replace(blame="conflicting_sources", message=MESSAGES["conflicting_sources"])
    diagnosis = DiagnosisReport(
        blame=d.blame, message=d.message, relevance=d.relevance, question_similarity=d.question_similarity, question_coverage=d.question_coverage,
    )
    warnings = report.warnings + ([d.message] if d.blame in ("retrieval", "weak_sources") else [])
    return report.model_copy(update={"diagnosis": diagnosis, "warnings": warnings})


def with_guarantee(report: Report, calibration: Calibration, alpha: float, task: str | None = None) -> Report:
    t = calibration.get(alpha, task)
    guarantee = GuaranteeReport(
        alpha=alpha, catch_threshold=t.catch, alarm_threshold=t.alarm,
        flagged_with_catch_guarantee=report.risk >= t.catch, flagged_with_alarm_guarantee=report.risk > t.alarm,
        calibrated_on=f"{calibration.data} ({t.hallucinated} hallucinated, {t.grounded} grounded answers)",
    )
    return report.model_copy(update={"guarantee": guarantee})


def with_triage(report: Report, lane: str, reason: str) -> Report:
    return report.model_copy(update={"triage": TriageReport(lane=lane, reason=reason)})


def cited_answer(sample: Sample, claims: list[ClaimReport]) -> str | None:
    """The answer with [n] after each supported claim, n being its evidence document's position."""
    numbers = {d.id: i for i, d in enumerate(sample.documents, 1)}
    marks = [(c.start, c.end, numbers.get(c.evidence.document_id)) for c in claims if c.status == "supported" and c.evidence]
    return cite(sample.answer, marks) if any(n for _, _, n in marks) else None


def build_report(
    sample: Sample,
    sentences: list[Sentence],
    prediction: Prediction,
    rows: list[dict],
    fixes: list[list[FixSuggestion]],
    thresholds: dict[str, float],
    model_version: str | None = None,
    agent: AgentReport | None = None,
    focus: list[list[tuple[int, int]]] | None = None,
    completeness: CompletenessReport | None = None,
    conflicts: list[Conflict] = (),
    sides: list[tuple[Conflict, str] | None] | None = None,
    citations: list[CitationCheck | None] | None = None,
    contributions: list[float | None] | None = None,
) -> Report:
    """rows[i] merges every signal's output for sentence i; fixes[i] are its Fix-it suggestions; focus[i] its error
    claims; sides[i] the source conflict it takes a side in; citations[i] the check of the documents it cites;
    contributions[i] how much the answer's risk falls without it."""
    sentence_scores = {(s.start, s.end): s.score for s in prediction.sentences}
    empty = [None for _ in sentences]
    claims = [
        claim_report(sample, s, sentence_scores.get((s.start, s.end), 0.0), thresholds["sentence"], row, fix, f, side, citation, contribution)
        for s, row, fix, f, side, citation, contribution in zip(
            sentences, rows, fixes, focus or [[] for _ in sentences], sides or empty, citations or empty, contributions or empty
        )
    ]
    warnings = []
    if claims and all(c.evidence is None for c in claims):
        warnings.append("the sources share almost no words with the answer; they may not be about this question")
    for caveat in (completeness.omitted_caveats if completeness else [])[:2]:
        warnings.append(f'the answer leaves out a condition stated in the sources: "{caveat}"')
    answer_verdict = verdict(prediction.score, thresholds["response"], claims)
    carriers = [c for c in claims if (c.contribution or 0.0) >= SPREAD_RISK_CONTRIBUTION]
    if answer_verdict != "grounded" and carriers and all(c.status == "supported" for c in claims):
        top = max(carriers, key=lambda c: c.contribution)
        warnings.append(f'no single claim is flagged; the answer\'s risk comes mostly from "{top.text[:80]}" (+{top.contribution:.2f})')
    return Report(
        id=sample.id,
        verdict=answer_verdict,
        risk=prediction.score,
        response_threshold=thresholds["response"],
        sentence_threshold=thresholds["sentence"],
        claims=claims,
        agent=agent,
        completeness=completeness,
        conflicts=[
            ConflictReport(first=c.first, first_document=c.first_document, second=c.second, second_document=c.second_document, first_value=c.first_value, second_value=c.second_value)
            for c in conflicts
        ],
        cited_answer=cited_answer(sample, claims),
        warnings=warnings,
        model_version=model_version,
    )
