"""Evaluate the live agent guardian: does it stop a hallucinating agent in time, and leave faithful agents alone?

Each trajectory is replayed step by step with only earlier evidence visible. Per policy: share of hallucinated
trajectories stopped (TPR), share of faithful ones stopped (FPR), any-alert rates, stop rate per error category and,
on stopped hallucinated trajectories, whether the first stop lands on the annotated responsible step, no later than it,
and before the agent's last step. Settings are fixed by design; the grid only shows their sensitivity. Dev only.
"""

import json
from collections import defaultdict
from itertools import product
from pathlib import Path

import numpy as np

from truth_guardian import guardian
from truth_guardian.schema import Sample, read_jsonl
from truth_guardian.tracer import StepTrace, TraceState

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("agenthallu_dev", "tg_agent_dev")
GRID = list(product((1, 2, 3), (False, True), (None, guardian.AFTER_ERROR_NOVELTY)))


def live_traces(sample: Sample) -> list[StepTrace]:
    state = TraceState(sample.question)
    return [state.add(step) for step in sample.agent_log or []]


def measure(samples: list[Sample], traces: dict[str, list[StepTrace]], **settings) -> dict:
    stopped, alerted, by_category = defaultdict(list), defaultdict(list), defaultdict(list)
    exact, no_later, before_end, steps_left = [], [], [], []
    for s in samples:
        g = guardian.AgentGuardian(s.question, **settings)
        for step, t in zip(s.agent_log or [], traces[s.id]):
            g.judge(step, t)
        stop = g.first_stop()
        stopped[s.labels.response].append(stop is not None)
        alerted[s.labels.response].append(bool(g.alerts))
        by_category[s.labels.category or "faithful"].append(stop is not None)
        if stop is None or s.labels.response != "hallucinated":
            continue
        steps = [st.step for st in s.agent_log]
        before_end.append(stop.step < steps[-1])
        steps_left.append((len(steps) - 1 - steps.index(stop.step)) / len(steps))
        if s.labels.responsible_step is not None:
            exact.append(stop.step == s.labels.responsible_step)
            no_later.append(stop.step <= s.labels.responsible_step)
    mean = lambda v: float(np.mean(v)) if v else None
    tpr, fpr = mean(stopped["hallucinated"]), mean(stopped["grounded"])
    return settings | {
        "stop_tpr": tpr, "stop_fpr": fpr, "youden": tpr - fpr,
        "any_alert_hallucinated": mean(alerted["hallucinated"]), "any_alert_faithful": mean(alerted["grounded"]),
        "stop_rate_by_category": {c: mean(v) for c, v in sorted(by_category.items())},
        "stop_on_responsible_step": mean(exact), "stop_no_later_than_responsible_step": mean(no_later),
        "stop_before_last_step": mean(before_end), "share_of_steps_left_after_stop": mean(steps_left),
    }


def main() -> None:
    report = {}
    for name in DATASETS:
        samples = list(read_jsonl(ROOT / "data/processed" / f"{name}.jsonl"))
        traces = {s.id: live_traces(s) for s in samples}
        report[name] = {
            "trajectories": len(samples),
            "policies": {p: measure(samples, traces, policy=p) for p in ("strict", "lenient")},
            "sensitivity_strict": [measure(samples, traces, min_new_values=m, watch_actions=w, after_error_novelty=e) for m, w, e in GRID],
        }
        print(name)
        for p, r in report[name]["policies"].items():
            print(f"  {p:8} stop TPR {r['stop_tpr']:.2f} FPR {r['stop_fpr']:.2f} | any alert {r['any_alert_hallucinated']:.2f} / {r['any_alert_faithful']:.2f} | "
                  f"on origin {r['stop_on_responsible_step']} no later {r['stop_no_later_than_responsible_step']} before last {r['stop_before_last_step']}")
            print(f"           {r['stop_rate_by_category']}")
        for r in report[name]["sensitivity_strict"]:
            print(f"    min_new {r['min_new_values']} actions {str(r['watch_actions']):5} after_error {str(r['after_error_novelty']):4}: TPR {r['stop_tpr']:.2f} FPR {r['stop_fpr']:.2f}")
    out = ROOT / "eval" / "results" / "guardian.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"saved {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
