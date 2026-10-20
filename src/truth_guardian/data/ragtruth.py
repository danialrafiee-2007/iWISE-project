"""Convert RAGTruth (response.jsonl + source_info.jsonl) into unified Samples."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

from truth_guardian.schema import Document, HallucinationType, Labels, Meta, Sample, Span

TASKS = {"QA": "qa", "Summary": "summary", "Data2txt": "data2text"}

LABEL_TYPES = {
    "Evident Conflict": HallucinationType.CONTRADICTED,
    "Subtle Conflict": HallucinationType.CONTRADICTED,
    "Evident Baseless Info": HallucinationType.UNSUPPORTED,
    "Subtle Baseless Info": HallucinationType.UNSUPPORTED,
}

_PASSAGE_HEADER = re.compile(r"passage \d+:", re.IGNORECASE)


def split_passages(passages: str) -> list[Document]:
    parts = [p.strip() for p in _PASSAGE_HEADER.split(passages)]
    return [Document(id=f"passage{i}", text=p) for i, p in enumerate((p for p in parts if p), 1)]


def _render_value(value) -> str:
    if value is None:
        return "not specified"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _flatten(prefix: str, value, lines: list[str]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            _flatten(f"{prefix} {key}".strip(), inner, lines)
    else:
        lines.append(f"{prefix}: {_render_value(value)}")


def render_business(info: dict) -> list[Document]:
    """Render Yelp structured data as 'key: value' lines plus one document per review."""
    lines: list[str] = []
    for key, value in info.items():
        if key != "review_info":
            _flatten(key, value, lines)
    documents = [Document(id="business", text="\n".join(lines))]
    for i, review in enumerate(info.get("review_info") or [], 1):
        header = f"Review {i} ({_render_value(review.get('review_stars'))} stars, {_render_value(review.get('review_date'))})"
        documents.append(Document(id=f"review{i}", text=f"{header}: {review.get('review_text', '')}"))
    return documents


def build_context(source: dict) -> tuple[str | None, list[Document]]:
    task, info = source["task_type"], source["source_info"]
    if task == "QA":
        return info["question"], split_passages(info["passages"])
    if task == "Summary":
        return None, [Document(id="article", text=info)]
    if task == "Data2txt":
        return None, render_business(info)
    raise ValueError(f"unknown RAGTruth task type: {task}")


def convert_response(response: dict, source: dict) -> Sample:
    spans = [
        Span(
            start=label["start"],
            end=label["end"],
            text=label["text"],
            type=LABEL_TYPES[label["label_type"]],
            source_label=label["label_type"],
            implicit_true=label["implicit_true"],
            due_to_null=label["due_to_null"],
        )
        for label in response["labels"]
    ]
    question, documents = build_context(source)
    return Sample(
        id=f"ragtruth-{response['id']}",
        question=question,
        documents=documents,
        answer=response["response"],
        labels=Labels(response="hallucinated" if spans else "grounded", spans=spans),
        meta=Meta(
            dataset="ragtruth",
            task=TASKS[source["task_type"]],
            split=response["split"],
            group_id=f"ragtruth-{response['source_id']}",
            generator=response["model"],
            source=source["source"],
            quality=response["quality"],
        ),
    )


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_ragtruth(raw_dir: str | Path) -> Iterator[Sample]:
    raw_dir = Path(raw_dir)
    sources = {s["source_id"]: s for s in _read_jsonl(raw_dir / "source_info.jsonl")}
    for response in _read_jsonl(raw_dir / "response.jsonl"):
        yield convert_response(response, sources[response["source_id"]])
