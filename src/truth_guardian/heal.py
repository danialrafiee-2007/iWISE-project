"""Self-healing: turn a report's findings into a corrected answer, then check the corrected answer again.

For each flagged claim, in order: apply its Fix-it replacements (a wrong number or name becomes the source's); if it
contradicts the sources (a swapped role included), replace the sentence with the source sentence it should have
restated; otherwise (unsupported, insufficient evidence) remove it. Contested claims stay, since the sources disagree.
The corrected answer is analyzed again, for at most MAX_ROUNDS rounds or until nothing is left to change.
"""

import re
from collections.abc import Callable
from typing import NamedTuple

from truth_guardian.report import Report
from truth_guardian.schema import Sample

MAX_ROUNDS = 2
_BARE_LINE = re.compile(r"^\W*(?:\d+[.)])?\W*$")


class Change(NamedTuple):
    start: int
    end: int
    original: str
    new: str
    reason: str


class Healing(NamedTuple):
    answer: str
    reports: list[Report]
    changes: list[list[Change]]


def corrections(report: Report) -> list[Change]:
    changes = []
    for c in report.claims:
        if c.status in ("supported", "contested"):
            continue
        fixes = [f for f in c.fixes if f.replacement]
        if fixes:
            changes += [Change(f.start, f.end, f.original, f.replacement, "replaced with the value in the sources") for f in fixes]
        elif c.status == "contradicted" and c.evidence is not None:
            changes.append(Change(c.start, c.end, c.text, c.evidence.text, "replaced with the source sentence it contradicts"))
        else:
            changes.append(Change(c.start, c.end, c.text, "", "removed: the sources do not support it"))
    return changes


def apply(text: str, changes: list[Change]) -> str:
    """Apply non-overlapping changes from the end backwards, then drop list markers left bare and doubled spaces."""
    for change in sorted(changes, key=lambda c: -c.start):
        text = text[: change.start] + change.new + text[change.end :]
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines()]
    kept = "\n".join(line for line in lines if not (line and _BARE_LINE.match(line)))
    return re.sub(r"\n{3,}", "\n\n", kept).strip()


def heal(sample: Sample, analyze: Callable[[Sample], Report], max_rounds: int = MAX_ROUNDS) -> Healing:
    report = analyze(sample)
    reports, rounds, current = [report], [], sample
    for _ in range(max_rounds):
        changes = corrections(report)
        answer = apply(current.answer, changes) if changes else current.answer
        if not changes or not answer or answer == current.answer:
            break
        current = current.model_copy(update={"answer": answer})
        report = analyze(current)
        reports.append(report)
        rounds.append(changes)
    return Healing(current.answer, reports, rounds)
