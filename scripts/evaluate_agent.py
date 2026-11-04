"""Does the agent work from end to end, and how does the Guardian behave beside it (D-170)?

    python scripts/evaluate_agent.py --folder runtime/rag-eval

The same made-up files as evaluate_mixed.py, on the shelf it left, with the local model. For tasks needing several steps it
reports the words a right answer holds, the tools used, every stop and warning, and the time; a stop on a run whose answer was
right is a false alarm of the live guardian. Too few tasks to measure quality.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from truth_guardian.rag.agent import run_agent
from truth_guardian.rag.generators import LocalGenerator
from truth_guardian.rag.library import MINE, Library
from truth_guardian.web.engine import ROOT as ENGINE_ROOT
from truth_guardian.web.engine import Engine

from evaluate_answers import has_gold

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "eval" / "rag_mixed"
OUT = ROOT / "eval" / "results" / "rag_agent.json"


def row(found, gold: list[str]) -> dict:
    return {
        "task": found.question, "status": found.status, "verdict": found.report.verdict if found.report else None, "text": found.text, "original": found.original,
        "right": bool(gold and has_gold(found.text, gold)), "seconds": found.seconds, "corrections": found.corrections, "tools": [s.tool for s in found.steps if s.tool],
        "alerts": [{"kind": s.kind, "level": s.alert, "reason": s.reason, "content": s.content[:120]} for s in found.steps if s.alert], "cited": sorted({c.document for c in found.citations}),
        "steps": [{"kind": s.kind, "content": s.content[:200], "failed": s.failed} for s in found.steps], "notes": found.notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", type=Path, required=True, help="holds the shelf evaluate_mixed.py made")
    args = parser.parse_args()
    questions = json.loads((FILES / "agent_tasks.json").read_text(encoding="utf-8"))
    books = Library(args.folder / "mixed.sqlite")
    engine = Engine(ENGINE_ROOT)
    engine.load()
    writer = LocalGenerator()
    results = {"tasks": [], "persian": [], "unanswerable": []}
    for group in ("tasks", "persian"):
        for case in questions[group]:
            results[group].append(row(run_agent(case["task"], books, engine, writer, (MINE,)), case["gold"]))
            print(json.dumps(results[group][-1], ensure_ascii=False), flush=True)
    for task in questions["unanswerable"]:
        results["unanswerable"].append(row(run_agent(task, books, engine, writer, (MINE,)), []))
        print(json.dumps(results["unanswerable"][-1], ensure_ascii=False), flush=True)
    books.close()
    every = results["tasks"] + results["persian"] + results["unanswerable"]
    results["summary"] = {
        "tasks": len(results["tasks"]),
        "right": sum(r["right"] for r in results["tasks"]),
        "persian_tasks": len(results["persian"]),
        "persian_right": sum(r["right"] for r in results["persian"]),
        "statuses": dict(Counter(r["status"] for r in every)),
        "unanswerable_said_none": sum(r["status"] == "not_in_documents" for r in results["unanswerable"]),
        "runs_with_a_stop": sum(any(a["level"] == "stop" for a in r["alerts"]) for r in every),
        "right_runs_with_a_stop": sum(any(a["level"] == "stop" for a in r["alerts"]) and r["right"] for r in results["tasks"]),
        "median_seconds": sorted(r["seconds"] for r in every)[len(every) // 2],
    }
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(results["summary"]))


if __name__ == "__main__":
    main()
