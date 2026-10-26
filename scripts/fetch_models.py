"""Download the two live language models at their pinned revisions and copy them, as plain files, into a Hugging Face
cache of their own (the Docker image's /opt/hf), so nothing else from the download cache comes along.

    python scripts/fetch_models.py /opt/hf

Only the safetensors weights are kept (no PyTorch .bin, ONNX, OpenVINO or other framework copies). Each model is
tried five times; on failure the script exits 1 with a message, so a build never ends with a model missing.
"""

import fnmatch
import shutil
import sys
import time
from pathlib import Path

from truth_guardian import models

SKIP = ["onnx/*", "openvino/*", "*.h5", "*.msgpack", "*.ot", "*.bin", "tf_*", "flax_*", "rust_*"]
ATTEMPTS = 5


def fetch(repo: str, revision: str) -> Path:
    # imported here, after truth_guardian has chosen the download cache (HF_HOME)
    from huggingface_hub import snapshot_download

    for attempt in range(1, ATTEMPTS + 1):
        try:
            return Path(snapshot_download(repo, revision=revision, ignore_patterns=SKIP))
        except Exception as e:
            print(f"{repo}: download attempt {attempt} failed ({type(e).__name__}: {e})", flush=True)
            if attempt < ATTEMPTS:
                time.sleep(20)
    sys.exit(f"ERROR: {repo} could not be downloaded after {ATTEMPTS} attempts; check the internet connection and build again")


def main() -> None:
    hub = Path(sys.argv[1]) / "hub"
    for repo in (models.EMBEDDING_MODEL, models.NLI_MODEL):
        revision = models.REVISIONS[repo]
        source = fetch(repo, revision)
        target = hub / f"models--{repo.replace('/', '--')}" / "snapshots" / revision
        size = 0
        for path in sorted(source.rglob("*")):
            name = path.relative_to(source).as_posix()
            if path.is_file() and not any(fnmatch.fnmatch(name, p) for p in SKIP):
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target / name)
                size += path.stat().st_size
        print(f"{repo} @ {revision[:8]}: {size / 1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
