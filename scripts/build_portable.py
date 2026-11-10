"""Build the ready-made package for judges from a finished install, so that the eight setup steps are already done.

    TruthGuardian.bat setup
    .venv/Scripts/python.exe scripts/build_portable.py --out D:/dist/TruthGuardian-Portable

The package is a folder: deploy/portable's two files and the app in zip parts, each small enough for GitHub Releases and
a FAT32 drive. It holds the same data as the Docker image (no raw datasets, training data or locked test sets) and no
key, log or cache of this computer. The Visual C++ runtime goes beside Python, since a clean Windows may not have it.
"""

import argparse
import fnmatch
import hashlib
import json
import math
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / "portable"
STARTER = "Start-Truth-Guardian.bat"
GUIDE = "README-FIRST.txt"
LLAMA_FOLDER = "runtime/tools/llama.cpp"
SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
PART_LIMIT = 1_900_000_000
ENTRY_OVERHEAD = 512
LONGEST_FOLDER = 85
WINDOWS_PATH_LIMIT = 260
ENVIRONMENT_BYTES = 2_000_000_000
SPARE_BYTES = 1_000_000_000
LEFT_OUT = {
    ".git", ".pytest_cache", ".venv", "data/features", "dist", "eval/predictions", "layers-originals", "runtime/hf/hub/.locks",
    "runtime/browser-profile", "runtime/hf/xet", "runtime/logs", "runtime/npm-cache", "runtime/online", "runtime/python/.temp", "runtime/rag-eval", "web/node_modules",
    "runtime/tmp", "runtime/media-smoke",
}
# The chat's document library: the project's documents go into the package, the person's own never (D-214).
LIBRARY = "data/web/library/library.sqlite"
LEFT_OUT_FILES = ("*.local.env", ".env", "*.pyc", "*.part", "*.incomplete", "*.tmp", ".agent_harnesses.json", "opened-*.txt")
KEPT_DATA = (
    "data/web", "data/raw/nltk_data/corpora/wordnet", "data/processed/ragtruth_dev.jsonl", "data/processed/xdev_halueval_dialogue.jsonl",
    "data/processed/tg_agent_dev.jsonl", "data/processed/perturb_dev.jsonl",
)
STORED = {".safetensors", ".gguf", ".onnx", ".bin", ".pt", ".zip", ".whl"}
VC_RUNTIME = (
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "vcruntime140.dll",
    "vcruntime140_1.dll", "vcruntime140_threads.dll", "vcomp140.dll", "concrt140.dll",
)


def _kept_data(relative: str) -> bool:
    return any(relative == kept or relative.startswith(f"{kept}/") for kept in KEPT_DATA)


def select(root: Path) -> dict[str, Path]:
    """What goes into the package: its path inside the app folder -> the file here. Junctions hold absolute paths, and the
    launcher works without them."""
    chosen = {}
    for folder, dirs, files in os.walk(root):
        here = Path(folder).relative_to(root).as_posix()
        here = "" if here == "." else f"{here}/"
        dirs[:] = [d for d in dirs if d != "__pycache__" and here + d not in LEFT_OUT and not os.path.isjunction(Path(folder) / d)]
        for name in files:
            relative = here + name
            if any(fnmatch.fnmatch(name, pattern) for pattern in LEFT_OUT_FILES):
                continue
            if not relative.startswith("data/") or _kept_data(relative):
                chosen[relative] = Path(folder) / name
    return chosen


def project_library(chosen: dict[str, Path], work: Path) -> None:
    """The library as the package carries it: a copy with only the project's documents, so the files a person added in
    the chat (and their passages, pictures and second readings) stay on this computer."""
    if LIBRARY not in chosen:
        return
    import sqlite3

    work.mkdir(parents=True, exist_ok=True)
    copy = work / "library.sqlite"
    source = sqlite3.connect(chosen[LIBRARY])
    target = sqlite3.connect(copy)
    source.backup(target)
    source.close()
    target.execute("PRAGMA foreign_keys = ON")
    target.execute("DELETE FROM documents WHERE collection != 'project'")
    target.commit()
    target.execute("VACUUM")
    target.close()
    chosen[LIBRARY] = copy


def add_vc_runtime(chosen: dict[str, Path], root: Path) -> None:
    """Beside the real python.exe and llama-server.exe, which Windows searches first, as one consistent set; Python's own
    copy is replaced with the newer one, which is backward compatible."""
    home = next((p for p in sorted((root / "runtime" / "python").glob("cpython-*")) if (p / "python.exe").is_file() and not os.path.isjunction(p)), None)
    if home is None:
        sys.exit("no Python in runtime/python; run TruthGuardian.bat setup first")
    folders = [home.relative_to(root).as_posix()]
    if (root / LLAMA_FOLDER / "llama-server.exe").is_file():
        folders.append(LLAMA_FOLDER)
    for name in VC_RUNTIME:
        if not (SYSTEM32 / name).is_file():
            sys.exit(f"{name} is not on this computer; install the Visual C++ Redistributable (x64) and build again")
        for folder in folders:
            chosen[f"{folder}/{name}"] = SYSTEM32 / name


