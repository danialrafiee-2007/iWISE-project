"""The ready-made package for judges: what goes into it, its parts, and its one-click starter run by cmd.exe itself."""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_portable", ROOT / "scripts" / "build_portable.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
windows = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe only")
FAKE_APP = '@echo off\r\necho STARTED %*\r\nif defined FAIL_APP exit /b 1\r\nexit /b 0\r\n'


def write(root: Path, *names: str) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(name.encode() * 20)


@pytest.fixture
def install(tmp_path, monkeypatch) -> Path:
    """A finished install in small, with a Visual C++ runtime of its own to copy."""
    root = tmp_path / "install"
    write(root, "src/app.py", "README.md", "runtime/python/cpython-3.13.17-x/python.exe", "runtime/python/cpython-3.13.17-x/vcruntime140.dll",
          "runtime/uv/uv.exe", "runtime/multimodal/whisper/model.bin", "data/raw/nltk_data/corpora/wordnet/LICENSE", "data/processed/ragtruth_dev.jsonl")
    (root / "TruthGuardian.bat").write_bytes(FAKE_APP.encode())
    system32 = tmp_path / "system32"
    system32.mkdir()
    for name in builder.VC_RUNTIME:
        (system32 / name).write_bytes(b"new " + name.encode())
    monkeypatch.setattr(builder, "SYSTEM32", system32)
    return root


def test_keys_logs_caches_and_raw_data_stay_out(install):
    left_out = [
        "smtp.local.env", "anthropic.local.env", ".env", ".venv/Scripts/python.exe", "src/__pycache__/app.cpython-313.pyc", "runtime/logs/llama-server.log",
        "runtime/online/usage.json", "runtime/hf/xet/logs/x.log", "runtime/hf/hub/.locks/m/a.lock", "runtime/hf/.agent_harnesses.json", "runtime/hf/hub/m/model.safetensors.part",
        "runtime/opened-truth-guardian-hhem-fast.zip.txt", "runtime/python/.temp/x", "data/raw/ragtruth/response.jsonl", "data/raw/nltk_data/corpora/source.zip",
        "data/processed/ragtruth_train.jsonl", "data/processed/locked/ragtruth_test.jsonl", "data/features/nli/x.jsonl", "eval/predictions/x.jsonl",
        "runtime/rag-eval/en-all.sqlite", "runtime/npm-cache/_cacache/index",
    ]
    write(install, *left_out, "runtime/hf/hub/m/model.safetensors", "data/web/examples/a.json")
    chosen = builder.select(install)
    assert not set(left_out) & set(chosen)
    assert {"src/app.py", "TruthGuardian.bat", "runtime/hf/hub/m/model.safetensors", "data/web/examples/a.json", "data/raw/nltk_data/corpora/wordnet/LICENSE", "data/processed/ragtruth_dev.jsonl"} <= set(chosen)


@windows
def test_a_junction_with_its_absolute_path_stays_out(install):
    real = install / "runtime" / "python" / "cpython-3.13.17-x"
    subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(install / "runtime" / "python" / "cpython-3.13-x"), str(real)], check=True, capture_output=True)
    chosen = builder.select(install)
    assert "runtime/python/cpython-3.13.17-x/python.exe" in chosen and not any("cpython-3.13-x/" in name for name in chosen)


def test_the_visual_cpp_runtime_goes_beside_python_and_the_image_server(install, tmp_path):
    write(install, f"{builder.LLAMA_FOLDER}/llama-server.exe")
    chosen = builder.select(install)
    builder.add_vc_runtime(chosen, install)
    for name in builder.VC_RUNTIME:
        assert chosen[f"runtime/python/cpython-3.13.17-x/{name}"] == tmp_path / "system32" / name
        assert chosen[f"{builder.LLAMA_FOLDER}/{name}"] == tmp_path / "system32" / name


def test_parts_stay_under_the_limit_and_hold_every_file_once(install, tmp_path):
    write(install, *[f"models/file{i}.txt" for i in range(40)])
    (install / "models" / "weights.safetensors").write_bytes(os.urandom(3000))
    chosen = builder.select(install)
    parts = builder.write_parts(chosen, tmp_path, limit=5000)
    assert len(parts) > 1 and [p.name for p in parts] == [f"truth-guardian-{i}-of-{len(parts)}.zip" for i in range(1, len(parts) + 1)]
    assert all(p.stat().st_size <= 5000 for p in parts)
    builder.verify(parts, chosen)
    with zipfile.ZipFile(parts[-1]) as archive:
        names = archive.namelist()
    found = {}
    for part in parts:
        with zipfile.ZipFile(part) as archive:
            found.update({info.filename: (info, archive.read(info)) for info in archive.infolist()})
    assert names and all(found[name][1] == chosen[name].read_bytes() for name in chosen)
    assert found["models/weights.safetensors"][0].compress_type == zipfile.ZIP_STORED and found["src/app.py"][0].compress_type == zipfile.ZIP_DEFLATED


