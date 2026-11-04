"""How the RAG answers end to end with the local model, and what the Guardian does with its answers (D-164).

    python scripts/evaluate_answers.py --raw data/raw --folder runtime/rag-eval [--per-language 20] [--only xquad|persian|documents]

XQuAD again: the articles of the half not used to choose the lines of "enough" (evaluate_retrieval.py). Each question is
asked of a library with all the articles, where it has an answer, and of one holding only the other half, where it has none.
Every answer is kept in --folder, so a stopped run goes on where it was. An answer counts as right when it holds the gold
words, which is rough: a right answer in other words counts as wrong, more so where a translation changes the form.
The Persian set is handmade and small, so it only shows whether the line and the light check behave. The documents set is
real articles and a legal text in all seven languages on one shelf (eval/rag_documents, D-166), so a question also meets
passages in the other six; its questions are ours too.
"""

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

from truth_guardian import multicheck
from truth_guardian.data.xquad import LANGUAGES
from truth_guardian.rag import answer as rag
from truth_guardian.rag.generators import LocalGenerator
from truth_guardian.rag.library import MINE, Hit, Library
from truth_guardian.web.engine import ROOT as ENGINE_ROOT
from truth_guardian.web.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "results" / "rag_answers.json"
PERSIAN = ROOT / "eval" / "rag_persian.json"
QUESTIONS = ROOT / "eval" / "rag_questions.json"
DOCUMENTS = ROOT / "eval" / "rag_documents"
HALF_OF_CHOOSING = 0


def half(article: str) -> int:
    return int(hashlib.sha256(f"rag-enough-v1:{article}".encode()).hexdigest(), 16) % 2


