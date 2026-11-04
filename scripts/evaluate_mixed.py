"""Does an answer that needs several files, of different kinds, work from end to end (D-169)?

    python scripts/evaluate_mixed.py --folder runtime/rag-eval

Recordings, images and documents go on one shelf through their real readers, and the local model answers questions that need
two or three of them while looking at the images it finds close. The files are made up and few, so this shows whether a
combined answer works at all and where it breaks, and is no measure of quality.
"""

import argparse
import json
from pathlib import Path

from truth_guardian.rag import answer as rag
from truth_guardian.rag.generators import LocalGenerator
from truth_guardian.rag.library import MINE, Library
from truth_guardian.web.engine import ROOT as ENGINE_ROOT
from truth_guardian.web.engine import Engine

from evaluate_answers import has_gold

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "eval" / "rag_mixed"
OUT = ROOT / "eval" / "results" / "rag_mixed.json"


def row(found: rag.Answer, case: dict) -> dict:
    cited = sorted({c.document for c in found.citations})
    parts = [{"file": part["file"], "said": has_gold(found.text, part["gold"]), "cited": part["file"] in cited} for part in case["parts"]]
    return {
        "question": found.question, "status": found.status, "verdict": found.report.verdict if found.report else None, "text": found.text, "seconds": found.seconds,
        "similarity": found.similarity, "cited": cited, "looked_at": found.looked_at, "parts": parts, "model_cited": not any(c.inferred for c in found.citations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", type=Path, required=True, help="keeps the shelf, for a second run")
    args = parser.parse_args()
    questions = json.loads((FILES / "questions.json").read_text(encoding="utf-8"))
    books = Library(args.folder / "mixed.sqlite")
    for path in sorted(FILES.iterdir()):
        if path.name != "questions.json":
            entry = books.add(path.name, path.read_bytes())
            print(f"{path.name}: {entry.kind}, {entry.passages} passages, concerns {entry.concerns!r}", flush=True)
    engine = Engine(ENGINE_ROOT)
    engine.load()
    writer = LocalGenerator()
    results = {}
    for group in ("combined", "single"):
        results[group] = []
        for case in questions[group]:
            found = answer_row = row(rag.answer(case["question"], books, engine, writer, (MINE,)), case)
            results[group].append(answer_row)
            print(json.dumps(found, ensure_ascii=False), flush=True)
    results["unanswerable"] = []
    for question in questions["unanswerable"]:
        found = rag.answer(question, books, engine, writer, (MINE,))
        results["unanswerable"].append({"question": question, "status": found.status, "verdict": found.report.verdict if found.report else None, "text": found.text, "similarity": found.similarity, "seconds": found.seconds})
        print(json.dumps(results["unanswerable"][-1], ensure_ascii=False), flush=True)
    books.close()
    summary = {
        group: {
            "questions": len(results[group]),
            "every_part_said": sum(all(p["said"] for p in r["parts"]) for r in results[group]),
            "parts": sum(len(r["parts"]) for r in results[group]),
            "parts_said": sum(p["said"] for r in results[group] for p in r["parts"]),
            "parts_cited": sum(p["cited"] for r in results[group] for p in r["parts"]),
        }
        for group in ("combined", "single")
    }
    summary["unanswerable_said_none"] = sum(r["status"] == "not_in_documents" for r in results["unanswerable"])
    OUT.write_text(json.dumps({"summary": summary, **results}, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
