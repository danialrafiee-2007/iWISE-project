"""Data story for the presentation: how often, how much and how each LLM hallucinates (RAGTruth train + dev).

The locked test set is not used. Output: eval/results/data_story.json
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from truth_guardian.schema import HallucinationType, read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def interval(values: list[int], groups: list[str], rounds: int = 1000, seed: int = 0) -> list[float]:
    """95% bootstrap interval of a rate, resampling whole source groups."""
    rng = np.random.default_rng(seed)
    by_group: dict[str, list[int]] = defaultdict(list)
    for v, g in zip(values, groups):
        by_group[g].append(v)
    members = list(by_group.values())
    rates = [np.mean(np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])) for _ in range(rounds)]
    return [float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))]


def main() -> None:
    samples = [s for name in ("train", "dev") for s in read_jsonl(ROOT / f"data/processed/ragtruth_{name}.jsonl") if s.meta.quality == "good"]
    story: dict = {"responses": len(samples), "generators": {}}
    for generator in sorted({s.meta.generator for s in samples}):
        subset = [s for s in samples if s.meta.generator == generator]
        flags = [int(s.labels.response == "hallucinated") for s in subset]
        spans = [sp for s in subset for sp in s.labels.spans]
        words = sum(len(s.answer.split()) for s in subset)
        hallucinated_words = sum(len(sp.text.split()) for sp in spans)
        story["generators"][generator] = {
            "responses": len(subset),
            "hallucination_rate": float(np.mean(flags)),
            "ci95": interval(flags, [s.meta.group_id for s in subset]),
            "by_task": {t: float(np.mean([f for f, s in zip(flags, subset) if s.meta.task == t])) for t in ("qa", "summary", "data2text")},
            "hallucinated_words_per_100": 100 * hallucinated_words / words,
            "contradiction_share": sum(sp.type == HallucinationType.CONTRADICTED for sp in spans) / max(len(spans), 1),
            "avg_answer_words": words / len(subset),
        }

    lengths = np.array([len(s.answer.split()) for s in samples])
    flags = np.array([s.labels.response == "hallucinated" for s in samples])
    edges = np.quantile(lengths, [0, 0.25, 0.5, 0.75, 1])
    story["rate_by_length_quartile"] = {
        f"{int(lo)}-{int(hi)} words": float(flags[(lengths >= lo) & (lengths <= hi)].mean()) for lo, hi in zip(edges[:-1], edges[1:])
    }

    out = ROOT / "eval" / "results" / "data_story.json"
    out.write_text(json.dumps(story, indent=2), encoding="utf-8", newline="\n")
    print(f"{'generator':22} {'rate':>6} {'95% CI':>15} {'qa':>6} {'summ':>6} {'d2t':>6} {'words/100':>9} {'contra':>7} {'len':>5}")
    for g, m in sorted(story["generators"].items(), key=lambda kv: kv[1]["hallucination_rate"]):
        ci = f"{m['ci95'][0]:.2f}-{m['ci95'][1]:.2f}"
        t = m["by_task"]
        print(f"{g:22} {m['hallucination_rate']:>6.2f} {ci:>15} {t['qa']:>6.2f} {t['summary']:>6.2f} {t['data2text']:>6.2f} {m['hallucinated_words_per_100']:>9.1f} {m['contradiction_share']:>7.2f} {m['avg_answer_words']:>5.0f}")
    print("rate by answer length:", {k: round(v, 2) for k, v in story["rate_by_length_quartile"].items()})


if __name__ == "__main__":
    main()
