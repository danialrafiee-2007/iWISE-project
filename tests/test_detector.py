from transformers import AutoTokenizer

from truth_guardian import detector
from truth_guardian.schema import Sample

ANSWER = "The cafe is in Paris. It opened in 1990."
SOURCE = "The cafe is in Paris. It opened in 1985 and has three floors."


def make_sample() -> Sample:
    start = ANSWER.index("1990")
    return Sample.model_validate({
        "id": "x", "documents": [{"id": "d", "text": SOURCE}], "answer": ANSWER,
        "labels": {"response": "hallucinated", "spans": [{"start": start, "end": start + 4, "text": "1990", "type": "contradicted"}]},
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": "g"},
    })


def test_examples_carry_spans_relative_to_their_sentence():
    first, second = detector.examples(make_sample())
    assert first.spans == [] and second.sentence[slice(*second.spans[0])] == "1990"
    assert "1985" in second.premise


def test_only_sentence_tokens_inside_the_span_are_labelled_positive():
    tokenizer = AutoTokenizer.from_pretrained(detector.BACKBONE, revision=detector.BACKBONE_REVISION)
    example = detector.Example("It opened in 1985.", "It opened in 1990.", [(13, 17)], "unit")
    batch = detector._batch(tokenizer, [example])
    labelled = [(tokenizer.convert_ids_to_tokens(int(i)), int(y)) for i, y in zip(batch["input_ids"][0], batch["labels"][0]) if y != -100]
    assert [t for t, y in labelled if y] == ["1990"]
    assert [t for t, _ in labelled] == ["it", "opened", "in", "1990", "."]
