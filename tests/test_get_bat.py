"""Get-Truth-Guardian.bat (D-213): the one file a judge downloads to fetch the whole project and run it."""

import re
from pathlib import Path

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
    import shutil
    import subprocess

    import pytest

    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat -text" in attributes and "*.bat text eol=crlf" not in attributes
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("no git repository here")
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.bat"], capture_output=True, text=True, check=True).stdout.split()
    assert "Get-Truth-Guardian.bat" in names
    for name in names:
        stored = subprocess.run(["git", "-C", str(ROOT), "show", f":{name}"], capture_output=True, check=True).stdout
        assert stored.count(b"\r\n") == stored.count(b"\n") > 0, name
