"""Live analysis of one answer: compute signals, score with a saved fusion model, apply overrides, build the report.

This is what the web app and API call. Signals are computed on the fly (nothing is read from the cache),
so any question, sources and answer can be checked.
"""

from collections.abc import Callable

from truth_guardian.correct import suggest
from truth_guardian.fusion import EnsembleModel, FusionModel, build_table
from truth_guardian.overrides import apply_polarity
from truth_guardian.report import Report, build_report
from truth_guardian.schema import Document, Meta, Sample
from truth_guardian.signals import SIGNALS
from truth_guardian.text import split_sentences

SignalFn = Callable[[Sample, list], list[dict]]


def make_sample(answer: str, sources: list[str], question: str | None = None, sample_id: str = "input") -> Sample:
    return Sample(
        id=sample_id,
        question=question,
        documents=[Document(id=f"source{i}", text=t) for i, t in enumerate(sources, 1) if t.strip()],
        answer=answer,
        meta=Meta(dataset="live", task="live", split="test", group_id=sample_id),
    )


def analyze(
    sample: Sample,
    model: FusionModel | EnsembleModel,
    use_polarity: bool = True,
    signal_fns: dict[str, SignalFn] | None = None,
    model_version: str | None = None,
) -> Report:
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
    return build_report(sample, sentences, prediction, merged, fixes, model.thresholds, model_version)
