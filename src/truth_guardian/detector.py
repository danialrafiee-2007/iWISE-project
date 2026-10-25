"""Token-level hallucination detector, fine-tuned on RAGTruth train and on attacks built from train answers.

Each answer sentence is paired with the evidence retrieved for it (signals.premises), and every sentence token gets
the probability that it lies in a hallucinated span; a sentence scores its highest token probability. The backbone,
MiniLM-L6 (22M parameters), is small enough to fine-tune on the laptop CPU. Attacks use only the structural edit
kinds (number, entity, negation, swapped roles, added claim); the kinds built from fixed word lists (opposite words,
quantifiers, hedges) are left out, so the Fool-the-Guardian suite still measures transfer to them. Training saves a
checkpoint every few hundred steps and resumes from it.
"""

import hashlib
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import numpy as np
import torch

from truth_guardian.schema import Sample
from truth_guardian.signals import premises
from truth_guardian.text import split_sentences

SHIPPED = Path(__file__).resolve().parents[2] / "models" / "detector" / "full"
BACKBONE = "sentence-transformers/all-MiniLM-L6-v2"
MAX_LENGTH = 256
ATTACK_KINDS = ("number", "entity", "negation", "role_swap", "addition")
POSITIVE_WEIGHT = 3.0
SPAN_THRESHOLD = 0.5
WORD_THRESHOLD = 0.25


class Example(NamedTuple):
    premise: str
    sentence: str
    spans: list[tuple[int, int]]
    origin: str


def examples(sample: Sample, origin: str = "natural") -> list[Example]:
    """One example per answer sentence; spans are the gold hallucinated ranges inside it, relative to the sentence."""
    sentences = split_sentences(sample.answer)
    gold = [(sp.start, sp.end) for sp in sample.labels.spans] if sample.labels else []
    out = []
    for s, premise in zip(sentences, premises(sample, sentences)):
        spans = [(max(a, s.start) - s.start, min(b, s.end) - s.start) for a, b in gold if a < s.end and s.start < b]
        out.append(Example(premise, s.text, spans, origin))
    return out


def _encode(tokenizer, premises_, sentences_):
    return tokenizer(premises_, sentences_, truncation="longest_first", max_length=MAX_LENGTH, padding=True, return_offsets_mapping=True, return_tensors="pt")


def _batch(tokenizer, batch: list[Example]) -> dict:
    """Inputs plus labels for the sentence's tokens (premise and special tokens are ignored)."""
    enc = _encode(tokenizer, [e.premise for e in batch], [e.sentence for e in batch])
    labels = torch.full(enc["input_ids"].shape, -100)
    for i, e in enumerate(batch):
        for j, (part, (a, b)) in enumerate(zip(enc.sequence_ids(i), enc["offset_mapping"][i].tolist())):
            if part == 1 and b > a:
                labels[i, j] = int(any(a < y and x < b for x, y in e.spans))
    enc.pop("offset_mapping")
    return {**enc, "labels": labels}


def train(data: list[Example], out_dir: Path, epochs: int = 2, batch_size: int = 16, lr: float = 5e-5, seed: int = 0,
          checkpoint_every: int = 200, log=print) -> Path:
    from transformers import AutoModelForTokenClassification, AutoTokenizer, get_linear_schedule_with_warmup

    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(BACKBONE)
    model = AutoModelForTokenClassification.from_pretrained(BACKBONE, num_labels=2)
    steps_per_epoch = math.ceil(len(data) / batch_size)
    total = epochs * steps_per_epoch
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * total), total)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor([1.0, POSITIVE_WEIGHT]), ignore_index=-100)
    checkpoint, done = out_dir / "checkpoint.pt", 0
    if checkpoint.exists():
        state = torch.load(checkpoint, weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        done = state["step"]
        log(f"resumed at step {done}/{total}")
    model.train()
    step, running = 0, []
    for epoch in range(epochs):
        order = list(range(len(data)))
        random.Random(f"{seed}:{epoch}").shuffle(order)
        for i in range(0, len(order), batch_size):
            step += 1
            if step <= done:
                continue
            batch = _batch(tokenizer, [data[j] for j in order[i : i + batch_size]])
            labels = batch.pop("labels")
            logits = model(**batch).logits
            loss = loss_fn(logits.view(-1, 2), labels.view(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            running.append(loss.item())
            if step % checkpoint_every == 0 or step == total:
                torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "step": step}, checkpoint)
                log(f"step {step}/{total} epoch {epoch + 1} loss {np.mean(running[-checkpoint_every:]):.4f}")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    checkpoint.unlink(missing_ok=True)
    return out_dir


@lru_cache(maxsize=1)
def shipped() -> "Detector | None":
    """The trained detector the app uses for exact words, if it is present."""
    return Detector(SHIPPED) if (SHIPPED / "model.safetensors").exists() else None


def fingerprint() -> str:
    path = SHIPPED / "model.safetensors"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else "missing"


def merged(tokens: list[tuple[int, int, float]], threshold: float) -> list[tuple[int, int]]:
    """Ranges of consecutive tokens at or above the threshold (gaps of one character, such as a space, are bridged)."""
    spans: list[tuple[int, int]] = []
    for a, b, p in tokens:
        if p < threshold:
            continue
        if spans and a - spans[-1][1] <= 1:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    return spans


class Detector:
    def __init__(self, path: Path, batch_size: int = 32):
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForTokenClassification.from_pretrained(path).eval()
        self.batch_size = batch_size

    def score(self, pairs: list[tuple[str, str]]) -> list[tuple[float, list[tuple[int, int]]]]:
        """Per (premise, sentence): highest token probability and the sentence's character ranges above SPAN_THRESHOLD."""
        return [(max((p for *_, p in tokens), default=0.0), merged(tokens, SPAN_THRESHOLD)) for tokens in self.tokens(pairs)]

    def tokens(self, pairs: list[tuple[str, str]]) -> list[list[tuple[int, int, float]]]:
        """Per (premise, sentence): (start, end, probability) of each sentence token, offsets within the sentence."""
        out = []
        for i in range(0, len(pairs), self.batch_size):
            chunk = pairs[i : i + self.batch_size]
            enc = _encode(self.tokenizer, [p for p, _ in chunk], [s for _, s in chunk])
            offsets = enc.pop("offset_mapping")
            with torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits, dim=-1)[:, :, 1]
            for k in range(len(chunk)):
                out.append([(a, b, float(p)) for part, (a, b), p in zip(enc.sequence_ids(k), offsets[k].tolist(), probs[k].tolist()) if part == 1 and b > a])
        return out
