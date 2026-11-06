"""The data builders only the build and evaluate scripts ran: the data card, XQuAD edits, translated RAGTruth, PsiloQA and provenance."""

import json
import subprocess

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from truth_guardian import provenance
from truth_guardian.data.card import render_card
from truth_guardian.data.multilingual import language_of, load_psiloqa, load_ragtruth_translated
from truth_guardian.data.xquad import _swap, load_xquad_edits
from truth_guardian.schema import HallucinationType, Sample


def sample(i: int, response: str = "grounded", task: str = "qa", spans=(), quality: str = "good", answer: str = "one two three", group: str | None = None) -> Sample:
    return Sample.model_validate({
        "id": f"s{i}",
        "documents": [{"id": "d", "text": "four five six seven"}],
        "answer": answer,
        "labels": {"response": response, "spans": list(spans)},
        "meta": {"dataset": "unit", "task": task, "split": "train", "group_id": group or f"g{i}", "quality": quality},
    })


def test_the_data_card_counts_samples_tasks_span_labels_quality_and_length():
    span = {"start": 0, "end": 3, "text": "one", "source_label": "Evident Conflict", "implicit_true": True}
    files = {
        "ragtruth_train": [sample(1), sample(2, "hallucinated", task="summary", spans=[span], group="g1"), sample(3, quality="truncated")],
        "halueval_qa": [sample(4, answer="a b"), sample(5, "hallucinated", answer="a b c d")],
    }
    card = render_card(files, ["RAGTruth from its repository"])
    assert card.startswith("# Data Card") and "- RAGTruth from its repository" in card
    assert "| ragtruth_train | 3 | 2 | 33.3% | 1 | 3 | 4 |" in card
    assert "| ragtruth_train | summary | 1 | 100.0% |" in card and "| ragtruth_train | qa | 2 | 0.0% |" in card
    assert "| ragtruth_train | 1 | 0 | 0 | 0 | 1 | 0 |" in card
    quality = card.split("## Response quality")[1].split("##")[0]
    assert "| ragtruth_train | 2 | 0 | 1 |" in quality and "halueval_qa" not in quality
    length = card.split("## Length shortcut")[1]
    assert "| halueval_qa | 2.0 | 4.0 |" in length and "ragtruth_train" not in length


def test_a_swap_moves_the_first_number_on_or_takes_an_answer_that_shares_nothing():
    assert _swap("in 1999 and 2000", []) == "in 2000 and 2000"
    assert _swap("Paris", ["Paris", "the Paris area", " ", "Rome"]) == "Rome"
    assert _swap("Paris", ["Paris"]) is None


def test_xquad_gives_each_question_its_sentence_and_the_same_sentence_with_the_answer_changed(tmp_path):
    context = "The tower was built in 1889. It stands in Paris."
    qas = [
        {"id": "q1", "question": "When was it built?", "answers": [{"text": "1889", "answer_start": context.index("1889")}]},
        {"id": "q2", "question": "Where is it?", "answers": [{"text": "Paris", "answer_start": context.index("Paris")}]},
        {"id": "q3", "question": "Misplaced", "answers": [{"text": "London", "answer_start": 0}]},
    ]
    (tmp_path / "xquad").mkdir()
    (tmp_path / "xquad" / "xquad.en.json").write_text(json.dumps({"data": [{"title": "Tower", "paragraphs": [{"context": context, "qas": qas}]}]}), encoding="utf-8")
    samples = list(load_xquad_edits(tmp_path, "en"))
    assert [s.id for s in samples] == ["xquad-en-q1-grounded", "xquad-en-q1-edited", "xquad-en-q2-grounded", "xquad-en-q2-edited"]
    grounded, edited = samples[0], samples[1]
    assert grounded.answer == "The tower was built in 1889." and grounded.labels.response == "grounded"
    assert edited.answer == "The tower was built in 1890." and edited.labels.response == "hallucinated"
    span = edited.labels.spans[0]
    assert edited.answer[span.start:span.end] == "1890" and span.type == HallucinationType.NUMERIC_ENTITY_MISMATCH and span.note == "Original: 1889"
    assert samples[3].answer == "It stands in 1889." and samples[3].labels.spans[0].type == HallucinationType.CONTRADICTED
    assert all(s.meta.synthetic and s.meta.split == "test" and s.meta.group_id == "xquad-Tower-0" for s in samples)
    assert [s.id for s in load_xquad_edits(tmp_path, "en", questions={"q2"})] == ["xquad-en-q2-grounded", "xquad-en-q2-edited"]


