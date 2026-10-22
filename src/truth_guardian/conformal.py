"""Statistical guarantees for the alarm threshold (split conformal prediction).

From calibration answers with known labels, two thresholds per error rate alpha:
- catch guarantee: flag when risk >= t_catch, the floor(alpha (n+1))-th smallest risk among n hallucinated answers;
  a new hallucinated answer is then missed with probability at most alpha;
- false-alarm guarantee: flag when risk > t_alarm, the ceil((1 - alpha)(n+1))-th smallest risk among n grounded
  answers; a new grounded answer is then flagged with probability at most alpha.
Both hold on average over calibration sets, for answers exchangeable with the calibration data (same kind of task
and generator). Under distribution shift they can break; scripts/evaluate_conformal.py measures by how much.
Per-task (Mondrian) thresholds keep the guarantee within each task, not only on average over tasks.
"""

import json
import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

ALPHAS = (0.05, 0.1, 0.2)
FILE = "conformal.json"


def catch_threshold(hallucinated_risks, alpha: float) -> float:
    s = np.sort(np.asarray(hallucinated_risks, dtype=float))
    k = math.floor(alpha * (len(s) + 1))
    return float(s[k - 1]) if k >= 1 else -math.inf


def alarm_threshold(grounded_risks, alpha: float) -> float:
    s = np.sort(np.asarray(grounded_risks, dtype=float))
    j = math.ceil((1 - alpha) * (len(s) + 1))
    return float(s[j - 1]) if j <= len(s) else math.inf


class Thresholds(BaseModel):
    """Infinite thresholds (too few calibration answers for this alpha) are written as Infinity, not null."""

    model_config = ConfigDict(ser_json_inf_nan="constants")
    alpha: float
    catch: float
    alarm: float
    hallucinated: int
    grounded: int


def calibrate(risks, labels, alphas=ALPHAS) -> list[Thresholds]:
    """labels: 1 for hallucinated, 0 for grounded."""
    risks, labels = np.asarray(risks, dtype=float), np.asarray(labels, dtype=int)
    positives, negatives = risks[labels == 1], risks[labels == 0]
    return [
        Thresholds(alpha=a, catch=catch_threshold(positives, a), alarm=alarm_threshold(negatives, a), hallucinated=len(positives), grounded=len(negatives))
        for a in alphas
    ]


class Calibration(BaseModel):
    model_config = ConfigDict(ser_json_inf_nan="constants")
    model_version: str
    data: str
    pooled: list[Thresholds]
    by_task: dict[str, list[Thresholds]]

    def get(self, alpha: float, task: str | None = None) -> Thresholds:
        table = self.by_task.get(task or "", self.pooled)
        return next(t for t in table if math.isclose(t.alpha, alpha))

    def save(self, folder: Path) -> Path:
        path = folder / FILE
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        return path


def load(folder: Path, model_version: str) -> Calibration | None:
    """The calibration saved next to a model, or None if absent or made for another model version."""
    path = folder / FILE
    if not path.exists():
        return None
    calibration = Calibration.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return calibration if calibration.model_version == model_version else None
