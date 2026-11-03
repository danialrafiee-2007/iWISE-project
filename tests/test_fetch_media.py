"""The download list and the downloader setup uses for the media models, with local files instead of the network."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_media_models", ROOT / "scripts" / "fetch_media_models.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def _source(tmp_path: Path, name: str, data: bytes) -> dict:
    source = tmp_path / "source" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(data)
    return {"relative_path": f"model/{name}", "url": source.as_uri(), "actual_size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_every_listed_file_can_be_fetched_and_checked():
    listed = json.loads(fetch.LIST.read_text(encoding="utf-8"))
    assert len(listed["files"]) == 193
    for f in listed["files"]:
        assert f["url"].startswith("https://") and len(f["sha256"]) == 64 and f["actual_size"] > 0
        assert not f["relative_path"].startswith(("/", "..")) and ".." not in f["relative_path"]
    tops = {f["relative_path"].split("/", 1)[0] for f in listed["files"]}
    assert tops == {"whisper-small-ct2", "qwen3-vl-2b-gguf", "tessdata_fast", "licenses", "multilingual-e5-small", "mdeberta-v3-base-mnli-xnli"}
    assert listed["llama_cpp"]["url"].startswith("https://") and len(listed["llama_cpp"]["sha256"]) == 64


def test_the_list_holds_no_local_path():
    text = fetch.LIST.read_text(encoding="utf-8")
    assert "D:\\" not in text and "IWISE" not in text.replace("iWISE", "") and "locked" not in text


def test_fetches_what_is_missing_and_leaves_the_rest(tmp_path):
    first, second = _source(tmp_path, "a.bin", b"a" * 10), _source(tmp_path, "b.bin", b"b" * 20)
    root = tmp_path / "models"
    (root / "model").mkdir(parents=True)
    (root / "model" / "a.bin").write_bytes(b"x" * 10)  # right size: left alone, as a zip from the Release would be
    assert fetch.fetch_files([first, second], root, wait=0) == []
    assert (root / "model" / "a.bin").read_bytes() == b"x" * 10
    assert (root / "model" / "b.bin").read_bytes() == b"b" * 20
    assert not (root / "model" / "b.bin.part").exists()


def test_a_wrong_checksum_never_lands(tmp_path):
    entry = {**_source(tmp_path, "c.bin", b"c" * 8), "sha256": "0" * 64}
    root = tmp_path / "models"
    assert fetch.fetch_files([entry], root, wait=0) == ["model/c.bin"]
    assert not (root / "model" / "c.bin").exists()


def test_a_missing_source_is_reported(tmp_path):
    entry = {**_source(tmp_path, "d.bin", b"d" * 8), "url": (tmp_path / "nowhere.bin").as_uri()}
    assert fetch.fetch_files([entry], tmp_path / "models", wait=0) == ["model/d.bin"]
