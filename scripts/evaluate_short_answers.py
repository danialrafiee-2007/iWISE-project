"""Short answers outside English (D-172): how the multilingual check reads an answer of a few words, such as "308 [1]".

A short answer means nothing without its question, and the check reads each sentence alone, so right ones were flagged.
On the XQuAD articles used to choose the lines of "enough" (evaluate_answers.py keeps the other half for the RAG's final
measure), each sampled question gets two short answers against its paragraph: its gold answer, which is right, and the
gold answer of another question of the same paragraph, which is in the source but does not answer it. For each setting
of how many words count as short (0: never, the check as it was), this counts right answers not shown as grounded (risk
at or above the response line less the uncertain band) and wrong ones shown as grounded, and the AUROC between them.
Output: eval/results/short_answers_dev.json
"""

import argparse
import json
import random
from pathlib import Path

from sklearn.metrics import roc_auc_score

from evaluate_answers import HALF_OF_CHOOSING, half, load
from truth_guardian import fusion, multicheck
from truth_guardian.pipeline import make_sample
from truth_guardian.report import UNCERTAIN_BAND
from truth_guardian.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("es", "ar", "ru", "zh")
SETTINGS = (0, 3, 6)


def cases(raw: Path, code: str, n: int) -> list[dict]:
    """One question per paragraph of the choosing half, with a right and a wrong short answer."""
    data = json.loads((raw / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"]
    out = []
    for number, article in enumerate(data):
        if half(str(number)) != HALF_OF_CHOOSING:
            continue
        for k, paragraph in enumerate(article["paragraphs"]):
            qas = [qa for qa in paragraph["qas"] if qa["answers"]]
            if len(qas) < 2:
                continue
            rng = random.Random(f"short-answers-v1:{code}:{number}:{k}")
            qa = rng.choice(qas)
            right = qa["answers"][0]["text"]
            others = [o["answers"][0]["text"] for o in qas if o is not qa and o["answers"][0]["text"] not in right and right not in o["answers"][0]["text"]]
            if others:
                out.append({"question": qa["question"], "source": paragraph["context"], "right": right, "wrong": rng.choice(others)})
    return random.Random(f"short-answers-v1:{code}").sample(out, min(n, len(out)))


def risk(model, question: str, source: str, answer: str) -> float:
    sample = make_sample(f"{answer} [1]", [source], question)
    sentences = split_sentences(sample.answer)
    rows = [{"start": s.start, "end": s.end, **r} for s, r in zip(sentences, multicheck.signal(sample, sentences))]
    table = fusion.build_table([sample], {"multilingual": {sample.id: rows}}, model.signals, model.structure)
    return model.predictions([sample], table)[0].score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--per-language", type=int, default=60)
    args = parser.parse_args()
    model, manifest = fusion.load(ROOT / "models" / "fusion-multilingual")
    shown = model.thresholds["response"] - UNCERTAIN_BAND
    report = {"model": manifest["version"], "per_language": args.per_language, "shown_as_grounded_below": shown, "languages": {}}
    for code in LANGUAGES:
        chosen = cases(args.raw, code, args.per_language)
        report["languages"][code] = {}
        for words in SETTINGS:
            multicheck.SHORT_ANSWER_WORDS = words
            right = [risk(model, c["question"], c["source"], c["right"]) for c in chosen]
            wrong = [risk(model, c["question"], c["source"], c["wrong"]) for c in chosen]
            row = {
                "answers": len(chosen),
                "right_not_shown_as_grounded": sum(r >= shown for r in right) / len(right),
                "wrong_shown_as_grounded": sum(w < shown for w in wrong) / len(wrong),
                "auroc": roc_auc_score([0] * len(right) + [1] * len(wrong), right + wrong),
            }
            report["languages"][code][str(words)] = row
            print(code, words, json.dumps(row), flush=True)
    out = ROOT / "eval" / "results" / "short_answers_dev.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
