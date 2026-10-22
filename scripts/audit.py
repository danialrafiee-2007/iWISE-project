"""Audit a RAG system: run every answer in a log through the guardian and write its health summary.

Input: a JSONL file, one answer per line, either in the project's Sample format or simply
{"id": ..., "question": ..., "sources": [...], "answer": ...}. With --profile, a domain profile (adapt.py) replaces
the RAGTruth calibration. Output: <out>/summary.json and <out>/reports.jsonl (one full report per answer).
"""

import argparse
import json
from pathlib import Path

from truth_guardian import adapt, conformal, fusion, triage
from truth_guardian.audit import audit
from truth_guardian.pipeline import analyze, make_sample
from truth_guardian.schema import Sample

ROOT = Path(__file__).resolve().parents[1]


def read_log(path: Path, limit: int | None) -> list[Sample]:
    samples = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        if "documents" in row:
            samples.append(Sample.model_validate(row))
        else:
            samples.append(make_sample(row["answer"], row.get("sources", []), row.get("question"), sample_id=str(row.get("id", i))))
        if limit and len(samples) == limit:
            break
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", type=Path, help="a domain profile JSON from adapt.fit")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--final", action="store_true", help="required for locked test data")
    args = parser.parse_args()
    if "locked" in args.input.resolve().parts and not args.final:
        parser.error("locked test data needs --final")

    model, manifest = fusion.load(ROOT / "models" / "fusion")
    folder = ROOT / "models" / "fusion" / manifest["version"]
    options = {"model_version": manifest["version"], "calibration": conformal.load(folder, manifest["version"]), "triage_policy": triage.load(folder, manifest["version"])}
    if args.profile:
        profile = adapt.load(args.profile, manifest["version"])
        if profile is None:
            parser.error(f"{args.profile} was made for another model version")
        options["profile"] = profile
    samples = read_log(args.input, args.limit)
    summary, reports = audit(samples, lambda s: analyze(s, model, **options), lambda i, n: print(f"{i}/{n}", flush=True) if i % 10 == 0 or i == n else None)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8", newline="\n")
    with (args.out / "reports.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for report in reports:
            f.write(report.model_dump_json() + "\n")
    low, high = summary.estimate_interval
    truth = f", true {summary.true_hallucination_rate:.0%}" if summary.true_hallucination_rate is not None else ""
    print(f"{summary.answers} answers: estimated hallucinated {summary.estimated_hallucination_rate:.0%} [{low:.0%}, {high:.0%}]{truth}")
    print(f"lanes {summary.lanes}  blame {summary.blame}")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
