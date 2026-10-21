import json

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from truth_guardian import fusion
from truth_guardian.schema import Sample
from truth_guardian.text import split_sentences

ANSWER = "First claim here. Second claim here. Third claim here."


def make_sample(i: int, bad_sentence: int | None) -> Sample:
    sentences = split_sentences(ANSWER)
    labels = {"response": "grounded"}
    if bad_sentence is not None:
        s = sentences[bad_sentence]
        labels = {"response": "hallucinated", "spans": [{"start": s.start, "end": s.end, "text": s.text}]}
    return Sample.model_validate({
        "id": f"s{i}",
        "documents": [{"id": "d", "text": "doc"}],
        "answer": ANSWER,
        "labels": labels,
        "meta": {"dataset": "unit", "task": "qa", "split": "train", "group_id": f"g{i // 2}"},
    })


def synthetic(n: int = 200, seed: int = 0):
    """The lexical signal is high on the hallucinated sentence (plus noise); dense is pure noise."""
    rng = np.random.default_rng(seed)
    samples = [make_sample(i, int(rng.integers(0, 3)) if i % 2 else None) for i in range(n)]
    rows = {"lexical": {}, "dense": {}}
    for s in samples:
        sentences = split_sentences(s.answer)
        bad = {sp.start for sp in s.labels.spans}
        rows["lexical"][s.id] = [
            {"start": x.start, "end": x.end, "lex_unsupported": float((x.start in bad) * 0.8 + rng.random() * 0.4)}
            for x in sentences
        ]
        rows["dense"][s.id] = [{"start": x.start, "end": x.end, "dense_max": float(rng.random())} for x in sentences]
    return samples, rows


@pytest.mark.parametrize("kind", ["logreg", "hgb"])
def test_fit_learns_informative_signal(kind):
    samples, rows = synthetic()
    table = fusion.build_table(samples, rows, ["lexical", "dense"])
    model, report, _ = fusion.fit(samples, table, ["lexical", "dense"], kind, folds=4)
    assert report["oof_sentence_auroc"] > 0.9 and report["oof_response_auroc"] > 0.9
    test_samples, test_rows = synthetic(seed=1)
    predictions = model.predictions(test_samples, fusion.build_table(test_samples, test_rows, ["lexical", "dense"]))
    y = [s.labels.response == "hallucinated" for s in test_samples]
    assert roc_auc_score(y, [p.score for p in predictions]) > 0.9
    assert all(0 <= p.score <= 1 for p in predictions)
    assert [len(p.sentences) for p in predictions] == [3] * len(test_samples)


def test_build_table_rejects_misaligned_signals():
    samples, rows = synthetic(n=2)
    rows["dense"]["s0"][0]["start"] = 99
    with pytest.raises(ValueError, match="sentence boundaries"):
        fusion.build_table(samples, rows, ["lexical", "dense"])


def test_response_features_summaries():
    samples, rows = synthetic(n=2)
    table = fusion.build_table(samples, rows, ["lexical"])
    features, names = fusion.response_features(np.array([0.1, 0.9, 0.5, 0.2, 0.2, 0.2]), table)
    first = dict(zip(names, features[0]))
    assert first["p_max"] == 0.9 and first["p_count"] == 2 and first["n_sentences"] == 3
    assert first["p_top2"] == pytest.approx(0.7)


def test_structure_flag_removes_shortcut_features():
    samples, rows = synthetic(n=40)
    table = fusion.build_table(samples, rows, ["lexical"], structure=False)
    assert table.feature_names == ["lex_unsupported"]
    _, names = fusion.response_features(np.zeros(len(table.labels)), table)
    assert "n_sentences" not in names
    model, _, _ = fusion.fit(samples, table, ["lexical"], "logreg", folds=2)
    with pytest.raises(ValueError, match="structure flag"):
        model.score(fusion.build_table(samples, rows, ["lexical"]))


def test_group_folds_keep_groups_together():
    folds = fusion.group_folds(["a", "a", "b", "c", "d"], 2)
    assert set(folds) == {"a", "b", "c", "d"} and set(folds.values()) == {0, 1}


def test_save_and_load_round_trip(tmp_path):
    samples, rows = synthetic(n=40)
    table = fusion.build_table(samples, rows, ["lexical", "dense"])
    model, _, _ = fusion.fit(samples, table, ["lexical", "dense"], "logreg", folds=2)
    fusion.save(model, tmp_path, {"version": "v1"})
    loaded, manifest = fusion.load(tmp_path)
    assert manifest["version"] == "v1" and len(manifest["model_sha256"]) == 64
    assert np.allclose(loaded.score(table)[1], model.score(table)[1])


def test_load_rejects_tampered_file(tmp_path):
    samples, rows = synthetic(n=40)
    table = fusion.build_table(samples, rows, ["lexical"])
    model, _, _ = fusion.fit(samples, table, ["lexical"], "logreg", folds=2)
    folder = fusion.save(model, tmp_path, {"version": "v1"})
    with (folder / "model.joblib").open("ab") as f:
        f.write(b"x")
    with pytest.raises(ValueError, match="checksum"):
        fusion.load(tmp_path)


def test_load_rejects_stale_signal_versions(tmp_path):
    samples, rows = synthetic(n=40)
    table = fusion.build_table(samples, rows, ["lexical"])
    model, _, _ = fusion.fit(samples, table, ["lexical"], "logreg", folds=2)
    model.signal_versions = {"lexical": "v0"}
    fusion.save(model, tmp_path, {"version": "v1"})
    with pytest.raises(ValueError, match="older signal versions"):
        fusion.load(tmp_path)
