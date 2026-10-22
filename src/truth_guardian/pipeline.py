"""Live analysis of one answer: compute signals, score with a saved fusion model, apply overrides, build the report.

Around the score it adds the atomic claim carrying each error, meaning shifts (swapped roles override the score;
overclaims become cautions), conflicts between sources, citation checks, the key evidence the answer leaves out,
who is to blame (retriever, generator or conflicting sources), the conformal guarantee, the reliability card and,
for agent trajectories, the step timeline with the guardian's alerts. `heal` corrects an answer and re-checks it.

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
from truth_guardian.conformal import Calibration
from truth_guardian.guardian import Policy, replay
from truth_guardian.heal import Healing
from truth_guardian.heal import heal as heal_answer
from truth_guardian.overrides import apply_polarity, apply_shifts
from truth_guardian.report import Report, agent_report, build_report, completeness_report, with_diagnosis, with_guarantee
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
) -> Sample:
    """agent_steps: dicts with step, kind, content and optionally observation; tool outputs also become sources."""
    steps = [AgentStep.model_validate(s) for s in agent_steps or []]
    documents = [Document(id=f"source{i}", text=t) for i, t in enumerate(sources, 1) if t.strip()]
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
    classify=None,
    calibration: Calibration | None = None,
    alpha: float = 0.1,
) -> Report:
    """consistency, encode and classify override HHEM, the sentence encoder and NLI in the tracer, claim, citation,
    omission, blame and conflict checks (tests); calibration adds the conformal guarantee at error rate alpha."""
    consistency = consistency or models.hhem_consistency
    encode = encode or models.encode
    classify = classify or models.nli_probabilities
    overrides = [*(["polarity"] if use_polarity else []), *(["shifts"] if use_shifts else [])]
    signal_fns = signal_fns or {name: SIGNALS[name][1] for name in [*model.signals, *overrides]}
    sentences = split_sentences(sample.answer)
    per_signal = {
        name: [{"start": s.start, "end": s.end, **row} for s, row in zip(sentences, signal_fns[name](sample, sentences))]
        for name in signal_fns
    }
    table = build_table([sample], {name: {sample.id: per_signal[name]} for name in model.signals}, model.signals, model.structure)
    prediction = model.predictions([sample], table)[0]
    if use_polarity and "polarity" in per_signal:
        prediction = apply_polarity(prediction, per_signal["polarity"])
    if use_shifts and "shifts" in per_signal:
        prediction = apply_shifts(prediction, per_signal["shifts"])

    merged = [{k: v for name in per_signal for k, v in per_signal[name][i].items()} for i in range(len(sentences))]
    flagged = {(s.start, s.end) for s in prediction.sentences if s.score >= model.thresholds["sentence"]}
    fixes = [suggest(sample, s) if (s.start, s.end) in flagged else [] for s in sentences]
    premise_for = lambda text: premises(sample, [Sentence(0, len(text), text)])[0]
    focus = [localize(s, row, premise_for, consistency) if (s.start, s.end) in flagged else [] for s, row in zip(sentences, merged)]
    agent = None
    if tracer is not None and sample.agent_log:
        agent = agent_report(sample, *tracer.analyse(sample, consistency), alerts=replay(sample, guardian_policy))
    omissions = completeness_report(completeness.check(sample, encode))
    found = conflicts.find_conflicts(sample, classify)
    sides = [conflicts.contested(s, found) for s in sentences]
    citation_checks = citations.check_sample(sample, sentences, consistency)
    report = build_report(sample, sentences, prediction, merged, fixes, model.thresholds, model_version, agent, focus, omissions, found, sides, citation_checks)
    report = with_diagnosis(report, diagnosis.diagnose(sample, report.verdict != "grounded", encode))
    if calibration is not None:
        report = with_guarantee(report, calibration, alpha, sample.meta.task)
    return report.model_copy(update={"card": build_card(report)})


def heal(sample: Sample, model: FusionModel | EnsembleModel, **options) -> Healing:
    """Correct the answer from its own report and check it again (heal.py); options go to analyze."""
    return heal_answer(sample, lambda s: analyze(s, model, **options))
