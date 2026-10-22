"""Human evaluation kit: two team members independently judge the system's flagged claims; agreement via Cohen's kappa.

  export  writes eval/annotation/claims_A.csv and claims_B.csv (same claims, shuffled the same way) from RAGTruth dev,
          using the saved final model's cached signals; annotators fill the empty columns without talking.
  score   reads both files and reports Cohen's kappa per question and the human-judged precision of the flags.
See docs/ANNOTATION_GUIDE.md for what each answer means.
"""

import argparse
import csv
import random
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from truth_guardian import fusion
from truth_guardian.correct import suggest
from truth_guardian.evaluation import read_predictions
from truth_guardian.features import load_rows
from truth_guardian.overrides import apply_polarity
from truth_guardian.report import build_report
from truth_guardian.schema import read_jsonl
from truth_guardian.text import Sentence

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "annotation"
QUESTIONS = ("flag_correct", "type_correct", "explanation_helpful")
FIELDS = ["claim_id", "task", "claim", "flagged_words", "status", "type", "explanation", "evidence", "fix", *QUESTIONS, "notes"]


def export(n_answers: int, seed: int) -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    data = ROOT / "data/processed/ragtruth_dev.jsonl"
    samples = {s.id: s for s in read_jsonl(data)}
    rows = load_rows([*model.signals, "polarity"], data, ROOT / "data" / "features")
    name = f"fusion-{model.kind}-{'+'.join(model.signals)}" + ("" if model.structure else "-nostructure")
    predictions = read_predictions(ROOT / "eval" / "predictions" / f"{name}__ragtruth_dev.jsonl")

    claims = []
    for sid, sample in samples.items():
        prediction = apply_polarity(predictions[sid], rows["polarity"][sid])
        per_sentence = [{k: v for signal in rows for k, v in rows[signal][sid][i].items()} for i in range(len(rows["polarity"][sid]))]
        sentences = [Sentence(r["start"], r["end"], sample.answer[r["start"] : r["end"]]) for r in per_sentence]
        flagged = {(s.start, s.end) for s in prediction.sentences if s.score >= model.thresholds["sentence"]}
        fixes = [suggest(sample, s) if (s.start, s.end) in flagged else [] for s in sentences]
        report = build_report(sample, sentences, prediction, per_sentence, fixes, model.thresholds, manifest["version"])
        for i, c in enumerate(report.claims):
            if c.status != "supported":
                claims.append({
                    "claim_id": f"{sid}#{i}",
                    "task": sample.meta.task,
                    "claim": c.text,
                    "flagged_words": " | ".join(sample.answer[a:b] for a, b in c.spans),
                    "status": c.status,
                    "type": c.type.value if c.type else "",
                    "explanation": c.explanation,
                    "evidence": c.evidence.text if c.evidence else "",
                    "fix": "; ".join(f"{f.original} -> {f.replacement}" for f in c.fixes if f.replacement),
                })
    rng = random.Random(seed)
    answers = sorted({c["claim_id"].split("#")[0] for c in claims})
    chosen = set(rng.sample(answers, min(n_answers, len(answers))))
    selected = [c for c in claims if c["claim_id"].split("#")[0] in chosen]
    rng.shuffle(selected)
    OUT.mkdir(parents=True, exist_ok=True)
    for annotator in ("A", "B"):
        with (OUT / f"claims_{annotator}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({**c, **{q: "" for q in QUESTIONS}, "notes": ""} for c in selected)
    print(f"{len(selected)} flagged claims from {len(chosen)} answers -> {OUT.relative_to(ROOT).as_posix()}/claims_A.csv, claims_B.csv")


def score() -> None:
    def read(name: str) -> dict[str, dict]:
        with (OUT / name).open(encoding="utf-8-sig", newline="") as f:
            return {r["claim_id"]: r for r in csv.DictReader(f)}

    a, b = read("claims_A.csv"), read("claims_B.csv")
    ids = [i for i in a if i in b and all(a[i][q].strip() and b[i][q].strip() for q in QUESTIONS)]
    print(f"{len(ids)} claims answered by both annotators")
    for q in QUESTIONS:
        x, y = [a[i][q].strip().lower() for i in ids], [b[i][q].strip().lower() for i in ids]
        weights = "quadratic" if q == "explanation_helpful" else None
        print(f"  {q}: Cohen's kappa {cohen_kappa_score(x, y, weights=weights):.2f}")
    agreed = [i for i in ids if a[i]["flag_correct"].strip().lower() == b[i]["flag_correct"].strip().lower()]
    correct = sum(a[i]["flag_correct"].strip().lower() == "yes" for i in agreed)
    print(f"  human-judged flag precision (where both agree): {correct}/{len(agreed)} = {correct / max(len(agreed), 1):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export")
    e.add_argument("--answers", type=int, default=40)
    e.add_argument("--seed", type=int, default=0)
    sub.add_parser("score")
    args = parser.parse_args()
    export(args.answers, args.seed) if args.command == "export" else score()


if __name__ == "__main__":
    main()
