"""Live analysis of one answer: compute signals, score with a saved fusion model, apply overrides, build the report.

Around the score it adds the atomic claim carrying each error, the key evidence the answer leaves out, who is
to blame (retriever or generator) and, for agent trajectories, the step timeline with the guardian's alerts.

This is what the web app and API call. Signals are computed on the fly (nothing is read from the cache),
so any question, sources and answer can be checked.
"""

from collections.abc import Callable

from truth_guardian import completeness, diagnosis, models
from truth_guardian.claims import localize
from truth_guardian.correct import suggest
from truth_guardian.evidence import Encoder
from truth_guardian.fusion import EnsembleModel, FusionModel, build_table
from truth_guardian.guardian import Policy, replay
from truth_guardian.overrides import apply_polarity
from truth_guardian.report import Report, agent_report, build_report, completeness_report, with_diagnosis
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
) -> Report:
    """consistency and encode override HHEM and the sentence encoder in the tracer, claim, omission and blame checks (tests)."""
    consistency = consistency or models.hhem_consistency
    encode = encode or models.encode
    signal_fns = signal_fns or {name: SIGNALS[name][1] for name in [*model.signals, *(["polarity"] if use_polarity else [])]}
    sentences = split_sentences(sample.answer)
    per_signal = {
        name: [{"start": s.start, "end": s.end, **row} for s, row in zip(sentences, signal_fns[name](sample, sentences))]
        for name in signal_fns
    }
    table = build_table([sample], {name: {sample.id: per_signal[name]} for name in model.signals}, model.signals, model.structure)
    prediction = model.predictions([sample], table)[0]
    if use_polarity and "polarity" in per_signal:
        prediction = apply_polarity(prediction, per_signal["polarity"])

    merged = [{k: v for name in per_signal for k, v in per_signal[name][i].items()} for i in range(len(sentences))]
    flagged = {(s.start, s.end) for s in prediction.sentences if s.score >= model.thresholds["sentence"]}
    fixes = [suggest(sample, s) if (s.start, s.end) in flagged else [] for s in sentences]
    premise_for = lambda text: premises(sample, [Sentence(0, len(text), text)])[0]
    focus = [localize(s, row, premise_for, consistency) if (s.start, s.end) in flagged else [] for s, row in zip(sentences, merged)]
    agent = None
    if tracer is not None and sample.agent_log:
        agent = agent_report(sample, *tracer.analyse(sample, consistency), alerts=replay(sample, guardian_policy))
    omissions = completeness_report(completeness.check(sample, encode))
    report = build_report(sample, sentences, prediction, merged, fixes, model.thresholds, model_version, agent, focus, omissions)
    return with_diagnosis(report, diagnosis.diagnose(sample, report.verdict != "grounded", encode))
