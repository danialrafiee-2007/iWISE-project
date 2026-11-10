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
        if path.name == "arch-src.js":
            continue  # the project's source code shown as text on the Architecture page (D-206); nothing in it is loaded
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


def test_an_image_answers_check_is_shown_in_the_full_report():
    """D-199: the full report shows the image check's verdict, its share and each sentence; the opinion note is translated."""
    chat = (HTML / "js" / "chat.js").read_text(encoding="utf-8")
    assert "function seenHTML(a)" in chat and "${seenHTML(a)}" in chat and "html.free.n.opinion" in chat
    i18n = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    assert '"html.seen.hallucinated": "توهم: پاسخ می‌گوید در تصویر متنی هست که وجود ندارد"' in i18n


def test_the_second_opinion_is_shown_in_the_full_report():
    """D-200: the full report shows the second model's opinion on an image or a recording, agreed or disputed."""
    chat = (HTML / "js" / "chat.js").read_text(encoding="utf-8")
    assert "function secondHTML(a)" in chat and "${secondHTML(a)}" in chat
    i18n = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    assert '"html.second.disputed": "دو مدل اختلاف دارند: احتمال توهم"' in i18n


def test_the_chat_scrolls_inside_itself_and_the_report_opens_in_a_window():
    """D-201: the chat keeps its height and its log scrolls; the full report opens in a window over the page."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert '<dialog class="person-dialog report-dialog" id="chat-full"' in page and 'class="report-dialog-body"' in page
    chat = (HTML / "js" / "chat.js").read_text(encoding="utf-8")
    assert "full.showModal()" in chat and "scrollIntoView" not in chat and "log.scrollTop = log.scrollHeight" in chat
    css = (HTML / "css" / "style.css").read_text(encoding="utf-8")
    assert ".chat .chat-log { flex: 1 1 0; min-height: 0;" in css and ".report-dialog-body {" in css


def test_the_banner_has_a_second_lamp_for_the_online_models_and_the_new_description():
    """D-202: under the local models' lamp, a second one says whether the free online models answer; the banner's
    description says what is checked for text, images and recordings, in all seven languages."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert 'id="online-lamp"' in page and 'id="online-state"' in page and 'data-i18n="html.lead"' in page
    assert page.index('id="chip-lamp"') < page.index('id="online-lamp"')
    script = (HTML / "js" / "app.js").read_text(encoding="utf-8")
    assert "/api/online/status" in script and "html.online.on" in script
    strings = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    for key in ("html.lead", "html.online.on", "html.online.partly", "html.online.off", "html.online.checking"):
        assert strings.count(f'"{key}"') == 7, key


def test_the_architecture_page_and_the_rails_online_lamp():
    """D-203: a rail button opens the Architecture page, six stages each naming its models, local or online; the online
    lamp also stands in the rail under the local models' one; the home page fits the screen."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert 'href="/architecture" data-page="architecture"' in page and 'class="page" data-page="architecture"' in page
    assert page.count('class="card arch-step"') == 6
    assert page.index('id="rail-lamp"') < page.index('id="rail-online-lamp"')
    assert '"/architecture": "architecture"' in (HTML / "js" / "pages.js").read_text(encoding="utf-8")
    assert "rail-online-lamp" in (HTML / "js" / "app.js").read_text(encoding="utf-8")
    strings = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    for n in range(1, 7):
        assert strings.count(f'"html.arch.s{n}.d"') == 7
    css = (HTML / "css" / "style.css").read_text(encoding="utf-8")
    assert 'grid-template-rows: auto minmax(0, 1fr)' in css and "text-align: justify" in css


def test_three_lamps_soft_tabs_and_the_reliability_diagram():
    """D-204: a third lamp for the Guardian in the banner and the rail; the Model performance tabs change without the
    page dropping to the top (the new height is worked out, never measured by letting the page go short); Reliability
    has the previous site's reliability diagram."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert 'id="guard-lamp"' in page and 'id="rail-guard-lamp"' in page
    assert page.index('id="rail-online-lamp"') < page.index('id="rail-guard-lamp"')
    script = (HTML / "js" / "app.js").read_text(encoding="utf-8")
    assert "html.guard.ready" in script and "/api/health" in script and "/api/media/status" in script
    pages = (HTML / "js" / "pages.js").read_text(encoding="utf-8")
    assert "from - shownHeight + next.offsetHeight" in pages and 'page.style.minHeight = ""' in pages
    models = (HTML / "js" / "models.js").read_text(encoding="utf-8")
    assert "calib.aria" in models and "card.calib1" in models
    strings = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    for key in ("html.guard.ready", "calib.point", "card.calib3"):
        assert strings.count(f'"{key}"') == 7, key


