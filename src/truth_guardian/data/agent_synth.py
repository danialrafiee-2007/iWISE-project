"""TG-Agent: scripted agent trajectories built from grounded RAG answers, with one injected error at a known step.

The scripted agent searches twice (each observation is one source passage), reasons over what it read,
and answers. Injections reuse the perturbation edits: a fabricated fact in the reasoning step that the
answer repeats, an ignored tool error (the second search fails but the agent still reports its content),
and an unsupported addition in the final answer. The step that first carries the error is the label.
"""

import random

from truth_guardian.perturb import perturb
from truth_guardian.schema import AgentStep, Document, Labels, Meta, Sample
from truth_guardian.text import split_sentences

INJECTIONS = ("fabricated_fact", "ignored_tool_error", "answer_addition")
TOOL_ERROR = "Error: the search service timed out; no results were returned."


def _steps(question: str, passages: list[str], reasoning: str, answer: str, second_observation: str | None = None) -> list[AgentStep]:
    first, second = passages[0], (passages[1] if len(passages) > 1 else passages[0])
    return [
        AgentStep(step=1, kind="action", content=f"call search({question!r})", tool="search", observation=first),
        AgentStep(step=2, kind="action", content=f"call search({(question + ' details')!r})", tool="search", observation=second_observation or second),
        AgentStep(step=3, kind="thought", content=f"From the search results: {reasoning}"),
        AgentStep(step=4, kind="answer", content=answer),
    ]


def _sample(base: Sample, suffix: str, steps: list[AgentStep], answer: str, labels: Labels) -> Sample:
    documents = [Document(id="task", text=base.question or "", source="question")]
    documents += [Document(id=f"step{s.step}", text=s.observation, source=f"step {s.step} tool output") for s in steps if s.observation]
    return Sample(
        id=f"tgagent-{suffix}-{base.id}",
        question=base.question,
        documents=documents,
        answer=answer,
        agent_log=steps,
        labels=labels,
        meta=Meta(dataset="tg_agent", task="agent", split="dev", group_id=base.meta.group_id, synthetic=True, source=base.meta.source),
    )


def build(base: Sample, rng: random.Random, entity_pool: dict[str, list[str]] | None = None) -> list[Sample]:
    """A clean trajectory plus one per applicable injection, from a grounded QA sample with at least two passages.

    The fabricated fact changes a number, else swaps a name (from entity_pool), else negates the reasoning.
    """
    passages = [d.text for d in base.documents]
    sentences = split_sentences(base.answer)
    if len(passages) < 2 or not sentences:
        return []
    reasoning, answer = sentences[0].text, base.answer
    out = [_sample(base, "clean", _steps(base.question, passages, reasoning, answer), answer, Labels(response="grounded"))]

    reasoning_sample = base.model_copy(update={"answer": reasoning, "labels": None})
    fabricated = (
        perturb(reasoning_sample, "number", rng)
        or perturb(reasoning_sample, "entity", rng, entity_pool or {})
        or perturb(reasoning_sample, "negation", rng)
    )
    if fabricated is not None:
        wrong = fabricated.answer
        out.append(_sample(
            base, "fabricated_fact", _steps(base.question, passages, wrong, answer.replace(reasoning, wrong, 1)),
            answer.replace(reasoning, wrong, 1),
            Labels(response="hallucinated", responsible_step=3, category="synthetic: fabricated fact"),
        ))

    second_only = [s.text for s in split_sentences(passages[1]) if s.text not in passages[0]]
    if second_only:
        claim = second_only[0]
        out.append(_sample(
            base, "ignored_tool_error", _steps(base.question, passages, claim, f"{answer} {claim}", second_observation=TOOL_ERROR),
            f"{answer} {claim}",
            Labels(response="hallucinated", responsible_step=3, category="synthetic: ignored tool error"),
        ))

    added = perturb(base.model_copy(update={"labels": None}), "addition", rng)
    if added is not None:
        out.append(_sample(
            base, "answer_addition", _steps(base.question, passages, reasoning, added.answer), added.answer,
            Labels(response="hallucinated", responsible_step=4, category="synthetic: answer addition"),
        ))
    return out