def test_a_build_replaces_an_earlier_package_but_never_another_folder(install, tmp_path):
    out = tmp_path / "out"
    builder.build(install, out)
    text = (out / "packages" / "package.txt").read_text(encoding="ascii")
    assert "BUILD=" in text and "PARTS=1" in text and "NEED_GB=" in text
    assert (out / builder.STARTER).read_bytes().count(b"\r\n") > 50 and b"\n" not in (out / builder.STARTER).read_bytes().replace(b"\r\n", b"")
    guide = (out / builder.GUIDE).read_text(encoding="utf-8-sig")
    assert "{" not in guide and "راهنمای فارسی" in guide
    (out / "packages" / "stale.zip").write_bytes(b"x")
    builder.build(install, out)
    assert not (out / "packages" / "stale.zip").exists()
    other = tmp_path / "other"
    other.mkdir()
    (other / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        builder.build(install, other)
    assert (other / "keep.txt").exists()


def test_two_packages_built_in_the_same_minute_never_share_a_build(install, tmp_path, monkeypatch):
    monkeypatch.setattr(builder.time, "strftime", lambda *_: "20261106-1742")
    builder.build(install, tmp_path / "a")
    write(install, "models/extra.txt")
    builder.build(install, tmp_path / "b")
    builds = [(tmp_path / name / "packages" / "package.txt").read_text(encoding="ascii").split("BUILD=")[1].split()[0] for name in "ab"]
    assert builds[0].startswith("20261106-1742-") and builds[0] != builds[1]


def start(package: Path, *args: str, **env) -> subprocess.CompletedProcess:
    """SystemDrive points at a folder of the test, so that nothing here can ever unpack on the real system drive."""
    command = f'cmd /d /s /c ""{package / builder.STARTER}" {" ".join(args)}"'
    sandbox = {"SystemDrive": str(package.parent / "system-drive"), "USERPROFILE": str(package.parent / "profile"), **env}
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL, env={**os.environ, **sandbox})


