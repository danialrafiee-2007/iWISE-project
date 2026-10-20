import pytest
from pydantic import ValidationError

from truth_guardian import Sample, read_jsonl, write_jsonl

ANSWER = "Paris is the capital of France. It has 90 million residents."


def make_sample(**overrides) -> dict:
    sample = {
        "id": "s1",
        "question": "What is the capital of France?",
        "documents": [{"id": "d1", "text": "Paris is the capital of France. It has about 2 million residents."}],
        "answer": ANSWER,
        "labels": {
            "response": "hallucinated",
            "spans": [{"start": 39, "end": 59, "text": "90 million residents", "type": "numeric_entity_mismatch"}],
        },
        "meta": {"dataset": "unit", "task": "qa", "split": "train", "group_id": "d1"},
    }
    sample.update(overrides)
    return sample


def test_valid_sample_parses():
    sample = Sample.model_validate(make_sample())
    span = sample.labels.spans[0]
    assert sample.answer[span.start : span.end] == span.text


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Sample.model_validate(make_sample(extra_field=1))


def test_requires_at_least_one_document():
    with pytest.raises(ValidationError):
        Sample.model_validate(make_sample(documents=[]))


def test_span_text_must_match_answer():
    labels = {"response": "hallucinated", "spans": [{"start": 0, "end": 5, "text": "Rome!"}]}
    with pytest.raises(ValidationError, match="does not match"):
        Sample.model_validate(make_sample(labels=labels))


def test_span_must_fit_inside_answer():
    labels = {"response": "hallucinated", "spans": [{"start": 50, "end": 500, "text": "x"}]}
    with pytest.raises(ValidationError, match="exceeds"):
        Sample.model_validate(make_sample(labels=labels))


def test_grounded_response_cannot_have_spans():
    labels = make_sample()["labels"] | {"response": "grounded"}
    with pytest.raises(ValidationError, match="grounded"):
        Sample.model_validate(make_sample(labels=labels))


def test_hallucinated_without_spans_is_allowed():
    sample = Sample.model_validate(make_sample(labels={"response": "hallucinated"}))
    assert sample.labels.spans == []


def test_agent_steps_must_be_ascending():
    log = [
        {"step": 1, "kind": "thought", "content": "a"},
        {"step": 0, "kind": "observation", "content": "b"},
    ]
    with pytest.raises(ValidationError, match="ascending"):
        Sample.model_validate(make_sample(agent_log=log))


def test_responsible_step_must_exist():
    log = [{"step": 0, "kind": "thought", "content": "a"}]
    labels = {"response": "hallucinated", "responsible_step": 3}
    with pytest.raises(ValidationError, match="responsible_step"):
        Sample.model_validate(make_sample(agent_log=log, labels=labels))


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "out" / "samples.jsonl"
    original = [Sample.model_validate(make_sample(id=f"s{i}")) for i in range(3)]
    assert write_jsonl(original, path) == 3
    assert list(read_jsonl(path)) == original


def test_read_jsonl_reports_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "broken"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        list(read_jsonl(path))
