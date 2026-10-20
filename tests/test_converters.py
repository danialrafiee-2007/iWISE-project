import json

import pytest

from truth_guardian.data.halueval import load_halueval
from truth_guardian.data.ragtruth import build_context, convert_response, load_ragtruth, render_business, split_passages
from truth_guardian.schema import HallucinationType

QA_SOURCE = {
    "source_id": "7",
    "task_type": "QA",
    "source": "MARCO",
    "source_info": {"question": "butcher shop phone", "passages": "passage 1:Shop A (510) 889\n\npassage 2:Shop B (507) 662\n\n"},
}

RESPONSE = {
    "id": "42",
    "source_id": "7",
    "model": "gpt-4-0613",
    "split": "train",
    "quality": "good",
    "response": "Shop A is at (510) 889. It opened in 1990.",
    "labels": [
        {
            "start": 24,
            "end": 42,
            "text": "It opened in 1990.",
            "label_type": "Evident Baseless Info",
            "implicit_true": False,
            "due_to_null": False,
            "meta": "",
        }
    ],
}


def test_split_passages():
    docs = split_passages(QA_SOURCE["source_info"]["passages"])
    assert [d.id for d in docs] == ["passage1", "passage2"]
    assert docs[1].text == "Shop B (507) 662"


def test_render_business_flattens_nested_values_and_reviews():
    info = {
        "name": "Cafe",
        "attributes": {"WiFi": None, "Ambience": {"casual": True}},
        "review_info": [{"review_stars": 4.0, "review_date": "2022-01-01", "review_text": "Nice."}],
    }
    docs = render_business(info)
    assert docs[0].text == "name: Cafe\nattributes WiFi: not specified\nattributes Ambience casual: yes"
    assert docs[1].text == "Review 1 (4.0 stars, 2022-01-01): Nice."


def test_summary_context_has_no_question():
    question, docs = build_context({"task_type": "Summary", "source_info": "Article text."})
    assert question is None and docs[0].text == "Article text."


def test_unknown_task_rejected():
    with pytest.raises(ValueError):
        build_context({"task_type": "Poem", "source_info": ""})


def test_convert_response_maps_labels_and_meta():
    sample = convert_response(RESPONSE, QA_SOURCE)
    assert sample.id == "ragtruth-42"
    assert sample.question == "butcher shop phone"
    assert sample.labels.response == "hallucinated"
    span = sample.labels.spans[0]
    assert span.type == HallucinationType.UNSUPPORTED
    assert span.source_label == "Evident Baseless Info"
    assert sample.meta.group_id == "ragtruth-7"
    assert sample.meta.generator == "gpt-4-0613"


def test_response_without_labels_is_grounded():
    sample = convert_response(RESPONSE | {"labels": []}, QA_SOURCE)
    assert sample.labels.response == "grounded" and sample.labels.spans == []


def test_load_ragtruth_joins_files(tmp_path):
    (tmp_path / "source_info.jsonl").write_text(json.dumps(QA_SOURCE) + "\n", encoding="utf-8")
    (tmp_path / "response.jsonl").write_text(json.dumps(RESPONSE) + "\n", encoding="utf-8")
    samples = list(load_ragtruth(tmp_path))
    assert len(samples) == 1 and samples[0].documents[0].id == "passage1"


def test_halueval_row_yields_grounded_and_hallucinated_pair(tmp_path):
    row = {"knowledge": "K", "question": "Q?", "right_answer": "A", "hallucinated_answer": "B"}
    (tmp_path / "qa_data.json").write_text(json.dumps(row) + "\n", encoding="utf-8")
    right, wrong = load_halueval(tmp_path, "qa")
    assert (right.labels.response, wrong.labels.response) == ("grounded", "hallucinated")
    assert right.meta.group_id == wrong.meta.group_id == "halueval-qa-0"
    assert wrong.meta.synthetic and not right.meta.synthetic
    assert right.meta.split == "test"
