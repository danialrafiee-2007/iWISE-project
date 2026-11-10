"""Get-Truth-Guardian.bat (D-213): the one file a judge downloads to fetch the whole project and run it."""

import functools
import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "Get-Truth-Guardian.bat"


def test_the_download_file_asks_for_a_drive_and_makes_its_folder_there():
    text = BAT.read_text(encoding="utf-8")
    assert 'set "FOLDER=iWISE_Truth Guardian"' in text
    assert 'set /p "DRIVE=' in text and r'set "ROOT=%DRIVE%:\%FOLDER%"' in text


def test_it_downloads_the_latest_release_checks_every_part_and_starts_the_package():
    text = BAT.read_text(encoding="utf-8")
    assert re.search(r'set "BASE=https://github\.com/%REPO%/releases/latest/download"', text)
    for name in ("package.txt", "SHA256SUMS.txt", "Start-Truth-Guardian.bat", "README-FIRST.txt"):
        assert f'call :fetch "{name}"' in text, name
    assert "Get-FileHash -Algorithm SHA256" in text and "-C -" in text  # every part checked; broken downloads resume
    assert r'call "%ROOT%\Start-Truth-Guardian.bat"' in text


def test_it_installs_nothing_and_keeps_windows_line_endings():
    raw = BAT.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")  # cmd misreads a batch file with bare line feeds and Persian text
    assert not raw.startswith(b"\xef\xbb\xbf")  # a byte-order mark would break "@echo off"
    text = raw.decode("utf-8").lower()
    for forbidden in ("runas", "reg add", "setx", "msiexec", "winget", "choco "):
        assert forbidden not in text, forbidden


def test_the_repository_keeps_every_batch_file_with_crlf_line_ends():
    """D-215: git keeps .bat files byte for byte, so the copy on the code page and in a ZIP of the repository is the
    same as the Release's; stored with LF, cmd misreads a batch file that holds Persian text."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat -text" in attributes and "*.bat text eol=crlf" not in attributes
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("no git repository here")
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.bat"], capture_output=True, text=True, check=True).stdout.split()
    assert "Get-Truth-Guardian.bat" in names
    for name in names:
        stored = subprocess.run(["git", "-C", str(ROOT), "show", f":{name}"], capture_output=True, check=True).stdout
        assert stored.count(b"\r\n") == stored.count(b"\n") > 0, name


def test_its_messages_are_in_english_only():
    """D-217: the console of Windows 10 draws Persian letters as empty boxes; the Persian guide is README-FIRST.txt."""
    assert BAT.read_bytes().isascii()


# ---- the whole file at work, against a small release served on this computer (D-217) ----

windows = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe only")
FOLDER = "iWISE_Truth Guardian"
OFFLINE = "http://127.0.0.1:9"  # nothing listens there: no internet


def _builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_portable", ROOT / "scripts" / "build_portable.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def drive(tmp_path):
    """A drive letter of the test's own (subst), so that the folder at the top of a drive stays inside the test."""
    folder = tmp_path / "drive"
    folder.mkdir()
    free = next(letter for letter in "TUVWXYZ" if not os.path.exists(f"{letter}:\\"))
    subprocess.run(["subst", f"{free}:", str(folder)], check=True, capture_output=True)
    yield free
    subprocess.run(["subst", f"{free}:", "/D"], capture_output=True)


@pytest.fixture
def release(tmp_path, monkeypatch):
    """A small package, built by the real build script and served the way the Release serves it: every file side by side."""
    builder = _builder()
    install = tmp_path / "install"
    for name in ["src/app.py", "README.md", "runtime/python/cpython-3.13.17-x/python.exe", *[f"models/file{i}.txt" for i in range(10)]]:
        (install / name).parent.mkdir(parents=True, exist_ok=True)
        (install / name).write_bytes(name.encode() * 20)
    (install / "TruthGuardian.bat").write_bytes(b"@echo off\r\necho STARTED %*\r\nexit /b 0\r\n")
    system32 = tmp_path / "system32"
    system32.mkdir()
    for name in builder.VC_RUNTIME:
        (system32 / name).write_bytes(name.encode())
    monkeypatch.setattr(builder, "SYSTEM32", system32)
    out = tmp_path / "package"
    builder.build(install, out, limit=1500)
    served = tmp_path / "release"
    served.mkdir()
    for path in [*(out / "packages").iterdir(), out / builder.STARTER, out / builder.GUIDE]:
        shutil.copyfile(path, served / path.name)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(served)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def get(drive: str, base: str, tmp_path, answers: str) -> subprocess.CompletedProcess:
    """Get-Truth-Guardian.bat run by cmd.exe itself, its questions answered from a file, its desktop a folder of the test."""
    (tmp_path / "answers.txt").write_text(answers, encoding="ascii")
    desktop = tmp_path / "desktop"
    desktop.mkdir(exist_ok=True)
    # TG_DRIVE: the drive offered first is the test's own, so that even an answer lost on the way never reaches a real drive.
    sandbox = {"TG_RELEASE_BASE": base, "TG_DESKTOP": str(desktop), "TG_DRIVE": drive, "SystemDrive": str(tmp_path / "system-drive"),
               "USERPROFILE": str(tmp_path / "profile"), "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    with open(tmp_path / "answers.txt", "rb") as stdin:
        done = subprocess.run(f'cmd /d /s /c ""{BAT}""', capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, stdin=stdin, env={**os.environ, **sandbox})
    folders = [line.split("Folder:", 1)[1].strip() for line in done.stdout.splitlines() if "Folder:" in line]
    assert all(folder == folder_on(drive) for folder in folders), done.stdout
    return done


def folder_on(drive: str) -> str:
    return os.path.join(f"{drive}:" + os.sep, FOLDER)


def shortcut_target(link) -> str:
    command = f"(New-Object -ComObject WScript.Shell).CreateShortcut('{link}').TargetPath"
    return subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, check=True).stdout.strip()


