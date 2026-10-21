import pytest

from truth_guardian.features import FeatureStore, extract
from truth_guardian.schema import Sample


def make_sample(i: int) -> Sample:
    return Sample.model_validate({
        "id": f"s{i}",
        "documents": [{"id": "d", "text": "doc"}],
        "answer": "One sentence. Two sentences.",
        "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": f"g{i}"},
    })


def length_signal(sample, sentences):
    return [{"chars": s.end - s.start} for s in sentences]


def test_extract_stores_rows_aligned_with_sentences(tmp_path):
    store = FeatureStore(tmp_path / "sig" / "dev.jsonl", "length", "v1")
    assert extract([make_sample(0)], store, length_signal) == 1
    assert store.load()["s0"] == [{"start": 0, "end": 13, "chars": 13}, {"start": 14, "end": 28, "chars": 14}]


def test_extract_resumes_without_recomputing(tmp_path):
    path = tmp_path / "dev.jsonl"
    extract([make_sample(0), make_sample(1)], FeatureStore(path, "length", "v1"), length_signal)
    calls = []
    counting = lambda s, sents: calls.append(s.id) or length_signal(s, sents)
    assert extract([make_sample(i) for i in range(3)], FeatureStore(path, "length", "v1"), counting) == 1
    assert calls == ["s2"]


def test_partial_last_line_is_dropped(tmp_path):
    path = tmp_path / "dev.jsonl"
    extract([make_sample(0)], FeatureStore(path, "length", "v1"), length_signal)
    with path.open("a", encoding="utf-8") as f:
        f.write('{"id": "s1", "senten')
    store = FeatureStore(path, "length", "v1")
    assert set(store.load()) == {"s0"}


def test_version_mismatch_is_refused(tmp_path):
    path = tmp_path / "dev.jsonl"
    FeatureStore(path, "length", "v1")
    with pytest.raises(ValueError, match="delete it to rebuild"):
        FeatureStore(path, "length", "v2")
