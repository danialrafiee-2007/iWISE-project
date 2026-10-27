"""Multilingual retrieval (intfloat/multilingual-e5-small) and NLI (MoritzLaurer/mDeBERTa-v3-base-mnli-xnli), local only.

Not part of the fusion model yet: they can rank passages and judge a claim against one in any language they cover, but
HHEM, the spaCy rules and the fusion model stay English, and each new language needs labelled examples and its own
calibration before its numbers mean anything. E5 needs its "query: " and "passage: " prefixes in every language. The NLI
labels are read by name from the model's config (this model orders them entailment, neutral, contradiction; the English
model the app uses orders them differently), and a long premise is read in overlapping windows instead of being cut
silently at 512 tokens, which could drop the very sentence that matters.
"""

import threading

from truth_guardian.media import models_dir

E5 = "multilingual-e5-small"
NLI = "mdeberta-v3-base-mnli-xnli"
MAX_TOKENS = 512
WINDOW, STRIDE = 400, 200  # premise tokens per window, and how far each window moves
THREADS = 4

_lock = threading.Lock()
_e5 = None
_nli = None


def e5():
    global _e5
    with _lock:
        if _e5 is None:
            from sentence_transformers import SentenceTransformer

            _e5 = SentenceTransformer(str(models_dir() / E5), device="cpu", local_files_only=True)
        return _e5


def nli():
    global _nli
    with _lock:
        if _nli is None:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            torch.set_num_threads(THREADS)
            path = str(models_dir() / NLI)
            tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).float().eval()
            _nli = (tokenizer, model, {i: label.lower() for i, label in model.config.id2label.items()})
        return _nli


def unload() -> None:
    global _e5, _nli
    with _lock:
        _e5 = _nli = None


def embed(texts: list[str], kind: str) -> "object":
    """Unit-length vectors; kind is "query" or "passage" and becomes E5's prefix."""
    if kind not in ("query", "passage"):
        raise ValueError("kind must be 'query' or 'passage'")
    return e5().encode([f"{kind}: {t}" for t in texts], normalize_embeddings=True, convert_to_numpy=True)


def rank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    """Passage indexes by cosine similarity to the query, best first."""
    q = embed([query], "query")[0]
    p = embed(passages, "passage")
    scores = p @ q
    return sorted(((i, round(float(s), 4)) for i, s in enumerate(scores)), key=lambda t: t[1], reverse=True)


def windows(premise_ids: list[int]) -> list[list[int]]:
    if len(premise_ids) <= WINDOW:
        return [premise_ids]
    out, start = [], 0
    while start < len(premise_ids):
        out.append(premise_ids[start : start + WINDOW])
        if start + WINDOW >= len(premise_ids):
            break
        start += STRIDE
    return out


def judge(premise: str, hypothesis: str) -> dict:
    """Entailment, neutral and contradiction probabilities for the hypothesis given the premise. A long premise is read
    window by window; the window with the strongest entailment or contradiction speaks, and its index is returned."""
    import torch

    tokenizer, model, labels = nli()
    ids = tokenizer(premise, add_special_tokens=False)["input_ids"]
    best, best_window = None, 0
    for i, chunk in enumerate(windows(ids)):
        batch = tokenizer(tokenizer.decode(chunk), hypothesis, return_tensors="pt", truncation="only_first", max_length=MAX_TOKENS)
        with torch.inference_mode():
            probs = model(**batch).logits.softmax(-1)[0].tolist()
        scores = {labels[k]: round(p, 4) for k, p in enumerate(probs)}
        strength = max(scores.get("entailment", 0), scores.get("contradiction", 0))
        if best is None or strength > max(best.get("entailment", 0), best.get("contradiction", 0)):
            best, best_window = scores, i
    return {**best, "label": max(("entailment", "neutral", "contradiction"), key=lambda k: best.get(k, 0)), "window": best_window, "windows": len(windows(ids))}
