"""Build the multilingual check's data from data/raw (D-138): a train set, a dev set, and PsiloQA's test as a locked set.

The CPU reads mDeBERTa NLI at about three pairs a second here (ONNX was no faster; int8 kept only 16% of its labels), so
the sets are sampled by whole source groups, chosen by hash: RAGTruth's translated rows by the same sources in Spanish,
French and Chinese (and, apart, the same sources' English responses, to compare with the English engine on identical
items), PsiloQA by Wikipedia article. XQuAD's controlled edits (data/xquad.py) are an evaluation set of their own.
"""

import hashlib
import json
from pathlib import Path

from truth_guardian.data.card import render_card
from truth_guardian.data.multilingual import PSILOQA_LANGUAGES, load_psiloqa, load_ragtruth_translated
from truth_guardian.data.splits import check_no_group_leak, sample_groups
from truth_guardian.data.xquad import LANGUAGES as XQUAD_LANGUAGES
from truth_guardian.data.xquad import load_xquad_edits
from truth_guardian.schema import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
LOCKED = OUT / "locked"
TRANSLATED = ("es", "fr", "zh")
TRAIN_SOURCES_PER_TASK = 25  # x 6 responses x 3 languages = 1,350 RAGTruth answers
DEV_SOURCES_PER_TASK = 20  # x 6 responses x 4 languages (with English) = 1,440
PSILOQA_TRAIN_PER_LANGUAGE = 300  # articles; about 2.4 answers each
XQUAD_QUESTIONS = 300  # x 2 answers x 5 languages
SEED = "tg-multilingual-v1"


def by_task_groups(samples: list, per_task: int) -> set[str]:
    groups = set()
    for task in sorted({s.meta.task for s in samples}):
        groups |= {s.meta.group_id for s in sample_groups([s for s in samples if s.meta.task == task], per_task, seed=SEED)}
    return groups


def main() -> None:
    english_dev = list(read_jsonl(OUT / "ragtruth_dev.jsonl"))
    english_train_groups = {s.meta.group_id for s in read_jsonl(OUT / "ragtruth_train.jsonl")}
    translated = {code: list(load_ragtruth_translated(RAW, code, {s.id for s in english_dev})) for code in TRANSLATED}
    first = translated[TRANSLATED[0]]
    train_groups = by_task_groups([s for s in first if s.meta.split == "train" and s.meta.group_id in english_train_groups], TRAIN_SOURCES_PER_TASK)
    dev_groups = by_task_groups([s for s in first if s.meta.split == "dev"], DEV_SOURCES_PER_TASK)

    train = [s for code in TRANSLATED for s in translated[code] if s.meta.group_id in train_groups and s.meta.split == "train"]
    dev = [s for code in TRANSLATED for s in translated[code] if s.meta.group_id in dev_groups and s.meta.split == "dev"]
    # English answers go to the English engine, so they only compare the two checks and never set the threshold.
    dev_english = [s.model_copy(update={"meta": s.meta.model_copy(update={"dataset": "ragtruth_en"})}) for s in english_dev if s.meta.group_id in dev_groups]

    psilo = {split: list(load_psiloqa(RAW, split)) for split in ("train", "validation", "test")}
    # PsiloQA's own splits share articles; the locked test keeps all of its own, dev and train give theirs up.
    test_groups = {s.meta.group_id for s in psilo["test"]}
    psilo_dev = [s for s in psilo["validation"] if s.meta.group_id not in test_groups]
    held = test_groups | {s.meta.group_id for s in psilo_dev}
    leaked = {s.meta.group_id for s in psilo["train"]} & held
    for code in PSILOQA_LANGUAGES:
        own = [s for s in psilo["train"] if s.meta.dataset == f"psiloqa_{code}" and s.meta.group_id not in held]
        train += sample_groups(own, PSILOQA_TRAIN_PER_LANGUAGE, seed=SEED)
    dev += psilo_dev
    check_no_group_leak(train + dev + dev_english + psilo["test"])

    # The same XQuAD questions in every language, chosen by hash; an evaluation set only (data/xquad.py).
    every = [{qa["id"] for a in json.loads((RAW / "xquad" / f"xquad.{code}.json").read_text(encoding="utf-8"))["data"] for p in a["paragraphs"] for qa in p["qas"]} for code in XQUAD_LANGUAGES]
    chosen = set(sorted(set.intersection(*every), key=lambda q: hashlib.sha256(f"{SEED}:{q}".encode()).hexdigest())[:XQUAD_QUESTIONS])
    edits = [s for code in XQUAD_LANGUAGES for s in load_xquad_edits(RAW, code, chosen)]

    files = {"multilingual_train": train, "multilingual_dev": dev, "multilingual_dev_en": dev_english, "xquad_edits": edits, "psiloqa_test": psilo["test"]}
    for name, samples in files.items():
        target = (LOCKED if name.endswith("test") else OUT) / f"{name}.jsonl"
        print(f"{target.relative_to(ROOT).as_posix()}: {write_jsonl(samples, target)} samples")
    provenance = [
        "RAGTruth translated by KRLabs with Gemma 3 27B (MIT): ragtruth-es-translated @ 39d88100, ragtruth-fr-translated @ 95d0aa3e, "
        "ragtruth-cn-translated @ 1f3db52b; train files only (their test files translate the locked RAGTruth test set)",
        f"Rows matched to English RAGTruth train by order; dev = the English dev's sources. Sampled by source (seed {SEED}): "
        f"{TRAIN_SOURCES_PER_TASK} train and {DEV_SOURCES_PER_TASK} dev sources per task, the same ones in every language; "
        "multilingual_dev_en holds those sources' English responses (ragtruth_en), only to compare with the English engine",
        f"PsiloQA @ 375c3321 (CC BY 4.0), {', '.join(PSILOQA_LANGUAGES)} only; spans labelled by GPT-4o, not by people; "
        f"{PSILOQA_TRAIN_PER_LANGUAGE} train articles per language (articles also in dev or test dropped: {len(leaked)}); "
        f"validation as dev without the articles it shares with test ({len(psilo['validation']) - len(psilo_dev)} answers dropped); test locked",
        f"XQuAD @ 7d30520c (CC BY-SA 4.0): controlled edits of the same {XQUAD_QUESTIONS} questions in {', '.join(XQUAD_LANGUAGES)} "
        "(the answer's context sentence, and the same sentence with its number plus one or another question's answer); "
        "synthetic, evaluation only, never used for training or thresholds",
        "Locked files live in data/processed/locked and may only be evaluated with --final",
    ]
    card = ROOT / "docs" / "DATA_CARD_MULTILINGUAL.md"
    text = render_card(files, provenance).replace("# Data Card", "# Data Card: multilingual check", 1)
    card.write_text(text.replace("scripts/build_data.py", "scripts/build_multilingual.py", 1), encoding="utf-8", newline="\n")
    print(f"wrote {card.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
