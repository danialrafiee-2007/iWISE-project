"""Live analysis of one answer: compute signals, score with a saved fusion model, apply overrides, build the report.

Around the score it adds the atomic claim carrying each error, meaning shifts (swapped roles override the score;
overclaims become cautions), conflicts between sources, citation checks, the key evidence the answer leaves out,
who is to blame (retriever, generator or conflicting sources), the conformal guarantee, the triage lane, the
reliability card, each claim's contribution to the answer's risk and, for agent trajectories, the step timeline
with the guardian's alerts. A domain profile (adapt.py) replaces the RAGTruth calibration for another domain.
`heal` corrects an answer and re-checks it.

This is what the web app and API call. Signals are computed on the fly (nothing is read from the cache),
so any question, sources and answer can be checked.
"""

from collections.abc import Callable

from truth_guardian import citations, completeness, conflicts, diagnosis, models
from truth_guardian.card import build_card
from truth_guardian.claims import localize
from truth_guardian.correct import suggest
from truth_guardian.evidence import Encoder
from truth_guardian.fusion import EnsembleModel, FusionModel, build_table
from truth_guardian.adapt import DomainProfile, domain_features
from truth_guardian.conformal import Calibration
from truth_guardian.guardian import Policy, replay
from truth_guardian.heal import Healing
from truth_guardian.heal import heal as heal_answer
from truth_guardian.detector import shipped as shipped_detector
from truth_guardian.overrides import apply_flips, apply_polarity, apply_shifts, with_words
from truth_guardian.report import DomainReport, Report, agent_report, build_report, completeness_report, verdict, with_diagnosis, with_guarantee, with_triage
from truth_guardian.triage import BLOCK_FALSE_ALARM
from truth_guardian.triage import Policy as TriagePolicy
from truth_guardian.schema import AgentStep, Document, Meta, Sample
from truth_guardian.signals import SIGNALS, premises
from truth_guardian.text import Sentence, split_sentences
from truth_guardian.tracer import LearnedTracer

SignalFn = Callable[[Sample, list], list[dict]]


def make_sample(
    answer: str,
    sources: list[str],
    question: str | None = None,
    agent_steps: list[dict] | None = None,
    sample_id: str = "input",
    origins: list[str | None] | None = None,
) -> Sample:
    """agent_steps: dicts with step, kind, content and optionally observation; tool outputs also become sources.
    origins[i] names the file source i came from (parts of one long document share it)."""
    steps = [AgentStep.model_validate(s) for s in agent_steps or []]
    origins = origins or []
    documents = [
        Document(id=f"source{i}", text=t, origin=origins[i - 1] if i - 1 < len(origins) else None)
        for i, t in enumerate(sources, 1) if t.strip()
    ]
    documents += [Document(id=f"step{s.step}", text=s.observation, source=f"step {s.step} tool output") for s in steps if s.observation]
    if not documents and question:
        documents = [Document(id="task", text=question, source="question")]
    return Sample(
        id=sample_id,
        question=question,
        documents=documents,
        answer=answer,
        agent_log=steps or None,
        meta=Meta(dataset="live", task="live", split="test", group_id=sample_id),
    )


def _risk(sample: Sample, model, per_signal: dict[str, list[dict]], keep: list[int], use_polarity: bool, use_shifts: bool) -> float:
    """The answer's risk from a subset of its sentences, reusing their signal rows."""
    rows = {name: {sample.id: [per_signal[name][i] for i in keep]} for name in model.signals}
    prediction = model.predictions([sample], build_table([sample], rows, model.signals, model.structure))[0]
    if use_polarity and "polarity" in per_signal:
        prediction = apply_polarity(prediction, [per_signal["polarity"][i] for i in keep])
    if use_shifts and "shifts" in per_signal:
        prediction = apply_shifts(prediction, [per_signal["shifts"][i] for i in keep])
    if "flips" in per_signal:
        prediction = apply_flips(prediction, [per_signal["flips"][i] for i in keep])
    return prediction.score


def contributions(sample: Sample, model, per_signal: dict[str, list[dict]], risk: float, use_polarity: bool, use_shifts: bool) -> list[float | None]:
    """Leave-one-out attribution: how much the answer's risk falls without each sentence (None for one sentence).

    The answer-level model reads all sentences together, so an answer can be risky without any single sentence
    crossing the sentence threshold; this shows which sentences carry that risk.
    """
    n = len(next(iter(per_signal.values()), []))
    if n < 2:
        return [None] * n
    return [risk - _risk(sample, model, per_signal, [j for j in range(n) if j != i], use_polarity, use_shifts) for i in range(n)]


