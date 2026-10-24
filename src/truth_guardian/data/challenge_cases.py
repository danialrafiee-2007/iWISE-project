"""TG-Bench challenge cases: the five harder cases of the Challenge 4 description, written as paired samples.

Per topic: a faithful answer (control) and copies that mix in a wrong detail, add a claim no source supports, use only
part of the evidence (a left-out fact, or a dropped caveat that overstates), and the faithful answer again over
sources that miss the question, with an honest answer as its control. Per agent run: a faithful trajectory and one
whose error starts at a known step. [[...]] in the written answers marks the wrong words.
"""

import json
import re
from pathlib import Path

from truth_guardian.pipeline import make_sample
from truth_guardian.schema import HallucinationType, Labels, Meta, Sample, Span

MARK = re.compile(r"\[\[(.+?)\]\]")
MIXED_TYPES = {
    "number": HallucinationType.NUMERIC_ENTITY_MISMATCH, "date": HallucinationType.NUMERIC_ENTITY_MISMATCH,
    "place": HallucinationType.NUMERIC_ENTITY_MISMATCH, "entity": HallucinationType.NUMERIC_ENTITY_MISMATCH,
    "opposite": HallucinationType.CONTRADICTED, "roles": HallucinationType.CONTRADICTED, "negation": HallucinationType.CONTRADICTED,
}


def unmark(text: str) -> tuple[str, list[tuple[int, int]]]:
    """The text without [[ ]] marks, and the character range of each marked part in it."""
    clean, spans, last = [], [], 0
    for m in MARK.finditer(text):
        clean.append(text[last : m.start()])
        start = sum(map(len, clean))
        clean.append(m.group(1))
        spans.append((start, start + len(m.group(1))))
        last = m.end()
    clean.append(text[last:])
    out = "".join(clean)
    if "[[" in out or "]]" in out:
        raise ValueError(f"unbalanced marks in {text!r}")
    return out, spans


def _sample(
    sample_id: str, group: str, answer: str, sources: list[str], question: str, category: str,
    span_type: HallucinationType | None = None, steps: list[dict] | None = None, responsible: int | None = None,
    reason: str | None = None, grounded: bool = False,
) -> Sample:
    text, spans = unmark(answer)
    if grounded and spans:
        raise ValueError(f"{sample_id}: a grounded answer has marked words")
    if not grounded and not spans and span_type is not None:
        raise ValueError(f"{sample_id}: no marked words")
    base = make_sample(text, sources, question, steps, sample_id=sample_id)
    labels = Labels(
        response="grounded" if grounded else "hallucinated",
        spans=[Span(start=a, end=b, text=text[a:b], type=span_type) for a, b in spans],
        responsible_step=responsible, category=category, reason=reason,
    )
    meta = Meta(dataset="tg_challenge_cases", task="qa", split="test", group_id=group, source="written for TG-Bench", synthetic=True)
    return Sample.model_validate(base.model_dump() | {"labels": labels.model_dump(), "meta": meta.model_dump()})


def _numbered(steps: list[dict]) -> list[dict]:
    return [{"step": i, **s} for i, s in enumerate(steps, 1)]


def build(spec: dict) -> list[Sample]:
    out = []
    for t in spec["topics"]:
        q, src, tid = t["question"], t["sources"], t["id"]
        out.append(_sample(f"cases-control-{tid}", tid, t["faithful"], src, q, "control", grounded=True))
        mixed = t["mixed"]
        out.append(_sample(f"cases-mixed-{tid}", tid, mixed["answer"], src, q, f"mixed: {mixed['kind']}", MIXED_TYPES[mixed["kind"]]))
        out.append(_sample(f"cases-unsupported-{tid}", tid, t["unsupported"], src, q, "unsupported", HallucinationType.UNSUPPORTED))
        partial = t["partial"]
        if partial["kind"] == "omission":
            out.append(_sample(f"cases-partial-{tid}", tid, partial["answer"], src, q, "partial: omission", reason=partial["left_out"], grounded=True))
        else:
            out.append(_sample(f"cases-partial-{tid}", tid, partial["answer"], src, q, "partial: caveat", HallucinationType.OVERCLAIM, reason=partial["left_out"]))
        weak = t["weak"]
        out.append(_sample(f"cases-weak-{tid}", tid, weak["answer"], weak["sources"], q, f"weak: {weak['kind']}", HallucinationType.WEAK_EVIDENCE))
        out.append(_sample(f"cases-weakcontrol-{tid}", tid, weak["honest"], weak["sources"], q, "weak control", grounded=True))
    for a in spec["agents"]:
        faithful = _numbered(a["steps"] + a["faithful"])
        wrong = _numbered(a["steps"] + a["hallucinated"])
        clean_wrong = [{**s, "content": unmark(s["content"])[0]} for s in wrong]
        out.append(_sample(f"cases-agentcontrol-{a['id']}", a["id"], faithful[-1]["content"], [], a["question"], "agent control", steps=faithful, grounded=True))
        out.append(_sample(
            f"cases-agent-{a['id']}", a["id"], wrong[-1]["content"], [], a["question"], f"agent: {a['kind']}",
            HallucinationType.AGENT_INTRODUCED, steps=clean_wrong, responsible=a["responsible"],
        ))
    return out


def load(path: Path) -> list[Sample]:
    return build(json.loads(path.read_text(encoding="utf-8")))


def case_of(sample: Sample) -> str:
    """mixed, unsupported, partial, weak, agent, or the control kind: control, weakcontrol, agentcontrol."""
    return sample.id.split("-")[1]
