"""Readiness check for running the web app offline: what is present, what is missing, and how to get it.

Nothing here touches the network; Hugging Face models are looked up in the local cache only.
"""

import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.media import models_dir, multilingual
from truth_guardian.polarity import NLTK_DATA
from truth_guardian.web.app import STATIC

SETUP = (
    "run TruthGuardian.bat setup once with internet"
    if sys.platform == "win32"
    else "run python -m truth_guardian.web --prepare once with internet (in Docker: rebuild the image, docker compose build)"
)


class Item(NamedTuple):
    name: str
    ok: bool
    required: bool
    hint: str


def _cached(repo: str, revision: str | None = None) -> bool:
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(repo, revision=revision, local_files_only=True)
        return True
    except Exception:
        return False


def _trained(root: Path, kind: str) -> bool:
    latest = root / "models" / kind / "LATEST"
    return latest.exists() and (root / "models" / kind / latest.read_text(encoding="utf-8").strip() / "model.joblib").exists()


def _portable(root: Path) -> bool:
    """uv, Python, the package cache and the language models all live in runtime/, so a copy of the folder runs offline."""
    from huggingface_hub import constants

    runtime = (root / "runtime").resolve()
    return (
        (runtime / "uv" / "uv.exe").exists()
        and (runtime / "uv-cache").is_dir()
        and Path(sys.base_prefix).resolve().is_relative_to(runtime)
        and Path(constants.HF_HUB_CACHE).resolve().is_relative_to(runtime)
    )


def readiness(root: Path) -> list[Item]:
    processed = root / "data" / "processed"
    onnx = models.HHEM_ONNX.exists() and models.HHEM_ONNX.with_suffix(".json").exists() and models.HHEM_TOKENIZER.exists()
    hhem = onnx or (_cached(models.HHEM_MODEL, models.HHEM_REVISION) and _cached("google/flan-t5-base"))
    readers = all((models_dir() / name).is_dir() for name in (multilingual.E5, multilingual.NLI))
    return [
        Item("built web front end", (STATIC / "index.html").exists(), True, "cd web && npm install && npm run build"),
        Item("trained fusion model and tracer", _trained(root, "fusion") and _trained(root, "tracer"), True, "restore models/fusion and models/tracer from the repository"),
        Item("sentence encoder (all-MiniLM-L6-v2)", _cached(models.EMBEDDING_MODEL, models.REVISIONS[models.EMBEDDING_MODEL]), True, SETUP),
        Item("NLI model (nli-deberta-v3-base)", _cached(models.NLI_MODEL, models.REVISIONS[models.NLI_MODEL]), True, SETUP),
        Item("HHEM consistency model", hhem, True, SETUP),
        Item("spaCy English model", importlib.util.find_spec("en_core_web_sm") is not None, True, SETUP),
        Item("WordNet", (NLTK_DATA / "corpora" / "wordnet").exists(), True, SETUP),
        Item("fast HHEM (ONNX export)", onnx, False, f"{SETUP} (about 35% faster per answer)"),
        Item("development data for the examples", (processed / "ragtruth_dev.jsonl").exists(), False, f"{SETUP} (without it only the written showcase examples appear)"),
        Item("Fool-the-Guardian answers", (processed / "perturb_dev.jsonl").exists(), False, f"{SETUP} (the game needs them)"),
        Item("TG-Agent trajectories", (processed / "tg_agent_dev.jsonl").exists(), False, f"{SETUP} (without them only the written agent example appears)"),
        Item("exact-word detector", (root / "models" / "detector" / "full" / "model.safetensors").exists(), False, "unzip truth-guardian-word-detector.zip from the repository's Releases into this folder, or train it: uv run python scripts/train_detector.py --full (about 7 hours; without it flagged claims mark the whole sentence)"),
        Item("check of other languages", readers, False, f"{SETUP} (without them answers in other languages are not checked)"),
        Item("domain profiles", any((root / "models" / "profiles").glob("*.json")), False, "restore models/profiles from the repository (without them the Domain profile menu is hidden)"),
    ] + ([Item("portable folder (runtime)", _portable(root), False, f"{SETUP}; afterwards the whole folder runs offline on another Windows computer")] if sys.platform == "win32" else [])


def report(root: Path) -> bool:
    """Print the checklist; True when everything required is present."""
    items = readiness(root)
    for item in items:
        mark = "ok  " if item.ok else ("MISS" if item.required else "warn")
        print(f"  [{mark}] {item.name}" + ("" if item.ok else f"  ->  {item.hint}"))
    ready = all(i.ok for i in items if i.required)
    print("  ready to run offline" if ready else "  not ready: fix the items marked MISS")
    return ready
