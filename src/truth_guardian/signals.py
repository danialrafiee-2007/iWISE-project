"""Per-sentence signals for the fusion model. Each signal returns one dict per answer sentence.

Bump a signal's version whenever its output could change, so cached features are rebuilt.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from truth_guardian import models
from truth_guardian.baselines.lexical import sentence_score
from truth_guardian.evidence import evidence_for
from truth_guardian.retrieval import Bm25, retrieve
from truth_guardian.schema import Sample
from truth_guardian.symbolic import check_sample
from truth_guardian.text import Sentence, content_words

PREMISE_SENTENCES = 5

_bm25_cache: dict[tuple, Bm25] = {}


def premises(sample: Sample, sentences: list[Sentence]) -> list[str]:
    """Hybrid-retrieved evidence (BM25 + embeddings, top 5 source sentences) for each answer sentence."""
    evidence = evidence_for(sample, models.encode)
    if not evidence.sentences:
        return ["" for _ in sentences]
    key = tuple(evidence.sentences)
    bm25 = _bm25_cache.setdefault(key, Bm25(evidence.sentences))
    embeddings = models.encode([s.text for s in sentences])
    return [
        " ".join(evidence.sentences[i] for i in retrieve(s.text, e, evidence, bm25, PREMISE_SENTENCES))
        for s, e in zip(sentences, embeddings)
    ]


def lexical(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    context = content_words(" ".join([sample.question or "", *(d.text for d in sample.documents)]))
    return [{"lex_unsupported": sentence_score(s.text, context)} for s in sentences]


def dense(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    evidence = evidence_for(sample, models.encode)
    if not evidence.sentences:
        return [{"dense_max": 0.0} for _ in sentences]
    similarities = models.encode([s.text for s in sentences]) @ evidence.embeddings.T
    return [{"dense_max": float(v)} for v in similarities.max(axis=1)]


def symbolic(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    return [
        {
            "sym_numbers": c.numbers,
            "sym_numbers_unmatched": c.numbers_unmatched,
            "sym_entities": c.entities,
            "sym_entities_unmatched": c.entities_unmatched,
            "sym_null_mentions": c.null_mentions,
            "sym_spans": [list(span) for span in c.spans],
        }
        for c in check_sample(sample, sentences)
    ]


def _nli_rows(sample: Sample, sentences: list[Sentence], model_name: str, prefix: str) -> list[dict]:
    pairs = list(zip(premises(sample, sentences), (s.text for s in sentences)))
    probs = models.nli_probabilities(pairs, model_name) if pairs else np.zeros((0, 3))
    return [{f"{prefix}_{label}": float(p) for label, p in zip(models.NLI_LABELS, row)} for row in probs]


def nli(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    return _nli_rows(sample, sentences, models.NLI_MODEL, "nli")


def nli_large(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    return _nli_rows(sample, sentences, models.NLI_LARGE_MODEL, "nlil")


def hhem(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    pairs = list(zip(premises(sample, sentences), (s.text for s in sentences)))
    return [{"hhem_consistency": float(v)} for v in (models.hhem_consistency(pairs) if pairs else [])]


def polarity(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    from truth_guardian.polarity import check_sample as polarity_check

    return [
        {
            "pol_candidate": int(c.candidate),
            "pol_confirmed": int(c.confirmed),
            "pol_contradiction": c.contradiction if c.contradiction is not None else 0.0,
            "pol_spans": [list(s) for s in c.negation_spans + c.antonym_spans] if c.confirmed else [],
            "pol_evidence": c.evidence if c.confirmed else "",
        }
        for c in polarity_check(sample, sentences)
    ]


def shifts(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    from truth_guardian.shifts import check_sample as shift_check

    return [
        {
            "shift_kind": c.kind if c.confirmed else "",
            "shift_candidate": int(c.candidate),
            "shift_confirmed": int(c.confirmed),
            "shift_overrides": int(c.overrides),
            "shift_entailment": c.entailment if c.entailment is not None else 1.0,
            "shift_spans": [list(x) for x in c.spans] if c.confirmed else [],
            "shift_evidence": c.evidence if c.confirmed else "",
            "shift_detail": c.detail if c.confirmed else "",
        }
        for c in shift_check(sample, sentences)
    ]


def flips(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    from truth_guardian.flips import check_sample as flip_check

    return [
        {
            "flip_kind": c.kind if c.confirmed else "",
            "flip_confirmed": int(c.confirmed),
            "flip_original": c.original_entailment if c.original_entailment is not None else 0.0,
            "flip_flipped": c.flipped_entailment if c.flipped_entailment is not None else 0.0,
            "flip_spans": [list(x) for x in c.spans] if c.confirmed else [],
            "flip_detail": c.detail if c.confirmed else "",
        }
        for c in flip_check(sample, sentences, premises(sample, sentences))
    ]


def detector(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    """Token probabilities of the trained detector (detector.py), as absolute character ranges in the answer."""
    from truth_guardian.detector import shipped

    model = shipped()
    if model is None or not sentences:
        return [{"det_max": 0.0, "det_tokens": []} for _ in sentences]
    tokens = model.tokens(list(zip(premises(sample, sentences), (s.text for s in sentences))))
    return [
        {"det_max": max((p for *_, p in t), default=0.0), "det_tokens": [[s.start + a, s.start + b, round(p, 4)] for a, b, p in t]}
        for s, t in zip(sentences, tokens)
    ]


def _detector_version() -> str:
    """Keyed by the trained detector's weights, read directly (detector.py imports this module)."""
    weights = Path(__file__).resolve().parents[2] / "models" / "detector" / "full" / "model.safetensors"
    fingerprint = hashlib.sha256(weights.read_bytes()).hexdigest()[:12] if weights.exists() else "missing"
    return f"v1:{fingerprint}:top{PREMISE_SENTENCES}"


