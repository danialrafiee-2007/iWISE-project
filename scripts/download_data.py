"""Download raw datasets from pinned commits of their official repositories and verify SHA-256 checksums."""

import hashlib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

RAGTRUTH = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/c103204b9ce28d6bbad859304bf30de72b8ed8fe/dataset"
HALUEVAL = "https://raw.githubusercontent.com/RUCAIBox/HaluEval/b7253db3cdaa0ab2c382f92b26b390109174f77e/data"
# Multilingual check (D-137): RAGTruth machine-translated by KRLabs, train files only (their test files translate the
# locked RAGTruth test set and are never fetched); PsiloQA (Wikipedia contexts, GPT-4o labels); XQuAD (human translations).
HUB = "https://huggingface.co/datasets"
RAGTRUTH_ES = f"{HUB}/KRLabsOrg/ragtruth-es-translated/resolve/39d88100950c20d44c391750ba0cd485ae59940c/data"
RAGTRUTH_FR = f"{HUB}/KRLabsOrg/ragtruth-fr-translated/resolve/95d0aa3eb623f1476279cead58623b5a34eb68fe/data"
RAGTRUTH_ZH = f"{HUB}/KRLabsOrg/ragtruth-cn-translated/resolve/1f3db52b24e63b0e00c1c3b522034d49c7dd7c96/data"
PSILOQA = f"{HUB}/s-nlp/PsiloQA/resolve/375c3321b8331a689d664f77eb2753c6cdb17159/data"
XQUAD = "https://raw.githubusercontent.com/google-deepmind/xquad/7d30520c717524000f0d9d2f9c10a069acd9d285"

FILES = [
    ("ragtruth", f"{RAGTRUTH}/response.jsonl", "e4c2e4ac24fff676d8984cc61c35d791612fadc58015335d97dd632375e18073"),
    ("ragtruth", f"{RAGTRUTH}/source_info.jsonl", "0dffc26ea9f3c1c3d7c7e8336b56ef1646e3cec876edffcca3c9c624d12d578b"),
    ("halueval", f"{HALUEVAL}/qa_data.json", "89ed139ec5e3a3169a0b30e45569ac1283846f76f27f7bb5e908ee6deed57e88"),
    ("halueval", f"{HALUEVAL}/dialogue_data.json", "9c461df2691e4362837f66fceaaff3bc260453350c3a1cae76a5a52e5e338bfd"),
    ("halueval", f"{HALUEVAL}/summarization_data.json", "86d2561eeb4271eb50b6bd90c9fd38636d30eaf4e98b648045f221adb1c2c758"),
    ("halueval", f"{HALUEVAL}/general_data.json", "73302cd97666b808fb94b5d8a4a2c924049c9484e609017a2f808c4a6d539219"),
    ("ragtruth_es", f"{RAGTRUTH_ES}/train-00000-of-00001.parquet", "7412c03f35d1bbf071df0e73b7a32629537bb0cceadda20c80d32f54a0132dcf"),
    ("ragtruth_fr", f"{RAGTRUTH_FR}/train-00000-of-00001.parquet", "d1c0f756afaa60a9e7fe4b792cd2ec0823a328f71de8f3944ab173396590efb7"),
    ("ragtruth_zh", f"{RAGTRUTH_ZH}/train-00000-of-00001.parquet", "cc31a66f5131b9daf61a690ce938b6eda1ee5eee9b422c7eda7b4b91b1e1f4af"),
    ("psiloqa", f"{PSILOQA}/train-00000-of-00001.parquet", "314b2b8d9f76eb929d4471d4d4b0ae1f2d171101bc0b84e74bf1ec331f5e22e9"),
    ("psiloqa", f"{PSILOQA}/validation-00000-of-00001.parquet", "258af88997f91ae01a9ef189647f25bb888c14246e8526711e89db024854655e"),
    ("psiloqa", f"{PSILOQA}/test-00000-of-00001.parquet", "a38b11aee4a56461dec5e7d64986850964b516f29b7499b386cade4a8e5b813b"),
    ("xquad", f"{XQUAD}/xquad.en.json", "e4c57d1c9143aaa1c5d265ba5987a65f4e69528d2a98f29d6e75019b10344f29"),
    ("xquad", f"{XQUAD}/xquad.ar.json", "abdabd7afed5c635d99cca0f3f0d0c9d9ed0bc77451e963c2e4e0638c29e486d"),
    ("xquad", f"{XQUAD}/xquad.es.json", "dcbae93ec3a9f4b9e78fd834a171d6f96c1a875e10e15b7530b7e4ef4971e37e"),
    ("xquad", f"{XQUAD}/xquad.ru.json", "208d5b1aa154c52b1b5c5eda16281e455e8fd198cdb9af3f469f0d6037d973bf"),
    ("xquad", f"{XQUAD}/xquad.zh.json", "691d0b3359bc6b8faa8de931dfdfe21d50a65861ae348e32a0d1a0190b0c8835"),
    ("xquad", f"{XQUAD}/CC-BY-SA4.0.txt", "25ddafc153e4cfdafd70729574ef1b44348e1814709e57680d55347038d3f92c"),
]

ARCHIVES = [
    {
        "dataset": "agenthallu",
        "url": "https://codeload.github.com/liuxuannan/AgentHallu/zip/9ffe8bc888feaf15d89833f4b0e3c4697f44acc1",
        "sha256": "ea2e13a0f1542df8685ad033f8c4dc904c52fb7c53a2bdc1c1a762dea0ea010e",
        "keep": ("AgentHallu/", "LICENSE", "README.md"),
    },
    {
        "dataset": "nltk_data/corpora",
        "url": "https://raw.githubusercontent.com/nltk/nltk_data/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/corpora/wordnet.zip",
        "sha256": "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59",
        "keep": ("wordnet/",),
        "strip_top": False,
    },
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


def fetch_archive(dataset: str, url: str, expected: str | None, keep: tuple[str, ...], strip_top: bool = True) -> None:
    """Download a zip, verify it, and extract only the kept paths (a repository zip's top folder is stripped)."""
    target_dir = (RAW_DIR / dataset).resolve()
    archive = target_dir / "source.zip"
    if not (archive.exists() and sha256(archive) == expected):
        target_dir.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(archive.name + ".part")
        urllib.request.urlretrieve(url, partial)
        partial.replace(archive)
    actual = sha256(archive)
    if expected and actual != expected:
        raise SystemExit(f"checksum mismatch for {dataset} archive: got {actual}")
    extracted = 0
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            relative = member.filename.split("/", 1)[-1] if strip_top else member.filename
            if member.is_dir() or not relative.startswith(keep):
                continue
            destination = (target_dir / relative).resolve()
            if not destination.is_relative_to(target_dir):
                raise SystemExit(f"unsafe path in {dataset} archive: {member.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(z.read(member))
            extracted += 1
    print(f"{archive.relative_to(ROOT).as_posix()}  {archive.stat().st_size / 1e6:.1f} MB  sha256={actual}  ({extracted} files extracted)")


def main() -> None:
    for dataset, url, expected in FILES:
        fetch(dataset, url, expected)
    for a in ARCHIVES:
        fetch_archive(a["dataset"], a["url"], a["sha256"], a["keep"], a.get("strip_top", True))


if __name__ == "__main__":
    main()
