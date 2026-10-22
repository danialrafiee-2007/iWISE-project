"""The report contract: what every interface (web app, API, batch file) receives for one checked answer.

Per claim (sentence): status, risk, error type, exact words, evidence, a plain-language explanation,
a suggested action, Fix-it replacements and the atomic claim that carries the error. Per answer: verdict,
calibrated risk, who is to blame (retriever or generator), which key evidence it leaves out, and warnings.
"Insufficient evidence" is kept apart from "contradicted" and "unsupported", and an answer whose risk
sits close to the decision threshold is reported as "uncertain" instead of forcing a verdict.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from truth_guardian.completeness import Completeness
from truth_guardian.correct import Suggestion as FixSuggestion
from truth_guardian.correct import _source_index, _singular
from truth_guardian.diagnosis import Blame, Diagnosis
from truth_guardian.evaluation import Prediction
from truth_guardian.explain import explain_sentence
from truth_guardian.guardian import Alert
from truth_guardian.schema import HallucinationType, Sample
from truth_guardian.text import Sentence

UNCERTAIN_BAND = 0.1

Status = Literal["supported", "contradicted", "unsupported", "insufficient_evidence"]
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
    warnings: list[str] = Field(default_factory=list)
    model_version: str | None = None


_STATUS = {
    HallucinationType.CONTRADICTED: "contradicted",
    HallucinationType.NUMERIC_ENTITY_MISMATCH: "contradicted",
    HallucinationType.PARTIAL: "unsupported",
    HallucinationType.UNSUPPORTED: "unsupported",
    HallucinationType.WEAK_EVIDENCE: "insufficient_evidence",
    HallucinationType.AGENT_INTRODUCED: "unsupported",
}


def best_evidence(sample: Sample, sentence: Sentence) -> Evidence | None:
    """The source sentence closest to the claim (BM25 with plural folding), with the document it came from."""
    best, best_score = None, 0.0
    for doc in sample.documents:
        sentences, bm25 = _source_index((doc.text,))
        if not sentences:
            continue
        scores = bm25.scores(_singular(sentence.text))
        i = int(scores.argmax())
        if scores[i] > best_score:
            best, best_score = Evidence(text=sentences[i], document_id=doc.id), float(scores[i])
    return best


def claim_report(
    sample: Sample, sentence: Sentence, risk: float, threshold: float, row: dict, fixes: list[FixSuggestion], focus: list[tuple[int, int]] | None = None
) -> ClaimReport:
    """focus: the claim spans that carry the error; kept only when narrower than the whole sentence."""
    evidence = Evidence(text=row["pol_evidence"]) if row.get("pol_confirmed") and row.get("pol_evidence") else best_evidence(sample, sentence)
    if risk < threshold and not row.get("pol_confirmed"):
        return ClaimReport(start=sentence.start, end=sentence.end, text=sentence.text, status="supported", risk=risk, evidence=evidence, explanation="the sources support this claim", action="keep")
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
        explanation=explanation.reason, action=action, fixes=replacements,
    )


def verdict(risk: float, threshold: float, claims: list[ClaimReport]) -> Literal["grounded", "hallucinated", "uncertain"]:
    if any(c.status == "contradicted" for c in claims) and risk >= threshold:
        return "hallucinated"
    if abs(risk - threshold) < UNCERTAIN_BAND:
        return "uncertain"
    flagged = [c for c in claims if c.status != "supported"]
    if flagged and all(c.status == "insufficient_evidence" for c in flagged):
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
    """Diagnosis needs the verdict, so it is attached after the report is built; doubtful sources also become a warning."""
    diagnosis = DiagnosisReport(
        blame=d.blame, message=d.message, relevance=d.relevance, question_similarity=d.question_similarity, question_coverage=d.question_coverage,
    )
    warnings = report.warnings + ([d.message] if d.blame in ("retrieval", "weak_sources") else [])
    return report.model_copy(update={"diagnosis": diagnosis, "warnings": warnings})


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
) -> Report:
    """rows[i] merges every signal's output for sentence i; fixes[i] are its Fix-it suggestions; focus[i] its error claims."""
    sentence_scores = {(s.start, s.end): s.score for s in prediction.sentences}
    focus = focus or [[] for _ in sentences]
    claims = [
        claim_report(sample, s, sentence_scores.get((s.start, s.end), 0.0), thresholds["sentence"], row, fix, f)
        for s, row, fix, f in zip(sentences, rows, fixes, focus)
    ]
    warnings = []
    if claims and all(c.evidence is None for c in claims):
        warnings.append("the sources share almost no words with the answer; they may not be about this question")
    for caveat in (completeness.omitted_caveats if completeness else [])[:2]:
        warnings.append(f'the answer leaves out a condition stated in the sources: "{caveat}"')
    return Report(
        id=sample.id,
        verdict=verdict(prediction.score, thresholds["response"], claims),
        risk=prediction.score,
        response_threshold=thresholds["response"],
        sentence_threshold=thresholds["sentence"],
        claims=claims,
        agent=agent,
        completeness=completeness,
        warnings=warnings,
        model_version=model_version,
    )
