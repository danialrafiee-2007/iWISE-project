"""Evaluate Fix-it suggestions against RAGTruth annotator notes ("Original: ...") on train.

For contradicted spans whose wrong item is caught by the symbolic checks, a suggestion counts as correct
when its replacement appears in what the annotator wrote the source originally said. Notes are free text,
so this is a lower bound on true accuracy. Runs on train only, keeping dev clean.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from truth_guardian.correct import suggest
from truth_guardian.data.splits import TRAIN_SUBSET_SEED, sample_groups
from truth_guardian.schema import HallucinationType, read_jsonl
from truth_guardian.symbolic import _numbers_in, normalize_number
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL = re.compile(r"original\s*:\s*(.*?)(?:\n\s*(?:generated|generative|aigc)\b|$)", re.IGNORECASE | re.DOTALL)


def original_text(note: str | None) -> str | None:
    match = _ORIGINAL.search(note or "")
    return match.group(1).strip() if match else None


def replacement_matches(replacement: str, kind: str, original: str) -> bool:
    if kind == "number":
        forms = {f for m in _numbers_in(original) for f in normalize_number(m.group())}
        return bool(normalize_number(replacement) & forms)
    return replacement.lower() in original.lower()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=int, default=600, help="train source groups to evaluate on")
    args = parser.parse_args()

    samples = sample_groups([s for s in read_jsonl(ROOT / "data/processed/ragtruth_train.jsonl") if s.meta.quality == "good"], args.groups, seed=TRAIN_SUBSET_SEED)
    counts: Counter = Counter()
    examples = []
    for sample in samples:
        sentences = split_sentences(sample.answer)
        for span in sample.labels.spans:
            if span.type != HallucinationType.CONTRADICTED:
                continue
            counts["contradicted_spans"] += 1
            original = original_text(span.note)
            touching = [s for s in sentences if s.start < span.end and span.start < s.end]
            caught = [g for s in touching for g in suggest(sample, s) if g.start < span.end and span.start < g.end]
            if not caught:
                continue
            counts["caught_by_symbolic"] += 1
            proposed = [g for g in caught if g.replacement is not None]
            if not proposed:
                continue
            counts["with_replacement"] += 1
            counts[f"with_replacement_{sample.meta.task}"] += 1
            if original is None:
                continue
            counts["with_replacement_and_note"] += 1
            correct = any(replacement_matches(g.replacement, g.kind, original) for g in proposed)
            counts["correct"] += correct
            counts[f"correct_{sample.meta.task}"] += correct
            counts[f"checked_{sample.meta.task}"] += 1
            if len(examples) < 12:
                examples.append({"answer": sample.answer[span.start : span.end], "suggestions": [(g.original, g.replacement) for g in proposed], "original_note": original[:120], "correct": correct})

    report = {
        "samples": len(samples),
        **counts,
        "precision_vs_notes": counts["correct"] / counts["with_replacement_and_note"] if counts["with_replacement_and_note"] else None,
        "precision_by_task": {t: counts[f"correct_{t}"] / counts[f"checked_{t}"] for t in ("qa", "summary", "data2text") if counts[f"checked_{t}"]},
        "examples": examples,
    }
    out = ROOT / "eval" / "results" / "fixit_train.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
    for e in examples[:8]:
        print(" ", "OK " if e["correct"] else "MISS", e["suggestions"], "| note:", e["original_note"][:80].replace("\n", " "))


if __name__ == "__main__":
    main()
