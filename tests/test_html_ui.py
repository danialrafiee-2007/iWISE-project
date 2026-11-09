"""The plain HTML front end next to the React one: TG_UI=html picks its folder, and its own launcher sets that."""

import re
from pathlib import Path

from truth_guardian.web import app as web_app

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "truth_guardian" / "web" / "static_html"
LAUNCHER = ROOT / "TruthGuardian-HTML.bat"


def test_tg_ui_html_picks_the_html_folder_and_anything_else_the_react_build():
    assert web_app.ui_folder("html") == HTML
    assert web_app.ui_folder(" HTML ") == HTML
    for choice in (None, "", "react", "static"):
        assert web_app.ui_folder(choice).name == "static"


def test_the_html_front_end_loads_nothing_from_the_internet():
    files = [p for p in HTML.rglob("*") if p.suffix in {".html", ".css", ".js"}]
    assert (HTML / "index.html") in files
    for path in files:
        assert not re.search(r"https?://", path.read_text(encoding="utf-8")), path


def test_the_html_launcher_sets_its_front_end_and_its_own_port():
    raw = LAUNCHER.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    assert 'set "TG_UI=html"' in text
    # The launcher opens the site itself, full screen, so the plain launcher is told not to open a browser.
    assert re.search(r'call "%HERE%TruthGuardian\.bat" --port 8766 --no-browser%PASS%', text)
    assert re.search(r'-File "%HERE%scripts\\open_fullscreen\.ps1" -Port %PORT%', text)
    # shift moves %0 as well, so the folder is kept before the options are read and %~dp0 is not used after them.
    assert text.index('set "HERE=%~dp0"') < text.index(":args") and "%~dp0" not in text[text.index(":args") :]


def test_the_full_screen_opener_waits_for_the_server_and_uses_its_own_profile():
    raw = (ROOT / "scripts" / "open_fullscreen.ps1").read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    assert "/api/health" in text and "--start-fullscreen" in text and "--app=" in text
    assert "runtime\\browser-profile" in text


def _launcher_choice(tmp_path: Path, *args: str) -> str:
    """Runs the launcher's argument handling alone in cmd.exe and returns PORT, OPEN and PASS."""
    text = LAUNCHER.read_text(encoding="utf-8").replace("\r\n", "\n")
    head = text[text.index('set "PORT=8766"') : text.index(":args_done")]
    script = tmp_path / "args.bat"
    script.write_text("@echo off\r\nsetlocal\r\n" + head.replace("\n", "\r\n") + ":args_done\r\necho [%PORT%][%OPEN%][%PASS%]\r\n", encoding="ascii")
    import subprocess

    return subprocess.run(["cmd", "/d", "/c", str(script), *args], capture_output=True, text=True, timeout=30).stdout.strip()


def test_the_launcher_opens_full_screen_only_when_it_starts_the_site(tmp_path):
    import sys

    if sys.platform != "win32":
        return
    assert _launcher_choice(tmp_path) == "[8766][1][]"
    assert _launcher_choice(tmp_path, "--port", "8780") == "[8780][1][ --port 8780]"
    assert _launcher_choice(tmp_path, "--no-browser") == "[8766][0][ --no-browser]"
    assert _launcher_choice(tmp_path, "check") == "[8766][0][ check]"


def test_the_server_shows_the_html_pages_when_asked(monkeypatch):
    from fastapi.testclient import TestClient

    from truth_guardian.web.examples import ExampleStore
    from test_web_api import FakeEngine

    monkeypatch.setattr(web_app, "STATIC", HTML)
    with TestClient(web_app.create_app(FakeEngine(), ExampleStore(ROOT), load=False)) as c:
        page = c.get("/analyze")
        assert page.status_code == 200 and "/js/app.js" in page.text
        assert c.get("/css/style.css").status_code == 200
        assert c.get("/api/health").status_code == 200
