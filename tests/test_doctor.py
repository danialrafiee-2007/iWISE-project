import sys

import huggingface_hub
import pytest

from truth_guardian.media import status
from truth_guardian.web import doctor


@pytest.mark.skipif(sys.platform != "win32", reason="setup fetches the media models on Windows only")
def test_the_checklist_names_the_media_readers_that_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "_cached", lambda repo, revision=None: True)
    rows = [{"name": name, "files_present": name != "speech", "runtime_ready": name != "vision"} for name in ("speech", "ocr", "vision")]
    monkeypatch.setattr(status, "status", lambda: rows)
    items = {item.name: item for item in doctor.readiness(tmp_path)}
    assert not items["sound reader (Whisper)"].ok and not items["image model (Qwen3-VL and llama.cpp)"].ok
    assert items["text in images (Tesseract)"].ok
    assert not items["sound reader (Whisper)"].required


def test_a_snapshot_counts_only_with_its_config_and_finished_weights(tmp_path, monkeypatch):
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *args, **kwargs: str(tmp_path))
    assert not doctor._cached("repo")
    (tmp_path / "model.safetensors.part").write_bytes(b"x")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert not doctor._cached("repo")
    (tmp_path / "model.safetensors").write_bytes(b"x")
    assert doctor._cached("repo")
    (tmp_path / "config.json").unlink()
    assert not doctor._cached("repo")
