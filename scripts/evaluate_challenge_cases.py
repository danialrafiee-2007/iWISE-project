"""Run the TG-Bench challenge cases through the live guardian (the web app's engine, strict policy) and score each case.

Per case, the check that matters for it: mixed answers (is the wrong part found and the correct parts kept?), partial
use of the evidence (is the left-out fact or the dropped caveat noticed?), unsupported claims (found and called
unsupported?), weak sources (is the retriever blamed?), agent runs (is the step where the error began found, and does
the guardian stop the run?). Every case is compared with its paired faithful answers. Nothing is tuned on this set.
Output: eval/results/challenge_cases.json
"""

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from truth_guardian.data.challenge_cases import case_of, load
from truth_guardian.report import Report
from truth_guardian.schema import Sample
from truth_guardian.text import content_words
from truth_guardian.web.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmark" / "challenge_cases.json"
SAME_SENTENCE = 0.6


def overlaps(a: int, b: int, spans) -> bool:
    return any(a < s.end and s.start < b for s in spans)


def mentions(reported: list[str], left_out: str) -> bool:
    words = content_words(left_out)
    return any(len(words & content_words(r)) >= SAME_SENTENCE * len(words) for r in reported)


def outcome(sample: Sample, report: Report) -> dict:
    gold = sample.labels.spans
    on_gold = [c for c in report.claims if overlaps(c.start, c.end, gold)]
    off_gold = [c for c in report.claims if not overlaps(c.start, c.end, gold)]
    missing = report.completeness.missing if report.completeness else []
    caveats = report.completeness.omitted_caveats if report.completeness else []
    out = {
        "id": sample.id, "case": case_of(sample), "category": sample.labels.category,
        "risk": round(report.risk, 4), "verdict": report.verdict, "flagged": report.risk >= report.response_threshold,
        "statuses": [c.status for c in on_gold],
        "located": any(c.status != "supported" for c in on_gold),
        "cautioned": any(c.cautions for c in on_gold),
        "kept": [c.status == "supported" for c in off_gold],
        "missing": len(missing), "omitted_caveats": len(caveats),
        "left_out_reported": mentions(missing, sample.labels.reason) if sample.labels.reason else None,
        "blame": report.diagnosis.blame if report.diagnosis else None,
    }
    if report.agent is not None:
        out |= {
            "agent_risk": round(report.agent.risk, 4), "suspected_step": report.agent.suspected_step,
            "responsible_step": sample.labels.responsible_step, "guardian_stop": report.agent.guardian_stop,
        }
    return out


def rate(values) -> float | None:
    values = list(values)
    return float(np.mean(values)) if values else None


def auroc(positives: list[float], negatives: list[float]) -> float | None:
    if not positives or not negatives:
        return None
    return float(roc_auc_score([1] * len(positives) + [0] * len(negatives), positives + negatives))


def summarise(items: list[dict]) -> dict:
    by = lambda case: [i for i in items if i["case"] == case]
    control, weak_control, agent_control = by("control"), by("weakcontrol"), by("agentcontrol")
    mixed, unsupported, weak, agent = by("mixed"), by("unsupported"), by("weak"), by("agent")
    omission = [i for i in by("partial") if i["category"] == "partial: omission"]
    caveat = [i for i in by("partial") if i["category"] == "partial: caveat"]
    risks = lambda xs, key="risk": [x[key] for x in xs]
    steps = [(i["suspected_step"], i["responsible_step"]) for i in agent]
    cases = {
        "mixed": {
            "n": len(mixed), "caught": rate(i["flagged"] for i in mixed), "wrong_part_found": rate(i["located"] for i in mixed),
            "correct_parts_kept": rate(k for i in mixed for k in i["kept"]), "auroc_vs_faithful": auroc(risks(mixed), risks(control)),
            "wrong_part_found_but_answer_passed": rate(i["located"] and not i["flagged"] for i in mixed),
        },
        "partial": {
            "n": len(omission) + len(caveat),
            "omission": {"n": len(omission), "left_out_reported": rate(i["left_out_reported"] for i in omission), "flagged": rate(i["flagged"] for i in omission)},
            "caveat": {
                "n": len(caveat), "caught": rate(i["flagged"] for i in caveat), "overstated_part_found": rate(i["located"] for i in caveat),
                "noticed": rate(i["located"] or i["cautioned"] or i["omitted_caveats"] > 0 or i["left_out_reported"] for i in caveat),
                "auroc_vs_faithful": auroc(risks(caveat), risks(control)),
            },
        },
        "unsupported": {
            "n": len(unsupported), "caught": rate(i["flagged"] for i in unsupported), "claim_found": rate(i["located"] for i in unsupported),
            "called_unsupported": rate(any(s in {"unsupported", "insufficient_evidence"} for s in i["statuses"]) for i in unsupported),
            "auroc_vs_faithful": auroc(risks(unsupported), risks(control)),
        },
        "weak": {
            "n": len(weak), "caught": rate(i["flagged"] for i in weak), "retrieval_blamed": rate(i["blame"] == "retrieval" for i in weak),
            "auroc_vs_honest": auroc(risks(weak), risks(weak_control)),
        },
        "agent": {
            "n": len(agent), "caught": rate(i["flagged"] for i in agent), "guardian_stopped": rate(i["guardian_stop"] is not None for i in agent),
            "exact_step": rate(s == r for s, r in steps), "within_one_step": rate(s is not None and abs(s - r) <= 1 for s, r in steps),
            "auroc_answer_risk_vs_faithful": auroc(risks(agent), risks(agent_control)),
            "auroc_tracer_risk_vs_faithful": auroc(risks(agent, "agent_risk"), risks(agent_control, "agent_risk")),
            "by_kind": {
                kind: {"n": len(xs), "caught": rate(i["flagged"] for i in xs), "exact_step": rate(i["suspected_step"] == i["responsible_step"] for i in xs)}
                for kind in ("generate", "revise", "stale", "handoff") if (xs := [i for i in agent if i["category"] == f"agent: {kind}"])
            },
        },
    }
    controls = {
        "faithful": {"n": len(control), "flagged": rate(i["flagged"] for i in control), "completeness_reported_missing": rate(i["missing"] > 0 for i in control)},
        "honest_over_weak_sources": {
            "n": len(weak_control), "flagged": rate(i["flagged"] for i in weak_control),
            "blamed_sources": rate(i["blame"] in {"weak_sources", "retrieval"} for i in weak_control),
        },
        "faithful_agents": {"n": len(agent_control), "flagged": rate(i["flagged"] for i in agent_control), "guardian_stopped": rate(i["guardian_stop"] is not None for i in agent_control)},
    }
    problems = mixed + caveat + unsupported + weak
    overall = auroc(risks(problems), risks(control + weak_control))
    return {"cases": cases, "controls": controls, "auroc_answers_vs_faithful": overall}


def main() -> None:
    samples = load(SPEC)
    engine = Engine(ROOT)
    engine.load()
    started = time.perf_counter()
    items = [outcome(s, engine.analyze(s)) for s in samples]
    elapsed = time.perf_counter() - started
    report = {
        "set": SPEC.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "model_version": engine.version, "tracer_version": engine.tracer_manifest["version"], "policy": "strict",
        "samples": len(samples), "seconds_per_sample": elapsed / len(samples), **summarise(items), "items": items,
    }
    out = ROOT / "eval" / "results" / "challenge_cases.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("cases", "controls", "auroc_answers_vs_faithful")}, indent=2))
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
