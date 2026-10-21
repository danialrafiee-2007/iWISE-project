"""Provenance tracer: find the agent step where a hallucination first enters a trajectory.

Time rule: at step k the agent may only rely on the question and on tool outputs of steps before k.
For each step we measure what it introduces that this evidence does not contain (numbers, dates, names,
new content words), whether its own tool call failed, and whether its unsupported items reach the final
answer. The highest-scoring step is the suspected origin. v0 weights are set by hand; Phase 3 learns them.
"""

import re
from typing import NamedTuple

from truth_guardian.schema import Sample
from truth_guardian.symbolic import Atom, unmatched_atoms
from truth_guardian.text import content_words

MAX_STEP_CHARS = 20_000
MAX_EVIDENCE_CHARS = 200_000
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
    evidence = sample.question or ""
    seen_words = content_words(evidence)
    traces = []
    for i, step in enumerate(sample.agent_log):
        content = step.content[:MAX_STEP_CHARS]
        atoms = unmatched_atoms(content, evidence[-MAX_EVIDENCE_CHARS:]) if content else []
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
            evidence += "\n" + step.observation
            seen_words |= content_words(step.observation[:MAX_STEP_CHARS])
    return traces


def suspected_step(traces: list[StepTrace]) -> StepTrace | None:
    """Highest score; ties go to the earliest step, since a hallucination's origin precedes its spread."""
    return max(traces, key=lambda t: (t.score, -t.step)) if traces else None
