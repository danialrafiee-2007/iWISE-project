"""The launcher's setup steps, run by cmd.exe itself: a step's name may hold brackets, as three of them do."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "TruthGuardian.bat"

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
