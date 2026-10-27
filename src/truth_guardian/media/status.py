"""What each media reader can do on this computer, in four separate states, as the handover asks: its files are present
(checked against runtime/multimodal/MODEL_MANIFEST.json by size), its runtime is installed, it has run on known samples
(eval/results/media_pilot.json, written by scripts/media_pilot.py), and its quality has been evaluated on labelled data
(eval/results/media_eval.json; nothing yet). A model's name or the languages it lists never stand in for the last two.
"""

import importlib.util
import json
from functools import lru_cache
from pathlib import Path

from truth_guardian.media import ROOT, llama_server, models_dir

PILOT = ROOT / "eval" / "results" / "media_pilot.json"
EVALUATION = ROOT / "eval" / "results" / "media_eval.json"

# name, what it does, model, folders it needs in runtime/multimodal, Python modules it needs, whether it needs llama-server
COMPONENTS = [
    ("speech", "speech to text", "Whisper Small (Systran/faster-whisper-small)", ["whisper-small-ct2"], ["faster_whisper", "ctranslate2", "av"], False),
    ("ocr", "text in images", "Tesseract 5 with tessdata_fast", ["tessdata_fast"], ["tesserocr"], False),
    ("vision", "what an image shows", "Qwen3-VL-2B-Instruct (GGUF)", ["qwen3-vl-2b-gguf"], [], True),
    ("video", "video: sound and sampled frames", "PyAV with the speech and OCR readers", ["whisper-small-ct2", "tessdata_fast"], ["av", "faster_whisper", "tesserocr"], False),
    ("retrieval", "multilingual retrieval", "intfloat/multilingual-e5-small", ["multilingual-e5-small"], ["sentence_transformers"], False),
    ("nli", "multilingual entailment", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", ["mdeberta-v3-base-mnli-xnli"], ["transformers"], False),
]


@lru_cache(maxsize=1)
def _manifest(folder: str) -> tuple[tuple[str, int], ...]:
    path = Path(folder) / "MODEL_MANIFEST.json"
    if not path.is_file():
        return ()
    return tuple((f["relative_path"].replace("\\", "/"), int(f["actual_size"])) for f in json.loads(path.read_text(encoding="utf-8"))["files"])


def files_present(folders: list[str]) -> bool:
    root = models_dir()
    listed = _manifest(str(root))
    wanted = [(rel, size) for rel, size in listed if rel.split("/", 1)[0] in folders]
    if not wanted:
        return False
    return all((root / rel).is_file() and (root / rel).stat().st_size == size for rel, size in wanted)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def status() -> list[dict]:
    pilot, evaluation = _read(PILOT).get("components", {}), _read(EVALUATION).get("components", {})
    rows = []
    for name, role, model, folders, modules, server in COMPONENTS:
        runtime = all(importlib.util.find_spec(m) is not None for m in modules) and (not server or llama_server().is_file())
        ran = pilot.get(name, {})
        rows.append({
            "name": name, "role": role, "model": model,
            "files_present": files_present(folders), "runtime_ready": runtime,
            "run_tested": bool(ran.get("passed")), "quality_evaluated": bool(evaluation.get(name)),
            "pilot": {k: ran[k] for k in ("seconds", "peak_mb", "checks", "passed_checks") if k in ran} or None,
        })
    return rows
