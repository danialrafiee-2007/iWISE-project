import http.server
import json
import threading
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from truth_guardian import online
from truth_guardian.heal import Change, Healing
from truth_guardian.media import vision
from truth_guardian.rag.answer import HISTORY_CHARS, HISTORY_TURNS, NOT_IN_DOCUMENTS, _HoldBack, _tidy_citations, answer, light_check
from truth_guardian.rag.generators import ClaudeGenerator, LocalGenerator, NotAvailable, Written, repeat_starts
from truth_guardian.rag.library import MINE, Hit, Library
from truth_guardian.report import ClaimReport, Evidence, Report
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT, Cancelled, NotChecked
from truth_guardian.web.examples import ExampleStore

from test_rag_library import FRANK, fake_encode
from test_web_api import FakeEngine, events

QUESTION = "When did Anne Frank die of typhus at Bergen-Belsen in February 1945?"
RIGHT = "Anne Frank died in February 1945 [1]."


def report(verdict: str, risk: float, text: str = RIGHT) -> Report:
    claim = ClaimReport(start=0, end=len(text), text=text, status="supported" if verdict == "grounded" else "unsupported", risk=risk, explanation="x", action="keep")
    return Report(id="rag", verdict=verdict, risk=risk, response_threshold=0.45, sentence_threshold=0.3, claims=[claim])


class Script:
    """Stands in for a generator: says the scripted words, and records what it was asked."""

    name = "script"

    def __init__(self, *replies: str):
        self.replies, self.asked = list(replies), []

    def available(self) -> bool:
        return True

    def write(self, system, messages, on_text=None, images=(), schema=None) -> Written:
        self.asked.append((system, messages))
        self.images, self.schema = list(images), schema
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        for start in range(0, len(reply), 7):
            if on_text:
                on_text(reply[start : start + 7])
        return Written(reply, "script-model", 0.25)


class Checker:
    """Stands in for the Guardian: a fixed report, and a heal that replaces the answer."""

    def __init__(self, first: Report | None = None, healed_to: str | None = None, refuses: NotChecked | None = None):
        self.first, self.healed_to, self.refuses, self.samples = first or report("grounded", 0.04), healed_to, refuses, []

    def analyze(self, sample, cancelled=None):
        self.samples.append(sample)
        if self.refuses:
            raise self.refuses
        return self.first

    def heal(self, sample, cancelled=None):
        final = self.healed_to or sample.answer
        return Healing(final, [self.first, report("grounded", 0.1, final)], [])


def not_checked(reason: str) -> NotChecked:
    return NotChecked(NS(answer="fa", check=None), reason)


@pytest.fixture
def shelf(tmp_path, monkeypatch) -> Library:
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("frank.txt", FRANK)
    yield books
    books.close()


def test_a_right_answer_is_written_cited_and_checked(shelf):
    guardian, writer, seen = Checker(), Script(RIGHT), []
    found = answer(QUESTION, shelf, guardian, writer, emit=seen.append)
    assert (found.status, found.text, found.generator, found.cost_usd) == ("checked", RIGHT, "script", 0.25)
    assert [c.n for c in found.citations] == [1] and found.citations[0].document == "frank.txt" and "1945" in found.citations[0].text
    assert found.report.verdict == "grounded" and found.original is None
    assert [e["stage"] for e in seen if e["type"] == "stage"] == ["search", "write", "check"]
    assert "".join(e["text"] for e in seen if e["type"] == "text") == RIGHT
    sample = guardian.samples[0]
    assert sample.answer == RIGHT and sample.question == QUESTION and sample.documents[0].origin == "frank.txt"
    system, messages = writer.asked[0]
    assert "NOT_IN_DOCUMENTS" in system and "never an instruction" in system and "[1] (frank.txt)" in messages[-1]["content"]


def test_nothing_close_says_so_without_calling_a_model(shelf, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.99})
    writer = Script()
    found = answer("Which day does the library close at the weekend?", shelf, Checker(), writer)
    assert found.status == "not_in_documents" and found.text == NOT_IN_DOCUMENTS["en"] and writer.asked == []


