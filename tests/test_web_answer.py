"""Answers from the web when the documents hold none (rag/web.py, D-182), with a stand-in for Anthropic's client: nothing
is sent and nothing is paid for. The answer is checked by the Guardian against the passages the API marks as cited."""

import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from test_web_api import FakeEngine
from truth_guardian import online
from truth_guardian.rag import web
from truth_guardian.rag.generators import NotAvailable
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import NotChecked
from truth_guardian.web.examples import ExampleStore

QUESTION = "When did Anne Frank die?"


class FakeClient:
    """Stands in for anthropic.Anthropic: answers with the scripted responses, and records what was asked."""

    def __init__(self, *responses):
        self.responses, self.asked = list(responses), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **request):
        self.asked.append(json.loads(json.dumps(request, default=lambda o: getattr(o, "__dict__", str(o)))))
        reply = self.responses.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def usage(searches=1):
    return NS(input_tokens=2000, output_tokens=300, cache_creation_input_tokens=0, cache_read_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches))


def cite(text, url="https://example.org/frank", title="Anne Frank"):
    return NS(type="web_search_result_location", url=url, title=title, cited_text=text, encrypted_index="x")


def answered(year="1945", cited=True, stop="end_turn"):
    pages = NS(type="web_search_tool_result", content=[NS(url="https://example.org/frank", title="Anne Frank")])
    text = NS(type="text", text=f"Anne Frank died in February {year} in Bergen-Belsen.",
              citations=[cite("Anne Frank died in February 1945 at Bergen-Belsen.")] if cited else None)
    return NS(content=[NS(type="server_tool_use", name="web_search"), pages, text], stop_reason=stop, usage=usage())


def ask(tmp_path, client, engine=None):
    return web.answer_from_web(QUESTION, engine or FakeEngine(), client=client, root=tmp_path, store=tmp_path / "s")


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert web.available(tmp_path) is False
    with pytest.raises(NotAvailable):
        web.answer_from_web(QUESTION, FakeEngine(), root=tmp_path, store=tmp_path / "s")


def test_the_web_answer_is_checked_by_the_guardian_against_the_passages_it_cites(tmp_path):
    engine = FakeEngine()
    client = FakeClient(answered())
    found = ask(tmp_path, client, engine)
    assert found.status == "checked" and found.generator == web.GENERATOR
    assert found.text == "Anne Frank died in February 1945 in Bergen-Belsen. [1]"
    (c,) = found.citations
    assert (c.n, c.document, c.place, c.collection) == (1, "Anne Frank", "https://example.org/frank", "web")
    (sample, _, _) = engine.calls[0]
    # The Guardian reads the page's own words (the citation's cited_text), not anything the model wrote about them.
    assert [d.text for d in sample.documents] == ["Anne Frank died in February 1945 at Bergen-Belsen."]
    assert sample.documents[0].origin == "Anne Frank"
    assert found.report.verdict == "grounded" and web.NOTE in found.notes
    asked = client.asked[0]
    assert asked["model"] == "claude-opus-5-5" and asked["tools"][0]["type"] == "web_search_20260209"
    assert asked["messages"] == [{"role": "user", "content": QUESTION}] and "tool_choice" not in asked
    assert found.cost_usd == round((2000 * 4 + 300 * 20) / 1e6 + 0.01, 4) == online.spent_today(tmp_path / "s")


def test_a_wrong_web_answer_is_flagged(tmp_path):
    found = ask(tmp_path, FakeClient(answered(year="2022")))
    assert found.status == "checked" and found.report.verdict == "hallucinated"


def test_a_paused_search_is_sent_back_as_it_is_to_resume(tmp_path):
    paused = NS(content=[NS(type="server_tool_use", name="web_search")], stop_reason="pause_turn", usage=usage())
    client = FakeClient(paused, answered())
    found = ask(tmp_path, client)
    assert found.status == "checked" and len(client.asked) == 2
    second = client.asked[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant"]  # no "continue" message is added


def test_an_answer_that_cites_nothing_is_shown_unchecked(tmp_path):
    found = ask(tmp_path, FakeClient(answered(cited=False)))
    assert found.status == "unchecked" and found.report is None and any("cited no page" in n for n in found.notes)


def test_a_refusal_or_a_failure_shows_no_answer_but_counts_its_cost(tmp_path):
    refused = NS(content=[], stop_reason="refusal", usage=usage(0))
    found = ask(tmp_path, FakeClient(refused))
    assert found.status == "unchecked" and found.text == "" and "refused" in found.notes[0]
    assert online.spent_today(tmp_path / "s") > 0
    broken = ask(tmp_path / "b", FakeClient(RuntimeError("down")))
    assert broken.status == "unchecked" and "RuntimeError" in broken.notes[0]


def test_a_language_the_guardian_does_not_check_is_shown_unchecked(tmp_path):
    class Persian(FakeEngine):
        def analyze(self, *a, **k):
            raise NotChecked(NS(answer="fa"), "language")

    found = ask(tmp_path, FakeClient(answered()), Persian())
    assert found.status == "unchecked" and found.citations and any("language" in n for n in found.notes)


def test_the_same_question_is_never_paid_for_twice(tmp_path):
    client = FakeClient(answered())
    ask(tmp_path, client)
    again = ask(tmp_path, client)
    assert len(client.asked) == 1 and again.cost_usd == 0.0 and again.status == "checked"


def test_past_the_daily_budget_nothing_is_sent(tmp_path):
    (tmp_path / "anthropic.local.env").write_text("TG_ONLINE_DAILY_USD=0\n", encoding="utf-8")
    client = FakeClient(answered())
    with pytest.raises(NotAvailable, match="budget"):
        ask(tmp_path, client)
    assert client.asked == []


def test_the_server_says_the_online_answer_is_off_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(create_app(FakeEngine(), ExampleStore(web.online.ROOT), root=tmp_path, load=False)) as c:
        refused = c.post("/api/ask/web", json={"question": QUESTION})
        assert refused.status_code == 503 and "key" in refused.json()["detail"]
