"""Fine-tune the token-level detector on the laptop CPU (detector.py).

--pilot: about 2,500 RAGTruth train answers (whole source groups): every hallucinated sentence, twice as many clean
sentences, and one structural attack per grounded answer; two epochs. --full: the same recipe on every good-quality
train answer (2,264 source groups), one epoch by default. Resumes from its checkpoint if interrupted.
Output: models/detector/<name>/ and the training-set summary next to it.
"""

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from truth_guardian import detector
from truth_guardian.data.splits import sample_groups
from truth_guardian.perturb import entity_pool, perturb
from truth_guardian.schema import read_jsonl
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
PILOT_GROUPS = 420
ALL_GROUPS = 100_000
CLEAN_PER_HALLUCINATED = 2


def build(groups: int, seed: str) -> list[detector.Example]:
    train = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"]
    chosen = sample_groups(train, groups, seed=seed)
    rng = random.Random(seed)
    hallucinated, clean, attacks = [], [], []
    for s in chosen:
        for e in detector.examples(s):
            (hallucinated if e.spans else clean).append(e)
    pool = entity_pool(chosen)
    for s in chosen:
        if s.labels.response != "grounded":
            continue
        kind = rng.choice(detector.ATTACK_KINDS)
        edited = perturb(s, kind, random.Random(f"{seed}:{s.id}:{kind}"), pool)
        if edited is None:
            continue
        span = edited.labels.spans[0]
        sentence = next((x for x in split_sentences(edited.answer) if x.start <= span.start < x.end), None)
        if sentence is not None:
            attacks += [e._replace(origin=kind) for e in detector.examples(edited) if e.sentence == sentence.text and e.spans]
    clean = rng.sample(clean, min(len(clean), CLEAN_PER_HALLUCINATED * len(hallucinated)))
    data = hallucinated + clean + attacks
    rng.shuffle(data)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--epochs", type=int)
    args = parser.parse_args()
    name = "pilot" if args.pilot else "full"
    groups, seed, epochs = (PILOT_GROUPS, "tg-detector-pilot-v1", args.epochs or 2) if args.pilot else (ALL_GROUPS, "tg-detector-full-v1", args.epochs or 1)
    out = ROOT / "models" / "detector" / name
    data_file = out / "train_examples.jsonl"
    started = time.perf_counter()
    if data_file.exists():
        data = [detector.Example(**json.loads(line)) for line in data_file.read_text(encoding="utf-8").splitlines()]
    else:
        data = build(groups, seed)
        out.mkdir(parents=True, exist_ok=True)
        with data_file.open("w", encoding="utf-8", newline="\n") as f:
            for e in data:
                f.write(json.dumps(e._asdict(), ensure_ascii=False) + "\n")
    summary = {"examples": len(data), "by_origin": dict(Counter("hallucinated" if e.origin == "natural" and e.spans else e.origin if e.origin != "natural" else "clean" for e in data))}
    print(f"{name}: {summary} (built in {time.perf_counter() - started:.0f}s)", flush=True)
    summary["epochs"] = epochs
    detector.train(data, out, epochs=epochs, log=lambda m: print(m, flush=True))
    summary["train_seconds"] = time.perf_counter() - started
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    print(f"done in {summary['train_seconds'] / 60:.0f} min -> {out.relative_to(ROOT).as_posix()}", flush=True)


if __name__ == "__main__":
    main()
