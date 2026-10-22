"""Triage: which answers can go out unchecked, which need a person, which should be blocked.

Two risk thresholds split answers into three lanes, each edge with its own guarantee for later answers like the
calibration ones:
- pass: the largest group of lowest-risk answers in which, with CONFIDENCE, at most PASS_ERROR are hallucinated.
  Lane sizes grow along a fixed grid (from the first with MIN_LANE answers), each tested with an exact
  Clopper-Pearson bound, and the first size that fails stops the search (fixed-sequence learn-then-test).
- block: risk above the split-conformal false-alarm threshold at BLOCK_FALSE_ALARM, so at most that share of
  grounded answers is ever blocked (conformal.py). A precision target for the block lane was not reachable: the
  highest-risk 5% of RAGTruth dev answers are hallucinated about 88% of the time, too few for a 90%-confidence bound.
- review: everything between.
scripts/evaluate_triage.py checks both on held-out answers.
"""

import json
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel
from scipy.stats import beta

from truth_guardian.conformal import alarm_threshold

PASS_ERROR = 0.1
BLOCK_FALSE_ALARM = 0.05
CONFIDENCE = 0.9
LANE_SHARES = tuple(round(x, 2) for x in np.arange(0.05, 0.75, 0.05))
MIN_LANE = 50
FILE = "triage.json"
Lane = Literal["pass", "review", "block"]


class Policy(BaseModel):
    model_version: str
    data: str
    pass_below: float
    block_from: float
    pass_error: float = PASS_ERROR
    block_false_alarm: float = BLOCK_FALSE_ALARM
    confidence: float = CONFIDENCE

    def lane(self, risk: float) -> Lane:
        if risk < self.pass_below:
            return "pass"
        return "block" if risk >= self.block_from else "review"

    def save(self, folder: Path) -> Path:
        path = folder / FILE
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        return path


def thresholds(risks, labels, pass_error: float = PASS_ERROR, block_false_alarm: float = BLOCK_FALSE_ALARM, confidence: float = CONFIDENCE) -> tuple[float, float]:
    """(pass_below, block_from) from labelled calibration answers; labels: 1 hallucinated, 0 grounded."""
    risks, labels = np.asarray(risks, dtype=float), np.asarray(labels, dtype=int)
    order = np.argsort(risks)
    low_to_high, labels_sorted = risks[order], labels[order]
    sizes = [n for n in (int(share * len(labels)) for share in LANE_SHARES) if MIN_LANE <= n < len(labels)]
    delta = 1 - confidence
    pass_below = float(low_to_high[0])
    for n in sizes:
        errors = int(labels_sorted[:n].sum())
        if (beta.ppf(1 - delta, errors + 1, n - errors) if errors < n else 1.0) > pass_error:
            break
        pass_below = float(low_to_high[n])
    block_from = float(np.nextafter(alarm_threshold(risks[labels == 0], block_false_alarm), np.inf))
    return pass_below, max(block_from, pass_below)


def fit(risks, labels, model_version: str, data: str) -> Policy:
    pass_below, block_from = thresholds(risks, labels)
    return Policy(model_version=model_version, data=data, pass_below=pass_below, block_from=block_from)


def load(folder: Path, model_version: str) -> Policy | None:
    path = folder / FILE
    if not path.exists():
        return None
    policy = Policy.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return policy if policy.model_version == model_version else None


def workload(risks, labels, policy: Policy) -> dict:
    """Share of answers per lane, hallucinations among passed answers and precision among blocked ones."""
    risks, labels = np.asarray(risks, dtype=float), np.asarray(labels, dtype=int)
    lanes = np.array([policy.lane(r) for r in risks])
    passed, blocked = labels[lanes == "pass"], labels[lanes == "block"]
    return {
        "pass": float(np.mean(lanes == "pass")),
        "review": float(np.mean(lanes == "review")),
        "block": float(np.mean(lanes == "block")),
        "hallucinated_among_passed": float(passed.mean()) if len(passed) else None,
        "hallucinated_among_blocked": float(blocked.mean()) if len(blocked) else None,
        "grounded_blocked": float(np.mean(lanes[labels == 0] == "block")) if (labels == 0).any() else None,
        "hallucinations_caught": float(np.mean(lanes[labels == 1] != "pass")) if labels.sum() else None,
    }