def write_parts(chosen: dict[str, Path], folder: Path, limit: int | None = None) -> list[Path]:
    """Zip parts of at most limit bytes; no file is split, so each part unpacks on its own. Model weights barely compress,
    so they are stored as they are, which also unpacks them faster."""
    limit = limit or PART_LIMIT
    parts, archive, used = [], None, 0
    for relative, source in sorted(chosen.items()):
        size = source.stat().st_size
        if size + ENTRY_OVERHEAD > limit:
            sys.exit(f"{relative} alone is larger than a part")
        if archive is None or used + size + ENTRY_OVERHEAD > limit:
            if archive is not None:
                archive.close()
            parts.append(folder / f"part-{len(parts) + 1}.tmp")
            archive, used = zipfile.ZipFile(parts[-1], "w", allowZip64=True, strict_timestamps=False), 0
        method = zipfile.ZIP_STORED if source.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
        archive.write(source, relative, compress_type=method)
        used += archive.getinfo(relative).compress_size + ENTRY_OVERHEAD
    if archive is not None:
        archive.close()
    named = [part.with_name(f"truth-guardian-{i}-of-{len(parts)}.zip") for i, part in enumerate(parts, 1)]
    for part, name in zip(parts, named):
        part.replace(name)
    return named


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(parts: list[Path], chosen: dict[str, Path]) -> None:
    """Every file is in exactly one part, and every part reads back without a CRC error."""
    found = []
    for part in parts:
        with zipfile.ZipFile(part) as archive:
            damaged = archive.testzip()
            if damaged:
                sys.exit(f"{part.name}: {damaged} did not read back")
            found += archive.namelist()
    if sorted(found) != sorted(chosen):
        sys.exit("the parts do not hold exactly the chosen files")


def build(root: Path, out: Path, limit: int | None = None) -> list[Path]:
    packages = out / "packages"
    if (packages / "package.txt").is_file():
        shutil.rmtree(out)
    elif out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty and holds no earlier package; choose another folder")
    packages.mkdir(parents=True)
    chosen = select(root)
    project_library(chosen, out / "work")
    add_vc_runtime(chosen, root)
    longest = max(chosen, key=len)
    if LONGEST_FOLDER + 1 + len(longest) >= WINDOWS_PATH_LIMIT:
        sys.exit(f"{longest} is too long for the {LONGEST_FOLDER}-character folders the starter unpacks into")
    parts = write_parts(chosen, packages, limit)
    verify(parts, chosen)
    unpacked = sum(source.stat().st_size for source in chosen.values())
    need_gb = math.ceil((unpacked + ENVIRONMENT_BYTES + SPARE_BYTES) / 2**30)
    sums = "".join(f"{sha256_of(part)}  {part.name}\n" for part in parts)
    build_id = time.strftime("%Y%m%d-%H%M") + "-" + hashlib.sha256(sums.encode("ascii")).hexdigest()[:8]
    (packages / "package.txt").write_text(f"BUILD={build_id}\nPARTS={len(parts)}\nNEED_GB={need_gb}\n", encoding="ascii", newline="\r\n")
    (packages / "SHA256SUMS.txt").write_text(sums, encoding="ascii", newline="\r\n")
    shutil.rmtree(out / "work", ignore_errors=True)
    shutil.copyfile(TEMPLATE / STARTER, out / STARTER)
    guide = (TEMPLATE / GUIDE).read_text(encoding="utf-8").replace("{need_gb}", str(need_gb)).replace("{build}", build_id)
    (out / GUIDE).write_text(guide, encoding="utf-8-sig", newline="\r\n")
    return parts


def ready_or_exit(root: Path) -> None:
    """A package built from an unfinished install, or with stale example reports, would make the judges wait or fail."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from truth_guardian.web.doctor import readiness
    from truth_guardian.web.examples import brain_fingerprint

    missing = [item.name for item in readiness(root) if not item.ok]
    if missing:
        sys.exit(f"this install is not finished ({', '.join(missing)}); run TruthGuardian.bat setup first")
    reports = list((root / "data" / "web" / "examples").glob("*.json"))
    code = brain_fingerprint()
    if not reports or any(json.loads(report.read_text(encoding="utf-8")).get("code") != code for report in reports):
        sys.exit("the example reports do not match this code; run TruthGuardian.bat setup again")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "TruthGuardian-Portable")
    args = parser.parse_args()
    ready_or_exit(ROOT)
    parts = build(ROOT, args.out.resolve())
    print(f"{args.out}: {len(parts)} parts, {sum(part.stat().st_size for part in parts) / 2**30:.2f} GB")
    for part in parts:
        print(f"  {part.name}  {part.stat().st_size / 2**30:.2f} GB")


if __name__ == "__main__":
    main()
