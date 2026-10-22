"""Does an audit estimate a system's hallucination rate correctly?

Two simulated systems, run live through the full pipeline: 90 RAGTruth dev answers (one per source group, so many
systems' answers mixed) and 60 HaluEval QA answers, a domain the model was not calibrated on. For HaluEval the audit
runs twice: with the RAGTruth calibration and with a domain profile fitted on 50 other labelled HaluEval QA answers
(their risks from the feature cache). The estimate is the mean calibrated risk; the truth comes from the labels.
Output: eval/results/audit.json
"""

import json
import random
from pathlib import Path

import numpy as np

from truth_guardian import adapt, conformal, fusion, triage
from truth_guardian.audit import audit
from truth_guardian.overrides import cached_predictions
from truth_guardian.pipeline import analyze
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "features"


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion")
    folder = ROOT / "models" / "fusion" / manifest["version"]
    base = {"model_version": manifest["version"], "calibration": conformal.load(folder, manifest["version"]), "triage_policy": triage.load(folder, manifest["version"])}
    rng = random.Random("audit-v1")

    seen, ragtruth = set(), []
    for s in rng.sample(list(read_jsonl(ROOT / "data/processed/ragtruth_dev.jsonl")), 1506):
        if s.meta.group_id not in seen:
            seen.add(s.meta.group_id)
            ragtruth.append(s)
    ragtruth = ragtruth[:90]

    halueval, predictions = cached_predictions(model, ROOT / "data/processed/xdev_halueval_qa.jsonl", FEATURES)
    order = list(range(len(halueval)))
    rng.shuffle(order)
    labelled, audited = [halueval[i] for i in order[:50]], [halueval[i] for i in order[50:110]]
    profile = adapt.fit("halueval-qa", [predictions[s.id].score for s in labelled], [s.labels.response == "hallucinated" for s in labelled], manifest["version"])

    runs = {
        "ragtruth_dev": (ragtruth, base),
        "halueval_qa_ragtruth_calibration": (audited, base),
        "halueval_qa_domain_profile": (audited, {"model_version": manifest["version"], "profile": profile}),
    }
    report = {"model_version": manifest["version"], "profile_examples": profile.examples}
    for name, (samples, options) in runs.items():
        summary, _ = audit(samples, lambda s: analyze(s, model, **options))
        report[name] = summary.model_dump()
        low, high = summary.estimate_interval
        print(f"{name}: estimated {summary.estimated_hallucination_rate:.3f} [{low:.3f}, {high:.3f}] true {summary.true_hallucination_rate:.3f}; lanes {summary.lanes}; blame {summary.blame}", flush=True)
    out = ROOT / "eval" / "results" / "audit.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
