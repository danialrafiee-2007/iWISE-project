from truth_guardian.evaluation import Prediction
from truth_guardian.overrides import apply_polarity


def prediction() -> Prediction:
    return Prediction(id="x", score=0.2, sentences=[{"start": 0, "end": 10, "score": 0.1}, {"start": 11, "end": 20, "score": 0.3}])


def test_confirmed_contradiction_raises_sentence_and_response():
    rows = [
        {"start": 0, "end": 10, "pol_confirmed": 0, "pol_contradiction": 0.0},
        {"start": 11, "end": 20, "pol_confirmed": 1, "pol_contradiction": 0.95},
    ]
    result = apply_polarity(prediction(), rows)
    assert result.score == 0.95
    assert [s.score for s in result.sentences] == [0.1, 0.95]


def test_unconfirmed_rows_change_nothing():
    rows = [{"start": 0, "end": 10, "pol_confirmed": 0, "pol_contradiction": 0.6}]
    assert apply_polarity(prediction(), rows) == prediction()
