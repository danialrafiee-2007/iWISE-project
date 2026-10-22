import random

from truth_guardian.data.agent_synth import TOOL_ERROR, build
from truth_guardian.schema import Sample


def base() -> Sample:
    return Sample.model_validate({
        "id": "b1",
        "question": "When did Anne Frank die?",
        "documents": [
            {"id": "passage1", "text": "Anne Frank died in 1945 in Bergen-Belsen."},
            {"id": "passage2", "text": "Anne Frank died in 1945 in Bergen-Belsen. The camp was liberated in April by British troops."},
        ],
        "answer": "Anne Frank died in 1945 in Bergen-Belsen. She was 15 years old.",
        "labels": {"response": "grounded"},
        "meta": {"dataset": "ragtruth", "task": "qa", "split": "dev", "group_id": "g1"},
    })


def test_builds_clean_and_injected_trajectories_with_known_origins():
    samples = {s.id.split("-")[1]: s for s in build(base(), random.Random(0))}
    assert set(samples) == {"clean", "fabricated_fact", "ignored_tool_error", "answer_addition"}
    assert samples["clean"].labels.response == "grounded" and samples["clean"].labels.responsible_step is None
    assert samples["fabricated_fact"].labels.responsible_step == 3
    assert samples["ignored_tool_error"].labels.responsible_step == 3
    assert samples["answer_addition"].labels.responsible_step == 4
    assert all(s.meta.synthetic and len(s.agent_log) == 4 for s in samples.values())


def test_fabricated_fact_reaches_the_answer_and_is_absent_from_tool_outputs():
    s = {x.id.split("-")[1]: x for x in build(base(), random.Random(0))}["fabricated_fact"]
    reasoning = s.agent_log[2].content.removeprefix("From the search results: ")
    assert reasoning in s.answer
    assert "1945" not in reasoning


def test_ignored_tool_error_reports_content_the_failed_search_never_returned():
    s = {x.id.split("-")[1]: x for x in build(base(), random.Random(0))}["ignored_tool_error"]
    assert s.agent_log[1].observation == TOOL_ERROR
    assert "liberated in April" in s.agent_log[2].content
    assert all("liberated" not in (step.observation or "") for step in s.agent_log)


def test_bases_without_two_passages_are_skipped():
    single = base().model_copy(update={"documents": base().documents[:1]})
    assert build(single, random.Random(0)) == []
