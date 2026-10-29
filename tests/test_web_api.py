import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from truth_guardian import models
from truth_guardian.heal import Change, Healing
from truth_guardian.report import ClaimReport, Report
from truth_guardian.web.app import _changed_range, create_app, prepare
from truth_guardian.web.engine import ROOT, Cancelled, Engine
from truth_guardian.web.examples import ExampleStore


class FakeEngine:
    state, version, error = "ready", "fake-1", None

    def __init__(self):
        self.calls = []

    def load(self):
        pass

    def busy(self):
        return False

    def info(self):
        return {"state": self.state, "model_version": self.version}

    route = Engine.route  # the real language routing, with the multilingual check counted as installed
    multilingual = object()

    def consult(self, sample, report, progress=None):
        return report

    def analyze(self, sample, profile=None, policy="strict", progress=None, cancelled=None, hint=None):
        self.calls.append((sample, profile, policy))
        for stage in ("lexical", "score", "verdict"):
            (progress or (lambda s: None))(stage)
        risky = "2022" in sample.answer
        claim = ClaimReport(start=0, end=len(sample.answer), text=sample.answer, status="contradicted" if risky else "supported", risk=0.9 if risky else 0.1, explanation="x", action="verify" if risky else "keep")
        return Report(id=sample.id, verdict="hallucinated" if risky else "grounded", risk=claim.risk, response_threshold=0.4, sentence_threshold=0.3, claims=[claim])

    def heal(self, sample, profile=None, on_check=None, cancelled=None):
        first = self.analyze(sample)
        on_check and on_check(0)
        fixed = sample.answer.replace("2022", "1945")
        on_check and on_check(1)
        return Healing(fixed, [first, self.analyze(sample.model_copy(update={"answer": fixed}))], [[Change(12, 16, "2022", "1945", "replaced with the value in the sources")]])

    def edit(self, sample, kind, seed, pool_from):
        if kind == "number":
            return None
        raise KeyError(f"unknown edit kind {kind!r}")


@pytest.fixture
def client():
    engine = FakeEngine()
    with TestClient(create_app(engine, ExampleStore(ROOT), load=False)) as c:
        c.engine = engine
        yield c


def events(response) -> list[dict]:
    return [json.loads(line) for line in response.iter_lines() if line]


def test_health_and_examples(client):
    assert client.get("/api/health").json()["state"] == "ready"
    listing = client.get("/api/examples").json()
    assert {"anne-frank", "semi-final", "library"} <= {e["id"] for e in listing["answers"]}
    assert listing["agents"][0]["id"] == "agent-liberation"


def test_analyze_streams_stages_then_the_report(client):
    body = {"question": "When?", "sources": ["She died in 1945."], "answer": "She died in 2022.", "task": "qa"}
    found = events(client.post("/api/analyze", json=body))
    assert [e["type"] for e in found] == ["stage", "stage", "stage", "result"]
    assert found[-1]["report"]["verdict"] == "hallucinated"
    sample = client.engine.calls[-1][0]
    assert sample.meta.task == "qa" and sample.documents[0].text == "She died in 1945."


def test_an_answer_no_check_reads_is_refused_before_the_stream_with_a_code_the_page_translates(client):
    persian = {"sources": ["این موزه در سال ۱۳۲۹ باز شد و قدیمی‌ترین ساختمان شهر است."], "answer": "این موزه در سال ۱۳۳۰ باز شد و قدیمی‌ترین ساختمان شهر است."}
    refused = client.post("/api/analyze", json=persian)
    assert refused.status_code == 422 and refused.json()["detail"] == {"code": "language", "language": "fa", "sources": ["fa"]}
    assert client.post("/api/heal", json=persian).status_code == 422
    spanish = {"sources": ["El museo se abrió en 1950 y es el edificio más antiguo de la ciudad."], "answer": "El museo se abrió en 2022 y es el más antiguo de la ciudad."}
    assert events(client.post("/api/analyze", json=spanish))[-1]["type"] == "result"
    assert client.post("/api/analyze", json={"sources": ["1950"], "answer": "1950", "language": "fa"}).json()["detail"]["code"] == "language"


def test_inputs_are_validated(client):
    assert client.post("/api/analyze", json={"sources": ["x"], "answer": " "}).status_code == 422
    assert client.post("/api/analyze", json={"sources": [], "answer": "An answer."}).status_code == 422
    assert client.post("/api/analyze", json={"sources": ["x"], "answer": "a" * 5_001}).status_code == 422
    assert client.post("/api/analyze", json={"sources": ["x"], "answer": "y", "extra": 1}).status_code == 422
    assert client.post("/api/analyze", json={"example_id": "nope"}).status_code == 404


def test_only_localhost_host_names_are_served(client):
    assert client.get("/api/health", headers={"host": "evil.example.com"}).status_code == 400


def test_a_hosted_demo_accepts_its_host_and_asks_for_the_access_code(monkeypatch):
    monkeypatch.setenv("TG_ALLOWED_HOSTS", "*.hf.space")
    monkeypatch.setenv("TG_ACCESS_CODE", "judge-2027")
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False)) as c:
        host = {"host": "team-truth-guardian.hf.space"}
        assert c.get("/api/health", headers=host).status_code == 200
        refused = c.get("/api/examples", headers=host)
        assert refused.status_code == 401 and refused.headers["www-authenticate"].startswith("Basic")
        assert c.get("/api/examples", headers=host, auth=("judge", "wrong")).status_code == 401
        assert c.get("/api/examples", headers=host, auth=("judge", "judge-2027")).status_code == 200
        assert c.get("/api/health", headers={"host": "evil.example.com"}).status_code == 400


