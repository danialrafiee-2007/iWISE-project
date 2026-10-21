from truth_guardian.schema import Sample
from truth_guardian.symbolic import unmatched_atoms
from truth_guardian.tracer import suspected_step, trace


def trajectory(steps: list[dict], answer: str) -> Sample:
    return Sample.model_validate({
        "id": "t",
        "question": "What was the world record time on Yoshi Circuit in 150cc?",
        "documents": [{"id": "task", "text": "question"}],
        "answer": answer,
        "agent_log": steps,
        "labels": {"response": "hallucinated", "responsible_step": 2},
        "meta": {"dataset": "unit", "task": "agent", "split": "dev", "group_id": "g"},
    })


def test_unmatched_atoms_against_evidence():
    atoms = unmatched_atoms("The record is 1:41.614 set by Mario Rossi.", "Records: Yoshi Circuit 1:43.20 by Luigi Bianchi")
    assert {"1:41", "614"} <= {a.text for a in atoms}
    assert unmatched_atoms("The record is 1:43.20.", "Records: Yoshi Circuit 1:43.20 by Luigi Bianchi") == []


def test_step_that_introduces_an_unsupported_number_reaching_the_answer_is_suspected():
    steps = [
        {"step": 1, "kind": "action", "content": "call search(Yoshi Circuit world record 150cc)", "observation": "Yoshi Circuit 150cc record: 1:43.20 (2023)"},
        {"step": 2, "kind": "thought", "content": "The record is 1:39.87 according to my memory."},
        {"step": 3, "kind": "answer", "content": "Final answer: 1:39.87"},
    ]
    traces = trace(trajectory(steps, "1:39.87"))
    suspect = suspected_step(traces)
    assert suspect.step == 2
    assert "1:39" in suspect.propagated
    assert "reaches the final answer" in suspect.reason()


def test_later_steps_may_use_earlier_tool_output():
    steps = [
        {"step": 1, "kind": "action", "content": "call search(record)", "observation": "The record is 1:43.20"},
        {"step": 2, "kind": "answer", "content": "The record is 1:43.20"},
    ]
    traces = trace(trajectory(steps, "1:43.20"))
    assert traces[1].unsupported == [] and traces[1].propagated == []


def test_tool_error_is_flagged():
    steps = [
        {"step": 1, "kind": "action", "content": "call mv(report.pdf, temp)", "observation": "{\"error\": \"No such file\"}"},
        {"step": 2, "kind": "answer", "content": "Moved."},
    ]
    traces = trace(trajectory(steps, "Moved."))
    assert traces[0].tool_error and "error" in traces[0].reason()


def test_learned_tracer_finds_the_step_that_spreads_an_unsupported_value():
    from truth_guardian.tracer import STEP_FEATURES, fit_tracer, step_features

    samples = []
    for i in range(30):
        bad = 1 + i % 3
        steps = [
            {"step": k, "kind": "thought", "content": f"The record is 1:{40 + k}" if k == bad else "Searching the archive.", "observation": "nothing relevant"}
            for k in (1, 2, 3)
        ]
        s = trajectory(steps, f"1:{40 + bad}")
        s = s.model_copy(update={"id": f"t{i}", "labels": s.labels.model_copy(update={"responsible_step": bad}), "meta": s.meta.model_copy(update={"group_id": f"g{i}"})})
        samples.append(s)
    for i in range(10):
        steps = [{"step": k, "kind": "thought", "content": "Searching the archive.", "observation": "nothing relevant"} for k in (1, 2, 3)]
        s = trajectory(steps, "unknown")
        samples.append(s.model_copy(update={"id": f"c{i}", "labels": s.labels.model_copy(update={"response": "grounded", "responsible_step": None}), "meta": s.meta.model_copy(update={"group_id": f"c{i}"})}))
    features = {s.id: (trace(s), step_features(s, trace(s))) for s in samples}
    assert features["t0"][1].shape == (3, len(STEP_FEATURES))
    model = fit_tracer(samples, features)
    probs = dict(model.step_probabilities(samples[1]))
    assert max(probs, key=probs.get) == samples[1].labels.responsible_step


def test_ties_go_to_the_earliest_step():
    steps = [{"step": 1, "kind": "thought", "content": ""}, {"step": 2, "kind": "thought", "content": ""}]
    traces = [t._replace(score=1.0) for t in trace(trajectory(steps, "x"))]
    assert suspected_step(traces).step == 1
