import numpy as np

from truth_guardian import fusion
from truth_guardian.pipeline import analyze, make_sample
from truth_guardian.report import ClaimReport, verdict
from truth_guardian.schema import Sample
from truth_guardian.signals import lexical, symbolic
from truth_guardian.text import split_sentences

SOURCE = "Anne Frank died in 1945 in Bergen-Belsen. The camp was liberated weeks later."


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
    model = trained_model()
    sample = make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE])
    report = analyze(sample, model, use_polarity=False, signal_fns={"lexical": lexical, "symbolic": symbolic})
    (claim,) = report.claims
    assert report.verdict == "hallucinated" and claim.status == "contradicted"
    assert claim.action == "replace" and claim.fixes[0].replacement == "1945"
    assert [sample.answer[a:b] for a, b in claim.spans] == ["2022"]
    assert "1945" in claim.evidence.text


def test_live_analysis_supports_a_faithful_answer():
    model = trained_model()
    report = analyze(make_sample("Anne Frank died in 1945 in Bergen-Belsen.", [SOURCE]), model, use_polarity=False, signal_fns={"lexical": lexical, "symbolic": symbolic})
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
    report = analyze(sample, trained_model(), use_polarity=False, signal_fns={"lexical": lexical, "symbolic": symbolic}, tracer=tracer)
    assert report.agent is not None and report.agent.suspected_step == 2
    assert [s.step for s in report.agent.steps] == [1, 2, 3, 4]
    assert "1992" in report.agent.steps[1].unsupported and not report.agent.steps[3].unsupported


def test_report_round_trips_as_json():
    model = trained_model()
    report = analyze(make_sample("Anne Frank died in 2022 in Bergen-Belsen.", [SOURCE]), model, use_polarity=False, signal_fns={"lexical": lexical, "symbolic": symbolic})
    assert type(report).model_validate_json(report.model_dump_json()) == report
    assert np.isfinite(report.risk)
