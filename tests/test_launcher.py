"""The launcher's setup steps, run by cmd.exe itself: a step's name may hold brackets, as three of them do."""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from test_fetch_media import DATA, dropping_server

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "TruthGuardian.bat"
INSTALLER = ROOT / "Install-Truth-Guardian.bat"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe only")


def _run_step(tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    text = BAT.read_text(encoding="utf-8").replace("\r\n", "\n")
    step = re.search(r"^:step\n.*?^:skip\n", text, flags=re.M | re.S).group(0).removesuffix(":skip\n")
    script = tmp_path / "steps.bat"
    script.write_text(f'@echo off\r\ncall :step 2 "Datasets (checksums verified)" "{command}" || (echo STOPPED & exit /b 1)\r\necho WENT ON\r\nexit /b 0\r\n'
                      + step.replace("\n", "\r\n"), encoding="ascii")
    return subprocess.run(["cmd", "/d", "/c", str(script)], capture_output=True, text=True, timeout=30)


def test_a_step_that_works_goes_on_whatever_its_name(tmp_path):
    done = _run_step(tmp_path, "ver")
    assert done.returncode == 0 and "WENT ON" in done.stdout and "done" in done.stdout and "failed" not in done.stdout


def test_a_step_that_fails_stops_and_says_so(tmp_path):
    done = _run_step(tmp_path, "cmd /c exit 3")
    assert done.returncode == 1 and "STOPPED" in done.stdout and "Step 2 failed" in done.stdout and "(checksums verified)" in done.stdout


def test_every_step_block_is_flat():
    text = BAT.read_text(encoding="utf-8")
    step = re.search(r"^:step\r?\n(.*?)^:skip", text, flags=re.M | re.S).group(1)
    assert "(" not in step.replace("%~2", "")


def test_setup_steps_do_not_need_the_network_for_uv_itself():
    commands = re.findall(r'call :step \d "[^"]*" "([^"]*)"', BAT.read_text(encoding="utf-8"))
    uv = [c for c in commands if c.startswith("uv ")]
    assert len(uv) == 7 and all(c.startswith("uv run --offline ") for c in uv)


def test_a_setup_with_models_missing_does_not_say_it_is_complete():
    text = BAT.read_text(encoding="utf-8")
    assert text.index("goto setup_partial") < text.index("Setup complete.")
    assert "exit /b 2" in text[text.index(":setup_partial") :]
    installer = INSTALLER.read_text(encoding="utf-8")
    assert 'if not "%SETUP_RC%"=="0" if not "%SETUP_RC%"=="2" goto fail' in installer
    assert installer.index("goto partly_done") < installer.index("Done. The app opens")


def _installer_fetch(tmp_path: Path, url: str, target: Path, sha256: str) -> subprocess.CompletedProcess:
    text = INSTALLER.read_text(encoding="utf-8").replace("\r\n", "\n")
    fetch = re.search(r"^:fetch\n.*?^:bad_zip\n", text, flags=re.M | re.S).group(0).removesuffix(":bad_zip\n")
    script = tmp_path / "fetch.bat"
    script.write_text(f'@echo off\r\nset "CURL=%SystemRoot%\\System32\\curl.exe"\r\ncall :fetch "{url}" "{target}" "{sha256}" || (echo GAVE UP & exit /b 1)\r\necho FETCHED\r\nexit /b 0\r\n'
                      + fetch.replace("\n", "\r\n"), encoding="ascii")
    return subprocess.run(["cmd", "/d", "/c", str(script)], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)


def test_the_installer_finishes_a_download_that_keeps_breaking(tmp_path):
    target = tmp_path / "model.zip"
    with dropping_server(DATA, len(DATA) // 16 + 1) as (url, asked):
        done = _installer_fetch(tmp_path, url, target, hashlib.sha256(DATA).hexdigest())
    assert done.returncode == 0 and "FETCHED" in done.stdout, done.stdout + done.stderr
    assert target.read_bytes() == DATA and asked == sorted(set(asked)) and len(asked) > 10


def test_the_installer_gives_up_on_a_download_that_brings_nothing(tmp_path):
    with dropping_server(DATA, 0) as (url, asked):
        done = _installer_fetch(tmp_path, url, tmp_path / "model.zip", hashlib.sha256(DATA).hexdigest())
    assert done.returncode == 1 and "GAVE UP" in done.stdout and "Could not download" in done.stdout
    assert len(asked) == 10
