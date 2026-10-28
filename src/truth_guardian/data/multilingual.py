"""Labelled data for the multilingual check (D-137, D-138): RAGTruth translated by KRLabs, and PsiloQA.

The translated RAGTruth files list the English train responses in the same order (every task type matches, and the
number of labelled spans matches in 99.3% of rows), so each translated row keeps its English response's source as its
group, its generator and its quality flag, and lands in dev exactly when the English response is in our English dev.
Their prompt (the RAGTruth instruction, question and passages, translated) becomes the one source document; a QA
prompt's second line is its question. The Chinese file left the business data of Data2txt prompts in English, so those
rows pair Chinese answers with English sources.

PsiloQA's spans were labelled by GPT-4o, not by people, and 89% of its answers in these languages contain one. Its test
split is a locked set. A sample's language is the suffix of its dataset name (ragtruth_es, psiloqa_ar).
"""

import json
from collections.abc import Iterator
from pathlib import Path

from truth_guardian.data.ragtruth import LABEL_TYPES, TASKS
from truth_guardian.schema import Document, Labels, Meta, Sample, Span

PSILOQA_LANGUAGES = ("ar", "es", "fr", "zh")  # PsiloQA's languages that the check reads; its Persian is left out
PSILOQA_SPLITS = {"train": "train", "validation": "dev", "test": "test"}


def language_of(sample: Sample) -> str:
    return sample.meta.dataset.rsplit("_", 1)[-1]


def _rows(path: Path) -> list[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def _english_train(raw: Path) -> tuple[list[dict], dict[str, dict]]:
    with (raw / "ragtruth" / "response.jsonl").open(encoding="utf-8") as f:
        responses = [r for r in map(json.loads, filter(str.strip, f)) if r["split"] == "train"]
    with (raw / "ragtruth" / "source_info.jsonl").open(encoding="utf-8") as f:
        sources = {s["source_id"]: s for s in map(json.loads, filter(str.strip, f))}
    return responses, sources


def load_ragtruth_translated(raw: Path, code: str, dev_ids: set[str]) -> Iterator[Sample]:
    """dev_ids: the ids of the English dev samples (ragtruth-<response id>)."""
    english, sources = _english_train(raw)
    folder = f"ragtruth_{code}"
    rows = _rows(raw / folder / "train-00000-of-00001.parquet")
    if len(rows) != len(english):
        raise ValueError(f"{folder} has {len(rows)} rows, English RAGTruth train {len(english)}")
    for row, response in zip(rows, english):
        source = sources[response["source_id"]]
        if row["task_type"] != source["task_type"]:
            raise ValueError(f"{folder} row for response {response['id']} is {row['task_type']}, not {source['task_type']}")
        answer = row["answer"]
        spans = [
            Span(start=l["start"], end=l["end"], text=answer[l["start"]:l["end"]], type=LABEL_TYPES.get(l["label"]), source_label=l["label"])
            for l in row["labels"] if 0 <= l["start"] < l["end"] <= len(answer)
        ]
        lines = row["prompt"].split("\n")
        english_id = f"ragtruth-{response['id']}"
        yield Sample(
            id=f"ragtruth-{code}-{response['id']}",
            question=(lines[1].strip() or None) if row["task_type"] == "QA" and len(lines) > 1 else None,
            documents=[Document(id="prompt", text=row["prompt"])],
            answer=answer,
            labels=Labels(response="hallucinated" if spans else "grounded", spans=spans),
            meta=Meta(
                dataset=f"ragtruth_{code}",
                task=TASKS[row["task_type"]],
                split="dev" if english_id in dev_ids else "train",
                group_id=f"ragtruth-{response['source_id']}",
                generator=response["model"],
                source=source["source"],
                quality=response["quality"],
            ),
        )


def load_psiloqa(raw: Path, split: str) -> Iterator[Sample]:
    for row in _rows(raw / "psiloqa" / f"{split}-00000-of-00001.parquet"):
        if row["lang"] not in PSILOQA_LANGUAGES or not row["llm_answer"].strip():
            continue
        answer = row["llm_answer"]
        spans = [Span(start=s, end=e, text=answer[s:e]) for s, e in row["labels"] if 0 <= s < e <= len(answer)]
        yield Sample(
            id=f"psiloqa-{row['id']}",
            question=row["question"],
            documents=[Document(id="passage", text=row["wiki_passage"], source=row["wiki_url"])],
            answer=answer,
            labels=Labels(response="hallucinated" if spans else "grounded", spans=spans),
            meta=Meta(
                dataset=f"psiloqa_{row['lang']}",
                task="qa",
                split=PSILOQA_SPLITS[split],
                group_id=f"psiloqa-{row['lang']}-{row['wiki_title']}",
                generator=row["llm_checkpoint"],
                source="wikipedia",
            ),
        )
