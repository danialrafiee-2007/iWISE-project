import hashlib

import numpy as np

from truth_guardian import fusion
from truth_guardian.pipeline import analyze, make_sample
from truth_guardian.report import ClaimReport, verdict
from truth_guardian.schema import Sample
from truth_guardian.signals import lexical, symbolic
from truth_guardian.text import split_sentences

SOURCE = "Anne Frank died in 1945 in Bergen-Belsen. The camp was liberated weeks later."
GHEE = (
    "Ghee is made by simmering butter until the milk solids separate. "
    "However, the solids burn quickly if the heat is too high. "
    "Ghee keeps for months without refrigeration."
)
SIGNAL_FNS = {"lexical": lexical, "symbolic": symbolic}


def fake_encode(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 64))
    for row, text in enumerate(texts):
        for word in text.lower().replace(".", "").replace(",", "").replace("?", "").split():
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def run(sample: Sample, **kwargs):
    return analyze(sample, trained_model(), use_polarity=False, signal_fns=SIGNAL_FNS, encode=fake_encode, **kwargs)


def training_set(n: int = 60) -> tuple[list[Sample], dict]:
    """Half the answers repeat the source; half change the year, which lexical and symbolic signals both see."""
    samples, rows = [], {"lexical": {}, "symbolic": {}}
    for i in range(n):
        wrong = i % 2 == 1
        answer = "Anne Frank died in 2022 in Bergen-Belsen." if wrong else "Anne Frank died in 1945 in Bergen-Belsen."
        labels = {"response": "hallucinated", "spans": [{"start": 19, "end": 23, "text": "2022"}]} if wrong else {"response": "grounded"}
        s = Sample.model_validate({
            "id": f"s{i}", "documents": [{"id": "d", "text": SOURCE}], "answer": answer, "labels": labels,
            "meta": {"dataset": "unit", "task": "summary", "split": "train", "group_id": f"g{i}"},
        })
        sentences = split_sentences(s.answer)
        for name, fn in (("lexical", lexical), ("symbolic", symbolic)):
            rows[name][s.id] = [{"start": x.start, "end": x.end, **r} for x, r in zip(sentences, fn(s, sentences))]
        samples.append(s)
    return samples, rows


def trained_model():
    samples, rows = training_set()
    model, _, _ = fusion.fit(samples, fusion.build_table(samples, rows, ["lexical", "symbolic"]), ["lexical", "symbolic"], "logreg", folds=3)
    model.thresholds = {"response": 0.5, "sentence": 0.5}
    return model


def test_live_analysis_reports_wrong_year_with_fix_and_evidence():
    sample = make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE])
    report = run(sample)
    (claim,) = report.claims
    assert report.verdict == "hallucinated" and claim.status == "contradicted"
    assert claim.action == "replace" and claim.fixes[0].replacement == "1945"
    assert [sample.answer[a:b] for a, b in claim.spans] == ["2022"]
    assert "1945" in claim.evidence.text


def test_live_analysis_supports_a_faithful_answer():
    report = run(make_sample("Anne Frank died in 1945 in Bergen-Belsen.", [SOURCE]))
    assert report.verdict == "grounded" and report.claims[0].status == "supported" and report.claims[0].action == "keep"


def claim(status: str) -> ClaimReport:
    return ClaimReport(start=0, end=1, text="x", status=status, risk=0.9, explanation="", action="verify")


def test_verdict_is_uncertain_near_threshold_or_with_only_insufficient_evidence():
    assert verdict(0.52, 0.5, [claim("unsupported")]) == "uncertain"
    assert verdict(0.9, 0.5, [claim("insufficient_evidence")]) == "uncertain"
    assert verdict(0.9, 0.5, [claim("unsupported")]) == "hallucinated"
    assert verdict(0.1, 0.5, [claim("supported")]) == "grounded"


def test_agent_trajectory_gets_a_timeline_with_the_suspected_step():
    from truth_guardian.tracer import fit_tracer, step_features, trace

    def trajectory(i: int, bad: int | None) -> Sample:
        value = f"{1990 + i % 7}" if bad else "1945"
        steps = [{"step": 1, "kind": "action", "content": "call search(Anne Frank death)", "observation": "Archive: Anne Frank died in 1945."}]
        steps += [{"step": k, "kind": "thought", "content": f"So the year was {value}." if k == bad else "Reading the search results carefully."} for k in (2, 3)]
        steps += [{"step": 4, "kind": "answer", "content": value}]
        s = make_sample(value, [], question="When did Anne Frank die?", agent_steps=steps, sample_id=f"a{i}")
        labels = {"response": "hallucinated", "responsible_step": bad} if bad else {"response": "grounded"}
        return Sample.model_validate(s.model_dump() | {"labels": labels, "meta": s.meta.model_dump() | {"group_id": f"a{i}"}})

    train = [trajectory(i, 2 + i % 2) for i in range(30)] + [trajectory(100 + i, None) for i in range(10)]
    tracer = fit_tracer(train, {s.id: (trace(s), step_features(s, trace(s)), np.zeros(0)) for s in train})
    sample = make_sample("1992", [], question="When did Anne Frank die?", agent_steps=[
        {"step": 1, "kind": "action", "content": "call search(Anne Frank death)", "observation": "Archive: Anne Frank died in 1945."},
        {"step": 2, "kind": "thought", "content": "So the year was 1992."},
        {"step": 3, "kind": "thought", "content": "Reading the search results carefully."},
        {"step": 4, "kind": "answer", "content": "1992"},
    ])
    report = run(sample, tracer=tracer)
    assert report.agent is not None and report.agent.suspected_step == 2
    assert report.agent.guardian_stop == 2 and report.agent.alerts[0].level == "stop"
    assert [s.step for s in report.agent.steps] == [1, 2, 3, 4]
    assert "1992" in report.agent.steps[1].unsupported and not report.agent.steps[3].unsupported