def test_heal_returns_every_round_with_its_changes(client):
    found = events(client.post("/api/heal", json={"sources": ["She died in 1945."], "answer": "She died in 2022."}))
    result = found[-1]
    assert [e["round"] for e in found if e["type"] == "check"] == [0, 1]
    assert result["answer"] == "She died in 1945."
    assert [r["report"]["verdict"] for r in result["rounds"]] == ["hallucinated", "grounded"]
    assert result["rounds"][1]["changes"][0]["new"] == "1945"
    assert [r["answer"] for r in result["rounds"]] == ["She died in 2022.", "She died in 1945."]


def test_agent_needs_steps_and_an_answer(client):
    assert client.post("/api/agent", json={"steps": []}).status_code == 422
    steps = [{"step": 1, "kind": "action", "content": "search", "observation": "It opened in 1932."}, {"step": 2, "kind": "answer", "content": "It opened in 2022."}]
    found = events(client.post("/api/agent", json={"question": "When?", "steps": steps, "policy": "lenient"}))
    assert found[-1]["type"] == "result" and client.engine.calls[-1][2] == "lenient"
    assert client.engine.calls[-1][0].documents[0].text == "It opened in 1932."


def test_audit_parses_plain_logs_and_reports_line_errors(client):
    log = "\n".join(json.dumps({"id": i, "question": "q", "sources": ["She died in 1945."], "answer": a}) for i, a in enumerate(["She died in 2022.", "She died in 1945."]))
    found = events(client.post("/api/audit", json={"jsonl": log}))
    result = found[-1]
    assert [e["done"] for e in found if e["type"] == "progress"] == [0, 1]
    assert result["summary"]["answers"] == 2 and [a["verdict"] for a in result["answers"]] == ["hallucinated", "grounded"]
    bad = client.post("/api/audit", json={"jsonl": log + "\n{not json"})
    assert bad.status_code == 422 and "line 3" in bad.json()["detail"]


def test_fool_edit_errors_are_explained(client):
    answers = client.get("/api/fool/answers").json()
    if not answers:
        pytest.skip("the Fool-the-Guardian controls are not built")
    first = answers[0]["id"]
    assert "does not apply" in client.post("/api/fool/edit", json={"answer_id": first, "kind": "number"}).json()["detail"]
    assert client.post("/api/fool/edit", json={"answer_id": first, "kind": "bogus"}).status_code == 422


def test_model_card_reads_the_committed_results(client):
    card = client.get("/api/model-card").json()
    assert 0.8 < card["ragtruth_dev"]["auroc"] < 0.9 and "B1 lexical overlap" in card["baselines"]
    assert card["sources"]["final__ragtruth_dev.json"].startswith("eval/results/")
    assert 0.8 < card["ragtruth_dev"]["fusion_only_auroc"] < 0.9
    assert card["locked_test"]["answers"] == 2700 and set(card["locked_halueval"]) == {"qa", "dialogue", "summary"}
    assert card["locked_agenthallu"]["trajectories"] == 462 and 0 < card["locked_agenthallu"]["random"] < card["locked_agenthallu"]["exact"]
    assert 0.6 < card["locked_baselines"]["B1 lexical overlap"]["ragtruth"] < card["locked_test"]["auroc"]


def test_unknown_api_paths_are_not_served_the_app(client):
    assert client.get("/api/nothing").status_code == 404


def test_missing_asset_files_get_a_404_while_page_routes_get_the_app(client):
    assert client.get("/assets/Heal-old.js").status_code == 404
    assert client.get("/layers/missing.html").status_code == 404
    page = client.get("/heal")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]


def test_cached_reports_expire_with_the_model_or_the_brain_source(tmp_path):
    store = ExampleStore(ROOT)
    store.folder = tmp_path
    report = Report(id="x", verdict="grounded", risk=0.1, response_threshold=0.4, sentence_threshold=0.3, claims=[])
    store.store("anne-frank", "m1", report)
    assert store.cached("anne-frank", "m1") == report
    assert store.cached("anne-frank", "m2") is None
    store.code = "changed"
    assert store.cached("anne-frank", "m1") is None


def test_a_check_whose_client_left_is_dropped_before_it_runs():
    gone = threading.Event()
    gone.set()
    with pytest.raises(Cancelled):
        Engine().analyze(None, cancelled=gone)
    with pytest.raises(Cancelled):
        Engine().heal(None, cancelled=gone)


def test_setup_runs_the_nli_model_even_when_every_example_is_cached(monkeypatch):
    pairs = []
    monkeypatch.setattr(models, "nli_probabilities", pairs.extend)
    store = SimpleNamespace(examples={}, agents={})
    prepare(FakeEngine(), store)
    assert pairs == []
    prepare(FakeEngine(), store, every_model=True)
    assert len(pairs) == 1


def test_changed_range_finds_the_edit():
    assert _changed_range("She died in 1945.", "She died in 2022.") == (12, 16)
    assert _changed_range("It is big.", "It is not big.") == (6, 10)
    assert _changed_range("It is not big.", "It is big.") == (6, 7)
    assert _changed_range("Same.", "Same.") is None
