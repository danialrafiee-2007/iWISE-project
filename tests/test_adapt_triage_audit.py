import numpy as np

from truth_guardian import adapt, triage
from truth_guardian.audit import summarize
from truth_guardian.report import Card, ClaimReport, Evidence, Report, TriageReport
from truth_guardian.schema import Sample


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


def report(i: str, risk: float, status: str, document: str | None = None) -> Report:
    claim = ClaimReport(start=0, end=5, text="claim", status=status, risk=risk, explanation="why", action="keep",
                        evidence=Evidence(text="e", document_id=document) if document else None)
    return Report(id=i, verdict="hallucinated" if risk > 0.5 else "grounded", risk=risk, response_threshold=0.4, sentence_threshold=0.3,
                  claims=[claim], card=Card(grade="F" if risk > 0.7 else "A", risk=risk, dimensions=[]), triage=TriageReport(lane="review", reason="r"))


def sample(i: str, hallucinated: bool) -> Sample:
    return Sample.model_validate({"id": i, "answer": "x", "documents": [{"id": "d", "text": "x"}], "labels": {"response": "hallucinated" if hallucinated else "grounded"},
                                  "meta": {"dataset": "unit", "task": "qa", "split": "dev", "group_id": i}})


def test_audit_summary_estimates_rate_and_ranks_worst_answers():
    reports = [report("a", 0.9, "contradicted", "doc1"), report("b", 0.1, "supported"), report("c", 0.6, "unsupported", "doc1"), report("d", 0.2, "supported")]
    summary = summarize([sample("a", True), sample("b", False), sample("c", True), sample("d", False)], reports)
    assert summary.estimated_hallucination_rate == 0.45 and summary.true_hallucination_rate == 0.5
    assert summary.worst[0].id == "a" and summary.flagged_documents == {"doc1": 2}
    assert summary.lanes == {"review": 4} and summary.verdicts == {"hallucinated": 2, "grounded": 2}