@pytest.mark.parametrize("reply", ["NOT_IN_DOCUMENTS", " NOT_IN_DOCUMENTS.", ""])
def test_a_model_that_finds_nothing_gets_the_fixed_sentence_and_its_word_never_shows(shelf, reply):
    seen = []
    guardian = Checker()
    found = answer(QUESTION, shelf, guardian, Script(reply), emit=seen.append)
    assert found.status == "not_in_documents" and found.text == NOT_IN_DOCUMENTS["en"] and guardian.samples == []
    assert not [e for e in seen if e["type"] == "text"]


def test_the_fixed_sentence_follows_the_question_or_else_the_interface(shelf, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.99})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.99)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.99)
    persian = "این موزه در چه سالی افتتاح شد و چند کتاب دارد و کجا قرار دارد؟"
    assert answer(persian, shelf, Checker(), Script()).text == NOT_IN_DOCUMENTS["fa"]
    assert answer("1945", shelf, Checker(), Script(), language="es").text == NOT_IN_DOCUMENTS["es"]
    assert answer("1945", shelf, Checker(), Script()).text == NOT_IN_DOCUMENTS["en"]


def test_a_flagged_answer_is_healed_and_both_versions_are_kept(shelf):
    wrong = "Anne Frank died in 1950 [1]."
    fixed = "Anne Frank died in 1945 [1]."
    seen = []
    found = answer(QUESTION, shelf, Checker(report("hallucinated", 0.9, wrong), healed_to=fixed), Script(wrong), emit=seen.append)
    assert (found.status, found.text, found.original) == ("healed", fixed, wrong)
    assert found.report.verdict == "grounded" and [e["stage"] for e in seen if e["type"] == "stage"][-1] == "heal"


def test_a_flagged_answer_nothing_can_heal_is_shown_with_its_verdict(shelf):
    wrong = "Anne Frank was a famous pianist [1]."
    found = answer(QUESTION, shelf, Checker(report("hallucinated", 0.9, wrong)), Script(wrong))
    assert found.status == "checked" and found.text == wrong and found.report.verdict == "hallucinated"


def test_a_language_no_check_reads_gets_the_light_check_and_says_so(shelf):
    persian = "آنه فرانک در سال 1945 درگذشت [1]."
    found = answer(QUESTION, shelf, Checker(refuses=not_checked("language")), Script(persian))
    assert found.status == "light" and found.report is None and found.text == persian
    assert [c.status for c in found.light] == ["close"] or found.light[0].reasons


def test_a_check_that_is_not_installed_leaves_the_answer_unchecked_and_says_why(shelf):
    found = answer(QUESTION, shelf, Checker(refuses=not_checked("not_installed")), Script(RIGHT))
    assert found.status == "unchecked" and found.text == RIGHT and "not installed" in found.notes[0]


def test_a_follow_up_is_searched_for_as_a_question_of_its_own(shelf):
    writer = Script("When did Anne Frank die of typhus?", RIGHT)
    history = [{"role": "user", "content": "Who was Anne Frank?"}, {"role": "assistant", "content": "A diarist [1]."}]
    found = answer("And when did she die?", shelf, Checker(), writer, history=history)
    assert found.searched_for == "When did Anne Frank die of typhus?" and found.question == "And when did she die?"
    assert "Who was Anne Frank?" in writer.asked[0][1][0]["content"]
    assert writer.asked[1][1][0] == history[0] and "And when did she die?" in writer.asked[1][1][-1]["content"]


def test_a_failed_rewrite_falls_back_to_the_question_as_asked(shelf):
    history = [{"role": "user", "content": "Who was Anne Frank?"}]
    found = answer(QUESTION, shelf, Checker(), Script(NotAvailable("server down"), RIGHT), history=history)
    assert found.searched_for == QUESTION and found.status == "checked"


def test_citations_of_documents_never_given_are_removed():
    hit = Hit(1, 1, "a.txt", MINE, 3, "Text.", 0.9, 0.1)
    tidy, citations, notes = _tidy_citations("It opened [1, 7]. It closed [9]. It sold [1][1].", [hit])
    assert tidy == "It opened [1]. It closed. It sold [1] [1]."
    assert [(c.n, c.page) for c in citations] == [(1, 3)] and "removed" in notes[0]
    assert _tidy_citations("It opened.", [hit]) == ("It opened.", [], [])


def test_a_heading_copied_from_the_prompt_is_no_part_of_the_answer():
    hit = Hit(1, 1, "a.txt", MINE, 3, "Text.", 0.9, 0.1)
    assert _tidy_citations("[1] (a.txt, page 3)  \nIt opened.", [hit])[0] == "[1] It opened."


