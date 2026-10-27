"""Local readers for sound, images and video, the challenge's other inputs (D-125).

Each reader turns a file into text segments with where they came from (a box in the image, a time range in the sound),
the language and script it found and how sure it is, in one contract (contract.py), so the text checks can use them as
evidence later. Nothing here reaches the network: the models sit in runtime/multimodal (TG_MEDIA_MODELS overrides the
folder) and the one program they need, llama.cpp's server for the image model, in runtime/tools (TG_LLAMA_SERVER).

  speech.py        Whisper Small (faster-whisper, CTranslate2 int8): speech to text with word times, per-segment language
  ocr.py           Tesseract 5 (tesserocr) with tessdata_fast: text in images, script first, then likely languages
  vision.py        Qwen3-VL-2B (GGUF) through llama-server: what an image shows, never proof on its own
  video.py         PyAV: the soundtrack to speech.py and a few timed frames to ocr.py
  multilingual.py  multilingual E5 (retrieval) and mDeBERTa NLI, not yet part of the fusion model
  status.py        what is installed, what has run, what has been evaluated, kept apart
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def models_dir() -> Path:
    return Path(os.environ.get("TG_MEDIA_MODELS") or ROOT / "runtime" / "multimodal")


def llama_server() -> Path:
    return Path(os.environ.get("TG_LLAMA_SERVER") or ROOT / "runtime" / "tools" / "llama.cpp" / "llama-server.exe")
