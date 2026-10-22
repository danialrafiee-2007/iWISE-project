from truth_guardian.guardian import AgentGuardian
from truth_guardian.schema import AgentStep


def step(n: int, kind: str, content: str, observation: str | None = None) -> AgentStep:
    return AgentStep(step=n, kind=kind, content=content, observation=observation)


def test_stops_at_the_step_that_invents_a_value_before_the_answer():
    guardian = AgentGuardian("When did Anne Frank die?")
    assert guardian.observe(step(1, "action", "call search(Anne Frank death)", "Anne Frank died in 1945.")) is None
    alert = guardian.observe(step(2, "thought", "So she died in 1992."))
    assert alert.level == "stop" and alert.step == 2 and "1992" in alert.reason
    guardian.observe(step(3, "answer", "1992"))
    assert guardian.first_stop().step == 2


def test_faithful_run_raises_nothing():
    guardian = AgentGuardian("When did Anne Frank die?")
    guardian.observe(step(1, "action", "call search(Anne Frank death)", "Anne Frank died in 1945."))
    guardian.observe(step(2, "thought", "So she died in 1945."))
    guardian.observe(step(3, "answer", "1945"))
    assert guardian.alerts == []


def test_tool_error_warns_and_reporting_results_anyway_stops():
    guardian = AgentGuardian("Where was the camp?")
    warning = guardian.observe(step(1, "action", "call search(camp)", "Error: the search service timed out."))
    assert warning.level == "warning"
    stop = guardian.observe(step(2, "thought", "The results show the camp was liberated by allied troops in spring."))
    assert stop.level == "stop" and "failed tool call" in stop.reason


def test_actions_are_ignored_unless_watched():
    quiet = AgentGuardian("Find the record.")
    assert quiet.observe(step(1, "action", "call lookup(id=98765)")) is None
    strict = AgentGuardian("Find the record.", watch_actions=True)
    assert strict.observe(step(1, "action", "call lookup(id=98765)")).level == "stop"
