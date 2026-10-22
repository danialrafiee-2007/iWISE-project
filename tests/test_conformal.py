import math

import numpy as np

from truth_guardian import conformal


def test_thresholds_follow_the_conformal_quantiles():
    risks = np.arange(1, 20) / 20
    assert conformal.catch_threshold(risks, 0.1) == risks[1]
    assert conformal.alarm_threshold(risks, 0.1) == risks[17]
    assert conformal.catch_threshold(risks[:5], 0.1) == -math.inf
    assert conformal.alarm_threshold(risks[:5], 0.1) == math.inf


def test_guarantees_hold_on_average_for_exchangeable_data():
    rng = np.random.default_rng(0)
    misses, alarms = [], []
    for _ in range(300):
        hallucinated, grounded = rng.beta(4, 2, 200), rng.beta(2, 4, 200)
        (t,) = conformal.calibrate(np.r_[hallucinated[:100], grounded[:100]], np.r_[np.ones(100), np.zeros(100)], alphas=(0.1,))
        misses.append(np.mean(hallucinated[100:] < t.catch))
        alarms.append(np.mean(grounded[100:] > t.alarm))
    assert np.mean(misses) <= 0.1 + 0.01 and np.mean(alarms) <= 0.1 + 0.01


def test_calibration_round_trips_and_checks_the_model_version(tmp_path):
    table = conformal.calibrate([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])
    c = conformal.Calibration(model_version="v1", data="d", pooled=table, by_task={"qa": table})
    c.save(tmp_path)
    assert conformal.load(tmp_path, "v1").get(0.1, "qa") == table[1]
    assert conformal.load(tmp_path, "v2") is None