def test_the_prompt_ends_with_the_question_since_a_last_instruction_cost_the_citations(shelf):
    writer = Script(RIGHT)
    answer(QUESTION, shelf, Checker(), writer)
    assert writer.asked[0][1][-1]["content"].endswith(f"Question: {QUESTION}")
    assert "After each fact, cite its document" in writer.asked[0][0]


def test_the_model_is_told_the_language_only_where_the_script_tells_it(shelf):
    persian = "این موزه در چه سالی افتتاح شد و چند کتاب دارد و کجا قرار دارد؟"
    writer = Script(RIGHT)
    answer(persian, shelf, Checker(), writer)
    assert writer.asked[0][0].endswith("write the whole answer in Persian.") and writer.asked[0][1][-1]["content"].endswith(f"Question: {persian}")
    for question in (QUESTION, "¿Qué comprueba este documento sobre Anne Frank y el año de su muerte?", "1945"):
        writer = Script(RIGHT)
        answer(question, shelf, Checker(), writer)
        assert "write the whole answer" not in writer.asked[0][0]


@pytest.mark.parametrize(
    "healed, changes",
    [
        ("[3]", [Change(0, 10, "x", "", "removed: the sources do not support it")]),
        ("A sentence from a source.", [Change(0, 10, "x", "A sentence from a source.", "replaced with the source sentence it contradicts")]),
        ("Anne Frank died in 1945 [1].", [Change(19, 23, "1950", "1945", "replaced with the value in the sources")]),
    ],
)
def test_healing_that_leaves_no_answer_or_swaps_in_a_source_sentence_is_not_used(shelf, healed, changes):
    wrong = "Anne Frank died in 1950 [1]."
    guardian = Checker(report("hallucinated", 0.9, wrong))
    guardian.heal = lambda sample, cancelled=None: Healing(healed, [guardian.first, report("grounded", 0.1, healed)], [changes])
    found = answer(QUESTION, shelf, guardian, Script(wrong))
    assert (found.status, found.text, found.original) == ("checked", wrong, None) and found.report.verdict == "hallucinated"


def test_an_answer_citing_nothing_shows_the_passages_close_to_it_and_says_they_are_not_its_citations(shelf):
    words = "Anne Frank died in February 1945."
    checked = report("grounded", 0.04, words)
    held = shelf.search(QUESTION, (MINE,)).hits[0]
    checked.claims[0].evidence = Evidence(text=held.text.split(". ")[0])
    found = answer(QUESTION, shelf, Checker(checked), Script(words))
    assert [(c.document, c.inferred) for c in found.citations] == [("frank.txt", True)] and found.text == words
    assert answer(QUESTION, shelf, Checker(checked), Script(RIGHT)).citations[0].inferred is False
    assert answer(QUESTION, shelf, Checker(), Script("Nothing the passages say.")).citations == []


def test_a_light_checked_answer_citing_nothing_also_shows_the_passages_close_to_it(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("موزه.txt", "موزه ریورساید در سال ۱۳۲۹ در شهر باز شد.".encode())
    found = answer("موزه ریورساید در چه سالی در شهر باز شد؟", books, Checker(refuses=not_checked("language")), Script("موزه ریورساید در سال ۱۳۲۹ باز شد."), (MINE,))
    assert found.status == "light" and [(c.document, c.inferred) for c in found.citations] == [("موزه.txt", True)]
    books.close()


def test_one_sentence_joining_facts_from_two_files_shows_both(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("museum.txt", b"The museum holds many old books.")
    books.add("sign.txt", b"The library closes on Sunday every week.")
    words = "The museum holds many books, and the library closes on Sunday."
    found = answer("How many books does the museum hold and when does the library close?", books, Checker(report("grounded", 0.1, words)), Script(words), (MINE,))
    assert [c.document for c in found.citations] == ["museum.txt", "sign.txt"] and all(c.inferred for c in found.citations)
    books.close()


def test_a_healing_that_still_fails_its_check_is_not_used(shelf):
    wrong = "Anne Frank died in 1950 [1]. She was born in 1800 [1]."
    cut_short = "Anne Frank died in 1950 [1]."
    guardian = Checker(report("hallucinated", 0.9, wrong))
    guardian.heal = lambda sample, cancelled=None: Healing(cut_short, [guardian.first, report("hallucinated", 0.8, cut_short)], [[Change(0, 5, "x", "", "removed: the sources do not support it")]])
    found = answer(QUESTION, shelf, guardian, Script(wrong))
    assert (found.status, found.text, found.report.risk) == ("checked", wrong, 0.9)


def test_the_fixed_sentence_reads_a_language_tag_from_the_interface(shelf, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.99})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.99)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.99)
    assert answer("1945", shelf, Checker(), Script(), language="fa-IR").text == NOT_IN_DOCUMENTS["fa"]


