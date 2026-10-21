"""Convert AgentHallu trajectories (one JSON file per trajectory) into unified Samples.

Model inputs are only the question, the agent's steps and its final answer. The dataset's reference
answer and solution notes (`true_answer`, `explanation`) are dropped so they can never leak into a model.
Tool outputs become the documents: they are the evidence an agent's claims should rest on.
"""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

from truth_guardian.schema import AgentStep, Document, Labels, Meta, Sample

NO_ANSWER = "(no final answer)"


def _text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _question(value) -> str:
    """BFCL multi-turn questions are lists of turns; flatten them as "Turn 1: ..." lines."""
    if isinstance(value, str):
        return value
    turns = [" ".join(t) if isinstance(t, list) else _text(t) for t in value]
    return "\n".join(f"Turn {i}: {t}" for i, t in enumerate(turns, 1))


def _render_calls(calls: list | None) -> str:
    return "\n".join(f"call {c.get('name', '?')}({_text(c.get('arguments'))})" if isinstance(c, dict) else _text(c) for c in calls or [])


def convert_step(raw: dict, is_last: bool) -> AgentStep:
    content = _text(raw.get("content")).strip()
    calls = _render_calls(raw.get("tool_calls"))
    responses = "\n".join(_text(r) for r in raw.get("tool_responses") or [])
    kind = "action" if calls else ("answer" if is_last else "thought")
    return AgentStep(
        step=raw["step"],
        kind=kind,
        content="\n".join(p for p in (content, calls) if p),
        tool=", ".join(c.get("name", "?") for c in raw.get("tool_calls") or [] if isinstance(c, dict)) or None,
        role=raw.get("role"),
        observation=responses or None,
    )


def merge_repeated_steps(history: list[dict]) -> list[dict]:
    """A few trajectories log one step number twice; merge such entries so step numbers (and labels) stay valid."""
    merged: list[dict] = []
    for entry in history:
        if merged and merged[-1]["step"] == entry["step"]:
            previous = merged[-1]
            previous["content"] = "\n".join(_text(x) for x in (previous.get("content"), entry.get("content")) if x)
            previous["tool_calls"] = (previous.get("tool_calls") or []) + (entry.get("tool_calls") or [])
            previous["tool_responses"] = (previous.get("tool_responses") or []) + (entry.get("tool_responses") or [])
        else:
            merged.append(dict(entry))
    return merged


def convert_trajectory(raw: dict, framework: str, file_id: str) -> Sample:
    history = merge_repeated_steps(raw["history"])
    steps = [convert_step(s, i == len(history) - 1) for i, s in enumerate(history)]
    question = _question(raw["question"])
    documents = [Document(id="task", text=question, source="question")]
    documents += [Document(id=f"step{s.step}", text=s.observation, source=f"step {s.step} tool output") for s in steps if s.observation]
    hallucinated = str(raw["is_hallucination"]).lower() == "true"
    question_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
    return Sample(
        id=f"agenthallu-{framework}-{file_id}",
        question=question,
        documents=documents,
        answer=_text(raw.get("agent_answer")).strip() or NO_ANSWER,
        agent_log=steps,
        labels=Labels(
            response="hallucinated" if hallucinated else "grounded",
            responsible_step=int(raw["hallucination_step"]) if hallucinated else None,
            category=raw.get("hallucination_category"),
            reason=raw.get("hallucination_reason"),
        ),
        meta=Meta(
            dataset="agenthallu",
            task=raw["question_domain"].lower().replace(" ", "_"),
            split="test",
            group_id=f"agenthallu-q-{question_hash}",
            generator=raw.get("model_id"),
            source=f"{raw.get('question_source')} / {raw.get('agent_type')}",
        ),
    )


def load_agenthallu(raw_dir: str | Path) -> Iterator[Sample]:
    for path in sorted(Path(raw_dir).glob("*/*.json")):
        with path.open(encoding="utf-8") as f:
            yield convert_trajectory(json.load(f), path.parent.name, path.stem)
