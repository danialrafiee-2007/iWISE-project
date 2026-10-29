"""Real media for measuring the media chain (stage 2, D-139), from pinned revisions with SHA-256 checks; about 2.5 GB.

Kept out of download_data.py, which every setup runs: these files only serve the measurement.
  FLEURS (CC BY 4.0): read speech with its transcript, the dev split in English, Arabic, Spanish, French, Russian, Chinese
  TextVQA (annotations CC BY 4.0, OpenImages photos CC BY 2.0): a third of validation, ten human answers per question
  MTVQA (CC BY-NC 4.0, non-commercial): its test split, questions on text in images with expert answers; Arabic,
          French and Russian are used
"""

import importlib.util
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("download_data", HERE / "download_data.py")
download_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download_data)
RAW = download_data.RAW_DIR

FLEURS = "https://huggingface.co/datasets/google/fleurs/resolve/70bb2e84b976b7e960aa89f1c648e09c59f894dd/data"
TEXTVQA = "https://huggingface.co/datasets/lmms-lab/textvqa/resolve/9c0699cd19768ac5ab97568f6b3cbac4c0062884/data"
MTVQA = "https://huggingface.co/datasets/ByteDance/MTVQA/resolve/7cdca63ec6cd71cdd0b52f79fc3176bb9ce36a9c/data"
FLEURS_LANGUAGES = {"en": "en_us", "ar": "ar_eg", "es": "es_419", "fr": "fr_fr", "ru": "ru_ru", "zh": "cmn_hans_cn"}

FILES = [
    ("fleurs/en", f"{FLEURS}/{FLEURS_LANGUAGES['en']}/dev.tsv", "9d57ee7e91e9d4c92edb39f6bbea668ef8dc2a3ff96eb510d5580b2ad05d17ec"),
    ("fleurs/ar", f"{FLEURS}/{FLEURS_LANGUAGES['ar']}/dev.tsv", "3c9ea61dfd884a47e03ee33c4ef601bed0a1142ce7e5b279cccd0cf321792913"),
    ("fleurs/es", f"{FLEURS}/{FLEURS_LANGUAGES['es']}/dev.tsv", "352b2a5f03f02fe752254fab737f76519963650f4630d2fb63957177aeec927f"),
    ("fleurs/fr", f"{FLEURS}/{FLEURS_LANGUAGES['fr']}/dev.tsv", "3e0b792358c1cb4a426fe1c18fc1571d5406b390d738a2ed1bfd3c8b9d28de44"),
    ("fleurs/ru", f"{FLEURS}/{FLEURS_LANGUAGES['ru']}/dev.tsv", "25d9dc88a7533fc0f303354a8e6d3c8186c557229c9a0024487090a11226171e"),
    ("fleurs/zh", f"{FLEURS}/{FLEURS_LANGUAGES['zh']}/dev.tsv", "6b4efd804b543048feb278db06f3b58b5ea171cdd4ba072e328ad630ca25384b"),
    ("fleurs/en", f"{FLEURS}/{FLEURS_LANGUAGES['en']}/audio/dev.tar.gz", "2658fda72f199e12676ecac9415094667a4e14e149b146e568ea00b2a2f0954c"),
    ("fleurs/ar", f"{FLEURS}/{FLEURS_LANGUAGES['ar']}/audio/dev.tar.gz", "22271b3500c0e952aedbf0a6d7d3b959a91e1f02612293dce761fe5c87b66117"),
    ("fleurs/es", f"{FLEURS}/{FLEURS_LANGUAGES['es']}/audio/dev.tar.gz", "94f0f3d9fd89c0496385bf0991f2565410cc489a73dd18cafa0ee0177dc5c815"),
    ("fleurs/fr", f"{FLEURS}/{FLEURS_LANGUAGES['fr']}/audio/dev.tar.gz", "f2f065dec3b02212e27151c51162d2213df55d0a8efc6b88e36992673ddf66e6"),
    ("fleurs/ru", f"{FLEURS}/{FLEURS_LANGUAGES['ru']}/audio/dev.tar.gz", "4dc533cd0f312f749bd6d0fe968f3183288d938e07ed97dc141d9f10570457f9"),
    ("fleurs/zh", f"{FLEURS}/{FLEURS_LANGUAGES['zh']}/audio/dev.tar.gz", "3bc33212d5974eef7feb04bc4792458d6cd7e14ff10a1a24772f3c45ea87a822"),
    ("textvqa", f"{TEXTVQA}/validation-00000-of-00003.parquet", "491649b5b8add2c5bde13a1e36707002fcd11898699255d65e2e568ac4fbddff"),
    ("mtvqa", f"{MTVQA}/test-00000-of-00003.parquet", "5cfbb8df0cd49373196e01eeef74ecc2704f8df1f94e7e834500b6eeb34f3d2c"),
    ("mtvqa", f"{MTVQA}/test-00001-of-00003.parquet", "43489994e340c3921f0120120367bf33042a44fdd4ce9198e34a8aa5875ca40f"),
    ("mtvqa", f"{MTVQA}/test-00002-of-00003.parquet", "b66c6f8d0f0f62f60d4437d681abc2e4d99223fd7d7a1c94b449c553d6535162"),
]


def unpack(archive: Path) -> None:
    """The FLEURS audio, next to its archive; the "data" filter refuses links and paths outside the folder."""
    target = archive.parent / "audio"
    if target.exists() and any(target.iterdir()):
        return
    with tarfile.open(archive) as tar:
        tar.extractall(target, filter="data")
    print(f"  unpacked {sum(1 for _ in target.rglob('*.wav'))} recordings into {target.relative_to(RAW.parent.parent).as_posix()}")


def main() -> None:
    for dataset, url, expected in FILES:
        download_data.fetch(dataset, url, expected)
    for archive in sorted(RAW.glob("fleurs/*/dev.tar.gz")):
        unpack(archive)


if __name__ == "__main__":
    main()