def test_report_round_trips_as_json():
    report = run(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE], question="Anne Frank died in which year in Bergen-Belsen?"))
    assert type(report).model_validate_json(report.model_dump_json()) == report
    assert np.isfinite(report.risk)


def test_focus_narrows_a_flagged_sentence_to_the_claim_with_the_error():
    answer = "Anne Frank died in 2022 in Bergen-Belsen, and the camp was liberated weeks later."
    (claim,) = run(make_sample(answer, [SOURCE])).claims
    assert claim.status != "supported" and len(claim.focus) == 1
    focus = answer[claim.focus[0][0] : claim.focus[0][1]]
    assert "2022" in focus and "liberated" not in focus


def test_blame_points_to_generation_over_relevant_sources_and_to_retrieval_over_irrelevant_ones():
    question = "Anne Frank died in which year in Bergen-Belsen?"
    relevant = run(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE], question=question))
    assert relevant.verdict == "hallucinated" and relevant.diagnosis.blame == "generation"
    irrelevant = run(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [GHEE], question=question))
    assert irrelevant.diagnosis.blame == "retrieval" and irrelevant.diagnosis.message in irrelevant.warnings
    assert run(make_sample("Anne Frank died in 2022.", [SOURCE])).diagnosis.blame == "unknown"


def test_omitted_caveat_is_reported_and_warned():
    report = run(make_sample("Ghee is made by simmering butter until the milk solids separate.", [GHEE], question="How is ghee made and what can go wrong with the heat?"))
    assert report.completeness.omitted_caveats == ["However, the solids burn quickly if the heat is too high."]
    assert any("leaves out a condition" in w for w in report.warnings)
    assert run(make_sample("Anne Frank died in 1945.", [SOURCE])).completeness is None


def overlap_consistency(pairs):
    return [len(set(p.lower().split()) & set(h.lower().split())) / max(len(h.split()), 1) for p, h in pairs]


def always_contradiction(pairs):
    return np.tile([0.9, 0.05, 0.05], (len(pairs), 1))


def test_confirmed_role_swap_overrides_and_explains():
    def swapped(sample, sentences):
        return [{"shift_kind": "role_swap", "shift_candidate": 1, "shift_confirmed": 1, "shift_overrides": 1, "shift_entailment": 0.9,
                 "shift_spans": [[0, 6], [16, 23]], "shift_evidence": "Brazil defeated Germany.", "shift_detail": "the source has brazil acting on germany, the answer the reverse"} for _ in sentences]

    report = analyze(make_sample("Germany defeated Brazil.", ["Brazil defeated Germany."]), trained_model(), use_polarity=False,
                     signal_fns={**SIGNAL_FNS, "shifts": swapped}, encode=fake_encode)
    (claim,) = report.claims
    assert claim.status == "contradicted" and "swaps who did what" in claim.explanation and claim.evidence.text == "Brazil defeated Germany."


def test_answer_following_one_of_two_disagreeing_sources_is_contested():
    sources = ["The Eiffel Tower is 324 metres tall, including its antennas.", "The Eiffel Tower is 300 metres tall, including its antennas."]
    report = run(make_sample("The Eiffel Tower is 300 metres tall, including its antennas.", sources), classify=always_contradiction)
    (claim,) = report.claims
    assert claim.status == "contested" and claim.evidence.document_id == "source2" and len(report.conflicts) == 1
    assert report.verdict == "uncertain" and report.diagnosis.blame == "conflicting_sources"


def test_wrong_citation_becomes_a_caution_and_the_card_shows_it():
    sources = ["Ghee keeps for months without a fridge.", "Anne Frank died in 1945 in Bergen-Belsen."]
    report = run(make_sample("Anne Frank died in 1945 in Bergen-Belsen (Passage 1).", sources), consistency=overlap_consistency)
    (claim,) = report.claims
    assert claim.citation.cited == [1] and not claim.citation.supported and "supported by document 2" in claim.cautions[0]
    citations = next(d for d in report.card.dimensions if d.name == "citations")
    assert citations.score == 0.0 and report.card.grade in "ABCDF"


def test_guarantee_and_cited_answer():
    from truth_guardian.conformal import Calibration, calibrate

    table = calibrate([0.9, 0.8, 0.7, 0.2, 0.1, 0.05] * 5, [1, 1, 1, 0, 0, 0] * 5)
    report = run(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE]), calibration=Calibration(model_version="m", data="unit", pooled=table, by_task={}))
    assert report.guarantee.alpha == 0.1 and report.guarantee.flagged_with_catch_guarantee == (report.risk >= report.guarantee.catch_threshold)
    faithful = run(make_sample("Anne Frank died in 1945 in Bergen-Belsen.", [SOURCE]))
    assert faithful.cited_answer == "Anne Frank died in 1945 in Bergen-Belsen [1]."


def test_heal_fixes_the_wrong_year_and_rechecks():
    from truth_guardian.pipeline import heal

    healing = heal(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE]), trained_model(), use_polarity=False, signal_fns=SIGNAL_FNS, encode=fake_encode)
    assert healing.answer == "Anne Frank died in 1945 in Bergen-Belsen."
    assert healing.reports[0].verdict == "hallucinated" and healing.reports[-1].verdict == "grounded"
    assert healing.changes[0][0].new == "1945"
