"""Teach the guardian a new domain from a few labelled answers.

The model, its probabilities and its conformal guarantees were calibrated on RAGTruth; on other data (HaluEval)
the guarantees break and a risk of 0.3 no longer means a 30% chance (D-086, D-087). Given the model's risks for a
few dozen labelled answers from the new domain, a profile:
- recomputes the split-conformal catch and false-alarm thresholds on those answers alone, valid for later answers
  from the same domain;
- recalibrates the risk with Platt scaling on its logit, so the probability and the grade match how often the
  domain's answers are really hallucinated;
- when the answers' signals are given, also re-weights the model's risk and three evidence signals averaged over the
  answer's sentences (word overlap, embedding similarity, HHEM consistency) with a regularised logistic regression,
  since a new domain can trust the signals differently. The inputs are length-free on purpose: on HaluEval the
  answer length alone separates the labels (D-113), and a profile must not learn that shortcut. The conformal thresholds are
  then set on out-of-fold scores of the labelled answers, and the domain's verdict line is a probability of 0.5.
The thresholds are always on the scale of the domain's risk, so the report compares that risk with them.
"""

import json
import math
import random
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from truth_guardian import conformal

EPSILON = 1e-4
FEATURES = ("model_risk_logit", "lex_unsupported_mean", "dense_max_mean", "hhem_consistency_mean")
REGULARISATION = 0.3
FOLDS = 5
DECISION = 0.5
SHIPPED_LABELLED = 50


def _logit(risks) -> np.ndarray:
    r = np.clip(np.asarray(risks, dtype=float), EPSILON, 1 - EPSILON)
    return np.log(r / (1 - r))


def labelled_choice(n: int, domain: str, k: int = SHIPPED_LABELLED) -> list[int]:
    """Which of a domain's n external-dev answers the shipped profile was fitted on (fixed by the domain's name)."""
    return sorted(random.Random(f"profile-{domain}-v1").sample(range(n), k))


def domain_features(risk: float, rows: list[dict]) -> list[float]:
    """The model's risk as a logit and the mean of three evidence signals over the answer's sentence rows."""
    mean = lambda key, empty: float(np.mean([r[key] for r in rows if key in r])) if any(key in r for r in rows) else empty
    return [float(_logit([risk])[0]), mean("lex_unsupported", 1.0), mean("dense_max", 0.0), mean("hhem_consistency", 0.0)]


class Ranking(BaseModel):
    """Standardised logistic regression over FEATURES, fitted on one domain's labelled answers."""

    features: list[str]
    mean: list[float]
    scale: list[float]
    coef: list[float]
    intercept: float

    def probability(self, x: list[float]) -> float:
        z = sum(c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.mean, self.scale)) + self.intercept
        return float(1 / (1 + math.exp(-z)))


def _ranking(x: np.ndarray, y: np.ndarray) -> Ranking:
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 0, scale, 1.0)
    fitted = LogisticRegression(C=REGULARISATION, max_iter=1000).fit((x - mean) / scale, y)
    return Ranking(features=list(FEATURES), mean=mean.tolist(), scale=scale.tolist(), coef=fitted.coef_[0].tolist(), intercept=float(fitted.intercept_[0]))


def _out_of_fold(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    folds = min(FOLDS, int(np.bincount(y).min()))
    scores = np.zeros(len(y))
    for train, test in StratifiedKFold(n_splits=folds, shuffle=True, random_state=0).split(x, y):
        model = _ranking(x[train], y[train])
        scores[test] = [model.probability(row.tolist()) for row in x[test]]
    return scores


class DomainProfile(BaseModel):
    model_config = ConfigDict(ser_json_inf_nan="constants")

    name: str
    model_version: str
    examples: int
    hallucinated: int
    grounded: int
    thresholds: list[conformal.Thresholds]
    platt: tuple[float, float] | None = None
    ranking: Ranking | None = None
    decision: float = DECISION

    def domain_risk(self, risk: float, features: list[float] | None = None) -> float:
        """The domain's probability that the answer is hallucinated: re-weighted when the profile has a ranking."""
        if self.ranking is not None and features is not None:
            return self.ranking.probability(features)
        return self.calibrated(risk)

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


def fit(name: str, risks, labels, model_version: str, alphas=conformal.ALPHAS, features=None) -> DomainProfile:
    """labels: 1 for hallucinated, 0 for grounded; risks are the model's answer-level risks; features (optional) the
    domain_features of each answer, which adds the re-weighting when both labels have at least two answers."""
    risks, labels = np.asarray(risks, dtype=float), np.asarray(labels, dtype=int)
    platt = ranking = None
    scores = risks
    if len(set(labels.tolist())) == 2:
        fitted = LogisticRegression(C=1.0).fit(_logit(risks).reshape(-1, 1), labels)
        if fitted.coef_[0][0] > 0:
            platt = (float(fitted.coef_[0][0]), float(fitted.intercept_[0]))
            scores = 1 / (1 + np.exp(-(platt[0] * _logit(risks) + platt[1])))
        if features is not None and np.bincount(labels).min() >= 2:
            x = np.asarray(features, dtype=float)
            ranking, scores = _ranking(x, labels), _out_of_fold(x, labels)
    return DomainProfile(
        name=name, model_version=model_version, examples=len(labels), hallucinated=int(labels.sum()), grounded=int((labels == 0).sum()),
        thresholds=conformal.calibrate(scores, labels, alphas), platt=platt, ranking=ranking,
    )


def load(path: Path, model_version: str) -> DomainProfile | None:
    profile = DomainProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return profile if profile.model_version == model_version else None
