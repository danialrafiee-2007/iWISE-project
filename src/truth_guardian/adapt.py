"""Teach the guardian a new domain from a few labelled answers.

The model, its probabilities and its conformal guarantees were calibrated on RAGTruth; on other data (HaluEval)
the guarantees break and a risk of 0.3 no longer means a 30% chance (D-086, D-087). Given the model's risks for a
few dozen labelled answers from the new domain, a profile:
- recomputes the split-conformal catch and false-alarm thresholds on those answers alone, valid for later answers
  from the same domain;
- recalibrates the risk with Platt scaling on its logit, so the probability and the grade match how often the
  domain's answers are really hallucinated.
The model's ranking of answers (AUROC) is untouched; only thresholds and probabilities move.
"""

import json
import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.linear_model import LogisticRegression

from truth_guardian import conformal

EPSILON = 1e-4


def _logit(risks) -> np.ndarray:
    r = np.clip(np.asarray(risks, dtype=float), EPSILON, 1 - EPSILON)
    return np.log(r / (1 - r))


class DomainProfile(BaseModel):
    model_config = ConfigDict(ser_json_inf_nan="constants")

    name: str
    model_version: str
    examples: int
    hallucinated: int
    grounded: int
    thresholds: list[conformal.Thresholds]
    platt: tuple[float, float] | None = None

    def calibrated(self, risk: float) -> float:
        """The risk as this domain's probability of a hallucination (unchanged without both labels present)."""
        if self.platt is None:
            return risk
        a, b = self.platt
        return float(1 / (1 + math.exp(-(a * _logit([risk])[0] + b))))

    def calibration(self) -> conformal.Calibration:
        return conformal.Calibration(model_version=self.model_version, data=f"domain {self.name}", pooled=self.thresholds, by_task={})

    def save(self, path: Path) -> Path:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        return path


def fit(name: str, risks, labels, model_version: str, alphas=conformal.ALPHAS) -> DomainProfile:
    """labels: 1 for hallucinated, 0 for grounded; risks are the model's answer-level risks."""
    risks, labels = np.asarray(risks, dtype=float), np.asarray(labels, dtype=int)
    platt = None
    if len(set(labels.tolist())) == 2:
        fitted = LogisticRegression(C=1.0).fit(_logit(risks).reshape(-1, 1), labels)
        platt = (float(fitted.coef_[0][0]), float(fitted.intercept_[0]))
    return DomainProfile(
        name=name, model_version=model_version, examples=len(labels), hallucinated=int(labels.sum()), grounded=int((labels == 0).sum()),
        thresholds=conformal.calibrate(risks, labels, alphas), platt=platt,
    )


def load(path: Path, model_version: str) -> DomainProfile | None:
    profile = DomainProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return profile if profile.model_version == model_version else None
