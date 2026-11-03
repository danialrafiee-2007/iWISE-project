"""Download the models for sound, images and other languages, llama.cpp and the large weights of the two live language
models from their official sources into runtime/.

    python scripts/fetch_media_models.py

Each file is checked against the SHA-256 recorded when it was first downloaded (scripts/media_models.json). A file
already there with the right size is left alone and a broken download resumes, so running it again finishes the job.
The language models' weights come through here because the Hub's own downloader deletes its partial file on failure, so
on a connection that keeps dropping it may never finish; the Hub reuses a file already in its snapshot folder.
Exits 1 when something is still missing.
"""

import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import constants

from truth_guardian.media import llama_server, models_dir

LIST = Path(__file__).with_name("media_models.json")
ATTEMPTS = 8
MAX_WAIT = 60.0


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def receive(response, out) -> None:
    """Copies the body. http.client reports a connection closed early as a plain end of file, so the length is checked here."""
    promised = response.headers.get("Content-Length")
    received = 0
    while block := response.read(1 << 20):
        out.write(block)
        received += len(block)
    if promised is not None and received < int(promised):
        raise ConnectionError(f"the connection closed after {received:,} of {int(promised):,} bytes")


def download(url: str, path: Path, sha256: str, wait: float = 5.0) -> bool:
    """To path.part first, resuming it, then checked and moved into place. A try that brought more bytes does not count
    against ATTEMPTS and the waits grow to MAX_WAIT, so a link that keeps dropping for minutes still finishes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    attempt = 0
    while attempt < ATTEMPTS:
        attempt += 1
        have = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": "truth-guardian-setup", **({"Range": f"bytes={have}-"} if have else {})})
        try:
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    # A server that ignores Range sends the whole file again.
                    with part.open("ab" if have and response.status == 206 else "wb") as out:
                        receive(response, out)
            except urllib.error.HTTPError as e:
                if e.code != 416:  # 416: nothing left to send, the part is complete
                    raise
            if sha256_of(part) == sha256:
                part.replace(path)
                return True
            part.unlink()
            print(f"    checksum did not match, starting {path.name} again (try {attempt}/{ATTEMPTS})", flush=True)
        except (OSError, http.client.HTTPException) as e:
            print(f"    {path.name}: {e} (try {attempt}/{ATTEMPTS})", flush=True)
            if part.exists() and part.stat().st_size > have:
                attempt = 0
        if attempt < ATTEMPTS:
            time.sleep(min(wait * 2 ** max(attempt - 1, 0), MAX_WAIT))
    return False


def fetch_files(files: list[dict], root: Path, wait: float = 5.0) -> list[str]:
    """Fetches what is not there yet, smallest first; returns the paths it could not get."""
    missing = [f for f in files if not ((root / f["relative_path"]).is_file() and (root / f["relative_path"]).stat().st_size == f["actual_size"])]
    total, done = sum(f["actual_size"] for f in missing), 0
    print(f"  {len(files) - len(missing)} of {len(files)} files already here; {total / 2**20:,.0f} MB to download", flush=True)
    failed = []
    for f in sorted(missing, key=lambda f: f["actual_size"]):
        print(f"  {done / 2**20:7,.0f} / {total / 2**20:,.0f} MB  {f['relative_path']}", flush=True)
        if not download(f["url"], root / f["relative_path"], f["sha256"], wait):
            failed.append(f["relative_path"])
        done += f["actual_size"]
    return failed


def fetch_llama(entry: dict, server: Path, wait: float = 5.0) -> bool:
    """llama.cpp's server for the image reader; this build is for Windows."""
    if server.is_file():
        return True
    folder = server.parent
    archive = folder.with_name(folder.name + ".zip")
    print(f"  llama.cpp {entry['version']}", flush=True)
    if not download(entry["url"], archive, entry["sha256"], wait):
        return False
    with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    (folder / "VERSION.txt").write_text(f"{entry['version']} {entry['url'].rsplit('/', 1)[1]} sha256:{entry['sha256']}\n", encoding="utf-8")
    archive.unlink()
    return server.is_file()


def main() -> int:
    listed = json.loads(LIST.read_text(encoding="utf-8"))
    root = models_dir()
    failed = fetch_files(listed["language_models"], Path(constants.HF_HUB_CACHE))
    failed += fetch_files(listed["files"], root)
    if sys.platform == "win32" and not fetch_llama(listed["llama_cpp"], llama_server()):
        failed.append("llama.cpp")
    # The readers' status page compares the files with this list by size.
    manifest = root / "MODEL_MANIFEST.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"files": listed["files"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if failed:
        print(f"  {len(failed)} could not be downloaded, first {failed[0]}; run setup again to continue", flush=True)
        return 1
    print("  all present", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
