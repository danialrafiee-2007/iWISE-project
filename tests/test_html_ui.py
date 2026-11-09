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
    assert re.search(r'call "%~dp0TruthGuardian\.bat" --port 8766 %\*', text)


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