def test_a_long_conversation_is_cut_to_what_the_local_model_can_hold(shelf):
    writer = Script("When did Anne Frank die?", RIGHT)
    history = [{"role": "user", "content": f"{n} " + "x" * 5_000} for n in range(10)]
    answer(QUESTION, shelf, Checker(), writer, history=history)
    (*turns, asked) = writer.asked[1][1]
    assert len(turns) == HISTORY_TURNS and all(len(t["content"]) == HISTORY_CHARS for t in turns) and turns[0]["content"].startswith("4 ") and "Question:" in asked["content"]
    assert len(writer.asked[0][1][0]["content"]) < (HISTORY_CHARS + 10) * HISTORY_TURNS + len(QUESTION) + 10


def test_what_the_rewriting_cost_is_counted_with_the_answer(shelf):
    history = [{"role": "user", "content": "Who was Anne Frank?"}]
    assert answer(QUESTION, shelf, Checker(), Script(QUESTION, RIGHT), history=history).cost_usd == 0.5


def test_when_the_person_leaves_the_writing_stops(shelf):
    gone = threading.Event()
    gone.set()
    guardian = Checker()
    with pytest.raises(Cancelled):
        answer(QUESTION, shelf, guardian, Script(RIGHT), cancelled=gone)
    assert guardian.samples == []


def test_healing_keeps_its_own_words_so_its_report_still_lines_up(shelf):
    wrong = "Anne Frank died in 1950 [1]."
    healed = "Anne Frank died in February 1945 [12]."
    found = answer(QUESTION, shelf, Checker(report("hallucinated", 0.9, wrong), healed_to=healed), Script(wrong))
    assert found.text == healed and found.status == "healed" and all(c.inferred for c in found.citations)


def test_holding_back_shows_nothing_of_the_no_answer_word_and_everything_else():
    seen = []
    hold = _HoldBack(seen.append)
    for piece in ("NOT_", "IN_", "DOCUMENTS"):
        hold(piece)
    assert seen == []
    seen.clear()
    hold = _HoldBack(seen.append)
    for piece in ("NO", "T only that", ", it opened"):
        hold(piece)
    assert "".join(seen) == "NOT only that, it opened"


def light_hit(text: str) -> Hit:
    return Hit(1, 1, "a.txt", MINE, None, text, 0.9, 0.1)


def test_the_light_check_finds_numbers_no_passage_has_in_any_script():
    claims = light_check("موزه در سال ۱۳۲۹ باز شد. موزه در سال ۱۳۵۰ بسته شد.", [light_hit("موزه در سال 1329 باز شد و هنوز باز است.")], fake_encode_same)
    assert [c.status for c in claims] == ["close", "doubtful"] and "number" in claims[1].reasons[0]


def fake_encode_same(texts, kind):
    import numpy as np

    return np.ones((len(texts), 4)) / 2


def test_the_light_check_finds_a_sentence_no_passage_is_close_to():
    import numpy as np

    far = lambda texts, kind: np.tile([1.0, 0.0], (len(texts), 1)) if kind == "query" else np.tile([0.0, 1.0], (len(texts), 1))
    (claim,) = light_check("این جمله ربطی به اسناد ندارد.", [light_hit("متن دیگری درباره‌ی موضوع دیگری است.")], far)
    assert claim.status == "doubtful" and "close" in claim.reasons[0]


class LlamaLike(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for text in self.server.pieces:
                self.wfile.write(f'data: {json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)}\n\n'.encode())
                self.wfile.flush()
                self.server.sent += 1
            self.wfile.write(f'data: {json.dumps({"choices": [{"delta": {}, "finish_reason": self.server.finish}]})}\n\ndata: [DONE]\n\n'.encode())
        except OSError:
            pass

    def log_message(self, *args):
        pass


@pytest.fixture
def llama(monkeypatch):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), LlamaLike)
    server.pieces, server.finish, server.sent, server.body = ["Hel", "lo ", "دنیا"], "stop", 0, None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake = NS(url=f"http://127.0.0.1:{server.server_port}", start=lambda: None)
    monkeypatch.setattr(vision, "files_present", lambda: True)
    monkeypatch.setattr(vision, "server", lambda: fake)
    yield server
    server.shutdown()
    server.server_close()


