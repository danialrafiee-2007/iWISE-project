"""Live agent guardian: watches an agent while it runs and raises an alert before a hallucination reaches the answer.

After every step it applies the tracer's time rule with only what is known so far (the question and earlier tool
outputs). Two signals:
- a thought or answer introduces a number, date or name found nowhere in that evidence;
- right after a failed tool call, the agent reports mostly new content as if the tool had answered.
The second always stops the agent. The first depends on the policy: "strict" (every stated fact must come from a tool,
as in retrieval agents) stops; "lenient" (the agent may use its own knowledge) only warns, because faithful natural
agents do this routinely (80% of faithful AgentHallu dev runs). A failed tool call on its own is a warning. A name in a
thought that the question writes in another script (names.py) is not new: a model thinking in English about a Persian
task spells the task's own names in Latin letters.
Settings are fixed by design, not tuned; scripts/evaluate_guardian.py reports their sensitivity.
"""

from typing import Literal, NamedTuple

from truth_guardian.names import written_in
from truth_guardian.schema import AgentStep, Sample
from truth_guardian.tracer import StepTrace, TraceState

MIN_NEW_VALUES = 1
AFTER_ERROR_NOVELTY = 0.5
Policy = Literal["strict", "lenient"]


class Alert(NamedTuple):
    step: int
    level: Literal["warning", "stop"]
    reason: str


class AgentGuardian:
    def __init__(
        self,
        question: str | None,
        policy: Policy = "strict",
        min_new_values: int = MIN_NEW_VALUES,
        watch_actions: bool = False,
        after_error_novelty: float | None = AFTER_ERROR_NOVELTY,
    ):
        self.question = question
        self.state = TraceState(question)
        self.policy = policy
        self.min_new_values = min_new_values
        self.watch_actions = watch_actions
        self.after_error_novelty = after_error_novelty
        self.last_tool_failed = False
        self.alerts: list[Alert] = []

    def observe(self, step: AgentStep) -> Alert | None:
        return self.judge(step, self.state.add(step))

    def judge(self, step: AgentStep, t: StepTrace) -> Alert | None:
        """Apply the alarm rules to a step already traced with only earlier evidence."""
        alert = None
        checked = step.kind != "action" or self.watch_actions
        after_error = self.after_error_novelty is not None and self.last_tool_failed
        if step.kind == "thought":
            t = t._replace(unsupported=[a for a in t.unsupported if a.kind != "entity" or not written_in(a.text, self.question)])
        if checked and after_error and t.novelty >= self.after_error_novelty:
            alert = Alert(step.step, "stop", "reports new content right after a failed tool call, as if the tool had answered")
        elif checked and len(t.unsupported) >= self.min_new_values:
            values = ", ".join(sorted({a.text for a in t.unsupported})[:3])
            level = "stop" if self.policy == "strict" else "warning"
            alert = Alert(step.step, level, f"introduces {values}, absent from the question and every tool output so far")
        elif t.tool_error:
            alert = Alert(step.step, "warning", "the tool returned an error; the next step must not report results anyway")
        self.last_tool_failed = t.tool_error
        if alert:
            self.alerts.append(alert)
        return alert

    def first_stop(self) -> Alert | None:
        return next((a for a in self.alerts if a.level == "stop"), None)


def replay(sample: Sample, policy: Policy = "strict") -> list[Alert]:
    """The alerts the live guardian would have raised on a finished trajectory."""
    guardian = AgentGuardian(sample.question, policy)
    for step in sample.agent_log or []:
        guardian.observe(step)
    return guardian.alerts
