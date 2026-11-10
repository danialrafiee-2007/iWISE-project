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
    monkeypatch.setattr(free, "_countries", {})


def test_the_answer_is_checked_and_every_source_labelled(tmp_path):
    net, engine = Net(), Engine()
    a = free.answer_free("When was the Eiffel Tower completed?", engine, root=tmp_path, fetch=net, sleep=lambda s: None)
    assert a.status == "checked" and a.generator == "free-online:pollinations/openai-fast"
    assert "SOURCES" not in a.text and "1889" in a.text
    by = {c.place: c for c in a.citations}
    assert by["https://example.org/eiffel"].found_by == "model" and by["https://example.org/eiffel"].stance == "supports"
    assert by["https://dead.example/x"].stance == "not_found" and by["https://dead.example/x"].text == ""
    wiki = [c for c in a.citations if c.found_by == "guardian"]
    assert wiki and wiki[0].place.startswith("https://en.wikipedia.org/wiki/") and wiki[0].stance == "contradicts"
    # The engine read only the sources that opened, in their order, and the note names the page that did not.
    assert len(engine.samples[0].documents) == 2 and any("do not exist" in n for n in a.notes)


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
    assert {c.stance for c in a.citations} == {"unjudged", "not_found"}


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
        if url.startswith(free.READER) or url.startswith(("https://example.org", "https://dead.example")):
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


def test_the_web_search_keeps_passages_that_concern_the_answer():
    seen = {}

    def fetch(url, data=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers, data=data)
        return 200, json.dumps({"results": [
            {"title": "Karun River | Britannica", "url": "https://www.britannica.com/place/Karun-River", "content": "The Karun River, Iran's longest river, is about 950 km long and joins the Shatt al-Arab.", "score": 0.9},
            {"title": "Cooking", "url": "https://food.example/x", "content": "A recipe for rice with saffron.", "score": 0.9},
        ]})

    words = set(free.terms("How long is the Karun River? It is 950 km long."))
    found = free.tavily("How long is the Karun River?", words, None, fetch)
    assert [url for _, url, _ in found] == ["https://www.britannica.com/place/Karun-River"]
    assert seen["headers"] == {"X-Tavily-Access-Mode": "keyless"}
    free.tavily("q", words, "tvly-test", fetch)
    assert seen["headers"] == {"Authorization": "Bearer tvly-test"}
    assert free.tavily("q", words, None, lambda *a, **k: (429, "daily cap")) == []


def test_wikidata_facts_become_plain_sentences():
    entity = {"id": "Q243", "labels": {"en": {"value": "Eiffel Tower"}}, "claims": {
        "P2048": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"type": "quantity", "value": {"amount": "+330", "unit": "http://www.wikidata.org/entity/Q11573"}}}}],
        "P1619": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"type": "time", "value": {"time": "+1889-05-15T00:00:00Z", "precision": 11}}}}],
        "P17": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q142"}}}}],
        "P1082": [
            {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"type": "quantity", "value": {"amount": "+1", "unit": "1"}}}},
            {"rank": "preferred", "mainsnak": {"snaktype": "value", "datavalue": {"type": "quantity", "value": {"amount": "+2", "unit": "1"}}}, "qualifiers": {"P585": [{"datavalue": {"value": {"time": "+2016-00-00T00:00:00Z", "precision": 9}}}]}},
        ],
    }}

    def fetch(url, data=None, headers=None, timeout=None):
        if "ids=Q142" in url:
            return 200, json.dumps({"entities": {"Q142": {"labels": {"en": {"value": "France"}}}}})
        return 200, json.dumps({"entities": {"Q243": entity}})

    [(name, url, text)] = free.wikidata([("en", "Eiffel Tower")], fetch)
    assert name == "Eiffel Tower" and url == "https://www.wikidata.org/wiki/Q243"
    assert text == ("The population of Eiffel Tower is 2 (in 2016). The height of Eiffel Tower is 330 metres. "
                    "The date of official opening of Eiffel Tower is 15 May 1889. The country of Eiffel Tower is France.")


def test_one_wikidata_entity_is_given_once():
    entity = {"id": "Q622796", "labels": {"en": {"value": "Milad Tower"}}, "claims": {"P2048": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"type": "quantity", "value": {"amount": "+435", "unit": "http://www.wikidata.org/entity/Q11573"}}}}]}}
    fetch = lambda url, data=None, headers=None, timeout=None: (200, json.dumps({"entities": {"Q622796": entity}}))
    assert len(free.wikidata([("fa", "برج میلاد"), ("en", "Milad Tower")], fetch)) == 1


def test_a_page_is_told_apart_as_made_up_or_closed_to_programs():
    gone = lambda url, data=None, headers=None, timeout=None: (0, "URLError: <urlopen error [Errno 11001] getaddrinfo failed>")
    shut = lambda url, data=None, headers=None, timeout=None: (403, "Forbidden")
    assert free.probe("https://no-such-site.example/x", gone) == "not_found"
    assert free.probe("https://www.britannica.com/x", shut) == "blocked"
    assert free.read_page("https://www.britannica.com/x", set(), shut) == ("", "blocked")


