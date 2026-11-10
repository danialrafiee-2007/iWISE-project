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


def test_the_model_card_carries_the_sound_and_image_readers_measured_quality(tmp_path):
    """The Reliability tab reads them from /api/model-card; they come from eval/results/media_eval.json (D-139)."""
    import json

    from truth_guardian.web.metrics import model_card

    results = tmp_path / "eval" / "results"
    results.mkdir(parents=True)
    chain = {"auroc": 0.77}
    (results / "media_eval.json").write_text(json.dumps({
        "speech": {"en": {"recordings": 100, "error_rate": 0.08, "unit": "words", "language_right": 1.0, "chain": chain}},
        "images": {"textvqa_en": {"questions": 150, "text_found": 0.93, "answer_read": 0.09, "chain": chain}},
        "qwen": {"answers": 60, "right": 0.88, "chain": chain},
        "components": {"speech": {"data": "FLEURS dev"}},
    }), encoding="utf-8")
    media = model_card(tmp_path)["media"]
    assert media["speech"]["en"] == {"recordings": 100, "error_rate": 0.08, "unit": "words", "language_right": 1.0, "auroc": 0.77}
    assert media["images"]["textvqa_en"]["answer_read"] == 0.09 and media["vision"]["right"] == 0.88
    assert media["data"]["speech"] == "FLEURS dev"
    assert "media" not in model_card(tmp_path / "none")  # no file, no section


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


def test_check_an_answer_is_its_own_tab_and_ask_the_documents_is_gone():
    """D-185: the chat answers from the documents, so the separate Ask tab and js/library.js were removed; Check an
    answer is the previous site's page (examples, own input, streamed check, report, heal) in js/check.js."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert 'id="tab-ask"' not in page and 'id="panel-ask"' not in page and "library.js" not in page
    assert not (HTML / "js" / "library.js").exists()
    assert 'id="check-tab"' in page and "/js/check.js" in page
    check = (HTML / "js" / "check.js").read_text(encoding="utf-8")
    for endpoint in ("/api/examples", "/api/analyze", "/api/heal", "/api/documents"):
        assert endpoint in check
    assert "drawFull" in (HTML / "js" / "chat.js").read_text(encoding="utf-8")  # D-191: the full report shows under the chat


def test_fool_the_guardian_has_the_cards_cascade_and_waits_for_the_models():
    """D-186: the tricks are the previous site's cards cascade (js/cascade.js), the check streams its stages, the
    sources read in their own direction, and nothing is tricked or checked before the models are ready."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert page.index("/js/cascade.js") < page.index("/js/fool.js") and 'id="fool-score"' in page
    fool = (HTML / "js" / "fool.js").read_text(encoding="utf-8")
    assert "TGCascade" in fool and "TGReport.progress" in fool and "getReader" in fool
    assert "/api/health" in fool and 'dir="auto"' in fool
    cascade = (HTML / "js" / "cascade.js").read_text(encoding="utf-8")
    assert '"wheel"' in cascade and "preventDefault" in cascade and "prefers-reduced-motion" in cascade


def test_fool_outcome_is_the_coloured_shield_and_the_sources_are_a_list():
    """D-187: the outcome shows the project's shield in green, amber or red beside its title (no lamp); the sources are
    a list always in view whose text can be selected; report text cannot push its box off the page."""
    fool = (HTML / "js" / "fool.js").read_text(encoding="utf-8")
    assert "outcome-shield" in fool and "signal-lamp" not in fool and "<details" not in fool
    assert all(colour in fool for colour in ("green:", "amber:", "red:")) and "fool-source" in fool
    css = (HTML / "css" / "style.css").read_text(encoding="utf-8")
    assert "unicode-bidi: plaintext" in css and "overflow-wrap: anywhere" in css and "user-select: text" in css
    assert "signal-studio" not in css


def test_fool_marks_tricks_that_do_not_fit_and_its_score_starts_at_zero():
    """D-188: the cards of tricks that cannot change the answer are marked and their button finds an answer they fit;
    the score is kept for the visit only; the wheel turns one card per mouse notch."""
    fool = (HTML / "js" / "fool.js").read_text(encoding="utf-8")
    assert "/api/fool/tricks/" in fool and "findAnswer" in fool and "localStorage" not in fool
    cascade = (HTML / "js" / "cascade.js").read_text(encoding="utf-8")
    assert "const STEP = 100;" in cascade and "const PAUSE = 520;" in cascade


def test_fool_answer_comes_first_and_the_apply_row_sits_in_the_deck():
    """D-189: the answer panel before the deck, a taller deck with bigger cards, the Apply row inside the deck."""
    fool = (HTML / "js" / "fool.js").read_text(encoding="utf-8")
    assert fool.index('id="fool-answer-card"') < fool.index('id="fool-deck"')
    assert "height: 620" in fool and '.querySelector(".cascade-stage")?.appendChild(applyEl)' in fool


def test_check_an_answer_uses_the_previous_sites_coverflow_deck():
    """D-190: the examples are the previous site's ring coverflow (js/spectra.js, loaded before js/check.js), mounted
    once and paused while a check runs or a report is shown; the example titles come in every language."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert page.index("/js/spectra.js") < page.index("/js/check.js")
    check = (HTML / "js" / "check.js").read_text(encoding="utf-8")
    assert "TGSpectra.mount" in check and "paused: () => check.running || heal.running || !!view" in check
    spectra = (HTML / "js" / "spectra.js").read_text(encoding="utf-8")
    assert all(word in spectra for word in ("pointerdown", '"wheel"', "setInterval", "prefers-reduced-motion"))
    i18n = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    assert '"example.anne-frank.title": "سال اشتباه و ارجاع اشتباه"' in i18n and '"deck.browse"' in i18n


def test_the_chat_goes_to_the_free_online_answer_and_shows_the_full_report_below():
    """D-191: no Claude in the chat's online answer; "Truth Guardian check" shows the full report under the chat."""
    chat = (HTML / "js" / "chat.js").read_text(encoding="utf-8")
    assert "/api/ask/free" in chat and "/api/ask/web" not in chat and "TG.go" not in chat
    assert 'id="chat-full"' in (HTML / "index.html").read_text(encoding="utf-8")
    server = (ROOT / "src" / "truth_guardian" / "web" / "app.py").read_text(encoding="utf-8")
    assert '"/api/ask/free"' in server and '"/api/ask/web"' not in server


def test_the_chat_bubble_shows_the_answer_alone_and_an_untrusted_documents_answer_goes_online():
    """D-198: the Guardian's report is under the chat only; a documents' answer the check does not trust is not shown."""
    chat = (HTML / "js" / "chat.js").read_text(encoding="utf-8")
    bubble = chat[chat.index("  function showAnswer(box, a) {"):chat.index("  function untrusted(a) {")]
    assert "TGReport.render" not in bubble and "sourcesHTML" not in bubble and "msg-hint" in bubble
    assert "function untrusted(a)" in chat and 'a.status === "not_in_documents" || rejected' in chat
