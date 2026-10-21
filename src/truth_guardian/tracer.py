"""Provenance tracer: find the agent step where a hallucination first enters a trajectory.

Time rule: at step k the agent may only rely on the question and on tool outputs of steps before k.
For each step we measure what it introduces that this evidence does not contain (numbers, dates, names,
new content words), whether its own tool call failed, and whether its unsupported items reach the final
answer. The highest-scoring step is the suspected origin. v0 weights are set by hand; Phase 3 learns them.
"""

import math
import re
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from truth_guardian.schema import Sample
from truth_guardian.symbolic import Atom, EvidenceIndex
from truth_guardian.text import content_words

MAX_STEP_CHARS = 20_000
TOOL_ERROR = re.compile(r"\b(error|exception|traceback|not found|no such|failed|invalid|denied|unable to|cannot)\b", re.IGNORECASE)
WEIGHTS = {"unsupported": 1.0, "propagated": 1.5, "tool_error": 1.0, "novelty": 1.0, "is_first": 0.3}


class StepTrace(NamedTuple):
    step: int
    unsupported: list[Atom]
    propagated: list[str]
    novelty: float
    tool_error: bool
    score: float

    def reason(self) -> str:
        parts = []
        if self.propagated:
            parts.append(f"introduces {', '.join(sorted(set(self.propagated))[:3])}, absent from earlier tool outputs, which reaches the final answer")
        elif self.unsupported:
            parts.append(f"introduces {', '.join(sorted({a.text for a in self.unsupported})[:3])}, absent from earlier tool outputs")
        if self.tool_error:
            parts.append("its tool call returned an error")
        if self.novelty >= 0.5:
            parts.append(f"{self.novelty:.0%} of its content words appear nowhere earlier")
        return "; ".join(parts) or "no specific warning sign"


def trace(sample: Sample) -> list[StepTrace]:
    if not sample.agent_log:
        return []
    answer = sample.answer.lower()
    evidence = EvidenceIndex(sample.question or "")
    seen_words = content_words(sample.question or "")
    traces = []
    for i, step in enumerate(sample.agent_log):
        content = step.content[:MAX_STEP_CHARS]
        atoms = evidence.atoms(content) if content else []
        propagated = [a.text for a in atoms if a.text.lower() in answer]
        words = content_words(content)
        novelty = len(words - seen_words) / len(words) if words else 0.0
        tool_error = bool(step.observation and TOOL_ERROR.search(step.observation[:MAX_STEP_CHARS]))
        score = (
            WEIGHTS["unsupported"] * min(len(atoms), 3)
            + WEIGHTS["propagated"] * min(len(propagated), 3)
            + WEIGHTS["tool_error"] * tool_error
            + WEIGHTS["novelty"] * novelty
            + WEIGHTS["is_first"] * (i == 0)
        )
        traces.append(StepTrace(step.step, atoms, propagated, novelty, tool_error, score))
        seen_words |= words
        if step.observation:
            observation = step.observation[:MAX_STEP_CHARS]
            evidence.add(observation)
            seen_words |= content_words(observation)
    return traces


def suspected_step(traces: list[StepTrace]) -> StepTrace | None:
    """Highest score; ties go to the earliest step, since a hallucination's origin precedes its spread."""
    return max(traces, key=lambda t: (t.score, -t.step)) if traces else None


STEP_FEATURES = [
    "unsupported_numbers", "unsupported_entities", "propagated", "tool_error", "novelty",
    "is_first", "is_last", "position", "is_action", "is_thought", "is_answer", "log_content_chars", "has_observation",
]


def step_features(sample: Sample, traces: list[StepTrace]) -> np.ndarray:
    """One row per step, in the order of STEP_FEATURES."""
    rows = []
    n = len(traces)
    for i, (step, t) in enumerate(zip(sample.agent_log, traces)):
        rows.append([
            min(sum(a.kind == "number" for a in t.unsupported), 5),
            min(sum(a.kind == "entity" for a in t.unsupported), 5),
            min(len(t.propagated), 5),
            float(t.tool_error),
            t.novelty,
            float(i == 0),
            float(i == n - 1),
            i / max(n - 1, 1),
            float(step.kind == "action"),
            float(step.kind == "thought"),
            float(step.kind == "answer"),
            math.log1p(len(step.content)),
            float(bool(step.observation)),
        ])
    return np.array(rows, dtype=float).reshape(-1, len(STEP_FEATURES))


def trajectory_features(steps: np.ndarray) -> np.ndarray:
    """Max and mean of every step feature, plus the number of steps."""
    if len(steps) == 0:
        return np.zeros(2 * len(STEP_FEATURES) + 1)
    return np.concatenate([steps.max(axis=0), steps.mean(axis=0), [len(steps)]])


@dataclass
class LearnedTracer:
    """Two logistic regressions on the same step evidence: which step is the origin, and is anything wrong at all."""

    step_model: object
    detector: object
    feature_names: list[str]
    signal_versions: dict[str, str] = field(default_factory=dict)

    def step_probabilities(self, sample: Sample) -> list[tuple[int, float]]:
        traces = trace(sample)
        if not traces:
            return []
        probs = self.step_model.predict_proba(step_features(sample, traces))[:, 1]
        return [(t.step, float(p)) for t, p in zip(traces, probs)]

    def risk(self, sample: Sample) -> float:
        steps = step_features(sample, trace(sample))
        return float(self.detector.predict_proba(trajectory_features(steps).reshape(1, -1))[:, 1][0])


def _classifier():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))


def fit_tracer(samples: list[Sample], features: dict[str, tuple[list[StepTrace], np.ndarray]]) -> LearnedTracer:
    """features[sample.id] = (traces, step feature matrix); step model uses hallucinated trajectories only."""
    xs, ys = [], []
    for s in samples:
        traces, matrix = features[s.id]
        if s.labels.responsible_step is None or not traces:
            continue
        xs.append(matrix)
        ys += [int(t.step == s.labels.responsible_step) for t in traces]
    detector_x = np.stack([trajectory_features(features[s.id][1]) for s in samples])
    detector_y = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
    return LearnedTracer(
        step_model=_classifier().fit(np.vstack(xs), np.array(ys)),
        detector=_classifier().fit(detector_x, detector_y),
        feature_names=STEP_FEATURES,
    )
