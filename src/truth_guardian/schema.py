"""Unified sample format shared by every dataset converter, model and the web API."""

from collections.abc import Iterable, Iterator
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class HallucinationType(StrEnum):
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"
    NUMERIC_ENTITY_MISMATCH = "numeric_entity_mismatch"
    WEAK_EVIDENCE = "weak_evidence"
    AGENT_INTRODUCED = "agent_introduced"
    OVERCLAIM = "overclaim"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Document(_Strict):
    id: str
    text: str = Field(min_length=1)
    source: str | None = None
    retrieval_score: float | None = None
    origin: str | None = Field(default=None, description="The file the text came from; the parts of one long document share it.")


class AgentStep(_Strict):
    step: int = Field(ge=0)
    kind: Literal["thought", "action", "observation", "answer"]
    content: str
    tool: str | None = None
    role: str | None = Field(default=None, description="Which agent or component produced the step.")
    observation: str | None = Field(default=None, description="Tool output returned to the agent at this step.")


class Span(_Strict):
    start: int = Field(ge=0)
    end: int
    text: str
    type: HallucinationType | None = None
    source_label: str | None = None
    implicit_true: bool | None = Field(default=None, description="Unsupported by the sources but true in the world.")
    due_to_null: bool | None = Field(default=None, description="Caused by a missing (null) value in structured data.")
    note: str | None = Field(default=None, description="Annotator's free-text note, e.g. what the source originally said.")

    @model_validator(mode="after")
    def _check_order(self) -> "Span":
        if self.end <= self.start:
            raise ValueError("span end must be greater than start")
        return self


class Labels(_Strict):
    response: Literal["grounded", "hallucinated"]
    spans: list[Span] = Field(default_factory=list)
    responsible_step: int | None = None
    category: str | None = Field(default=None, description="Dataset-specific hallucination category, e.g. AgentHallu's.")
    reason: str | None = Field(default=None, description="Annotator's explanation; never used as model input.")


class Meta(_Strict):
    dataset: str
    task: str
    split: Literal["train", "dev", "test"]
    group_id: str = Field(description="Samples sharing a source; a group never crosses splits.")
    generator: str | None = None
    source: str | None = Field(default=None, description="Corpus the context came from, e.g. MARCO, CNN/DM, Yelp.")
    quality: str = "good"
    synthetic: bool = False


class Sample(_Strict):
    id: str
    question: str | None = None
    documents: list[Document] = Field(min_length=1)
    answer: str = Field(min_length=1)
    evidence: list[str] | None = None
    agent_log: list[AgentStep] | None = None
    labels: Labels | None = None
    meta: Meta

    @model_validator(mode="after")
    def _check_consistency(self) -> "Sample":
        if self.agent_log:
            steps = [s.step for s in self.agent_log]
            if steps != sorted(set(steps)):
                raise ValueError("agent_log steps must be unique and ascending")
        if self.labels is None:
            return self
        for span in self.labels.spans:
            if span.end > len(self.answer):
                raise ValueError(f"span {span.start}:{span.end} exceeds answer length {len(self.answer)}")
            if self.answer[span.start : span.end] != span.text:
                raise ValueError(f"span {span.start}:{span.end} text does not match the answer")
        if self.labels.spans and self.labels.response == "grounded":
            raise ValueError("a grounded response cannot contain hallucinated spans")
        if self.labels.responsible_step is not None:
            if self.labels.responsible_step not in {s.step for s in self.agent_log or []}:
                raise ValueError("responsible_step is not present in agent_log")
        return self


def read_jsonl(path: str | Path) -> Iterator[Sample]:
    with Path(path).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield Sample.model_validate_json(line)
            except ValidationError as e:
                raise ValueError(f"{path}:{line_no}: invalid sample\n{e}") from e


def write_jsonl(samples: Iterable[Sample], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for sample in samples:
            f.write(sample.model_dump_json(exclude_none=True) + "\n")
            count += 1
    return count