def test_a_reload_goes_home_and_the_lamps_are_level_with_the_description():
    """D-205: a reload anywhere opens the home page; the banner's three lamps share the description's row, as tall as
    its box, in three equal rows."""
    pages = (HTML / "js" / "pages.js").read_text(encoding="utf-8")
    assert '"reload"' in pages and 'history.replaceState(null, "", "/")' in pages
    assert pages.index('history.replaceState(null, "", "/")') < pages.index("show(location.pathname, { instant: true")
    css = (HTML / "css" / "style.css").read_text(encoding="utf-8")
    assert ".home-banner .status-stack { height: 100%; grid-template-rows: repeat(3, minmax(0, 1fr))" in css


def test_the_architecture_graph_shows_the_real_code_in_seven_languages():
    """D-206: every node of the code map names code that exists, the page's copy of that code is the code as it is now
    (run scripts/build_arch_source.py after changing a file it shows), and every node says what it does in all seven
    languages."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_arch_source", ROOT / "scripts" / "build_arch_source.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert (HTML / "js" / "arch-src.js").read_text(encoding="utf-8") == builder.build(), "run scripts/build_arch_source.py"
    data = (HTML / "js" / "arch-data.js").read_text(encoding="utf-8")
    ids = re.findall(r'id: "([^"]+)"', data)
    assert len(ids) == len(set(ids)) >= 90
    strings = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    for node in ids:
        assert strings.count(f'"html.ag.{node}"') == 7, node
    page = (HTML / "index.html").read_text(encoding="utf-8")
    order = [page.index(f'<script src="/js/{name}') for name in ("arch-data.js", "arch-src.js", "arch-graph.js")]
    assert 'id="arch-graphs"' in page and order == sorted(order)


def test_the_code_map_comes_first_and_every_stage_button_opens_real_code():
    """D-207: on the Architecture page the code map comes right after the banner and the six stages follow it as a
    catalog; every function button of a stage names code the page carries."""
    page = (HTML / "index.html").read_text(encoding="utf-8")
    arch = page[page.index('data-page="architecture"'):page.index('data-page="team" hidden')]
    assert arch.index('id="arch-graphs"') < arch.index('class="arch-flow"') < arch.index('id="code-dialog"')
    buttons = re.findall(r'class="arch-fn" data-src="([^"]+)"', arch)
    assert len(buttons) >= 18
    shown = (HTML / "js" / "arch-src.js").read_text(encoding="utf-8")
    for key in buttons:
        assert f'"{key}":' in shown, key


def test_a_node_opens_the_code_window_and_the_page_behind_it_is_locked():
    """D-208: a node of the code map opens the same window as the stages' buttons (no side panel), with its role, what
    it does, its inputs and outputs and its whole code; while any window is open the page behind it does not scroll."""
    script = (HTML / "js" / "arch-graph.js").read_text(encoding="utf-8")
    assert "ag-panel" not in script and "showNode(n," in script
    page = (HTML / "index.html").read_text(encoding="utf-8")
    for part in ("code-dialog-role", "code-dialog-desc", "code-dialog-io", "data-in", "data-out"):
        assert part in page[page.index('id="code-dialog"'):], part
    css = (HTML / "css" / "style.css").read_text(encoding="utf-8")
    assert "html:has(dialog[open]) { overflow: hidden;" in css


def test_the_site_tour_walks_the_site_home_models_and_architecture():
    """D-209: the rail's tour menu starts the site tour or plays it by itself; its steps go from the site as a whole to
    the home page, Model performance and Architecture, in that order, each step with its words in seven languages."""
    script = (HTML / "js" / "ui.js").read_text(encoding="utf-8")
    tour = script[script.index("const STEPS = ["):script.index("].map((step, i)")]
    urls = re.findall(r'url: "([^"]+)"', tour)
    assert urls[0] == "/" and urls[-1] == "/architecture" and len(urls) == 14
    order = [urls.index(u) for u in ("/", "/models", "/architecture")]
    assert order == sorted(order) and urls == sorted(urls, key=["/", "/models", "/architecture"].index)
    page = (HTML / "index.html").read_text(encoding="utf-8")
    assert 'data-tour="site"' in page and 'data-tour="play"' in page and 'data-tour="text"' not in page
    strings = (HTML / "js" / "i18n.js").read_text(encoding="utf-8")
    for i in range(1, 15):
        for part in ("t", "b"):
            assert strings.count(f'"html.tour.s{i}.{part}"') == 7, (i, part)