@windows
def test_one_run_downloads_unpacks_frees_the_parts_makes_the_shortcut_and_starts(drive, release, tmp_path):
    first = get(drive, release, tmp_path, f"{drive}\n\ny\n")
    root = folder_on(drive)
    packages = os.path.join(root, "packages")
    assert first.returncode == 0 and "STARTED" in first.stdout, first.stdout + first.stderr
    assert "Overall:" in first.stdout and "All" in first.stdout and "checked" in first.stdout
    assert os.path.isfile(os.path.join(root, "TruthGuardian", "src", "app.py")), first.stdout
    assert not [name for name in os.listdir(packages) if name.endswith((".zip", ".part"))]  # about 5 GB back
    assert os.path.isfile(os.path.join(packages, "package.txt")) and os.path.isfile(os.path.join(root, "Get-Truth-Guardian.bat"))
    link = tmp_path / "desktop" / "Truth Guardian.lnk"
    assert link.is_file() and shortcut_target(link).lower() == os.path.join(root, "Start-Truth-Guardian.bat").lower()

    again = get(drive, release, tmp_path, "\n")
    assert any(line.strip().startswith(f"{drive}:") and "already here" in line for line in again.stdout.splitlines()), again.stdout
    assert again.returncode == 0 and "already unpacked" in again.stdout and "STARTED" in again.stdout
    assert "Downloading" not in again.stdout and "Two questions" not in again.stdout

    offline = get(drive, OFFLINE, tmp_path, "\n")
    assert offline.returncode == 0 and "No connection to GitHub" in offline.stdout and "STARTED" in offline.stdout
    assert "curl:" not in offline.stdout + offline.stderr  # its own words say it, not curl's


@windows
def test_no_means_the_parts_stay_and_no_shortcut_is_made(drive, release, tmp_path):
    done = get(drive, release, tmp_path, f"{drive}\nn\nn\n")
    packages = os.path.join(folder_on(drive), "packages")
    assert done.returncode == 0 and "STARTED" in done.stdout, done.stdout + done.stderr
    assert [name for name in os.listdir(packages) if name.endswith(".zip")]
    assert not (tmp_path / "desktop" / "Truth Guardian.lnk").exists()


@windows
def test_without_internet_and_nothing_downloaded_it_says_so(drive, tmp_path):
    stopped = get(drive, OFFLINE, tmp_path, f"{drive}\n")
    assert stopped.returncode == 1 and "could not be read" in stopped.stdout and "STARTED" not in stopped.stdout


@windows
def test_without_internet_a_download_not_finished_says_to_connect_and_run_again(drive, release, tmp_path):
    done = get(drive, release, tmp_path, f"{drive}\nn\nn\n")
    assert done.returncode == 0
    root = folder_on(drive)
    shutil.rmtree(os.path.join(root, "TruthGuardian"))
    packages = os.path.join(root, "packages")
    for name in os.listdir(packages):
        if name.startswith("unpacked-"):
            os.remove(os.path.join(packages, name))
    os.remove(os.path.join(packages, sorted(n for n in os.listdir(packages) if n.endswith(".zip"))[-1]))
    stopped = get(drive, OFFLINE, tmp_path, "\nn\nn\n")
    assert stopped.returncode == 1 and "not finished" in stopped.stdout and "STARTED" not in stopped.stdout


@windows
def test_the_size_is_told_rounded_as_people_read_it(drive, release, tmp_path):
    """D-217: 5134 MB is "about 5 GB" in what the file says (the room it asks for is still rounded up)."""
    served = tmp_path / "release" / "package.txt"
    served.write_bytes(served.read_bytes().replace(b"TOTAL_MB=1\r\n", b"TOTAL_MB=5134\r\n"))
    done = get(drive, release, tmp_path, f"{drive}\nn\nn\n")
    assert done.returncode == 0 and "about 5 GB" in done.stdout and "about 6 GB" not in done.stdout, done.stdout
    assert "of 5.0 GB" in done.stdout