def _flip_version() -> str:
    from truth_guardian.flips import ACTIVE, MAX_FLIPS, MIN_FLIPPED_ENTAILMENT, MIN_GAIN

    return f"v1:wordnet3.0:{models.NLI_MODEL}:top{PREMISE_SENTENCES}:max{MAX_FLIPS}:" + ":".join(f"{k}{MIN_FLIPPED_ENTAILMENT[k]}-{MIN_GAIN[k]}" for k in ACTIVE)


def _shift_version() -> str:
    from truth_guardian.shifts import CONFIRM_ENTAILMENT, QUANTIFIER_OVERLAP

    return f"v3:wordnet3.0:{models.NLI_MODEL}:" + ":".join(f"{k}{v}" for k, v in CONFIRM_ENTAILMENT.items()) + f":qoverlap{QUANTIFIER_OVERLAP}"


def spans_per_sentence(spans: list[dict], sentences: list[Sentence]) -> list[dict]:
    """Share of each sentence covered by predicted spans, and the highest span confidence touching it."""
    rows = []
    for s in sentences:
        covered = {i for sp in spans for i in range(max(sp["start"], s.start), min(sp["end"], s.end))}
        touching = [sp["confidence"] for sp in spans if sp["start"] < s.end and s.start < sp["end"]]
        rows.append({"cover": len(covered) / max(s.end - s.start, 1), "max_confidence": max(touching, default=0.0)})
    return rows


def lettuce(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    question = sample.question if sample.meta.task in {"qa", "dialogue"} else None
    spans = models.lettuce_spans([d.text for d in sample.documents], question, sample.answer)
    return [
        {"lettuce_cover": r["cover"], "lettuce_max": r["max_confidence"]}
        for r in spans_per_sentence(spans, sentences)
    ]


SIGNALS: dict[str, tuple[str, Callable]] = {
    "lexical": ("v1", lexical),
    "dense": (f"v1:{models.EMBEDDING_MODEL}", dense),
    "symbolic": ("v2", symbolic),
    "nli": (f"v1:{models.NLI_MODEL}:hybrid-top{PREMISE_SENTENCES}", nli),
    "nli_large": (f"v1:{models.NLI_LARGE_MODEL}:hybrid-top{PREMISE_SENTENCES}", nli_large),
    "hhem": (f"v1:{models.HHEM_REVISION[:8]}:hybrid-top{PREMISE_SENTENCES}", hhem),
    "lettuce": (f"v1:{models.LETTUCE_MODEL}", lettuce),
    "polarity": (f"v2:wordnet3.0:{models.NLI_MODEL}:overlap0.65:ratio2.5:confirm0.8", polarity),
    "shifts": (_shift_version(), shifts),
    "flips": (_flip_version(), flips),
    "detector": (_detector_version(), detector),
}