def ragtruth_raw(tmp_path, rows: list[dict]):
    english = [
        {"id": "r1", "source_id": "src1", "split": "train", "model": "gpt-4", "quality": "good"},
        {"id": "r9", "source_id": "src1", "split": "test", "model": "gpt-4", "quality": "good"},
        {"id": "r2", "source_id": "src2", "split": "train", "model": "llama", "quality": "truncated"},
    ]
    sources = [{"source_id": "src1", "task_type": "QA", "source": "MARCO"}, {"source_id": "src2", "task_type": "Summary", "source": "CNN/DM"}]
    (tmp_path / "ragtruth").mkdir(exist_ok=True)
    (tmp_path / "ragtruth" / "response.jsonl").write_text("".join(json.dumps(r) + "\n" for r in english), encoding="utf-8")
    (tmp_path / "ragtruth" / "source_info.jsonl").write_text("".join(json.dumps(s) + "\n" for s in sources), encoding="utf-8")
    (tmp_path / "ragtruth_es").mkdir(exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "ragtruth_es" / "train-00000-of-00001.parquet")


def translated_rows() -> list[dict]:
    return [
        {"task_type": "QA", "answer": "Madrid es la capital.", "prompt": "Instrucción\n¿Cuál es la capital?\npasajes",
         "labels": [{"start": 0, "end": 6, "label": "Evident Conflict"}, {"start": 50, "end": 60, "label": "Evident Conflict"}]},
        {"task_type": "Summary", "answer": "Resumen corto.", "prompt": "Resume esto", "labels": []},
    ]


def test_translated_ragtruth_keeps_the_english_responses_group_generator_quality_and_split(tmp_path):
    ragtruth_raw(tmp_path, translated_rows())
    qa, summary = load_ragtruth_translated(tmp_path, "es", dev_ids={"ragtruth-r2"})
    assert qa.id == "ragtruth-es-r1" and qa.question == "¿Cuál es la capital?" and qa.documents[0].text.startswith("Instrucción")
    assert qa.labels.response == "hallucinated" and [s.text for s in qa.labels.spans] == ["Madrid"]
    assert qa.labels.spans[0].type == HallucinationType.CONTRADICTED and qa.labels.spans[0].source_label == "Evident Conflict"
    assert (qa.meta.task, qa.meta.split, qa.meta.group_id, qa.meta.generator, qa.meta.source) == ("qa", "train", "ragtruth-src1", "gpt-4", "MARCO")
    assert summary.question is None and summary.labels.response == "grounded"
    assert (summary.meta.task, summary.meta.split, summary.meta.quality) == ("summary", "dev", "truncated")
    assert language_of(qa) == "es"


def test_translated_ragtruth_refuses_rows_that_do_not_line_up_with_english(tmp_path):
    ragtruth_raw(tmp_path, translated_rows()[:1])
    with pytest.raises(ValueError, match="has 1 rows"):
        list(load_ragtruth_translated(tmp_path, "es", set()))
    rows = translated_rows()
    rows[1]["task_type"] = "QA"
    ragtruth_raw(tmp_path, rows)
    with pytest.raises(ValueError, match="is QA, not Summary"):
        list(load_ragtruth_translated(tmp_path, "es", set()))


def test_psiloqa_keeps_the_languages_the_check_reads_and_answers_that_are_not_empty(tmp_path):
    base = {"question": "¿Cuándo nació?", "wiki_passage": "Nació en 1990 en Lima.", "wiki_url": "https://example.org", "wiki_title": "Ana", "llm_checkpoint": "m1"}
    rows = [
        {**base, "id": "p1", "lang": "es", "llm_answer": "Nació en 1991.", "labels": [[9, 13], [3, 99]]},
        {**base, "id": "p2", "lang": "fa", "llm_answer": "در ۱۹۹۰ به دنیا آمد.", "labels": []},
        {**base, "id": "p3", "lang": "ar", "llm_answer": "   ", "labels": []},
    ]
    (tmp_path / "psiloqa").mkdir()
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "psiloqa" / "validation-00000-of-00001.parquet")
    [only] = load_psiloqa(tmp_path, "validation")
    assert only.id == "psiloqa-p1" and [s.text for s in only.labels.spans] == ["1991"] and only.labels.response == "hallucinated"
    assert (only.meta.dataset, only.meta.split, only.meta.group_id, only.meta.generator) == ("psiloqa_es", "dev", "psiloqa-es-Ana", "m1")
    assert only.documents[0].source == "https://example.org" and language_of(only) == "es"


def test_provenance_marks_a_commit_dirty_for_code_but_not_for_results(tmp_path):
    git = lambda *cmd: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *cmd], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "start")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    assert provenance.git_commit(tmp_path) == head
    (tmp_path / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert provenance.git_commit(tmp_path) == f"{head}-dirty"
