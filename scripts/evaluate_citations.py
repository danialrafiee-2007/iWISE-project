"""Evaluate the citation check on RAGTruth dev QA answers that cite passages.

Natural: share of citing sentences flagged as wrongly cited, in grounded and in hallucinated answers, with examples.
Swapped: in grounded answers, a citation the check accepts is changed to a passage that does not support the claim;
the check should now flag it. Unchanged citations are the control. Output: eval/results/citations.json
"""

import json
import re
from pathlib import Path

from truth_guardian import models
from truth_guardian.citations import CITATION, SUPPORT, check_sample
from truth_guardian.schema import read_jsonl
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
_cache: dict[tuple[str, str], float] = {}


def consistency(pairs):
    todo = [p for p in dict.fromkeys(pairs) if p not in _cache]
    if todo:
        _cache.update(zip(todo, (float(x) for x in models.hhem_consistency(todo))))
    return [_cache[p] for p in pairs]


def main() -> None:
    dev = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl") if s.meta.task == "qa"]
    natural = {"grounded": [0, 0], "hallucinated": [0, 0]}
    examples, swapped, controls = [], [], []
    for s in dev:
        sentences = split_sentences(s.answer)
        checks = check_sample(s, sentences, consistency)
        for sentence, check in zip(sentences, checks):
            if check is None:
                continue
            natural[s.labels.response][0] += 1
            natural[s.labels.response][1] += check.wrong
            if check.wrong and len(examples) < 20:
                examples.append({"id": s.id, "label": s.labels.response, "sentence": sentence.text[:200], "cited": check.cited, "cited_support": round(check.cited_support, 3), "better": check.best_other, "better_support": round(check.other_support, 3)})
            if s.labels.response != "grounded" or check.wrong or check.cited_support < SUPPORT or len(check.cited) != 1:
                continue
            controls.append(check.wrong)
            support = consistency([(p, h) for p, h in _pairs(s, sentence)])
            target = next((n for n in range(1, len(s.documents) + 1) if n not in check.cited and support[n - 1] < SUPPORT), None)
            if target is None:
                continue
            moved = CITATION.sub(lambda m: re.sub(r"\d+", str(target), m.group()), sentence.text)
            edited = sentence._replace(text=moved)
            (after,) = check_sample(s.model_copy(update={"answer": moved}), [edited._replace(start=0, end=len(moved))], consistency)
            swapped.append(after is not None and after.wrong)
    report = {
        "citing_sentences": {k: v[0] for k, v in natural.items()},
        "flagged_wrong_rate": {k: v[1] / v[0] if v[0] else None for k, v in natural.items()},
        "swapped_citations": len(swapped),
        "swapped_detected": sum(swapped) / len(swapped) if swapped else None,
        "control_flagged": sum(controls) / len(controls) if controls else None,
        "examples": examples,
    }
    out = ROOT / "eval" / "results" / "citations.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


def _pairs(sample, sentence):
    from truth_guardian.citations import _premise

    claim = CITATION.sub("", sentence.text).strip(" ()[],.;:")
    return [(_premise(d.text, claim), claim) for d in sample.documents]


if __name__ == "__main__":
    main()