def short_package_folder() -> tuple[Path, Path] | None:
    """A folder whose TruthGuardian folder the starter keeps beside it; past its limit, or in non-Latin letters, it would unpack at the top of the real drive."""
    roots = [tempfile.gettempdir()]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.path.join(os.environ["LOCALAPPDATA"], "Temp"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        base = Path(tempfile.mkdtemp(prefix="tg", dir=root))
        out = base / "A (b)" / "p"
        target = str(out / "TruthGuardian")
        if len(target) <= builder.LONGEST_FOLDER and target.isascii():
            return base, out
        shutil.rmtree(base, ignore_errors=True)
    return None


@pytest.fixture
def package(install) -> Path:
    """In a short folder with a space and brackets in its name: pytest's own folders are too long for unpacking next to the file."""
    write(install, *[f"models/file{i}.txt" for i in range(10)])
    folder = short_package_folder()
    if folder is None:
        pytest.skip(f"no temporary folder is short enough for the starter's {builder.LONGEST_FOLDER}-character limit")
    base, out = folder
    parts = builder.build(install, out, limit=1500)
    assert len(parts) > 2
    yield out
    shutil.rmtree(base, ignore_errors=True)


@windows
def test_the_first_click_unpacks_and_starts_and_the_second_only_starts(package):
    first = start(package, "--port", "8780")
    assert first.returncode == 0 and "Part 1 of" in first.stdout and "STARTED --port 8780" in first.stdout, first.stdout
    assert (package / "TruthGuardian" / "src" / "app.py").is_file() and (package / "TruthGuardian" / "models" / "file9.txt").is_file()
    second = start(package)
    assert second.returncode == 0 and "unpacking" not in second.stdout.lower() and "STARTED" in second.stdout


@windows
def test_a_missing_part_is_named_and_a_new_copy_continues_where_it_stopped(package, tmp_path):
    parts = sorted((package / "packages").glob("*.zip"))
    saved = tmp_path / "saved.zip"
    shutil.move(parts[-1], saved)
    stopped = start(package)
    assert stopped.returncode == 1 and parts[-1].name in stopped.stdout and "STARTED" not in stopped.stdout
    parts[0].unlink()
    shutil.move(saved, parts[-1])
    resumed = start(package)
    assert resumed.returncode == 0 and "Part 1 of" not in resumed.stdout and "STARTED" in resumed.stdout


@windows
def test_a_damaged_part_is_reported_and_nothing_starts(package):
    part = sorted((package / "packages").glob("*.zip"))[0]
    part.write_bytes(part.read_bytes()[: part.stat().st_size // 2])
    stopped = start(package)
    assert stopped.returncode == 1 and "could not be unpacked" in stopped.stdout and "STARTED" not in stopped.stdout


@windows
def test_too_little_disk_space_is_said_before_anything_is_unpacked(package):
    (package / "packages" / "package.txt").write_text("BUILD=x\r\nPARTS=3\r\nNEED_GB=999999\r\n", encoding="ascii")
    stopped = start(package)
    assert stopped.returncode == 1 and "999999 GB" in stopped.stdout and "Part 1 of" not in stopped.stdout


@windows
def test_a_copy_without_its_packages_folder_says_so(package):
    shutil.rmtree(package / "packages")
    stopped = start(package)
    assert stopped.returncode == 1 and "packages folder is missing" in stopped.stdout


@windows
def test_an_app_that_fails_keeps_the_window_with_a_message(package):
    stopped = start(package, FAIL_APP="1")
    assert stopped.returncode == 1 and "The app did not start" in stopped.stdout


@pytest.fixture
def virtual_drive(tmp_path):
    """A drive letter of the test's own (subst), so that unpacking at the top of a drive stays inside the test."""
    free = next(letter for letter in "TUVWXYZ" if not Path(f"{letter}:\\").exists())
    subprocess.run(["subst", f"{free}:", str(tmp_path)], check=True, capture_output=True)
    yield Path(f"{free}:\\")
    subprocess.run(["subst", f"{free}:", "/D"], capture_output=True)


@windows
@pytest.mark.parametrize("folder", ["l" * 90, "داوری (۱۴۰۵)"])
def test_a_long_or_non_latin_folder_unpacks_at_the_top_of_the_same_drive(install, virtual_drive, folder):
    out = virtual_drive / folder / "package"
    builder.build(install, out)
    done = start(out)
    assert done.returncode == 0 and "STARTED" in done.stdout, done.stdout + done.stderr
    assert (virtual_drive / "TruthGuardian" / "src" / "app.py").is_file() and not (out / "TruthGuardian").exists()
    again = start(out)
    assert again.returncode == 0 and "unpacking" not in again.stdout.lower()


@windows
def test_the_installer_refuses_a_non_latin_folder_before_downloading_anything(tmp_path):
    folder = tmp_path / "داوری"
    folder.mkdir()
    shutil.copyfile(ROOT / "Install-Truth-Guardian.bat", folder / "Install-Truth-Guardian.bat")
    done = subprocess.run(f'cmd /d /s /c ""{folder / "Install-Truth-Guardian.bat"}""', capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    assert done.returncode == 1 and "non-Latin" in done.stdout and "Project source" not in done.stdout
    assert not (folder / "TruthGuardian").exists()


@windows
def test_the_installer_will_not_make_a_second_copy_inside_a_project_folder(tmp_path):
    shutil.copyfile(ROOT / "Install-Truth-Guardian.bat", tmp_path / "Install-Truth-Guardian.bat")
    (tmp_path / "TruthGuardian.bat").write_text("@echo off\r\n", encoding="ascii")
    done = subprocess.run(f'cmd /d /s /c ""{tmp_path / "Install-Truth-Guardian.bat"}""', capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    assert done.returncode == 1 and "second copy" in done.stdout and "Project source" not in done.stdout
    assert not (tmp_path / "TruthGuardian").exists()


def test_a_name_too_long_for_the_folder_the_starter_allows_stops_the_build(install, tmp_path, monkeypatch):
    assert f"TARGET:~{builder.LONGEST_FOLDER}" in (ROOT / "deploy" / "portable" / builder.STARTER).read_text(encoding="ascii")
    long_name = "x" * (builder.WINDOWS_PATH_LIMIT - builder.LONGEST_FOLDER)
    monkeypatch.setattr(builder, "select", lambda root: {long_name: install / "README.md"})
    with pytest.raises(SystemExit, match="too long"):
        builder.build(install, tmp_path / "out")
