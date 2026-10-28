"""Controlled edits of XQuAD for the multilingual check (D-138): the only labelled set it has in Russian.

XQuAD gives the same 1,190 questions on the same 240 Wikipedia paragraphs in English, Arabic, Spanish, Russian and
Chinese, translated by professionals. For each question the context sentence that holds the human answer is a grounded
answer, and the same sentence with that answer changed is a hallucinated one: a number becomes the next number (the
near-number swap the English engine was seen to miss, D-135), anything else becomes the answer to another question on
the same paragraph. The paragraph is the source. These are synthetic: real errors are seldom a single swapped span, and a
verbatim copy is the easiest grounded answer there is, so the set measures whether a swap is seen, in every language
alike, not how often real answers are judged right. It is never used for training or for thresholds.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

from truth_guardian.schema import Document, HallucinationType, Labels, Meta, Sample, Span
from truth_guardian.text import split_sentences

LANGUAGES = ("en", "ar", "es", "ru", "zh")
_DIGITS = re.compile(r"\d+")


def _swap(answer: str, others: list[str]) -> str | None:
    """The changed answer: its first number plus one, or another question's answer that shares nothing with it."""
    number = _DIGITS.search(answer)
    if number:
        return answer[: number.start()] + str(int(number.group()) + 1) + answer[number.end() :]
    for other in others:
        if other.strip() and other not in answer and answer not in other:
            return other
    return None


def load_xquad_edits(raw: Path, code: str, questions: set[str] | None = None) -> Iterator[Sample]:
    """questions: the XQuAD question ids to keep (the same ones in every language), or all of them."""
    data = json.loads((raw / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"]
    for article in data:
        for p, paragraph in enumerate(article["paragraphs"]):
            context = paragraph["context"]
            sentences = split_sentences(context)
            answers = [qa["answers"][0]["text"] for qa in paragraph["qas"]]
            for qa in paragraph["qas"]:
                if questions is not None and qa["id"] not in questions:
                    continue
                gold = qa["answers"][0]
                start, text = gold["answer_start"], gold["text"]
                holder = next((s for s in sentences if s.start <= start and start + len(text) <= s.end), None)
                if holder is None or context[start : start + len(text)] != text:
                    continue
                replacement = _swap(text, [a for a in answers if a != text])
                if replacement is None:
                    continue
                local = start - holder.start
                edited = holder.text[:local] + replacement + holder.text[local + len(text) :]
                kind = HallucinationType.NUMERIC_ENTITY_MISMATCH if _DIGITS.search(text) else HallucinationType.CONTRADICTED
                meta = dict(dataset=f"xquad_{code}", task="qa", split="test", group_id=f"xquad-{article['title']}-{p}", source="wikipedia", synthetic=True)
                yield Sample(
                    id=f"xquad-{code}-{qa['id']}-grounded", question=qa["question"], documents=[Document(id="paragraph", text=context)],
                    answer=holder.text, labels=Labels(response="grounded"), meta=Meta(**meta),
                )
                yield Sample(
                    id=f"xquad-{code}-{qa['id']}-edited", question=qa["question"], documents=[Document(id="paragraph", text=context)],
                    answer=edited, labels=Labels(response="hallucinated", spans=[Span(start=local, end=local + len(replacement), text=replacement, type=kind, note=f"Original: {text}")]),
                    meta=Meta(**meta),
                )
