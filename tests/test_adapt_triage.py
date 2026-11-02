import numpy as np

from truth_guardian import adapt, triage


def synthetic(n: int = 600, seed: int = 0):
    rng = np.random.default_rng(seed)
    labels = rng.random(n) < 0.4
    risks = np.where(labels, rng.beta(5, 2, n), rng.beta(2, 5, n)) * 0.6
    return risks, labels.astype(int)


def test_profile_recalibrates_risk_and_round_trips(tmp_path):
    risks, labels = synthetic()
    profile = adapt.fit("unit", risks, labels, "m1")
    assert profile.platt is not None and profile.calibrated(0.5) > profile.calibrated(0.1)
    assert abs(np.mean([profile.calibrated(r) for r in risks]) - labels.mean()) < 0.05
    profile.save(tmp_path / "p.json")
    assert adapt.load(tmp_path / "p.json", "m1").examples == len(labels)
    assert adapt.load(tmp_path / "p.json", "m2") is None


def test_profile_reweights_the_signals_and_sets_thresholds_on_its_own_scale():
    rng = np.random.default_rng(0)
    labels = np.array([0, 1] * 40)
    risks = np.clip(0.5 + rng.normal(0, 0.2, 80), 0.01, 0.99)
    signal = labels + rng.normal(0, 0.3, 80)
    features = [[float(adapt._logit([r])[0]), s, 0.5, 0.5] for r, s in zip(risks, signal)]
    profile = adapt.fit("unit", risks, labels, "m1", features=features)
    assert profile.ranking is not None and profile.ranking.coef[1] > 0
    assert profile.domain_risk(0.5, [0.0, 1.5, 0.5, 0.5]) > 0.5 > profile.domain_risk(0.5, [0.0, -0.5, 0.5, 0.5])
    assert all(0 <= t.catch <= 1 for t in profile.thresholds)
    assert adapt.domain_features(0.5, [{"lex_unsupported": 0.2, "dense_max": 0.6, "hhem_consistency": 0.8}]) == [0.0, 0.2, 0.6, 0.8]


def test_profile_never_reverses_the_ranking_when_recalibrating():
    profile = adapt.fit("unit", [0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1], "m1")
    assert profile.platt is None


def test_profile_with_one_class_keeps_the_risk():
    profile = adapt.fit("unit", [0.2, 0.3, 0.4], [0, 0, 0], "m1")
    assert profile.platt is None and profile.calibrated(0.3) == 0.3


def test_triage_lanes_keep_their_targets_on_new_answers():
    risks, labels = synthetic(2000, seed=1)
    policy = triage.fit(risks, labels, "m1", "unit")
    test_risks, test_labels = synthetic(2000, seed=2)
    load = triage.workload(test_risks, test_labels, policy)
    assert load["pass"] > 0 and load["hallucinated_among_passed"] <= triage.PASS_ERROR + 0.03
    assert load["grounded_blocked"] <= triage.BLOCK_FALSE_ALARM + 0.03
    assert policy.lane(0.0) == "pass" and policy.lane(1.0) == "block"
