"""The free online answer (rag/free.py, D-191): a free model answers, the Guardian reads the pages it named and finds its
own on Wikipedia, the local engine checks the answer, and every source gets a label. The network is a stand-in here."""

import json

import pytest

from truth_guardian.rag import free
from truth_guardian.rag.generators import NotAvailable
from truth_guardian.report import ClaimReport, Evidence, Report
from truth_guardian.web.engine import NotChecked

PAGE = "Title: Eiffel Tower\n\nMarkdown Content:\n" + "The Eiffel Tower was completed in 1889 for the World's Fair in Paris. " * 4 + "\n\nIt is 330 metres tall today, with its antennas."


class Net:
    """Answers each address with what the test set; counts what was asked."""

    def __init__(self, reply="The Eiffel Tower was completed in 1889. It is 330 metres tall.\nSOURCES: https://example.org/eiffel https://dead.example/x", busy=None):
        self.reply, self.busy, self.calls = reply, busy, []

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.calls.append(url)
        if url.startswith("https://text.pollinations.ai") or "chat/completions" in url:
            if self.busy:
                waited, self.busy = self.busy, None
                return 402, json.dumps({"error": {"code": "FREE_LIMIT", "message": f"Free limit reached. Retry after {waited}s"}})
            return 200, json.dumps({"choices": [{"message": {"content": self.reply}}]})
        if url == free.READER + "https://example.org/eiffel":
            return 200, PAGE
        if url.startswith(free.READER):
            return 404, "Warning: Target URL returned error 404"
        if "list=search" in url:
            return 200, json.dumps({"query": {"search": [{"title": "Eiffel Tower"}]}})
        if "prop=extracts" in url:
            return 200, json.dumps({"query": {"pages": {"1": {"extract": "The Eiffel Tower is a wrought-iron lattice tower in Paris.\n\nIt was completed in 1889 and is 330 metres tall."}}}})
        return 404, ""


class Engine:
    def __init__(self, refuse=None):
        self.refuse, self.samples = refuse, []

    def analyze(self, sample, cancelled=None):
        self.samples.append(sample)
        if self.refuse:
            raise NotChecked(self.refuse, "language")
        supported = ClaimReport(start=0, end=10, text="completed in 1889", status="supported", risk=0.1, explanation="x", action="keep", evidence=Evidence(document_id="source1", text="completed in 1889"))
        wrong = ClaimReport(start=11, end=20, text="330 metres", status="contradicted", risk=0.8, explanation="x", action="verify", evidence=Evidence(document_id="source2", text="330"))
        return Report(id=sample.id, verdict="hallucinated", risk=0.7, response_threshold=0.4, sentence_threshold=0.3, claims=[supported, wrong])


class Route:
    answer = "fa"


@pytest.fixture(autouse=True)
def _fresh_wikipedia(monkeypatch):
    monkeypatch.setattr(free, "_wiki_kept", {})


def test_the_answer_is_checked_and_every_source_labelled(tmp_path):
    net, engine = Net(), Engine()
    a = free.answer_free("When was the Eiffel Tower completed?", engine, root=tmp_path, fetch=net, sleep=lambda s: None)
    assert a.status == "checked" and a.generator == "free-online:pollinations/openai-fast"
    assert "SOURCES" not in a.text and "1889" in a.text
    by = {c.place: c for c in a.citations}
    assert by["https://example.org/eiffel"].found_by == "model" and by["https://example.org/eiffel"].stance == "supports"
    assert by["https://dead.example/x"].stance == "missing" and by["https://dead.example/x"].text == ""
    wiki = [c for c in a.citations if c.found_by == "guardian"]
    assert wiki and wiki[0].place.startswith("https://en.wikipedia.org/wiki/") and wiki[0].stance == "contradicts"
    # The engine read only the sources that opened, in their order, and the note names the page that did not.
    assert len(engine.samples[0].documents) == 2 and any("could not be opened" in n for n in a.notes)


def test_a_wait_the_free_service_asks_for_is_waited_once(tmp_path):
    waited, events = [], []
    a = free.answer_free("When?", Engine(), events.append, root=tmp_path, fetch=Net(busy=12), sleep=waited.append)
    assert a.status == "checked" and len(waited) == 13
    assert any(e.get("stage") == "waiting" and e["seconds"] == 13 for e in events)


def test_a_long_wait_is_not_waited(tmp_path):
    with pytest.raises(NotAvailable, match="busy"):
        free.answer_free("When?", Engine(), root=tmp_path, fetch=Net(busy=300), sleep=lambda s: None)


def test_a_language_no_check_reads_gets_the_light_check(tmp_path, monkeypatch):
    monkeypatch.setattr(free, "light_check", lambda text, hits: [])
    engine = Engine(refuse=Route())
    a = free.answer_free("When?", engine, root=tmp_path, fetch=Net(), sleep=lambda s: None)
    assert a.status == "light" and a.report is None
    assert {c.stance for c in a.citations} == {"unjudged", "missing"}