def test_the_local_generator_reads_llama_servers_stream(llama):
    pieces = []
    written = LocalGenerator().write("Be brief.", [{"role": "user", "content": "Hi"}], pieces.append)
    assert written.text == "Hello دنیا" and pieces == ["Hel", "lo ", "دنیا"] and written.cost_usd == 0
    assert llama.body["messages"][0] == {"role": "system", "content": "Be brief."} and llama.body["stream"] is True


def test_the_local_model_stops_at_the_first_sentence_it_says_twice(llama):
    loop = "The check is done by the fusion model [1]. "
    llama.pieces = ["It opened in 1950. ", loop, "It has many books. ", loop, *[loop] * 500]
    pieces = []
    written = LocalGenerator().write("s", [], pieces.append)
    assert written.text == "It opened in 1950. The check is done by the fusion model [1]. It has many books."
    assert len(pieces) == 4


def test_a_reply_cut_off_by_its_token_limit_ends_at_its_last_whole_sentence(llama):
    llama.pieces, llama.finish = ["It opened in 1950. It has many books, ", "which"], "length"
    assert LocalGenerator().write("s", []).text == "It opened in 1950."
    llama.pieces = ["It opened in 1950 and"]
    assert LocalGenerator().write("s", []).text == "It opened in 1950 and"


@pytest.mark.parametrize(
    "text, at",
    [
        ("One long sentence here. Another long sentence. One long sentence here.", 47),
        ("One long sentence here [1]. One LONG sentence here [2].", 28),
        ("Yes. No. Yes.", None),
        ("他死于一九四五年的二月份那个冬天。她出生于一九二九年的六月份。他死于一九四五年的二月份那个冬天。", 31),
        ("Nothing is said twice in this reply. Not one sentence.", None),
    ],
)
def test_a_repeat_is_found_whatever_its_citations_and_case(text, at):
    assert repeat_starts(text) == at


def test_the_local_generator_says_when_its_model_is_missing(monkeypatch):
    monkeypatch.setattr(vision, "files_present", lambda: False)
    with pytest.raises(NotAvailable, match="not on this computer"):
        LocalGenerator().write("s", [])


def test_a_local_server_that_will_not_start_or_answer_is_told_in_words(monkeypatch):
    def fails():
        raise RuntimeError("llama-server stopped while starting")

    monkeypatch.setattr(vision, "files_present", lambda: True)
    monkeypatch.setattr(vision, "server", lambda: NS(start=fails))
    with pytest.raises(NotAvailable, match="did not answer: llama-server stopped"):
        LocalGenerator().write("s", [])
    monkeypatch.setattr(vision, "server", lambda: NS(url="http://127.0.0.1:9", start=lambda: None))
    with pytest.raises(NotAvailable, match="did not answer"):
        LocalGenerator().write("s", [])


def test_an_online_failure_is_told_in_words(tmp_path):
    def fails(**request):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))

    client = NS(beta=NS(messages=NS(stream=fails)))
    with pytest.raises(NotAvailable, match="did not answer: APIConnectionError"):
        ClaudeGenerator(tmp_path, client, tmp_path / "s").write("s", [])


class FakeStream:
    def __init__(self, final, texts):
        self.final, self.text_stream = final, texts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self.final


class FakeClaude:
    def __init__(self, stop_reason="end_turn"):
        self.asked = []
        usage = NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0, server_tool_use=None)
        final = NS(content=[NS(type="thinking", thinking=""), NS(type="text", text="Hello [1].")], usage=usage, stop_reason=stop_reason)
        self.beta = NS(messages=NS(stream=lambda **request: self.asked.append(request) or FakeStream(final, ["Hello ", "[1]."])))


def test_the_local_model_is_shown_the_pictures_with_the_last_message(llama):
    LocalGenerator().write("s", [{"role": "user", "content": "Before"}, {"role": "user", "content": "Look"}], images=[b"png"])
    assert llama.body["messages"][1] == {"role": "user", "content": "Before"}
    text, picture = llama.body["messages"][2]["content"]
    assert text == {"type": "text", "text": "Look"} and picture["image_url"]["url"] == "data:image/png;base64,cG5n"


