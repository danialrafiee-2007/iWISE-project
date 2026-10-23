"""Judge the token-level detector (detector.py) against the signals the system already has, with nothing tuned on dev.

RAGTruth dev: sentence AUROC (detector, HHEM alone, final fusion model, rank average of detector and fusion),
response AUROC (detector = its highest sentence), and character-level span F1 (detector tokens at its fixed
threshold against fusion sentences at the model's own sentence threshold). Fool-the-Guardian: AUROC against the
unedited controls and how often the edited words are hit, per edit kind, next to the fusion model's scores; antonym,
quantifier and certainty edits were never used in training, so they measure transfer.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

from score_benchmark import RELEASE, read, score_fool
from truth_guardian import detector, fusion
from truth_guardian.evaluation import _f1, read_predictions, span_counts
from truth_guardian.labels import sentence_labels
from truth_guardian.schema import read_jsonl
from truth_guardian.signals import premises
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
FUSION_PREDICTIONS = ROOT / "eval/predictions/fusion-ensemble-lexical+symbolic+dense+hhem-nostructure__ragtruth_dev.jsonl"


def detect(model: detector.Detector, samples) -> dict[str, list[tuple[int, int, float, list[tuple[int, int]]]]]:
    """Per answer: (start, end, score, absolute spans) for each sentence."""
    keys, pairs = [], []
    for s in samples:
        sentences = split_sentences(s.answer)
        for sentence, premise in zip(sentences, premises(s, sentences)):
            keys.append((s.id, sentence))
            pairs.append((premise, sentence.text))
    out = defaultdict(list)
    for (sid, sentence), (score, spans) in zip(keys, model.score(pairs)):
        out[sid].append((sentence.start, sentence.end, score, [(sentence.start + a, sentence.start + b) for a, b in spans]))
    return out


def rank_average(*columns) -> np.ndarray:
    return np.mean([rankdata(c) / len(c) for c in columns], axis=0)


def span_metrics(samples, predicted: dict[str, list[tuple[int, int]]]) -> dict:
    overlap = n_pred = n_gold = 0
    for s in samples:
        o, p, g = span_counts([(sp.start, sp.end) for sp in s.labels.spans], predicted.get(s.id, []))
        overlap, n_pred, n_gold = overlap + o, n_pred + p, n_gold + g
    precision, recall = overlap / max(n_pred, 1), overlap / max(n_gold, 1)
    return {"precision": precision, "recall": recall, "f1": _f1(precision, recall)}


def dev(model: detector.Detector) -> dict:
    samples = list(read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl"))
    found = detect(model, samples)
    fused = read_predictions(FUSION_PREDICTIONS)
    hhem = {r["id"]: {(x["start"], x["end"]): 1 - x["hhem_consistency"] for x in r["sentences"]} for r in read(ROOT / "data/features/hhem/ragtruth_dev.jsonl")}
    model_threshold = fusion.load(ROOT / "models" / "fusion")[0].thresholds["sentence"]
    rows, responses = [], []
    for s in samples:
        sentences = split_sentences(s.answer)
        gold = sentence_labels(s, sentences)
        fusion_sentences = {(x.start, x.end): x.score for x in fused[s.id].sentences}
        ours = {(a, b): score for a, b, score, _ in found[s.id]}
        for sentence, y in zip(sentences, gold):
            key = (sentence.start, sentence.end)
            if key in fusion_sentences and key in hhem.get(s.id, {}):
                rows.append((y, ours[key], fusion_sentences[key], hhem[s.id][key], s.meta.task))
        responses.append((s.labels.response == "hallucinated", max((x[2] for x in found[s.id]), default=0.0), fused[s.id].score, s.meta.task))
    y, ours, fused_s, hhem_s, _ = map(np.array, zip(*rows))
    sentence = {
        "n": len(rows), "hallucinated_rate": float(y.mean()),
        "auroc_detector": float(roc_auc_score(y, ours)),
        "auroc_hhem": float(roc_auc_score(y, hhem_s)),
        "auroc_fusion": float(roc_auc_score(y, fused_s)),
        "auroc_rank_average": float(roc_auc_score(y, rank_average(ours, fused_s))),
    }
    ry, rours, rfused, rtask = map(np.array, zip(*responses))
    response = {
        "n": len(responses),
        "auroc_detector": float(roc_auc_score(ry, rours)),
        "auroc_fusion": float(roc_auc_score(ry, rfused)),
        "auroc_rank_average": float(roc_auc_score(ry, rank_average(rours, rfused))),
        "by_task": {
            t: {k: float(roc_auc_score(ry[m], v[m])) for k, v in (("detector", rours), ("fusion", rfused), ("rank_average", rank_average(rours, rfused)))}
            for t in sorted(set(rtask)) for m in [rtask == t]
        },
    }
    spans = {"detector_tokens": span_metrics(samples, {sid: [sp for *_, ss in v for sp in ss] for sid, v in found.items()})}
    spans["fusion_sentences"] = span_metrics(samples, {sid: [(x.start, x.end) for x in p.sentences if x.score >= model_threshold] for sid, p in fused.items()})
    return {"sentence": sentence, "response": response, "span": spans}


def fool(model: detector.Detector) -> dict:
    samples = list(read_jsonl(ROOT / "data/processed/perturb_dev.jsonl"))
    labels = read(RELEASE / "fool_the_guardian.labels.jsonl")
    found = detect(model, samples)
    ours = {sid: {"score": max((x[2] for x in v), default=0.0), "spans": [list(sp) for *_, ss in v for sp in ss]} for sid, v in found.items()}
    fused = {p["id"]: p for p in read(RELEASE / "truth_guardian.fool_the_guardian.jsonl")}
    ids = [r["id"] for r in labels if r["id"] in ours and r["id"] in fused]
    combined = dict(zip(ids, rank_average([ours[i]["score"] for i in ids], [fused[i]["score"] for i in ids])))
    return {
        "detector": score_fool(labels, ours),
        "fusion": score_fool(labels, fused),
        "rank_average": score_fool(labels, {i: {"score": float(v)} for i, v in combined.items()}),
        "trained_kinds": list(detector.ATTACK_KINDS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "models/detector/pilot")
    args = parser.parse_args()
    model = detector.Detector(args.model)
    report = {"model": args.model.relative_to(ROOT).as_posix(), "dev": dev(model), "fool_the_guardian": fool(model)}
    out = ROOT / "eval/results" / f"detector_{args.model.name}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
