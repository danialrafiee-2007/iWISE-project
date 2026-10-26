"""Shared pretrained models, loaded lazily on CPU from the Hugging Face cache.

Outputs are memoised per input (sentence or sentence pair), so re-checking an edited answer only computes what changed.
HHEM, the slowest model, runs from an exact ONNX export when scripts/export_onnx.py has made one (1.8x faster on the
laptop CPU); TG_NO_ONNX=1 forces PyTorch.
"""

import hashlib
import json
import os
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# ONNX Runtime starts its usage telemetry when imported unless this is set; nothing here should report anywhere
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"
NLI_LARGE_MODEL = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
NLI_LABELS = ("contradiction", "entailment", "neutral")
HHEM_MODEL = "vectara/hallucination_evaluation_model"
HHEM_REVISION = "de9a5e6ba9ba49531a022dba17e35ffeb2a6fad8"
LETTUCE_MODEL = "KRLabsOrg/lettucedect-base-modernbert-en-v1"
# The live models load from these exact Hub commits, so every setup and image gets the files the results were made with
REVISIONS = {
    EMBEDDING_MODEL: "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    NLI_MODEL: "6c749ce3425cd33b46d187e45b92bbf96ee12ec7",
    HHEM_MODEL: HHEM_REVISION,
}
CACHE_SIZE = 50_000
HHEM_ONNX = Path(__file__).resolve().parents[2] / "models" / "onnx" / f"hhem-{HHEM_REVISION[:8]}.onnx"
HHEM_TOKENIZER = HHEM_ONNX.with_name(f"hhem-{HHEM_REVISION[:8]}-tokenizer")

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

    return SentenceTransformer(EMBEDDING_MODEL, device="cpu", revision=REVISIONS[EMBEDDING_MODEL])


@lru_cache(maxsize=2)
def _nli(name: str = NLI_MODEL):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(name, device="cpu", revision=REVISIONS.get(name))


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


@lru_cache(maxsize=1)
def _hhem_onnx():
    """(session, tokenizer, prompt) for the ONNX export, or None when absent, disabled or not matching its manifest."""
    manifest_path = HHEM_ONNX.with_suffix(".json")
    if os.environ.get("TG_NO_ONNX") or not HHEM_ONNX.exists() or not manifest_path.exists():
        return None
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("revision") != HHEM_REVISION or manifest.get("sha256") != hashlib.sha256(HHEM_ONNX.read_bytes()).hexdigest():
        return None
    from transformers import AutoTokenizer

    options = ort.SessionOptions()
    options.intra_op_num_threads = os.cpu_count() or 4
    session = ort.InferenceSession(str(HHEM_ONNX), options, providers=["CPUExecutionProvider"])
    tokenizer = AutoTokenizer.from_pretrained(HHEM_TOKENIZER if HHEM_TOKENIZER.exists() else manifest["foundation"])
    return session, tokenizer, manifest["prompt"]


def _hhem_scores(pairs: list[tuple[str, str]]) -> np.ndarray:
    """One pair at a time: padding a batch to its longest pair costs more than batching saves on a CPU."""
    onnx = _hhem_onnx()
    if onnx is None:
        import torch

        model = _hhem()
        with torch.no_grad():
            return np.array([model.predict([pair]).numpy()[0] for pair in pairs], dtype=float)
    session, tokenizer, prompt = onnx
    scores = []
    for premise, hypothesis in pairs:
        enc = tokenizer([prompt.format(text1=premise, text2=hypothesis)], return_tensors="np")
        feed = {"input_ids": enc["input_ids"].astype(np.int64), "attention_mask": enc["attention_mask"].astype(np.int64)}
        scores.append(session.run(None, feed)[0][0])
    return np.array(scores, dtype=float)


def hhem_consistency(pairs: list[tuple[str, str]]) -> np.ndarray:
    """(premise, hypothesis) pairs to HHEM consistency scores in [0, 1] (1 = consistent)."""
    return _cached("hhem", [tuple(p) for p in pairs], _hhem_scores)


def lettuce_spans(context: list[str], question: str | None, answer: str) -> list[dict]:
    """Hallucinated character spans in the answer, each with start, end and confidence."""
    return _lettuce().predict(context=context, question=question, answer=answer, output_format="spans")
