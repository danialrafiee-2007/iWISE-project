"""The model card shown in the web app, read from the committed evaluation results (nothing is typed in by hand).

Every number names the file it comes from; a missing file leaves its section out. The locked test set is reported
only once its result file exists.
"""

import json
from pathlib import Path

FINAL = "M2-ensemble-final__ragtruth_dev.json"
BASELINES = {"B1 lexical overlap": "B1-lexical__ragtruth_dev.json", "B2 embedding similarity": "B2-embedding__ragtruth_dev.json", "B3 NLI": "B3-nli__ragtruth_dev.json"}
ANALYSIS = "analysis__ensemble-lexical+symbolic+dense+hhem-nostructure.json"
SUITE = "perturbations__ensemble-lexical+symbolic+dense+hhem-nostructure-polarity-shifts.json"
LOCKED = "M2-ensemble-final__ragtruth_test.json"


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def model_card(root: Path) -> dict:
    results = root / "eval" / "results"
    card: dict = {"sources": {}}

    def use(name: str, folder: Path = results) -> dict | None:
        data = _read(folder / name)
        if data is not None:
            card["sources"][name] = (folder / name).relative_to(root).as_posix()
        return data

    if final := use(FINAL):
        r, s = final["response"], final["span"]
        card["ragtruth_dev"] = {
            "answers": r["n"], "hallucinated_share": r["hallucinated_rate"], "auroc": r["auroc"], "auroc_ci95": final.get("ci95", {}).get("auroc"),
            "f1": r["f1"], "f1_flag_everything": r["f1_flag_everything"], "precision": r["precision"], "recall": r["recall"],
            "ece": r["ece"], "span_f1": s["f1"], "by_task": {t: {"n": v["n"], "auroc": v["auroc"]} for t, v in final.get("breakdown", {}).get("task", {}).items()},
        }
    card["baselines"] = {name: {"auroc": d["response"]["auroc"], "span_f1": d["span"]["f1"]} for name, file in BASELINES.items() if (d := use(file))}
    if analysis := use(ANALYSIS):
        full = analysis["full"]
        card["halueval"] = {"qa": full["xdev_qa_auroc"], "dialogue": full["xdev_dialogue_auroc"], "summary": full["xdev_summary_auroc"], "answers_per_task": analysis["xdev_samples"]["xdev_qa_auroc"]}
        card["train"] = {"answers": analysis["train_samples"], "out_of_fold_auroc": full["oof_response_auroc"]}
    if suite := use(SUITE):
        card["fool_the_guardian"] = {
            "controls_flagged": suite["control_false_alarm_rate"],
            "edits": {k: {"n": v["n"], "detected": v["detected"], "auroc": v["auroc_vs_controls"], "located": v["located"], "cautioned": v.get("cautioned")} for k, v in suite["by_edit"].items()},
        }
    if conformal := use("conformal.json"):
        p = conformal["pooled"]["0.1"]
        card["guarantee"] = {"alpha": 0.1, "splits": conformal["splits"], "miss_rate": p["miss_rate_catch"], "false_alarm_rate": p["false_alarm_rate_alarm"]}
    if triage := use("triage.json"):
        card["triage"] = {**triage["held_out"], "pass_below": triage["final_policy"]["pass_below"], "block_from": triage["final_policy"]["block_from"]}
    if healing := use("healing.json"):
        card["healing"] = healing["strategies"]["full"]
    if tracer := use("tracer_learned__tg_agent_dev.json"):
        card["tracer_tg_agent"] = {"trajectories": tracer["trajectories"], "detection_auroc": tracer["detection_auroc"], **{k: tracer["localization"]["all"][k] for k in ("tracer_exact", "tracer_within_1", "baseline_random")}}
    if agenthallu := use("tracer_learned__agenthallu_dev.json"):
        card["tracer_agenthallu"] = {"trajectories": agenthallu["trajectories"], "detection_auroc": agenthallu["detection_auroc_learned"], "exact": agenthallu["localization"]["all"]["learned_exact"], "random": agenthallu["localization"]["all"]["random"]}
    if guardian := use("guardian.json"):
        card["guardian"] = {name: {k: p[k] for k in ("stop_tpr", "stop_fpr", "stop_on_responsible_step")} for name, p in guardian["tg_agent_dev"]["policies"].items()}
    if speed := use("speed_onnx.json"):
        card["speed"] = {"answers": speed["answers"], "cold_start_seconds": speed["cold_start_seconds"], **{k: speed["warm_seconds"][k] for k in ("mean", "p95")}}
    card["locked_test"] = (lambda d: {"auroc": d["response"]["auroc"], "f1": d["response"]["f1"], "span_f1": d["span"]["f1"]} if d else None)(use(LOCKED))
    return card
