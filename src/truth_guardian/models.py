"""Shared pretrained models, loaded lazily on CPU from the Hugging Face cache.

Outputs are memoised per input (sentence or sentence pair), so re-checking an edited answer only computes what changed.
"""

import os
from collections import OrderedDict
from functools import lru_cache

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"
NLI_LARGE_MODEL = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
NLI_LABELS = ("contradiction", "entailment", "neutral")
HHEM_MODEL = "vectara/hallucination_evaluation_model"
HHEM_REVISION = "de9a5e6ba9ba49531a022dba17e35ffeb2a6fad8"
LETTUCE_MODEL = "KRLabsOrg/lettucedect-base-modernbert-en-v1"
CACHE_SIZE = 50_000

_memo: dict[str, OrderedDict] = {}


def _cached(name: str, keys: list, compute) -> np.ndarray:
    """Look inputs up in a bounded per-model cache and compute only the missing ones, in one batch."""
    if not keys:
        return compute(keys)
    cache = _memo.setdefault(name, OrderedDict())
    missing = list(dict.fromkeys(k for k in keys if k not in cache))
    if missing:
        cache.update(zip(missing, compute(missing)))
    values = np.array([cache[k] for k in keys])
    while len(cache) > CACHE_SIZE:
        cache.popitem(last=False)
    return values


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


@lru_cache(maxsize=2)
def _nli(name: str = NLI_MODEL):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(name, device="cpu")


@lru_cache(maxsize=1)
def _hhem():
    """HHEM runs its own model code from the Hub, pinned to a reviewed revision."""
    from transformers import AutoModelForSequenceClassification

    return AutoModelForSequenceClassification.from_pretrained(HHEM_MODEL, trust_remote_code=True, revision=HHEM_REVISION).eval()


@lru_cache(maxsize=1)
def _lettuce():
    from lettucedetect.models.inference import HallucinationDetector

    return HallucinationDetector(method="transformer", model_path=LETTUCE_MODEL, device="cpu")


def encode(texts: list[str]) -> np.ndarray:
    """Unit-length sentence embeddings, shape (len(texts), dim)."""
    return _cached("encode", list(texts), lambda batch: _embedder().encode(batch, batch_size=64, normalize_embeddings=True, convert_to_numpy=True))


def canonical_columns(id2label: dict[int, str]) -> list[int]:
    """Model output columns reordered to NLI_LABELS, so any NLI model can be swapped in."""
    index = {label.lower(): i for i, label in id2label.items()}
    return [index[label] for label in NLI_LABELS]


def nli_probabilities(pairs: list[tuple[str, str]], model_name: str = NLI_MODEL) -> np.ndarray:
    """(premise, hypothesis) pairs to probabilities with columns in NLI_LABELS order."""

    def compute(batch):
        model = _nli(model_name)
        probs = model.predict(batch, batch_size=16, apply_softmax=True, convert_to_numpy=True)
        return probs[:, canonical_columns(model.config.id2label)]

    return _cached(f"nli:{model_name}", [tuple(p) for p in pairs], compute)


def hhem_consistency(pairs: list[tuple[str, str]]) -> np.ndarray:
    """(premise, hypothesis) pairs to HHEM consistency scores in [0, 1] (1 = consistent)."""
    return _cached("hhem", [tuple(p) for p in pairs], lambda batch: _hhem().predict(batch).numpy())


def lettuce_spans(context: list[str], question: str | None, answer: str) -> list[dict]:
    """Hallucinated character spans in the answer, each with start, end and confidence."""
    return _lettuce().predict(context=context, question=question, answer=answer, output_format="spans")
