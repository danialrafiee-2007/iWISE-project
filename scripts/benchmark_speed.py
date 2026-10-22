"""Measure the live pipeline's speed on this machine: cold start, then per-answer latency on dev answers.

Each answer comes from a different source group (no shared documents, so caches do not flatter the numbers).
Run once as is and once with TG_NO_ONNX=1; the second run also checks that both give the same risks.
Output: eval/results/speed_<onnx|torch>.json
"""

import json
import os
import platform
import time
from pathlib import Path

import numpy as np

from truth_guardian import fusion, models
from truth_guardian.pipeline import analyze
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
ANSWERS = 20


def main() -> None:
    started = time.perf_counter()
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    seen, chosen = set(), []
    for s in read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl"):
        if s.meta.group_id not in seen:
            seen.add(s.meta.group_id)
            chosen.append(s)
    first = analyze(chosen[0], model)
    cold = time.perf_counter() - started
    mode = "onnx" if models._hhem_onnx() is not None else "torch"
    latencies, risks = [], {chosen[0].id: first.risk}
    for s in chosen[1 : ANSWERS + 1]:
        t = time.perf_counter()
        risks[s.id] = analyze(s, model).risk
        latencies.append(time.perf_counter() - t)
    report = {
        "mode": mode,
        "model_version": manifest["version"],
        "machine": {"processor": platform.processor(), "logical_cpus": os.cpu_count(), "system": platform.platform()},
        "cold_start_seconds": cold,
        "answers": len(latencies),
        "warm_seconds": {"mean": float(np.mean(latencies)), "p50": float(np.percentile(latencies, 50)), "p95": float(np.percentile(latencies, 95)), "max": float(np.max(latencies))},
        "risks": risks,
    }
    other = ROOT / "eval" / "results" / f"speed_{'onnx' if mode == 'torch' else 'torch'}.json"
    if other.exists():
        theirs = json.loads(other.read_text(encoding="utf-8"))["risks"]
        report["max_risk_difference_vs_other_mode"] = max(abs(risks[k] - theirs[k]) for k in risks if k in theirs)
    out = ROOT / "eval" / "results" / f"speed_{mode}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    w = report["warm_seconds"]
    print(f"{mode}: cold start {cold:.1f}s; warm per answer mean {w['mean']:.2f}s, p50 {w['p50']:.2f}s, p95 {w['p95']:.2f}s")
    if "max_risk_difference_vs_other_mode" in report:
        print(f"max risk difference vs the other mode: {report['max_risk_difference_vs_other_mode']:.2e}")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