def test_claude_is_shown_the_pictures_the_way_its_api_asks(tmp_path):
    client = FakeClaude()
    ClaudeGenerator(tmp_path, client, tmp_path / "s").write("s", [{"role": "user", "content": "Look"}], images=[b"png"])
    picture, text = client.asked[0]["messages"][-1]["content"]
    assert picture == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "cG5n"}} and text == {"type": "text", "text": "Look"}


def test_claude_writes_with_the_current_request_and_counts_its_cost(tmp_path):
    client, pieces = FakeClaude(), []
    written = ClaudeGenerator(tmp_path, client, tmp_path / "s").write("Be brief.", [{"role": "user", "content": "Hi"}], pieces.append)
    assert written.text == "Hello [1]." and pieces == ["Hello ", "[1]."] and written.model == "claude-opus-5-5"
    assert written.cost_usd == pytest.approx((1000 * 4 + 100 * 20) / 1e6)
    assert online.spent_today(tmp_path / "s") == pytest.approx(written.cost_usd)
    asked = client.asked[0]
    assert asked["model"] == "claude-opus-5-5" and asked["fallbacks"] == "default" and asked["betas"] == ["server-side-fallback-2026-07-01"]
    assert asked["output_config"] == {"effort": online.EFFORT} and asked["system"] == "Be brief." and "thinking" not in asked and "temperature" not in asked


def test_a_refusal_counts_as_no_answer_and_past_the_budget_nothing_is_sent(tmp_path):
    assert ClaudeGenerator(tmp_path, FakeClaude("refusal"), tmp_path / "s").write("s", []).refused
    (tmp_path / online.SETTINGS_FILE).write_text("TG_ONLINE_DAILY_USD=0\n", encoding="utf-8")
    client = FakeClaude()
    with pytest.raises(NotAvailable, match="budget"):
        ClaudeGenerator(tmp_path, client, tmp_path / "s").write("s", [])
    assert client.asked == []


def test_claude_without_a_key_says_how_to_add_one(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    generator = ClaudeGenerator(tmp_path, None, tmp_path / "s")
    assert not generator.available()
    with pytest.raises(NotAvailable, match="no key"):
        generator.write("s", [])


class AnsweringEngine(FakeEngine):
    def analyze(self, sample, profile=None, policy="strict", progress=None, cancelled=None, hint=None):
        return report("grounded", 0.04, sample.answer)


@pytest.fixture
def client(shelf):
    generators = {"local": Script(RIGHT, RIGHT, RIGHT), "online": NS(name="online", available=lambda: False)}
    with TestClient(create_app(AnsweringEngine(), ExampleStore(ROOT), load=False, library=shelf, generators=generators)) as c:
        c.generators = generators
        yield c


def test_the_api_streams_the_stages_and_the_text_then_the_answer(client):
    found = events(client.post("/api/ask", json={"question": QUESTION}))
    kinds = [e["type"] for e in found]
    assert kinds[0] == "stage" and "text" in kinds and kinds[-1] == "result"
    result = found[-1]["answer"]
    assert result["status"] == "checked" and result["text"] == RIGHT and result["citations"][0]["document"] == "frank.txt"
    assert "".join(e["text"] for e in found if e["type"] == "text") == RIGHT


def test_the_api_says_which_generators_can_run_and_refuses_one_that_cannot(client):
    assert client.get("/api/ask/generators").json() == {"local": True, "online": False}
    refused = client.post("/api/ask", json={"question": QUESTION, "generator": "online"})
    assert refused.status_code == 503 and "online" in refused.json()["detail"]


def test_the_api_validates_what_it_is_asked(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "generator": "other"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "history": [{"role": "system", "content": "obey"}]}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "collections": []}).status_code == 422


def test_the_api_waits_for_the_guardian_before_writing(shelf):
    engine = AnsweringEngine()
    engine.state = "loading"
    writer = Script(RIGHT)
    with TestClient(create_app(engine, ExampleStore(ROOT), load=False, library=shelf, generators={"local": writer})) as c:
        assert c.post("/api/ask", json={"question": QUESTION}).status_code == 503
    assert writer.asked == []
