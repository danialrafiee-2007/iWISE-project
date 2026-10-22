"""Provenance tracer: find the agent step where a hallucination first enters a trajectory.

Time rule: at step k the agent may only rely on the question and on tool outputs of steps before k.
A value counts only at the step that first says it; later steps merely repeating it are not its origin.
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
    already_said: set[str] = set()
    traces = []
    for i, step in enumerate(sample.agent_log):
        content = step.content[:MAX_STEP_CHARS]
        unsupported = evidence.atoms(content) if content else []
        atoms = [a for a in unsupported if a.text.lower() not in already_said]
        already_said |= {a.text.lower() for a in unsupported}
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


SEMANTIC_FEATURES = ["prev_support", "prev_lexical", "self_doubt"]
ANSWER_FEATURES = ["answer_support", "answer_unsupported"]
SELF_DOUBT = re.compile(r"\b(i assume|assuming|probably|likely|i think|it seems|unable to|couldn't|could not|no information|not sure|guess)\b", re.IGNORECASE)
MAX_PREMISE_CHARS = 2_000
MAX_HYPOTHESIS_CHARS = 1_000


def semantic_rows(sample: Sample, consistency) -> dict:
    """Per step: HHEM consistency and word overlap with the latest earlier tool output, and guessing phrases.
    For the answer: consistency with all tool outputs and its unsupported numbers and names."""
    steps, pairs, latest = [], [], None
    for step in sample.agent_log or []:
        content = step.content[:MAX_HYPOTHESIS_CHARS]
        row = {"prev_support": 1.0, "prev_lexical": 1.0, "self_doubt": float(len(SELF_DOUBT.findall(step.content[:MAX_STEP_CHARS])))}
        if latest and content:
            words = content_words(content)
            row["prev_lexical"] = len(words & content_words(latest)) / len(words) if words else 1.0
            pairs.append((len(steps), (latest[-MAX_PREMISE_CHARS:], content)))
        steps.append(row)
        if step.observation:
            latest = step.observation[:MAX_STEP_CHARS]
    observations = "\n".join(s.observation[:MAX_STEP_CHARS] for s in sample.agent_log or [] if s.observation)
    evidence = (sample.question or "") + "\n" + observations
    batch = [pair for _, pair in pairs] + [(evidence[-2 * MAX_PREMISE_CHARS:], sample.answer[:MAX_HYPOTHESIS_CHARS])]
    scores = [float(s) for s in consistency(batch)]
    for (i, _), score in zip(pairs, scores):
        steps[i]["prev_support"] = score
    answer = {"answer_support": scores[-1], "answer_unsupported": float(min(len(EvidenceIndex(evidence).atoms(sample.answer[:MAX_STEP_CHARS])), 5))}
    return {"steps": steps, "answer": answer}


def combined_features(sample: Sample, traces: list[StepTrace], semantic: dict | None) -> tuple[np.ndarray, np.ndarray]:
    """(step matrix, answer vector); semantic rows are appended when given."""
    matrix = step_features(sample, traces)
    if semantic is None:
        return matrix, np.zeros(0)
    extra = np.array([[row[k] for k in SEMANTIC_FEATURES] for row in semantic["steps"]], dtype=float).reshape(-1, len(SEMANTIC_FEATURES))
    return np.hstack([matrix, extra]), np.array([semantic["answer"][k] for k in ANSWER_FEATURES], dtype=float)


def trajectory_features(steps: np.ndarray, answer: np.ndarray | None = None) -> np.ndarray:
    """Max and mean of every step feature, the number of steps, and the answer features."""
    answer = np.zeros(0) if answer is None else answer
    if len(steps) == 0:
        return np.zeros(2 * steps.shape[1] + 1 + len(answer))
    return np.concatenate([steps.max(axis=0), steps.mean(axis=0), [len(steps)], answer])


@dataclass
class LearnedTracer:
    """Two logistic regressions on the same step evidence: which step is the origin, and is anything wrong at all."""

    step_model: object
    detector: object
    feature_names: list[str]
    semantic: bool = False
    signal_versions: dict[str, str] = field(default_factory=dict)
    columns: list[int] | None = None
    hybrid: bool = False

    def step_scores(self, traces: list[StepTrace], matrix: np.ndarray) -> np.ndarray:
        """Origin score per step: the learned probability, or (hybrid) its equal mix with the v0 evidence score.

        Both are min-max scaled within the trajectory; the 50/50 mix is fixed, not tuned on any test set.
        """
        probs = self.step_model.predict_proba(matrix)[:, 1]
        if not self.hybrid:
            return probs
        scale = lambda v: (v - v.min()) / (v.max() - v.min()) if v.max() > v.min() else np.zeros_like(v)
        return 0.5 * scale(probs) + 0.5 * scale(np.array([t.score for t in traces]))

    def analyse(self, sample: Sample, consistency=None) -> tuple[list[StepTrace], np.ndarray, float]:
        """(step traces, origin probability per step, trajectory risk); consistency is HHEM unless given."""
        traces = trace(sample)
        if not traces:
            return [], np.zeros(0), 0.0
        semantic = None
        if self.semantic:
            from truth_guardian import models

            semantic = semantic_rows(sample, consistency or models.hhem_consistency)
        matrix, answer = combined_features(sample, traces, semantic)
        if self.columns is not None:
            matrix = matrix[:, self.columns]
        probs = self.step_scores(traces, matrix)
        risk = float(self.detector.predict_proba(trajectory_features(matrix, answer).reshape(1, -1))[:, 1][0])
        return traces, probs, risk


def _classifier():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))


POSITION_FEATURES = {"is_first", "is_last", "position", "is_action", "is_thought", "is_answer"}


def fit_tracer(
    samples: list[Sample],
    features: dict[str, tuple[list[StepTrace], np.ndarray, np.ndarray]],
    semantic: bool = False,
    content_only: bool = False,
) -> LearnedTracer:
    """features[sample.id] = (traces, step matrix, answer vector); the step model uses hallucinated trajectories only.

    content_only drops position and step-kind features, which encode one dataset's habits (where its agents and
    annotators tend to place errors) rather than evidence, and do not transfer to other agent designs.
    """
    names = STEP_FEATURES + (SEMANTIC_FEATURES if semantic else [])
    columns = [i for i, n in enumerate(names) if not (content_only and n in POSITION_FEATURES)]
    xs, ys = [], []
    for s in samples:
        traces, matrix, _ = features[s.id]
        if s.labels.responsible_step is None or not traces:
            continue
        xs.append(matrix[:, columns])
        ys += [int(t.step == s.labels.responsible_step) for t in traces]
    detector_x = np.stack([trajectory_features(features[s.id][1][:, columns], features[s.id][2]) for s in samples])
    detector_y = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)
    return LearnedTracer(
        step_model=_classifier().fit(np.vstack(xs), np.array(ys)),
        detector=_classifier().fit(detector_x, detector_y),
        feature_names=[names[i] for i in columns],
        semantic=semantic,
        columns=columns,
    )