def test_a_source_left_unrelated_is_judged_again_on_its_own():
    class Alone:
        def __init__(self):
            self.calls = 0

        def analyze(self, sample, cancelled=None):
            self.calls += 1
            claim = ClaimReport(start=0, end=4, text="1889", status="supported", risk=0.1, explanation="x", action="keep", evidence=Evidence(document_id="source1", text="1889"))
            return Report(id=sample.id, verdict="grounded", risk=0.1, response_threshold=0.4, sentence_threshold=0.3, claims=[claim])

    engine = Alone()
    labels = free.judge_each("It opened in 1889.", "When?", ["a", "b", "c"], ["supports", "unrelated", "contradicts"], engine)
    assert labels == ["supports", "supports", "contradicts"] and engine.calls == 1


def test_a_source_alone_never_turns_into_a_contradiction():
    class Strict:
        def analyze(self, sample, cancelled=None):
            claim = ClaimReport(start=0, end=4, text="1937", status="contradicted", risk=0.9, explanation="x", action="verify", evidence=Evidence(document_id="source1", text="1936"))
            return Report(id=sample.id, verdict="hallucinated", risk=0.9, response_threshold=0.4, sentence_threshold=0.3, claims=[claim])

    assert free.judge_each("Published in 1937.", "When?", ["born 1903, died 1951"], ["unrelated"], Strict()) == ["unrelated"]


def test_a_source_in_a_language_the_check_does_not_read_is_left_out_of_it(tmp_path, monkeypatch):
    persian = "برج ایفل در سال ۱۸۸۹ ساخته شد و ارتفاع آن ۳۳۰ متر است. این برج در پاریس قرار دارد و نماد فرانسه است."
    monkeypatch.setattr(free, "tavily", lambda question, words, *rest, **more: [("Persian page", "https://fa.example/eiffel", persian)])
    engine = Engine()
    a = free.answer_free("When was the Eiffel Tower completed?", engine, root=tmp_path, fetch=Net(), sleep=lambda s: None)
    assert a.status == "checked"
    assert all(persian not in d.text for d in engine.samples[0].documents)
    assert {c.stance for c in a.citations if c.place == "https://fa.example/eiffel"} == {"unjudged"}


def test_an_address_with_persian_letters_is_sent_encoded():
    url = "https://fa.wikipedia.org/wiki/برج_میلاد"
    sent = free.ascii_url(url)
    assert sent.isascii() and sent.startswith("https://fa.wikipedia.org/wiki/%D8%A8") and free.ascii_url(sent) == sent
    assert free.ascii_url("https://r.jina.ai/https://fa.wikipedia.org/wiki/حافظ").isascii()


def test_a_persian_question_also_searches_the_reliable_persian_sites(tmp_path, monkeypatch):
    calls = []

    def fake(question, words, key=None, fetch=None, sites=(), results=free.TAVILY_RESULTS, shared=2):
        calls.append(sites)
        return [("حافظ", "https://rch.ac.ir/article/Details?id=9348", "حافظ در حدود سال ۷۲۷ هجری در شیراز به دنیا آمد.")] if sites else []

    monkeypatch.setattr(free, "tavily", fake)
    monkeypatch.setattr(free, "light_check", lambda text, hits: [])
    persian = Net(reply="حافظ در شیراز به دنیا آمد.\nSOURCES: none")
    a = free.answer_free("حافظ در کدام شهر به دنیا آمد؟", Engine(refuse=Route()), root=tmp_path, fetch=persian, sleep=lambda s: None)
    assert calls.count(free.FA_SITES) == 1 and () in calls
    assert any(c.place == "https://rch.ac.ir/article/Details?id=9348" for c in a.citations)
    calls.clear()
    free.answer_free("When was the Eiffel Tower completed?", Engine(), root=tmp_path, fetch=Net(), sleep=lambda s: None)
    assert calls == [()]  # an English question: the general web search only


def test_a_web_hit_tavily_scores_low_is_left_out():
    hits = {"results": [{"title": "Prices", "url": "https://x.example/p", "content": "Karun River 950 km long prices today", "score": 0.12}]}
    words = set(free.terms("Karun River 950 km long"))
    assert free.tavily("Karun", words, None, lambda *a, **k: (200, json.dumps(hits))) == []


def _bank(url, data=None, headers=None, timeout=None):
    if "/country?format=json" in url:
        return 200, json.dumps([{}, [{"id": "IRN", "name": "Iran, Islamic Rep.", "region": {"value": "Middle East"}}, {"id": "WLD", "name": "World", "region": {"value": "Aggregates"}}]])
    if "/country/IRN/indicator/SP.POP.TOTL" in url:
        return 200, json.dumps([{}, [{"country": {"id": "IR", "value": "Iran, Islamic Rep."}, "date": "2025", "value": 92417681}]])
    return 404, ""


