"""Download raw datasets from pinned commits of their official repositories and verify SHA-256 checksums."""

import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

RAGTRUTH = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/c103204b9ce28d6bbad859304bf30de72b8ed8fe/dataset"
HALUEVAL = "https://raw.githubusercontent.com/RUCAIBox/HaluEval/b7253db3cdaa0ab2c382f92b26b390109174f77e/data"

FILES = [
    ("ragtruth", f"{RAGTRUTH}/response.jsonl", "e4c2e4ac24fff676d8984cc61c35d791612fadc58015335d97dd632375e18073"),
    ("ragtruth", f"{RAGTRUTH}/source_info.jsonl", "0dffc26ea9f3c1c3d7c7e8336b56ef1646e3cec876edffcca3c9c624d12d578b"),
    ("halueval", f"{HALUEVAL}/qa_data.json", "89ed139ec5e3a3169a0b30e45569ac1283846f76f27f7bb5e908ee6deed57e88"),
    ("halueval", f"{HALUEVAL}/dialogue_data.json", "9c461df2691e4362837f66fceaaff3bc260453350c3a1cae76a5a52e5e338bfd"),
    ("halueval", f"{HALUEVAL}/summarization_data.json", "86d2561eeb4271eb50b6bd90c9fd38636d30eaf4e98b648045f221adb1c2c758"),
    ("halueval", f"{HALUEVAL}/general_data.json", "73302cd97666b808fb94b5d8a4a2c924049c9484e609017a2f808c4a6d539219"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(dataset: str, url: str, expected: str | None) -> None:
    target = RAW_DIR / dataset / url.rsplit("/", 1)[1]
    if not (target.exists() and sha256(target) == expected):
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        urllib.request.urlretrieve(url, partial)
        partial.replace(target)
    actual = sha256(target)
    if expected and actual != expected:
        raise SystemExit(f"checksum mismatch for {target.name}: got {actual}")
    print(f"{target.relative_to(ROOT).as_posix()}  {target.stat().st_size / 1e6:.1f} MB  sha256={actual}")


def main() -> None:
    for dataset, url, expected in FILES:
        fetch(dataset, url, expected)


if __name__ == "__main__":
    main()
