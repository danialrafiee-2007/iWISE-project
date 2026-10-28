"""The multilingual check (D-138) on its evaluation sets, language by language and dataset by dataset.

Scores each set with the saved multilingual model from the cached signals: the dev set (by language and by source), the
same sources' English answers beside the English engine's scores on them (identical items, so the two checks compare
directly), and XQuAD's controlled edits, the one labelled set in Russian. AUROC, with 95% intervals over whole sources,
needs no threshold; F1 uses the model's one threshold, tuned on the pooled dev set, so dev F1 is optimistic. Writes
eval/results/multilingual_dev.json.
"""

import json
from collections import defaultdict
from pathlib import Path

from truth_guardian import fusion
from truth_guardian.data.multilingual import language_of
from truth_guardian.evaluation import evaluate, read_predictions
from truth_guardian.features import load_rows, usable
from truth_guardian.schema import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
FEATURES = ROOT / "data" / "features"
SETS = ("multilingual_dev", "multilingual_dev_en", "xquad_edits")


def manifest_of(folder: Path) -> dict:
    return json.loads((folder / (folder / "LATEST").read_text(encoding="utf-8").strip() / "manifest.json").read_text(encoding="utf-8"))


def row(report: dict) -> dict:
    r = report["response"]
    return {
        "n": r["n"], "hallucinated": round(r["hallucinated_rate"], 3), "auroc": round(r.get("auroc", float("nan")), 3),
        "auroc_ci95": [round(x, 3) for x in report["ci95"]["auroc"] or []], "f1": round(r["f1"], 3),
        "f1_flag_everything": round(r["f1_flag_everything"], 3), "span_f1": round(report["span"]["f1"], 3) if report["span"] else None,
    }


def main() -> None:
    model, manifest = fusion.load(ROOT / "models" / "fusion-multilingual")
    threshold, sentence = model.thresholds["response"], model.thresholds["sentence"]
    results = {"model": manifest["version"], "threshold": threshold, "sentence_threshold": sentence, "sets": {}}
    for name in SETS:
        path = DATA / f"{name}.jsonl"
        try:
            rows = load_rows(model.signals, path, FEATURES)
        except FileNotFoundError:
            print(f"{name}: no cached signals, skipped")
            continue
        samples = usable(list(read_jsonl(path)), rows)
        predictions = {p.id: p for p in model.predictions(samples, fusion.build_table(samples, rows, model.signals, model.structure))}
        groups = defaultdict(list)
        for s in samples:
            groups[s.meta.dataset].append(s)
            groups[f"language {language_of(s)}"].append(s)
        by = {g: row(evaluate(groups[g], predictions, threshold, sentence, bootstrap_rounds=500)) for g in sorted(groups, key=lambda n: (not n.startswith("language"), n))}
        results["sets"][name] = by
        if name == "multilingual_dev_en":
            shipped = manifest_of(ROOT / "models" / "fusion")
            engine = read_predictions(ROOT / "eval" / "predictions" / f"{shipped['name']}__ragtruth_dev.jsonl")
            t = shipped["thresholds"]
            by["English engine, same answers"] = row(evaluate(samples, engine, t["response"], t["sentence"], bootstrap_rounds=500))

    out = ROOT / "eval" / "results" / "multilingual_dev.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    for name, by in results["sets"].items():
        print(f"\n{name}\n{'':28} {'n':>5} {'halluc.':>8} {'AUROC':>6} {'95% interval':>13} {'F1':>6} {'flag-all F1':>11}")
        for group, r in by.items():
            ci = "-".join(f"{x:.2f}" for x in r["auroc_ci95"])
            print(f"{group:28} {r['n']:>5} {r['hallucinated']:>8.0%} {r['auroc']:>6.3f} {ci:>13} {r['f1']:>6.3f} {r['f1_flag_everything']:>11.3f}")
    print(f"\n-> {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