def analyze(
    sample: Sample,
    model: FusionModel | EnsembleModel,
    use_polarity: bool = True,
    signal_fns: dict[str, SignalFn] | None = None,
    model_version: str | None = None,
    tracer: LearnedTracer | None = None,
    consistency=None,
    encode: Encoder | None = None,
    guardian_policy: Policy = "strict",
    use_shifts: bool = True,
    use_flips: bool = True,
    use_detector: bool = True,
    classify=None,
    calibration: Calibration | None = None,
    alpha: float = 0.1,
    triage_policy: TriagePolicy | None = None,
    profile: DomainProfile | None = None,
    progress: Callable[[str], None] | None = None,
) -> Report:
    """consistency, encode and classify override HHEM, the sentence encoder and NLI in the tracer, claim, citation,
    omission, blame and conflict checks (tests); calibration adds the conformal guarantee at error rate alpha and
    triage_policy the triage lane, both from RAGTruth; a domain profile replaces them with its own calibration.
    progress is told the name of each stage as it starts (each signal, then "score", "claims", "checks", "verdict")."""
    consistency = consistency or models.hhem_consistency
    encode = encode or models.encode
    classify = classify or models.nli_probabilities
    progress = progress or (lambda stage: None)
    overrides = [*(["polarity"] if use_polarity else []), *(["shifts"] if use_shifts else []), *(["flips"] if use_flips else [])]
    overrides += ["detector"] if use_detector and shipped_detector() is not None else []
    signal_fns = signal_fns or {name: SIGNALS[name][1] for name in [*model.signals, *overrides]}
    sentences = split_sentences(sample.answer)
    per_signal = {}
    for name in signal_fns:
        progress(name)
        per_signal[name] = [{"start": s.start, "end": s.end, **row} for s, row in zip(sentences, signal_fns[name](sample, sentences))]
    progress("score")
    table = build_table([sample], {name: {sample.id: per_signal[name]} for name in model.signals}, model.signals, model.structure)
    prediction = model.predictions([sample], table)[0]
    if use_polarity and "polarity" in per_signal:
        prediction = apply_polarity(prediction, per_signal["polarity"])
    if use_shifts and "shifts" in per_signal:
        prediction = apply_shifts(prediction, per_signal["shifts"])
    if use_flips and "flips" in per_signal:
        prediction = apply_flips(prediction, per_signal["flips"])
    if "detector" in per_signal:
        prediction = with_words(prediction, per_signal["detector"])

    progress("claims")
    merged = [{k: v for name in per_signal for k, v in per_signal[name][i].items()} for i in range(len(sentences))]
    flagged = {(s.start, s.end) for s in prediction.sentences if s.score >= model.thresholds["sentence"]}
    fixes = [suggest(sample, s) if (s.start, s.end) in flagged else [] for s in sentences]
    premise_for = lambda text: premises(sample, [Sentence(0, len(text), text)])[0]
    focus = [localize(s, row, premise_for, consistency) if (s.start, s.end) in flagged else [] for s, row in zip(sentences, merged)]
    agent = None
    if tracer is not None and sample.agent_log:
        agent = agent_report(sample, *tracer.analyse(sample, consistency), alerts=replay(sample, guardian_policy))
    progress("checks")
    omissions = completeness_report(completeness.check(sample, encode))
    found = conflicts.find_conflicts(sample, classify)
    sides = [conflicts.contested(s, found) for s in sentences]
    citation_checks = citations.check_sample(sample, sentences, consistency)
    shares = contributions(sample, model, per_signal, prediction.score, use_polarity, use_shifts)
    progress("verdict")
    report = build_report(sample, sentences, prediction, merged, fixes, model.thresholds, model_version, agent, focus, omissions, found, sides, citation_checks, shares)
    if profile is not None:
        risk = profile.domain_risk(report.risk, domain_features(report.risk, merged))
        report = report.model_copy(update={
            "verdict": verdict(risk, profile.decision, report.claims),
            "domain": DomainReport(name=profile.name, examples=profile.examples, calibrated_risk=risk, model_risk=report.risk, decision=profile.decision),
        })
    report = with_diagnosis(report, diagnosis.diagnose(sample, report.verdict != "grounded", encode))
    if profile is not None:
        report = with_guarantee(report, profile.calibration(), alpha, risk=report.domain.calibrated_risk)
        report = _domain_lane(report, profile, report.domain.calibrated_risk)
    else:
        if calibration is not None:
            report = with_guarantee(report, calibration, alpha, sample.meta.task)
        if triage_policy is not None:
            report = _lane(report, triage_policy)
    return report.model_copy(update={"card": build_card(report)})


def _lane(report: Report, policy: TriagePolicy) -> Report:
    lane = policy.lane(report.risk)
    reason = {
        "pass": f"risk below {policy.pass_below:.2f}: at most {policy.pass_error:.0%} of such answers are hallucinated ({policy.confidence:.0%} confidence)",
        "block": f"risk above {policy.block_from:.2f}: at most {policy.block_false_alarm:.0%} of grounded answers are blocked",
        "review": "risk between the pass and block lines: a person should check it",
    }[lane]
    return with_triage(report, lane, reason)


def _domain_lane(report: Report, profile: DomainProfile, risk: float) -> Report:
    """No pass lane on a domain profile: a few dozen labels cannot back one; blocking uses the domain's alarm line."""
    t = next((x for x in profile.thresholds if abs(x.alpha - BLOCK_FALSE_ALARM) < 1e-9), None)
    if t is not None and risk > t.alarm:
        return with_triage(report, "block", f"risk above this domain's alarm line {t.alarm:.2f}: at most {BLOCK_FALSE_ALARM:.0%} of its grounded answers are blocked")
    return with_triage(report, "review", f"domain profile {profile.name}: answers go to review unless blocked")


def heal(sample: Sample, model: FusionModel | EnsembleModel, strategy: dict | None = None, **options) -> Healing:
    """Correct the answer from its own report and check it again (heal.py); strategy goes to heal.heal, options to analyze."""
    return heal_answer(sample, lambda s: analyze(s, model, **options), **(strategy or {}))
