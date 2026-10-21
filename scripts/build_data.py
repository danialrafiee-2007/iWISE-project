"""Build processed datasets from data/raw: convert, split, lock test sets, and write the data card."""

from pathlib import Path

from truth_guardian.data.card import render_card
from truth_guardian.data.halueval import TASK_FILES, load_halueval
from truth_guardian.data.ragtruth import load_ragtruth
from truth_guardian.data.splits import assign_dev, check_no_group_leak, sample_groups
from truth_guardian.schema import write_jsonl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
LOCKED = OUT / "locked"
HALUEVAL_GROUPS_PER_TASK = 500
HALUEVAL_DEV_GROUPS_PER_TASK = 250


def main() -> None:
    ragtruth = assign_dev(load_ragtruth(RAW / "ragtruth"))
    check_no_group_leak(ragtruth)

    files = {
        "ragtruth_train": [s for s in ragtruth if s.meta.split == "train"],
        "ragtruth_dev": [s for s in ragtruth if s.meta.split == "dev"],
        "ragtruth_test": [s for s in ragtruth if s.meta.split == "test"],
    }
    for task in TASK_FILES:
        halueval = list(load_halueval(RAW / "halueval", task))
        files[f"halueval_{task}"] = sample_groups(halueval, HALUEVAL_GROUPS_PER_TASK)
        external_dev = sample_groups(halueval, HALUEVAL_DEV_GROUPS_PER_TASK, offset=HALUEVAL_GROUPS_PER_TASK)
        files[f"xdev_halueval_{task}"] = [s.model_copy(update={"meta": s.meta.model_copy(update={"split": "dev"})}) for s in external_dev]

    for name, samples in files.items():
        target = (LOCKED if name.endswith("test") or name.startswith("halueval") else OUT) / f"{name}.jsonl"
        print(f"{target.relative_to(ROOT).as_posix()}: {write_jsonl(samples, target)} samples")

    provenance = [
        "RAGTruth: ParticleMedia/RAGTruth @ c103204b (MIT); official test split kept as the locked test set",
        "Dev: 10% of RAGTruth train sources per task, chosen by hash of source id (seed tg-dev-v1)",
        f"HaluEval: RUCAIBox/HaluEval @ b7253db3 (MIT); {HALUEVAL_GROUPS_PER_TASK} question groups per task (seed tg-subset-v1); 'general' excluded (no source documents)",
        f"External dev (xdev_halueval_*): the next {HALUEVAL_DEV_GROUPS_PER_TASK} groups per task in the same ranking, disjoint from the locked HaluEval files",
        "Locked files live in data/processed/locked and may only be evaluated with --final",
    ]
    card = ROOT / "docs" / "DATA_CARD.md"
    card.write_text(render_card(files, provenance), encoding="utf-8", newline="\n")
    print(f"wrote {card.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
