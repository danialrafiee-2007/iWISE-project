"""The report contract: what every interface (web app, API, batch file) receives for one checked answer.

Per claim (sentence): status, risk, error type, exact words, evidence, a plain-language explanation,
a suggested action and Fix-it replacements. Per answer: verdict, calibrated risk and warnings.
"Insufficient evidence" is kept apart from "contradicted" and "unsupported", and an answer whose risk
sits close to the decision threshold is reported as "uncertain" instead of forcing a verdict.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from truth_guardian.correct import Suggestion as FixSuggestion
from truth_guardian.correct import _source_index, _singular
from truth_guardian.evaluation import Prediction
from truth_guardian.explain import explain_sentence
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
    evidence: Evidence | None = None
    explanation: str
    action: Action
    fixes: list[Fix] = Field(default_factory=list)


class Report(_Strict):
    id: str
    verdict: Literal["grounded", "hallucinated", "uncertain"]
    risk: float
    response_threshold: float
    sentence_threshold: float
    claims: list[ClaimReport]
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


def claim_report(sample: Sample, sentence: Sentence, risk: float, threshold: float, row: dict, fixes: list[FixSuggestion]) -> ClaimReport:
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


def build_report(
    sample: Sample,
    sentences: list[Sentence],
    prediction: Prediction,
    rows: list[dict],
    fixes: list[list[FixSuggestion]],
    thresholds: dict[str, float],
    model_version: str | None = None,
) -> Report:
    """rows[i] merges every signal's output for sentence i; fixes[i] are its Fix-it suggestions."""
    sentence_scores = {(s.start, s.end): s.score for s in prediction.sentences}
    claims = [
        claim_report(sample, s, sentence_scores.get((s.start, s.end), 0.0), thresholds["sentence"], row, fix)
        for s, row, fix in zip(sentences, rows, fixes)
    ]
    warnings = []
    if claims and all(c.evidence is None for c in claims):
        warnings.append("the sources share almost no words with the answer; they may not be about this question")
    return Report(
        id=sample.id,
        verdict=verdict(prediction.score, thresholds["response"], claims),
        risk=prediction.score,
        response_threshold=thresholds["response"],
        sentence_threshold=thresholds["sentence"],
        claims=claims,
        warnings=warnings,
        model_version=model_version,
    )
