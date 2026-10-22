"""Evaluate conflicting-source detection on RAGTruth dev QA (several passages per question).

Injected: a grounded answer's number is found in one passage; a copy of that passage sentence with the number
changed is added as a new passage. The conflict should be found, and the answer sentence marked contested,
following the original passage (or the injected one when the answer is edited to its value).
Natural: how often the passages of a question (one source group, shared by its six answers) contain a conflict,
and how many answer sentences take a side in one; examples are saved for reading by hand.
Output: eval/results/conflicts.json
"""

import json
import random
from pathlib import Path

from truth_guardian.conflicts import contested, find_conflicts
from truth_guardian.perturb import _changed_number, _source_numbers
from truth_guardian.schema import Document, read_jsonl
from truth_guardian.symbolic import _numbers_in, normalize_number
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
INJECTED = 150


def injection(sample, rng):
    """(sample with a conflicting passage, answer sentence, original value, injected value, original passage id)."""
    taken = _source_numbers(sample)
    for sentence in split_sentences(sample.answer):
        for m in _numbers_in(sentence.text):
            forms = normalize_number(m.group())
            homes = [(d, s) for d in sample.documents for s in split_sentences(d.text) if any(normalize_number(n.group()) & forms for n in _numbers_in(s.text))]
            if len(homes) != 1:
                continue
            document, source = homes[0]
            match = next(n for n in _numbers_in(source.text) if normalize_number(n.group()) & forms)
            new = _changed_number(match.group(), rng, taken)
            if new is None:
                continue
            copy = source.text[: match.start()] + new + source.text[match.end() :]
            injected = sample.model_copy(update={"documents": [*sample.documents, Document(id="injected", text=copy)]})
            return injected, sentence, m.group(), new, document.id
    return None


def main() -> None:
    dev = [s for s in read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl") if s.meta.task == "qa"]
    rng = random.Random("conflicts-v1")

    by_group = {}
    for s in dev:
        if s.meta.group_id not in by_group:
            by_group[s.meta.group_id] = (s, find_conflicts(s))
    with_conflict = [(s, c) for s, c in by_group.values() if c]
    conflicted = {s.meta.group_id: c for s, c in with_conflict}
    contested_sentences = sum(bool(contested(x, conflicted[s.meta.group_id])) for s in dev if s.meta.group_id in conflicted for x in split_sentences(s.answer))

    grounded = [s for s in dev if s.labels.response == "grounded" and s.meta.quality == "good"]
    found = marked = followed = edited_followed = tried = 0
    for s in rng.sample(grounded, len(grounded)):
        if tried == INJECTED:
            break
        made = injection(s, rng)
        if made is None:
            continue
        tried += 1
        injected, sentence, original, new, home = made
        conflicts = [c for c in find_conflicts(injected) if "injected" in (c.first_document, c.second_document)]
        found += bool(conflicts)
        side = contested(sentence, conflicts)
        marked += side is not None
        followed += side is not None and side[1] == home
        edited_text = sentence.text.replace(original, new, 1)
        edited = sentence._replace(text=edited_text)
        side = contested(edited, conflicts)
        edited_followed += side is not None and side[1] == "injected"

    report = {
        "natural": {
            "qa_samples": len(dev),
            "source_groups": len(by_group),
            "groups_with_conflict": len(with_conflict),
            "rate": len(with_conflict) / len(by_group),
            "contested_answer_sentences": contested_sentences,
            "examples": [
                {"id": s.id, "first": c[0].first[:200], "second": c[0].second[:200], "values": [c[0].first_value, c[0].second_value], "contradiction": round(c[0].contradiction, 3)}
                for s, c in with_conflict[:25]
            ],
        },
        "injected": {
            "samples": tried,
            "conflict_found": found / tried,
            "answer_marked_contested": marked / tried,
            "follows_original_passage": followed / tried,
            "edited_answer_follows_injected_passage": edited_followed / tried,
        },
    }
    out = ROOT / "eval" / "results" / "conflicts.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: {x: y for x, y in v.items() if x != "examples"} for k, v in report.items()}, indent=1))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
