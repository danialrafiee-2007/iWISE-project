"""How well the library finds the right passage, and when it should say the documents do not hold an answer (D-163).

    python scripts/evaluate_retrieval.py [--raw data/raw] [--cache folder]

XQuAD gives the same 1,190 questions on the same 240 Wikipedia paragraphs in five languages, translated by professionals.
Each question looks for its own paragraph among all 240: in its own language, and across languages over the English ones.
The weight of word search and the lines for "enough", one per language and one across languages, are chosen on the articles
of one half and measured on the other: a question whose article is in the library should pass the line, and the same
question with its article left out should not. Ties count against the method, so a search that finds nothing is not
credited with the right rank. Paragraphs of an encyclopaedia are an easy case: the articles differ in subject, and the
questions were written from the paragraphs.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian.data.xquad import LANGUAGES
from truth_guardian.language import detect
from truth_guardian.rag.library import fuse
from truth_guardian.rag.words import WordIndex

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "results" / "rag_retrieval.json"
KEEP = 0.95
WEIGHTS = (0.1, 0.25, 0.5, 1.0)


def load(raw: Path, code: str) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    """(paragraphs, the article of each, each question with the index of its paragraph)."""
    data = json.loads((raw / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"]
    paragraphs, articles, questions = [], [], []
    for number, article in enumerate(data):
        for paragraph in article["paragraphs"]:
            for qa in paragraph["qas"]:
                questions.append((qa["question"], len(paragraphs)))
            paragraphs.append(paragraph["context"])
            articles.append(str(number))
    return paragraphs, articles, questions


def embedded(texts: list[str], kind: str, name: str, cache: Path | None) -> np.ndarray:
    path = cache / f"{name}-{kind}.npy" if cache else None
    if path and path.is_file():
        return np.load(path)
    from truth_guardian.media import multilingual

    vectors = multilingual.embed(texts, kind)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors)
    return vectors


def half(article: str) -> int:
    return int(hashlib.sha256(f"rag-enough-v1:{article}".encode()).hexdigest(), 16) % 2


def rates(ranks: np.ndarray) -> dict:
    return {"hit_at_1": float((ranks == 1).mean()), "hit_at_5": float((ranks <= 5).mean()), "mrr": float((1 / ranks).mean())}


def rank_of(scores: np.ndarray, gold: int) -> int:
    return int((scores >= scores[gold]).sum())


def ranks_by_method(vectors, words, queries, questions, corpus_language) -> dict[str, np.ndarray]:
    methods: dict[str, list[int]] = {"meaning": [], "words": [], **{f"fused_{w}": [] for w in WEIGHTS}, **{f"fused_{w}_same_language": [] for w in WEIGHTS}}
    for (question, gold), query in zip(questions, queries):
        dense, lexical = vectors @ query, words.scores(question)
        methods["meaning"].append(rank_of(dense, gold))
        methods["words"].append(rank_of(lexical, gold))
        same = detect(question).code in (corpus_language, None)
        for w in WEIGHTS:
            methods[f"fused_{w}"].append(rank_of(fuse(dense, lexical, w), gold))
            methods[f"fused_{w}_same_language"].append(rank_of(fuse(dense, lexical if same else np.zeros_like(lexical), w), gold))
    return {name: np.array(ranks) for name, ranks in methods.items()}


def closest(vectors, queries, questions, articles) -> tuple[np.ndarray, np.ndarray]:
    """Per question: the closest passage's similarity with its article in the library, and with all of it left out."""
    names = np.array(articles)
    inside, outside = [], []
    for (_, gold), query in zip(questions, queries):
        scores = vectors @ query
        inside.append(float(scores.max()))
        outside.append(float(scores[names != articles[gold]].max()))
    return np.array(inside), np.array(outside)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--cache", type=Path, help="keep the embeddings here, for a second run")
    args = parser.parse_args()
    corpora = {code: load(args.raw, code) for code in LANGUAGES}
    pairs = [(code, code) for code in LANGUAGES] + [(code, "en") for code in LANGUAGES if code != "en"]
    runs = {}
    for asked, corpus in pairs:
        paragraphs, articles, _ = corpora[corpus]
        _, _, questions = corpora[asked]
        vectors = embedded(paragraphs, "passage", corpus, args.cache)
        queries = embedded([q for q, _ in questions], "query", asked, args.cache)
        sides = np.array([half(articles[gold]) for _, gold in questions])
        runs[f"{asked}_over_{corpus}"] = (ranks_by_method(vectors, WordIndex(paragraphs), queries, questions, corpus), sides, *closest(vectors, queries, questions, articles))
        print(asked, "over", corpus, flush=True)

    methods = next(iter(runs.values()))[0]
    chosen = max(methods, key=lambda m: (np.mean([rates(r[0][m][r[1] == 0])["hit_at_5"] for r in runs.values()]), np.mean([rates(r[0][m][r[1] == 0])["hit_at_1"] for r in runs.values()])))
    line_of = lambda *names: float(np.quantile(np.concatenate([runs[n][2][runs[n][1] == 0] for n in names]), 1 - KEEP))
    lines = {code: line_of(f"{code}_over_{code}") for code in LANGUAGES} | {"across": line_of(*[f"{code}_over_en" for code in LANGUAGES if code != "en"])}
    results = {"chosen_on_half_0": {"method": chosen, "lines": lines}, "on_half_1": {}}
    for name, (ranks, sides, inside, outside) in runs.items():
        measured = sides == 1
        asked, corpus = name.split("_over_")
        line = lines[asked] if asked == corpus else lines["across"]
        results["on_half_1"][name] = {
            "questions": int(measured.sum()),
            "methods": {m: rates(ranks[m][measured]) for m in ("meaning", "words", chosen)},
            "line": line,
            "keeps_answerable": float((inside[measured] >= line).mean()),
            "refuses_outside": float((outside[measured] < line).mean()),
            "auroc": float(roc_auc_score(np.r_[np.ones(measured.sum()), np.zeros(measured.sum())], np.r_[inside[measured], outside[measured]])),
        }
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(results["chosen_on_half_0"]))
    for name, row in results["on_half_1"].items():
        print(f"{name:14} {chosen}: hit@1 {row['methods'][chosen]['hit_at_1']:.3f} hit@5 {row['methods'][chosen]['hit_at_5']:.3f} | meaning hit@5 {row['methods']['meaning']['hit_at_5']:.3f} | line {row['line']:.3f} keeps {row['keeps_answerable']:.3f} refuses {row['refuses_outside']:.3f} auroc {row['auroc']:.3f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
