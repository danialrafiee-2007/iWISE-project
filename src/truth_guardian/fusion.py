"""Fusion model: stacked sentence and response classifiers over cached signals, then calibrated.

Stage 1 predicts whether each sentence is hallucinated. Stage 2 predicts the response label from
aggregates of stage-1 probabilities and of the raw signals (not just the max, see D-034).
Stage-1 probabilities used to train stage 2, and stage-2 scores used to fit the calibrator, are
out-of-fold with folds grouped by source, so no stage learns from optimistic in-sample scores.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from truth_guardian.evaluation import Prediction, SentenceScore
from truth_guardian.labels import sentence_labels
from truth_guardian.schema import Sample
from truth_guardian.signals import SIGNALS
from truth_guardian.text import Sentence

SIGNAL_KEYS = {
    "lexical": ["lex_unsupported"],
    "dense": ["dense_max"],
    "symbolic": ["sym_numbers", "sym_numbers_unmatched", "sym_entities", "sym_entities_unmatched", "sym_null_mentions", "sym_spans"],
    "nli": ["nli_contradiction", "nli_entailment", "nli_neutral"],
    "nli_large": ["nlil_contradiction", "nlil_entailment", "nlil_neutral"],
    "hhem": ["hhem_consistency"],
    "lettuce": ["lettuce_cover", "lettuce_max"],
}
POSITION_FEATURES = ["position", "is_first", "sentence_words"]
STAGE1_SUMMARY = ["p_max", "p_mean", "p_top2", "p_std", "p_count", "p_fraction", "n_sentences"]


@dataclass
class SentenceTable:
    """All sentences of a set of samples, one row each, with features aligned across signals."""

    features: np.ndarray
    feature_names: list[str]
    sample_index: np.ndarray
    sentences: list[list[Sentence]]
    labels: np.ndarray | None = None


def _value(row: dict, key: str) -> float:
    value = row[key]
    return float(len(value)) if isinstance(value, list) else float(value)


def build_table(samples: Sequence[Sample], rows: dict[str, dict[str, list[dict]]], signals: Sequence[str]) -> SentenceTable:
    """rows[signal][sample_id] is the cached per-sentence output of that signal."""
    names = [k for s in signals for k in SIGNAL_KEYS[s]] + POSITION_FEATURES
    features, index, sentences, labels = [], [], [], []
    for i, sample in enumerate(samples):
        per_signal = [rows[s][sample.id] for s in signals]
        bounds = [(r["start"], r["end"]) for r in per_signal[0]]
        if any([(r["start"], r["end"]) for r in other] != bounds for other in per_signal[1:]):
            raise ValueError(f"signals disagree on sentence boundaries for {sample.id}")
        sents = [Sentence(a, b, sample.answer[a:b]) for a, b in bounds]
        sentences.append(sents)
        n = len(sents)
        for j, sent in enumerate(sents):
            row = [_value(per_signal[k][j], key) for k, s in enumerate(signals) for key in SIGNAL_KEYS[s]]
            row += [j / max(n - 1, 1), float(j == 0), float(len(sent.text.split()))]
            features.append(row)
            index.append(i)
        if sample.labels is not None:
            labels += sentence_labels(sample, sents)
    return SentenceTable(
        features=np.array(features, dtype=float).reshape(-1, len(names)),
        feature_names=names,
        sample_index=np.array(index, dtype=int),
        sentences=sentences,
        labels=np.array(labels, dtype=int) if len(labels) == len(index) else None,
    )


def response_features(probs: np.ndarray, table: SentenceTable) -> tuple[np.ndarray, list[str]]:
    """Per response: summaries of stage-1 probabilities plus max/mean/min of every raw sentence feature."""
    raw = table.features
    names = STAGE1_SUMMARY + [f"{stat}_{n}" for n in table.feature_names for stat in ("max", "mean", "min")]
    out = np.zeros((len(table.sentences), len(names)))
    for i in range(len(table.sentences)):
        mask = table.sample_index == i
        p = probs[mask]
        if len(p) == 0:
            continue
        top2 = np.sort(p)[-2:].mean()
        summary = [p.max(), p.mean(), top2, p.std(), (p >= 0.5).sum(), (p >= 0.5).mean(), len(p)]
        stats = np.stack([raw[mask].max(axis=0), raw[mask].mean(axis=0), raw[mask].min(axis=0)], axis=1).ravel()
        out[i] = np.concatenate([summary, stats])
    return out, names


def make_classifier(kind: str):
    if kind == "logreg":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    if kind == "hgb":
        return HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40,
            l2_regularization=1.0, early_stopping=False, random_state=0,
        )
    raise ValueError(f"unknown classifier kind: {kind}")


class PlattCalibrator:
    """Logistic fit on the logit of the raw score; keeps the ranking, so AUROC is unchanged."""

    def fit(self, scores: np.ndarray, y: np.ndarray) -> "PlattCalibrator":
        self.model = LogisticRegression().fit(self._logit(scores), y)
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(self._logit(scores))[:, 1]

    @staticmethod
    def _logit(scores: np.ndarray) -> np.ndarray:
        p = np.clip(scores, 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)


def group_folds(groups: Sequence[str], folds: int) -> dict[str, int]:
    """Deterministic fold per group, shared by both stages."""
    ranked = sorted(set(groups), key=lambda g: hashlib.sha256(g.encode()).hexdigest())
    return {g: i % folds for i, g in enumerate(ranked)}


@dataclass
class FusionModel:
    kind: str
    signals: list[str]
    signal_versions: dict[str, str]
    feature_names: list[str]
    response_feature_names: list[str]
    sentence_model: object
    response_model: object
    calibrator: PlattCalibrator
    thresholds: dict[str, float] = field(default_factory=dict)

    def score(self, table: SentenceTable) -> tuple[np.ndarray, np.ndarray]:
        """(sentence probabilities, calibrated response probabilities)."""
        sentence_probs = self.sentence_model.predict_proba(table.features)[:, 1]
        response, _ = response_features(sentence_probs, table)
        return sentence_probs, self.calibrator.predict(self.response_model.predict_proba(response)[:, 1])

    def predictions(self, samples: Sequence[Sample], table: SentenceTable) -> list[Prediction]:
        sentence_probs, response_probs = self.score(table)
        return [
            Prediction(
                id=sample.id,
                score=float(response_probs[i]),
                sentences=[
                    SentenceScore(start=s.start, end=s.end, score=float(p))
                    for s, p in zip(table.sentences[i], sentence_probs[table.sample_index == i])
                ],
            )
            for i, sample in enumerate(samples)
        ]


def fit(samples: Sequence[Sample], table: SentenceTable, signals: Sequence[str], kind: str, folds: int = 5) -> tuple[FusionModel, dict]:
    if table.labels is None:
        raise ValueError("training samples need labels")
    groups = [s.meta.group_id for s in samples]
    fold_of = group_folds(groups, folds)
    sample_fold = np.array([fold_of[g] for g in groups])
    sentence_fold = sample_fold[table.sample_index]
    y_response = np.array([s.labels.response == "hallucinated" for s in samples], dtype=int)

    oof_sentence = np.zeros(len(table.labels))
    for k in range(folds):
        train, test = sentence_fold != k, sentence_fold == k
        oof_sentence[test] = make_classifier(kind).fit(table.features[train], table.labels[train]).predict_proba(table.features[test])[:, 1]
    sentence_model = make_classifier(kind).fit(table.features, table.labels)

    response, response_names = response_features(oof_sentence, table)
    oof_response = np.zeros(len(samples))
    for k in range(folds):
        train, test = sample_fold != k, sample_fold == k
        oof_response[test] = make_classifier(kind).fit(response[train], y_response[train]).predict_proba(response[test])[:, 1]
    response_model = make_classifier(kind).fit(response, y_response)

    model = FusionModel(
        kind=kind,
        signals=list(signals),
        signal_versions={s: SIGNALS[s][0] for s in signals},
        feature_names=table.feature_names,
        response_feature_names=response_names,
        sentence_model=sentence_model,
        response_model=response_model,
        calibrator=PlattCalibrator().fit(oof_response, y_response),
    )
    report = {
        "oof_sentence_auroc": float(roc_auc_score(table.labels, oof_sentence)),
        "oof_response_auroc": float(roc_auc_score(y_response, oof_response)),
        "samples": len(samples),
        "groups": len(set(groups)),
        "sentences": int(len(table.labels)),
    }
    return model, report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(model: FusionModel, directory: str | Path, manifest: dict) -> Path:
    """Write models/<name>/<version>/{model.joblib, manifest.json} and point LATEST at it."""
    directory = Path(directory)
    out = directory / manifest["version"]
    out.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, out / "model.joblib")
    manifest = {**manifest, "model_sha256": _sha256(out / "model.joblib")}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    (directory / "LATEST").write_text(manifest["version"], encoding="utf-8")
    return out


def load(directory: str | Path, version: str = "latest") -> tuple[FusionModel, dict]:
    """Load a saved model after checking its checksum and that cached signals still match its versions.

    joblib files can run code when loaded, so only files written by `save` are trusted.
    """
    directory = Path(directory)
    if version == "latest":
        version = (directory / "LATEST").read_text(encoding="utf-8").strip()
    folder = directory / version
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if _sha256(folder / "model.joblib") != manifest["model_sha256"]:
        raise ValueError(f"{folder / 'model.joblib'} does not match its manifest checksum")
    model: FusionModel = joblib.load(folder / "model.joblib")
    stale = {s: v for s, v in model.signal_versions.items() if SIGNALS[s][0] != v}
    if stale:
        raise ValueError(f"model {version} was trained on older signal versions {stale}; retrain it")
    return model, manifest
