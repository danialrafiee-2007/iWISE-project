"""Compare highlighting strategies for flagged sentences on RAGTruth dev: whole sentence, symbolic refinement, atomic claims.

Uses the saved final model's cached predictions and signals (with the polarity override), so only claim checks run live.
"""

import json
from pathlib import Path

from truth_guardian import fusion, models
from truth_guardian.claims import localize, split_claims
from truth_guardian.evaluation import read_predictions, span_counts
from truth_guardian.explain import explain_sentence
from truth_guardian.features import load_rows
from truth_guardian.overrides import apply_polarity
from truth_guardian.schema import read_jsonl
from truth_guardian.signals import premises
from truth_guardian.text import Sentence

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    model, _ = fusion.load(ROOT / "models" / "fusion")
    data = ROOT / "data/processed/ragtruth_dev.jsonl"
    rows = load_rows([*model.signals, "polarity"], data, ROOT / "data" / "features")
    name = f"fusion-{model.kind}-{'+'.join(model.signals)}" + ("" if model.structure else "-nostructure")
    predictions = read_predictions(ROOT / "eval" / "predictions" / f"{name}__ragtruth_dev.jsonl")
    threshold = model.thresholds["sentence"]

    totals = {k: [0, 0, 0] for k in ("whole_sentence", "symbolic_refined", "atomic_claims")}
    split_sentences_count = flagged_count = 0
    for sample in read_jsonl(data):
        prediction = apply_polarity(predictions[sample.id], rows["polarity"][sample.id])
        gold = [(sp.start, sp.end) for sp in sample.labels.spans]
        merged = [{k: v for signal in rows for k, v in rows[signal][sample.id][i].items()} for i in range(len(rows["polarity"][sample.id]))]
        chosen = {k: [] for k in totals}
        for score, row in zip(prediction.sentences, merged):
            if score.score < threshold:
                continue
            flagged_count += 1
            sentence = Sentence(row["start"], row["end"], sample.answer[row["start"] : row["end"]])
            chosen["whole_sentence"].append((sentence.start, sentence.end))
            chosen["symbolic_refined"] += explain_sentence(row, sentence.start, sentence.end).spans
            premise_for = lambda text: premises(sample, [Sentence(0, len(text), text)])[0]
            claim_spans = localize(sentence, row, premise_for, models.hhem_consistency)
            split_sentences_count += len(split_claims(sentence)) > 1
            symbolic = [tuple(s) for s in row.get("sym_spans", []) + row.get("pol_spans", [])]
            chosen["atomic_claims"] += symbolic if symbolic else claim_spans
        for k, spans in chosen.items():
            o, p, g = span_counts(gold, spans)
            totals[k][0] += o
            totals[k][1] += p
            totals[k][2] += g

    report = {"flagged_sentences": flagged_count, "split_into_claims": split_sentences_count}
    for k, (o, p, g) in totals.items():
        precision, recall = o / p if p else 0.0, o / g if g else 0.0
        report[k] = {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
    out = ROOT / "eval" / "results" / "claims__ragtruth_dev.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
