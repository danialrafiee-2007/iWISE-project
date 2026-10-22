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


def test_repeating_an_unsupported_value_is_not_its_origin():
    steps = [
        {"step": 1, "kind": "action", "content": "call search(record)", "observation": "The record is 1:43.20"},
        {"step": 2, "kind": "thought", "content": "The record is 1:39.87."},
        {"step": 3, "kind": "answer", "content": "Final answer: 1:39.87"},
    ]
    traces = trace(trajectory(steps, "1:39.87"))
    assert traces[1].unsupported and not traces[2].unsupported
    assert suspected_step(traces).step == 2


def test_tool_error_is_flagged():
    steps = [
        {"step": 1, "kind": "action", "content": "call mv(report.pdf, temp)", "observation": "{\"error\": \"No such file\"}"},
        {"step": 2, "kind": "answer", "content": "Moved."},
    ]
    traces = trace(trajectory(steps, "Moved."))
    assert traces[0].tool_error and "error" in traces[0].reason()


def test_learned_tracer_finds_the_step_that_spreads_an_unsupported_value():
    import numpy as np

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
    features = {s.id: (trace(s), step_features(s, trace(s)), np.zeros(0)) for s in samples}
    assert features["t0"][1].shape == (3, len(STEP_FEATURES))
    model = fit_tracer(samples, features)
    traces, probs, risk = model.analyse(samples[1])
    assert traces[int(np.argmax(probs))].step == samples[1].labels.responsible_step
    assert 0 <= risk <= 1


def test_ties_go_to_the_earliest_step():
    steps = [{"step": 1, "kind": "thought", "content": ""}, {"step": 2, "kind": "thought", "content": ""}]
    traces = [t._replace(score=1.0) for t in trace(trajectory(steps, "x"))]
    assert suspected_step(traces).step == 1


def test_semantic_rows_compare_each_step_with_the_latest_tool_output():
    from truth_guardian.tracer import semantic_rows

    steps = [
        {"step": 1, "kind": "action", "content": "call search(record)", "observation": "The record is 1:43.20"},
        {"step": 2, "kind": "thought", "content": "Probably the record is 1:39.87."},
        {"step": 3, "kind": "answer", "content": "1:39.87"},
    ]
    seen = []

    def consistency(pairs):
        seen.extend(pairs)
        return [0.2] * len(pairs)

    rows = semantic_rows(trajectory(steps, "1:39.87"), consistency)
    assert rows["steps"][0]["prev_support"] == 1.0
    assert rows["steps"][1]["prev_support"] == 0.2 and rows["steps"][1]["self_doubt"] == 1.0
    assert seen[0] == ("The record is 1:43.20", "Probably the record is 1:39.87.")
    assert rows["answer"]["answer_support"] == 0.2 and rows["answer"]["answer_unsupported"] >= 1
