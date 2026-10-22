"""Self-healing: turn a report's findings into a corrected answer, then check the corrected answer again.

Each round handles the flagged claims: apply their Fix-it replacements (a wrong number or name becomes the source's);
else replace a contradicted sentence with the source sentence it should have restated; else remove the unsupported
part, only the wrong clause when the error sits in a subordinate or coordinated clause. Contested claims stay, since
the sources disagree. When no claim is flagged but the answer is still not judged grounded, the answer-level risk is
spread over several sentences: the claim whose removal lowers that risk most (leave-one-out contribution of at least
MIN_CONTRIBUTION) is removed, at most a third of the original claims in all. Every round is checked again, for at most
MAX_ROUNDS rounds or until nothing is left to change.
"""

import re
from collections.abc import Callable
from typing import NamedTuple

from truth_guardian.report import ClaimReport, Report
from truth_guardian.schema import Sample

MAX_ROUNDS = 4
MIN_CONTRIBUTION = 0.05
MAX_ATTRIBUTED_SHARE = 1 / 3
_BARE_LINE = re.compile(r"^\W*(?:\d+[.)])?\W*$")
_TRAILING_LINK = re.compile(r"(?:,?\s*\b(?:and|but|or|while|whereas)\b|,)\s*$", re.IGNORECASE)


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


def _clause(c: ClaimReport) -> tuple[int, int] | None:
    """The single wrong clause inside the sentence, if it is not the sentence's main clause."""
    if len(c.focus) != 1 or c.focus[0][0] == c.start:
        return None
    return c.focus[0]


def _correct(c: ClaimReport, clauses: bool = True) -> list[Change]:
    fixes = [f for f in c.fixes if f.replacement]
    if fixes:
        return [Change(f.start, f.end, f.original, f.replacement, "replaced with the value in the sources") for f in fixes]
    if c.status == "contradicted" and c.evidence is not None:
        return [Change(c.start, c.end, c.text, c.evidence.text, "replaced with the source sentence it contradicts")]
    clause = _clause(c) if clauses else None
    if clause:
        a, b = clause
        return [Change(a, b, c.text[a - c.start : b - c.start], "", "removed the unsupported clause")]
    return [Change(c.start, c.end, c.text, "", "removed: the sources do not support it")]


def corrections(report: Report, clauses: bool = True) -> list[Change]:
    return [change for c in report.claims if c.status not in ("supported", "contested") for change in _correct(c, clauses)]


def attributed(report: Report, min_contribution: float = MIN_CONTRIBUTION) -> list[Change]:
    """The claim whose removal lowers the answer's risk most, when that is at least min_contribution."""
    candidates = [c for c in report.claims if c.status != "contested" and (c.contribution or 0.0) >= min_contribution]
    if not candidates:
        return []
    top = max(candidates, key=lambda c: c.contribution)
    return [Change(top.start, top.end, top.text, "", f"removed: it raised the answer's risk by {top.contribution:.2f}")]


def _splice(text: str, change: Change) -> str:
    """Replace a span; for a removal, also drop the comma pair or the conjunction it leaves behind."""
    before, after = text[: change.start], text[change.end :]
    if change.new:
        return before + change.new + after
    head, tail = before.rstrip(), after.lstrip()
    if head.endswith(",") and tail.startswith(","):
        return head[:-1] + " " + tail[1:].lstrip()
    if tail[:1] in {".", ",", ";", "!", "?"}:
        return _TRAILING_LINK.sub("", head) + tail
    return before + after


def apply(text: str, changes: list[Change]) -> str:
    """Apply non-overlapping changes from the end backwards, then drop list markers left bare and doubled spaces."""
    for change in sorted(changes, key=lambda c: -c.start):
        text = _splice(text, change)
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines()]
    kept = "\n".join(line for line in lines if not (line and _BARE_LINE.match(line)))
    return re.sub(r"\n{3,}", "\n\n", kept).strip()


def heal(
    sample: Sample,
    analyze: Callable[[Sample], Report],
    max_rounds: int = MAX_ROUNDS,
    attribute: bool = True,
    clauses: bool = True,
    min_contribution: float = MIN_CONTRIBUTION,
) -> Healing:
    """attribute and clauses switch off the attribution step and clause-level removal (for comparison)."""
    report = analyze(sample)
    reports, rounds, current = [report], [], sample
    budget = int(len(report.claims) * MAX_ATTRIBUTED_SHARE) if attribute else 0
    for _ in range(max_rounds):
        changes = corrections(report, clauses)
        if not changes and report.verdict != "grounded" and budget > 0:
            changes = attributed(report, min_contribution)
            budget -= len(changes)
        answer = apply(current.answer, changes) if changes else current.answer
        if not changes or not answer or answer == current.answer:
            break
        current = current.model_copy(update={"answer": answer})
        report = analyze(current)
        reports.append(report)
        rounds.append(changes)
    return Healing(current.answer, reports, rounds)