def test_no_source_found_leaves_it_unchecked(tmp_path):
    net = Net(reply="It was finished in 1889.\nSOURCES: none")
    original = net.__call__
    net_calls = lambda url, data=None, headers=None, timeout=None: (200, json.dumps({"query": {"search": []}})) if "wikipedia" in url else original(url, data, headers, timeout)
    a = free.answer_free("When?", Engine(), root=tmp_path, fetch=net_calls, sleep=lambda s: None)
    assert a.status == "unchecked" and a.citations == [] and any("named no page" in n for n in a.notes)


def test_a_key_picks_its_service_and_its_model(tmp_path):
    (tmp_path / free.SETTINGS_FILE).write_text("GROQ_API_KEY=gsk_test\nOPENROUTER_API_KEY=sk-or-test\nOPENROUTER_MODEL=some/model:free\n", encoding="utf-8")
    values = free.settings(tmp_path)
    assert free.provider(values) == ("groq", "openai/gpt-oss-120b", "gsk_test")
    assert free.provider({**values, "TG_FREE_PROVIDER": "openrouter"}) == ("openrouter", "some/model:free", "sk-or-test")
    assert free.provider({}) == ("pollinations", "openai-fast", None)


def test_the_reply_is_split_from_its_sources():
    text, urls = free.split_reply("**Paris** is the capital. [1]\n\nSOURCES: https://a.org/x, https://b.org/y.\n")
    assert text == "Paris is the capital. [1]" and urls == ["https://a.org/x", "https://b.org/y"]
    assert free.split_reply("No sources here.\nSources: none") == ("No sources here.", [])


def test_a_search_hit_whose_title_has_nothing_to_do_with_the_question_is_not_read():
    words = set(free.terms("Who was the first woman to win the Fields Medal? Maryam Mirzakhani won it in 2014."))
    assert free.concerns("Fields Medal", words) and free.concerns("Maryam Mirzakhani", words)
    assert not free.concerns("Simone Biles", words) and not free.concerns("Shanghai Tower", set(free.terms("Eiffel Tower height")))


def test_a_page_that_does_not_answer_in_time_is_skipped_not_fatal(tmp_path):
    net = Net()

    def slow(url, data=None, headers=None, timeout=None):
        if url.startswith(free.READER):
            return 0, "TimeoutError: timed out"
        return net(url, data, headers, timeout)

    a = free.answer_free("When was the Eiffel Tower completed?", Engine(), root=tmp_path, fetch=slow, sleep=lambda s: None)
    assert a.status == "checked" and {c.stance for c in a.citations if c.found_by == "model"} == {"missing"}


def test_an_address_keeps_its_own_brackets_and_a_title_is_judged_without_its_aside():
    _, urls = free.split_reply("Mars has two moons.\nSOURCES: https://en.wikipedia.org/wiki/Phobos_(moon) (see https://a.org/x).")
    assert urls == ["https://en.wikipedia.org/wiki/Phobos_(moon)", "https://a.org/x"]
    assert free.concerns("Hafez (poet)", set(free.terms("Where was Hafez born?")))


def test_a_busy_or_failing_service_hands_the_question_to_the_next(tmp_path):
    (tmp_path / free.SETTINGS_FILE).write_text("GROQ_API_KEY=gsk_test\nOPENROUTER_API_KEY=sk-or-test\n", encoding="utf-8")
    net = Net()
    order = []

    def chain(url, data=None, headers=None, timeout=None):
        if "chat/completions" in url or "pollinations" in url:
            order.append(url.split("/")[2])
            if "groq" in url:
                return 429, "rate limited"
            if "openrouter" in url:
                return 500, "upstream error"
        return net(url, data, headers, timeout)

    a = free.answer_free("When was the Eiffel Tower completed?", Engine(), root=tmp_path, fetch=chain, sleep=lambda s: None)
    assert order == ["api.groq.com", "openrouter.ai", "text.pollinations.ai"]
    assert a.status == "checked" and a.generator == "free-online:pollinations/openai-fast"


def test_wikipedia_is_asked_again_once_after_too_many_and_kept_after(monkeypatch):
    monkeypatch.setattr(free, "_wiki_kept", {})
    answers = iter([(429, "too many"), (200, "first"), (200, "never asked")])
    calls, paused = [], []

    def fetch(url, data=None, headers=None, timeout=None):
        calls.append(url)
        return next(answers)

    assert free._wiki_get("https://en.wikipedia.org/w/api.php?x=1", fetch, paused.append) == (200, "first")
    assert free._wiki_get("https://en.wikipedia.org/w/api.php?x=1", fetch, paused.append) == (200, "first")
    assert len(calls) == 2 and paused == [free.WIKI_PAUSE]


def test_markup_is_cleaned_to_prose():
    page = "World Population Review[](https://worldpopulationreview.com/x) says ![logo](a.png) [Thimphu](https://t.org) has [12](n) 114,551 people.[3]\n| a | b |"
    assert free.clean(page) == "World Population Review says  Thimphu has  114,551 people."