def load(raw: Path, code: str) -> dict:
    """{article number: {"text", "questions": [(question, gold answers)]}}, in the order of the file."""
    data = json.loads((raw / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"]
    articles = {}
    for number, article in enumerate(data):
        questions = [(qa["question"], [a["text"] for a in qa["answers"]]) for p in article["paragraphs"] for qa in p["qas"]]
        articles[str(number)] = {"text": "\n\n".join(p["context"] for p in article["paragraphs"]), "questions": questions}
    return articles


class Remembered:
    """The embeddings of a passage are the same in both libraries, so each is made once."""

    def __init__(self):
        from truth_guardian.media import multilingual

        self.embed, self.seen = multilingual.embed, {}

    def __call__(self, texts: list[str], kind: str) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if (kind, t) not in self.seen]
        if missing:
            self.seen.update({(kind, t): v for t, v in zip(missing, self.embed(missing, kind))})
        return np.stack([self.seen[(kind, t)] for t in texts]) if texts else np.zeros((0, 384))


def shelf(path: Path, documents: dict[str, str], encode) -> Library:
    books = Library(path, encode)
    have = {entry.name for entry in books.documents(MINE)}
    for name, text in documents.items():
        if f"{name}.txt" not in have:
            books.add(f"{name}.txt", text.encode("utf-8"))
    return books


def plain(text: str) -> str:
    """Spaces and separators out and digits alike, so 8,848.86 and ۸۸۴۸٫۸۶ count as one."""
    return re.sub(r"[\s,٬.٫]", "", unicodedata.normalize("NFKC", text).translate(multicheck._DIGITS)).casefold()


def has_gold(text: str, gold: list[str]) -> bool:
    return any(plain(g) in plain(text) for g in gold)


def is_gold_document(name: str, gold: str) -> bool:
    return name == gold or name.endswith(f"-{gold}")


def row(found: rag.Answer, gold: list[str] | None, gold_document: str | None) -> dict:
    claims = found.report.claims if found.report else []
    return {
        "question": found.question, "status": found.status, "text": found.text, "similarity": found.similarity, "seconds": found.seconds, "notes": found.notes,
        "stopped_before_model": found.generator is None,
        "right": bool(gold and has_gold(found.text, gold)),
        "cited": [c.document for c in found.citations], "cited_right": bool(gold_document and any(is_gold_document(c.document, gold_document) for c in found.citations)),
        "cited_passage_holds_gold": bool(gold and any(has_gold(c.text, gold) for c in found.citations)),
        "verdict": found.report.verdict if found.report else None, "risk": found.report.risk if found.report else None,
        "flagged_claims": sum(c.status != "supported" for c in claims),
        "light": [c.status for c in found.light],
        "original": found.original,
    }


def asked(file: Path, cases: list[dict], books: Library, engine, writer) -> list[dict]:
    """Each case: question, gold, document. One line per answer, read back on a second run."""
    done = {}
    if file.is_file():
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                line = json.loads(line)
            except ValueError:
                continue
            done[line["question"]] = line
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8", newline="\n") as out:
        for case in cases:
            if case["question"] in done:
                continue
            found = rag.answer(case["question"], books, engine, writer, (MINE,))
            done[case["question"]] = row(found, case.get("gold"), case.get("document"))
            out.write(json.dumps(done[case["question"]], ensure_ascii=False) + "\n")
            out.flush()
            print(f"{file.stem}: {len(done)}/{len(cases)} {found.status} {found.seconds:.0f} s", flush=True)
    return [done[case["question"]] for case in cases]


def share(rows: list[dict], test) -> float | None:
    return round(sum(map(test, rows)) / len(rows), 3) if rows else None


def summary(answerable: list[dict], unanswerable: list[dict]) -> dict:
    wrote = [r for r in answerable if not r["status"] == "not_in_documents"]
    invented = [r for r in unanswerable if r["status"] != "not_in_documents"]
    seconds = [r["seconds"] for r in answerable + unanswerable if not r["stopped_before_model"]]
    return {
        "answerable": {
            "questions": len(answerable),
            "answered": share(answerable, lambda r: r["status"] != "not_in_documents"),
            "stopped_before_model": share(answerable, lambda r: r["stopped_before_model"]),
            "model_said_not_in_documents": share(answerable, lambda r: r["status"] == "not_in_documents" and not r["stopped_before_model"]),
            "holds_gold_words": share(answerable, lambda r: r["right"]),
            "holds_gold_words_of_answered": share(wrote, lambda r: r["right"]),
            "cites_the_right_article": share(wrote, lambda r: r["cited_right"]),
            "a_cited_passage_holds_gold": share(wrote, lambda r: r["cited_passage_holds_gold"]),
            "no_citation": share(wrote, lambda r: not r["cited"]),
            "statuses": dict(Counter(r["status"] for r in answerable)),
            "verdicts": dict(Counter(r["verdict"] for r in wrote)),
            "verdict_of_right": dict(Counter(r["verdict"] for r in wrote if r["right"])),
            "verdict_of_not_right": dict(Counter(r["verdict"] for r in wrote if not r["right"])),
        },
        "unanswerable": {
            "questions": len(unanswerable),
            "said_not_in_documents": share(unanswerable, lambda r: r["status"] == "not_in_documents"),
            "stopped_before_model": share(unanswerable, lambda r: r["stopped_before_model"]),
            "answered_anyway": len(invented),
            "verdicts_of_answered_anyway": dict(Counter(r["verdict"] for r in invented)),
            "shown_as_grounded": share(unanswerable, lambda r: r["status"] != "not_in_documents" and r["verdict"] == "grounded"),
        },
        "median_seconds_when_written": round(float(np.median(seconds)), 1) if seconds else None,
    }


def persian(folder: Path, encode, engine, writer) -> dict:
    data = json.loads(PERSIAN.read_text(encoding="utf-8"))
    names = {name.removesuffix(".txt"): text for name, text in data["documents"].items()}
    books = shelf(folder / "fa.sqlite", names, encode)
    answerable = asked(folder / "fa-answerable.jsonl", data["answerable"], books, engine, writer)
    unanswerable = asked(folder / "fa-unanswerable.jsonl", [{"question": q} for q in data["unanswerable"]], books, engine, writer)
    books.close()
    out = {**summary(answerable, unanswerable), "light_check_on_written_answers": dict(Counter(s for r in answerable for s in r["light"]))}
    flagged = []
    for claim in data["claims"]:
        hit = Hit(1, 1, claim["document"], MINE, None, data["documents"][claim["document"]], 0.9, 0.1)
        (checked, *_) = rag.light_check(claim["text"], [hit])
        flagged.append({**claim, "found": checked.status == "doubtful", "reasons": checked.reasons})
    kinds = {}
    for name in ("right", "number", "off_subject", "word_swap"):
        rows = [c for c in flagged if c.get("kind", "right") == name]
        kinds[name] = {"claims": len(rows), "called_doubtful": sum(c["found"] for c in rows)}
    return {**out, "light_check_on_handmade_claims": kinds, "claims": flagged}


def real_documents(folder: Path, encode, engine, writer) -> dict:
    names = {f"{path.parent.name}-{path.stem}": path.read_text(encoding="utf-8") for path in sorted(DOCUMENTS.glob("*/*.txt"))}
    books = shelf(folder / "documents.sqlite", names, encode)
    out = {}
    for code, group in json.loads(QUESTIONS.read_text(encoding="utf-8"))["languages"].items():
        answerable = asked(folder / f"documents-{code}-answerable.jsonl", group["answerable"], books, engine, writer)
        unanswerable = asked(folder / f"documents-{code}-unanswerable.jsonl", [{"question": q} for q in group["unanswerable"]], books, engine, writer)
        out[code] = summary(answerable, unanswerable)
        print(code, json.dumps(out[code], ensure_ascii=False), flush=True)
    books.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--folder", type=Path, required=True, help="keeps the libraries and the answers, for a second run")
    parser.add_argument("--per-language", type=int, default=20)
    parser.add_argument("--only", choices=("xquad", "persian", "documents"))
    args = parser.parse_args()

    engine = Engine(ENGINE_ROOT)
    engine.load()
    writer, encode = LocalGenerator(), Remembered()
    results = {"generator": "local", "per_language": args.per_language, "languages": {}}
    if OUT.is_file():
        results = {**results, **json.loads(OUT.read_text(encoding="utf-8"))}
    if args.only in (None, "xquad"):
        for code in LANGUAGES:
            articles = load(args.raw, code)
            everything = {n: a["text"] for n, a in articles.items()}
            kept = {n: a["text"] for n, a in articles.items() if half(n) == HALF_OF_CHOOSING}
            held = [(n, q, gold) for n, a in articles.items() if half(n) != HALF_OF_CHOOSING for q, gold in a["questions"]]
            step = max(1, len(held) // args.per_language)
            cases = [{"question": q, "gold": gold, "document": f"{n}.txt"} for n, q, gold in held[::step][: args.per_language]]
            books = shelf(args.folder / f"{code}-all.sqlite", everything, encode)
            answerable = asked(args.folder / f"{code}-answerable.jsonl", cases, books, engine, writer)
            books.close()
            books = shelf(args.folder / f"{code}-half.sqlite", kept, encode)
            unanswerable = asked(args.folder / f"{code}-unanswerable.jsonl", [{"question": c["question"]} for c in cases], books, engine, writer)
            books.close()
            results["languages"][code] = summary(answerable, unanswerable)
            print(code, json.dumps(results["languages"][code], ensure_ascii=False), flush=True)
            OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    if args.only in (None, "persian"):
        results["persian_handmade"] = persian(args.folder, encode, engine, writer)
        OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        print("fa", json.dumps({k: v for k, v in results["persian_handmade"].items() if k != "claims"}, ensure_ascii=False))
    if args.only in (None, "documents"):
        results["documents"] = real_documents(args.folder, encode, engine, writer)
        OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