def test_a_country_figure_comes_from_the_world_bank_only_when_asked_of_a_country():
    [(title, url, sentence)] = free.world_bank("What is the population of Iran?", _bank)
    assert sentence == "According to the World Bank, the population of Iran was 92,417,681 people in 2025." and "SP.POP.TOTL" in url
    assert free.world_bank("جمعیت ایران چقدر است؟", _bank)[0][2] == sentence
    assert free.world_bank("What is the population of Bam, Iran?", _bank) == []  # a place inside the country
    assert free.world_bank("جمعیت شهر بم چقدر است؟", _bank) == []
    assert free.world_bank("When was Iran's oldest bridge built?", _bank) == []  # no figure asked about


def test_a_research_question_gets_scholarly_works():
    works = {"results": [
        {"id": "https://openalex.org/W1", "title": "Growth of the number of simple closed geodesics on hyperbolic surfaces", "publication_year": 2008,
         "authorships": [{"author": {"display_name": "Maryam Mirzakhani"}}], "primary_location": {"source": {"display_name": "Annals of Mathematics"}},
         "doi": "https://doi.org/10.4007/annals.2008.168.97"},
        {"id": "https://openalex.org/W2", "title": "Cooking with saffron", "publication_year": 2001, "authorships": [], "doi": None},
    ]}
    fetch = lambda url, data=None, headers=None, timeout=None: (200, json.dumps(works))
    q = "Which paper did Mirzakhani publish on simple closed geodesics on hyperbolic surfaces?"
    [(title, url, sentence)] = free.scholarly(q, set(free.terms(q)), fetch)
    assert url == "https://doi.org/10.4007/annals.2008.168.97"
    assert sentence == ('The work "Growth of the number of simple closed geodesics on hyperbolic surfaces" by Maryam Mirzakhani was published '
                        "in 2008 in Annals of Mathematics (DOI 10.4007/annals.2008.168.97).")
    assert free.scholarly("When was the Eiffel Tower built?", set(), fetch) == []  # not a question about research


def test_a_source_alone_contradicts_only_a_claim_the_whole_check_found_wrong():
    wrong = ClaimReport(start=0, end=10, text="Iran's population is 86 million", status="contradicted", risk=0.9, explanation="x", action="verify", evidence=Evidence(document_id="source1", text="the population of Iran was 92,417,681"))

    class Bank:
        def analyze(self, sample, cancelled=None):
            return Report(id=sample.id, verdict="hallucinated", risk=0.9, response_threshold=0.4, sentence_threshold=0.3, claims=[wrong])

    main = Report(id="m", verdict="hallucinated", risk=0.9, response_threshold=0.4, sentence_threshold=0.3, claims=[wrong])
    right = Report(id="m", verdict="grounded", risk=0.1, response_threshold=0.4, sentence_threshold=0.3, claims=[wrong.model_copy(update={"status": "supported"})])
    assert free.judge_each("Iran has 86 million people.", "?", ["World Bank: 92,417,681"], ["unrelated"], Bank(), report=main) == ["contradicts"]
    assert free.judge_each("Iran has 86 million people.", "?", ["World Bank: 92,417,681"], ["unrelated"], Bank(), report=right) == ["unrelated"]


def test_a_source_on_something_else_does_not_count_against_a_claim():
    claim = ClaimReport(start=0, end=10, text="Iran's population is 86 million", status="contradicted", risk=0.9, explanation="x", action="verify", evidence=Evidence(document_id="source1", text="the life expectancy at birth of Iran was 77.9 years"))
    assert not free._about_same(claim)
    assert free._about_same(claim.model_copy(update={"evidence": Evidence(document_id="source1", text="the population of Iran was 92,417,681")}))


def test_a_capital_or_another_place_of_the_same_name_is_kept_apart():
    assert free.world_bank("What is the capital of Bhutan and how many people live there?", _bank) == []
    words = set(free.terms("When was the Eiffel Tower in Paris completed?"))
    assert not free.concerns("Eiffel Tower (Paris, Texas)", words) and free.concerns("Eiffel Tower", words)
    assert free.concerns("Hafez (poet)", set(free.terms("Where was Hafez born?")))


def test_the_online_lamp_asks_only_what_costs_nothing_and_keeps_its_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(free, "_status", {})
    (tmp_path / free.SETTINGS_FILE).write_text("GROQ_API_KEY=gsk_test\nTAVILY_API_KEY=tvly-test\n", encoding="utf-8")
    asked = []

    def fetch(url, data=None, headers=None, timeout=None):
        asked.append(url)
        return (200, "{}") if "groq" in url or "wikipedia" in url else (503, "")

    clock = iter([0.0, 0.0, 10.0, 10.0])
    status = free.online_status(tmp_path, fetch, lambda: next(clock))
    assert status == {"state": "online", "answer": ["groq"], "search": ["wikipedia", "tavily"], "keys": ["GROQ_API_KEY", "TAVILY_API_KEY"]}
    assert not any("tavily" in url or "openrouter" in url for url in asked)  # no search spent; no key, no request
    free.online_status(tmp_path, fetch, lambda: next(clock))
    assert len(asked) == 3  # kept for a minute: nothing asked again
