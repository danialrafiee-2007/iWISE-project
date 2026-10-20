"""Convert HaluEval QA, dialogue and summarization files into unified Samples (external test only).

The "general" file is skipped: it has no source documents, so it measures world factuality, not grounding.
"""

import json
from collections.abc import Iterator
from pathlib import Path

from truth_guardian.schema import Document, Labels, Meta, Sample

TASK_FILES = {
    "qa": ("qa_data.json", "knowledge", "question", "right_answer", "hallucinated_answer"),
    "dialogue": ("dialogue_data.json", "knowledge", "dialogue_history", "right_response", "hallucinated_response"),
    "summary": ("summarization_data.json", "document", None, "right_summary", "hallucinated_summary"),
}


def convert_row(task: str, index: int, row: dict) -> list[Sample]:
    _, context_key, question_key, right_key, hallucinated_key = TASK_FILES[task]
    group_id = f"halueval-{task}-{index}"
    samples = []
    for label, key in (("grounded", right_key), ("hallucinated", hallucinated_key)):
        samples.append(
            Sample(
                id=f"{group_id}-{label}",
                question=row[question_key] if question_key else None,
                documents=[Document(id=context_key, text=row[context_key])],
                answer=row[key],
                labels=Labels(response=label),
                meta=Meta(dataset="halueval", task=task, split="test", group_id=group_id, synthetic=label == "hallucinated"),
            )
        )
    return samples


def load_halueval(raw_dir: str | Path, task: str) -> Iterator[Sample]:
    path = Path(raw_dir) / TASK_FILES[task][0]
    with path.open(encoding="utf-8") as f:
        for index, line in enumerate(line for line in f if line.strip()):
            yield from convert_row(task, index, json.loads(line))
