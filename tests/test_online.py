from types import SimpleNamespace as NS

from truth_guardian import online
from truth_guardian.pipeline import make_sample
from truth_guardian.report import ClaimReport, LanguageReport, Report
from truth_guardian.web.engine import Engine


def claim(text, status, risk, start=0):
    return ClaimReport(start=start, end=start + len(text), text=text, status=status, risk=risk, explanation="x", action="verify")


def report(verdict="uncertain", claims=None, measured=True):
    claims = claims or [claim("Anne Frank died in 1944.", "unsupported", 0.55)]
    return Report(id="r", verdict=verdict, risk=0.5, response_threshold=0.45, sentence_threshold=0.3, claims=claims,
                  language=LanguageReport(check="english", answer="en", measured=measured))


class FakeClient:
    """Stands in for anthropic.Anthropic: answers with the scripted responses, and records what was asked."""

    def __init__(self, *responses):
        self.responses, self.asked = list(responses), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **request):
        self.asked.append(request)
        reply = self.responses.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def usage(searches=1):
    return NS(input_tokens=3000, output_tokens=500, cache_creation_input_tokens=0, cache_read_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches))


def verdict_reply(**item):
    found = {"index": 1, "in_sources": "contradicted", "on_web": "false", "explanation": "She died in 1945.",
             "correction": "Anne Frank died in 1945.", "urls": ["https://example.org/frank"], **item}
    pages = NS(type="web_search_tool_result", content=[NS(url="https://example.org/frank", title="Anne Frank")])
    return NS(content=[pages, NS(type="tool_use", name="report_verdict", input={"claims": [found]})], stop_reason="tool_use", usage=usage())


def test_only_doubtful_claims_are_asked_about():
    sure = report("hallucinated", [claim("A.", "contradicted", 0.9), claim("B.", "supported", 0.1, 3)])
    assert online.doubtful(sure) == []
    assert online.doubtful(report("hallucinated", [claim("A.", "insufficient_evidence", 0.6)])) == [0]
    assert online.doubtful(report("grounded", [claim("A.", "unsupported", 0.4)], measured=False)) == [0]
    many = report("uncertain", [claim(f"{i}.", "unsupported", 0.5, i * 3) for i in range(6)])
    assert len(online.doubtful(many)) == online.MAX_CLAIMS


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert online.configured(tmp_path) is False
    assert online.check("When?", ["She died in 1945."], report(), root=tmp_path, store=tmp_path / "s") is None


def test_claude_reports_each_claim_beside_the_local_verdict_with_its_pages_and_cost(tmp_path):
    client = FakeClient(verdict_reply())
    found = online.check("When did Anne Frank die?", ["She died in February 1945."], report(), client=client, root=tmp_path, store=tmp_path / "s")
    assert found.status == "checked" and found.model == online.MODEL
    (c,) = found.claims
    assert (c.in_sources, c.on_web, c.correction) == ("contradicted", "false", "Anne Frank died in 1945.")
    assert c.sources[0].title == "Anne Frank" and c.text == "Anne Frank died in 1944."
    assert found.cost_usd == round((3000 * 4 + 500 * 20) / 1e6 + 0.01, 4)
    asked = client.asked[0]
    assert asked["model"] == "claude-opus-5-5" and asked["fallbacks"] == "default" and "thinking" not in asked
    assert "1. Anne Frank died in 1944." in asked["messages"][0]["content"] and "February 1945" in asked["messages"][0]["content"]
    assert online.spent_today(tmp_path / "s") == found.cost_usd


def test_the_same_claims_over_the_same_sources_are_never_paid_for_twice(tmp_path):
    client = FakeClient(verdict_reply())
    args = ("When?", ["She died in February 1945."], report())
    online.check(*args, client=client, root=tmp_path, store=tmp_path / "s")
    again = online.check(*args, client=client, root=tmp_path, store=tmp_path / "s")
    assert again.cached and again.cost_usd == 0.0 and len(client.asked) == 1


def test_past_the_daily_budget_nothing_is_sent(tmp_path):
    (tmp_path / "anthropic.local.env").write_text("TG_ONLINE_DAILY_USD=0\n", encoding="utf-8")
    client = FakeClient(verdict_reply())
    found = online.check("When?", ["x"], report(), client=client, root=tmp_path, store=tmp_path / "s")
    assert found.status == "budget" and client.asked == []


def test_a_paused_search_is_resumed_and_a_failure_never_breaks_the_check(tmp_path):
    paused = NS(content=[NS(type="server_tool_use", name="web_search")], stop_reason="pause_turn", usage=usage(0))
    client = FakeClient(paused, verdict_reply())
    assert online.check("When?", ["x"], report(), client=client, root=tmp_path, store=tmp_path / "a").status == "checked"
    assert len(client.asked) == 2 and client.asked[1]["messages"][-1]["role"] == "assistant"
    broken = online.check("When?", ["y"], report(), client=FakeClient(RuntimeError("network down")), root=tmp_path, store=tmp_path / "b")
    assert broken.status == "error" and "network down" in broken.message


def test_turns_already_paid_for_count_against_the_budget_when_a_later_one_fails(tmp_path):
    paused = NS(content=[NS(type="server_tool_use", name="web_search")], stop_reason="pause_turn", usage=usage(0))
    found = online.check("When?", ["x"], report(), client=FakeClient(paused, RuntimeError("down")), root=tmp_path, store=tmp_path / "s")
    assert found.status == "error" and "down" in found.message
    assert found.cost_usd > 0 and online.spent_today(tmp_path / "s") == found.cost_usd


def test_a_damaged_cache_line_costs_one_question_not_the_check(tmp_path):
    store = tmp_path / "s"
    store.mkdir()
    (store / "cache.jsonl").write_text('not json\n[1]\n{"key": "other"\n', encoding="utf-8")
    assert online.check("When?", ["x"], report(), client=FakeClient(verdict_reply()), root=tmp_path, store=store).status == "checked"


def test_a_failing_online_check_keeps_the_local_report(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("read-only folder")

    monkeypatch.setattr(online, "configured", lambda root: True)
    monkeypatch.setattr(online, "check", broken)
    local = report()
    result = Engine().consult(make_sample("Anne Frank died in 1944.", ["She died in 1945."]), local)
    assert result.verdict == local.verdict and result.online.status == "error" and "read-only" in result.online.message
