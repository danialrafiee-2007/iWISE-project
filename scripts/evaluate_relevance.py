"""Does an answer address its question? (D-172) A verdict says an answer rests on its sources, not that it answers.

On the XQuAD articles used to choose the lines of "enough" (evaluate_answers.py keeps the other half for the RAG's final
measure), each sampled question meets two sentences of its own paragraph, both in the source word for word: the one
holding its gold answer, and one holding the answer to another question of that paragraph. Multilingual E5 scores each
as a passage for the question, as the library's search does. For each line, this counts answering sentences below it
(they would be told they may not answer) and others at or above it, per language and pooled.
Output: eval/results/relevance_dev.json
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from evaluate_answers import HALF_OF_CHOOSING, half
from truth_guardian.media import multilingual
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "es", "ar", "ru", "zh")
LINES = (0.75, 0.78, 0.8, 0.82, 0.84)


def pairs(raw: Path, code: str, n: int) -> list[tuple[str, str, str]]:
    """(question, the sentence holding its answer, a sentence holding another question's answer)."""
    data = json.loads((raw / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"]
    out = []
    for number, article in enumerate(data):
        if half(str(number)) != HALF_OF_CHOOSING:
            continue
        for k, paragraph in enumerate(article["paragraphs"]):
            sentences = split_sentences(paragraph["context"])
            holding = lambda qa: next((s.text for s in sentences if s.start <= qa["answers"][0]["answer_start"] < s.end), None)
            qas = [qa for qa in paragraph["qas"] if qa["answers"] and holding(qa)]
            rng = random.Random(f"relevance-v1:{code}:{number}:{k}")
            rng.shuffle(qas)
            for qa in qas:
                others = [holding(o) for o in qas if holding(o) != holding(qa)]
                if others:
                    out.append((qa["question"], holding(qa), rng.choice(others)))
                    break
    return random.Random(f"relevance-v1:{code}").sample(out, min(n, len(out)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--per-language", type=int, default=100)
    args = parser.parse_args()
    report, pooled = {"per_language": args.per_language, "languages": {}}, ([], [])
    for code in LANGUAGES:
        chosen = pairs(args.raw, code, args.per_language)
        questions = multilingual.embed([q for q, _, _ in chosen], "query")
        right = (questions * multilingual.embed([r for _, r, _ in chosen], "passage")).sum(axis=1)
        other = (questions * multilingual.embed([o for _, _, o in chosen], "passage")).sum(axis=1)
        pooled[0].extend(right)
        pooled[1].extend(other)
        report["languages"][code] = {
            "pairs": len(chosen),
            "auroc": roc_auc_score([1] * len(right) + [0] * len(other), np.concatenate([right, other])),
            "lines": {str(line): {"answering_below": float((right < line).mean()), "other_at_or_above": float((other >= line).mean())} for line in LINES},
        }
        print(code, json.dumps(report["languages"][code]), flush=True)
    right, other = map(np.array, pooled)
    report["pooled"] = {
        "auroc": roc_auc_score([1] * len(right) + [0] * len(other), np.concatenate([right, other])),
        "lines": {str(line): {"answering_below": float((right < line).mean()), "other_at_or_above": float((other >= line).mean())} for line in LINES},
    }
    print("pooled", json.dumps(report["pooled"]))
    out = ROOT / "eval" / "results" / "relevance_dev.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
