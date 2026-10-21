from truth_guardian.data.agenthallu import convert_trajectory, merge_repeated_steps

RAW = {
    "model_id": "gpt-4.1",
    "agent_type": "OpenManus",
    "question": [["Create a folder"], ["Move report.pdf into it"]],
    "true_answer": "SECRET-REFERENCE-ANSWER",
    "explanation": {"Steps": "SECRET-SOLUTION-NOTES"},
    "question_source": "BFCL",
    "question_domain": "Tool Use",
    "history": [
        {"step": 1, "role": "assistant", "content": "I will create the folder.", "tool_calls": [{"name": "mkdir", "arguments": {"dir_name": "temp"}}], "tool_responses": ["None"]},
        {"step": 2, "role": "assistant", "content": None, "tool_calls": [{"name": "mv", "arguments": {"source": "report.pdf"}}], "tool_responses": ["{\"error\": \"No such file\"}"]},
        {"step": 3, "content": "Done, the file was moved."},
    ],
    "agent_answer": "The file was moved.",
    "is_hallucination": "true",
    "hallucination_step": "3",
    "hallucination_category": "Tool-Use Hallucination",
    "hallucination_reason": "Claims success although mv failed.",
}


def test_converts_question_steps_and_labels():
    sample = convert_trajectory(RAW, "OpenManus", "007")
    assert sample.id == "agenthallu-OpenManus-007"
    assert sample.question == "Turn 1: Create a folder\nTurn 2: Move report.pdf into it"
    assert [s.kind for s in sample.agent_log] == ["action", "action", "answer"]
    assert sample.agent_log[1].observation == '{"error": "No such file"}'
    assert "call mv(" in sample.agent_log[1].content
    assert sample.labels.response == "hallucinated" and sample.labels.responsible_step == 3
    assert sample.labels.category == "Tool-Use Hallucination"
    assert [d.id for d in sample.documents] == ["task", "step1", "step2"]


def test_reference_answer_and_solution_notes_never_leak():
    dumped = convert_trajectory(RAW, "OpenManus", "007").model_dump_json()
    assert "SECRET-REFERENCE-ANSWER" not in dumped and "SECRET-SOLUTION-NOTES" not in dumped


def test_clean_trajectory_has_no_responsible_step():
    sample = convert_trajectory(RAW | {"is_hallucination": "false", "hallucination_step": None}, "OpenManus", "008")
    assert sample.labels.response == "grounded" and sample.labels.responsible_step is None


def test_repeated_step_numbers_are_merged():
    merged = merge_repeated_steps([
        {"step": 1, "content": "a"},
        {"step": 2, "content": "b", "tool_calls": [{"name": "x"}], "tool_responses": ["r1"]},
        {"step": 2, "content": "c", "tool_calls": [{"name": "y"}], "tool_responses": ["r2"]},
    ])
    assert [m["step"] for m in merged] == [1, 2]
    assert merged[1]["content"] == "b\nc" and merged[1]["tool_responses"] == ["r1", "r2"]
