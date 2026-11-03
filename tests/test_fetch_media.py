"""The download list and the downloader setup uses for the media models, with local files instead of the network."""

import hashlib
import http.server
import importlib.util
import json
import threading
from contextlib import contextmanager
from pathlib import Path

from truth_guardian import models

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_media_models", ROOT / "scripts" / "fetch_media_models.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)
DATA = bytes(range(256)) * 4096


@contextmanager
def dropping_server(data: bytes, per_try: int):
    """Honours Range, promises the whole rest of the file and closes cleanly after per_try bytes, as a dropped link does.
    Yields its address and the offsets it was asked for."""
    asked = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            wanted = self.headers.get("Range")
            start = int(wanted[len("bytes=") : -1]) if wanted else 0
            asked.append(start)
            self.send_response(206 if wanted else 200)
            self.send_header("Content-Length", str(len(data) - start))
            if wanted:
                self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.end_headers()
            self.wfile.write(data[start : start + per_try])
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/model.bin", asked
    finally:
        server.shutdown()
        server.server_close()


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


def test_a_connection_that_keeps_closing_early_resumes_and_finishes(tmp_path):
    target = tmp_path / "model.bin"
    with dropping_server(DATA, len(DATA) // 16 + 1) as (url, asked):
        assert fetch.download(url, target, hashlib.sha256(DATA).hexdigest(), wait=0)
    assert target.read_bytes() == DATA and not (tmp_path / "model.bin.part").exists()
    assert asked == sorted(set(asked)) and len(asked) > fetch.ATTEMPTS


def test_a_connection_that_brings_nothing_more_gives_up_and_keeps_the_part(tmp_path):
    target = tmp_path / "model.bin"
    with dropping_server(DATA, 0) as (url, asked):
        assert not fetch.download(url, target, hashlib.sha256(DATA).hexdigest(), wait=0)
    assert len(asked) == fetch.ATTEMPTS and not target.exists() and (tmp_path / "model.bin.part").exists()


def test_the_language_weights_are_the_revisions_the_app_loads():
    listed = json.loads(fetch.LIST.read_text(encoding="utf-8"))["language_models"]
    expected = {repo: models.REVISIONS[repo] for repo in (models.EMBEDDING_MODEL, models.NLI_MODEL)}
    assert len(listed) == len(expected)
    for f in listed:
        folder, _, revision, name = f["relative_path"].split("/")
        repo = folder.removeprefix("models--").replace("--", "/")
        assert expected[repo] == revision and name == "model.safetensors"
        assert f["url"] == f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        assert len(f["sha256"]) == 64 and f["actual_size"] > 0
