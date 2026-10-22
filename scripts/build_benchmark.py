"""Build TG-Bench, the project's open mini-benchmark, from RAGTruth dev, and check it matches the published release.

TG-Bench = the Fool-the-Guardian suite (controlled edits of grounded answers) and TG-Agent (scripted agent runs with
one injected error each). Both are rebuilt deterministically from data/processed/ragtruth_dev.jsonl, so the release
carries only labels and recipes (benchmark/*.labels.jsonl) and checksums, never the third-party source texts.
--write refreshes the published labels and checksums; without it the rebuilt files are checked against them.
"""

import argparse
import hashlib
import json
import runpy
from pathlib import Path

from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "benchmark"
PARTS = {
    "fool_the_guardian": ("build_perturbations.py", ROOT / "data/processed/perturb_dev.jsonl"),
    "tg_agent": ("build_tg_agent.py", ROOT / "data/processed/tg_agent_dev.jsonl"),
}


def labels(name: str, path: Path) -> list[dict]:
    rows = []
    for s in read_jsonl(path):
        row = {"id": s.id, "group": s.meta.group_id, "response": s.labels.response, "category": s.labels.category}
        if name == "fool_the_guardian":
            row["kind"] = s.id.split("-")[1]
            row["spans"] = [{"start": sp.start, "end": sp.end, "text": sp.text, "original": (sp.note or "").removeprefix("Original: ")} for sp in s.labels.spans]
        else:
            row["responsible_step"] = s.labels.responsible_step
            row["steps"] = len(s.agent_log or [])
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="refresh the published labels and checksums")
    args = parser.parse_args()
    checksums_path = RELEASE / "checksums.json"
    published = json.loads(checksums_path.read_text(encoding="utf-8")) if checksums_path.exists() else {}
    current = {}
    for name, (script, path) in PARTS.items():
        runpy.run_path(str(ROOT / "scripts" / script), run_name="__main__")
        current[name] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "samples": sum(1 for _ in read_jsonl(path))}
        if args.write:
            RELEASE.mkdir(exist_ok=True)
            with (RELEASE / f"{name}.labels.jsonl").open("w", encoding="utf-8", newline="\n") as f:
                for row in labels(name, path):
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if args.write:
        checksums_path.write_text(json.dumps(current, indent=2), encoding="utf-8", newline="\n")
        print(f"wrote labels and checksums to {RELEASE.relative_to(ROOT).as_posix()}")
        return
    for name, info in current.items():
        expected = published.get(name, {}).get("sha256")
        print(f"{name}: {info['samples']} samples, {'matches the release' if expected == info['sha256'] else 'DOES NOT match the release'}")


if __name__ == "__main__":
    main()
