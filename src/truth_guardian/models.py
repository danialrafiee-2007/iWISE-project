"""Shared pretrained models, loaded lazily on CPU from the Hugging Face cache."""

import os
from functools import lru_cache

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"
NLI_LABELS = ("contradiction", "entailment", "neutral")


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _nli():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(NLI_MODEL, device="cpu")


def encode(texts: list[str]) -> np.ndarray:
    """Unit-length sentence embeddings, shape (len(texts), dim)."""
    return _embedder().encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)


def canonical_columns(id2label: dict[int, str]) -> list[int]:
    """Model output columns reordered to NLI_LABELS, so any NLI model can be swapped in."""
    index = {label.lower(): i for i, label in id2label.items()}
    return [index[label] for label in NLI_LABELS]


def nli_probabilities(pairs: list[tuple[str, str]]) -> np.ndarray:
    """(premise, hypothesis) pairs to probabilities with columns in NLI_LABELS order."""
    model = _nli()
    probs = model.predict(pairs, batch_size=16, apply_softmax=True, convert_to_numpy=True)
    return probs[:, canonical_columns(model.config.id2label)]
