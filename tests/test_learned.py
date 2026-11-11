"""What the Guardian learned online (D-222): an online answer found grounded is kept, to be answered offline next time."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from truth_guardian.rag import free, learned
from truth_guardian.rag.library import LEARNED, MINE, PROJECT, Library
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore

from test_rag_library import fake_encode
from test_web_api import FakeEngine, events

QUESTION = "When was the Eiffel Tower completed and how tall is it?"
TEXT = "The Eiffel Tower was completed in 1889. It is about 330 metres tall."
SOURCE = "The Eiffel Tower is a wrought-iron lattice tower in Paris. It was completed in 1889 and is 330 metres tall."


def cite(stance: str, n: int = 1):
    return SimpleNamespace(stance=stance, document=f"Wikipedia (en): Eiffel Tower {n}", place=f"https://en.wikipedia.org/wiki/Eiffel_Tower_{n}", text=SOURCE)


def online(verdict="grounded", status="checked", stances=("supports", "unrelated"), text=TEXT):
    report = SimpleNamespace(verdict=verdict, risk=0.12)
    return SimpleNamespace(status=status, report=report, text=text, question=QUESTION, generator="free:groq/model",
                           citations=[cite(s, n) for n, s in enumerate(stances, 1)])


@pytest.fixture
def shelf(tmp_path) -> Library:
    books = Library(tmp_path / "library.sqlite", fake_encode)
    yield books
    books.close()


def test_only_a_grounded_answer_with_a_supporting_source_and_none_against_it_is_kept():
    record = learned.record_of(online())
    assert record["question"] == QUESTION and record["answer"] == TEXT and record["risk"] == 0.12
    assert [s["url"] for s in record["sources"]] == ["https://en.wikipedia.org/wiki/Eiffel_Tower_1"]  # only the supporting one
    assert learned.record_of(online(verdict="uncertain")) is None
    assert learned.record_of(online(verdict="hallucinated")) is None
    assert learned.record_of(online(status="light")) is None  # the light check is not enough
    assert learned.record_of(online(stances=("supports", "contradicts"))) is None
    assert learned.record_of(online(stances=("unrelated", "missing"))) is None
    assert learned.record_of(online(text="  ")) is None


def test_what_is_kept_holds_the_question_the_answer_and_the_sources_own_words():
    text = learned.text_of(learned.record_of(online()))
    assert text.startswith(f"Question: {QUESTION}\nAnswer: {TEXT}\n") and "grounded (risk 0.12)" in text
    assert SOURCE in text and "https://en.wikipedia.org/wiki/Eiffel_Tower_1" in text
    long = learned.record_of(online())
    long["sources"][0]["text"] = learned._excerpt("A sentence. " * 400)
    assert len(long["sources"][0]["text"]) <= learned.SOURCE_CHARS + 2


def test_a_kept_answer_is_found_again_replaces_its_older_self_and_the_oldest_go(shelf, tmp_path, monkeypatch):
    record = learned.record_of(online())
    first = learned.keep(shelf, record, tmp_path)
    assert first.collection == LEARNED and first.name == "Learned online - When was the Eiffel Tower completed and how tall is it?.txt"
    again = learned.keep(shelf, {**record, "date": "2026-12-01"}, tmp_path)
    assert [e.id for e in shelf.documents(LEARNED)] == [again.id]  # one per question
    found = shelf.search("How tall is the Eiffel Tower?", (MINE, PROJECT, LEARNED))
    assert found.hits[0].collection == LEARNED and "330 metres" in found.hits[0].text
    monkeypatch.setattr(learned, "MAX_KEPT", 2)
    for n in range(3):
        learned.keep(shelf, {**record, "question": f"Question number {n}?"}, tmp_path)
    assert [e.name for e in shelf.documents(LEARNED)] == ["Learned online - Question number 1?.txt", "Learned online - Question number 2?.txt"]


def test_switched_off_nothing_is_kept(shelf, tmp_path):
    learned.save_settings(tmp_path, {"on": False})
    assert learned.keep(shelf, learned.record_of(online()), tmp_path) is None and shelf.documents(LEARNED) == []


def test_the_projects_examples_load_once_and_one_removed_stays_removed(shelf, tmp_path):
    record = learned.record_of(online())
    (tmp_path / learned.SEED).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / learned.SEED).write_text(json.dumps([record]), encoding="utf-8")
    assert learned.ensure_seed(shelf, tmp_path) == 1 and learned.ensure_seed(shelf, tmp_path) == 0
    item = learned.items(shelf, tmp_path)[0]
    assert item["seed"] and item["question"] == QUESTION
    assert learned.forget(shelf, tmp_path, item["id"]) and learned.ensure_seed(shelf, tmp_path) == 0
    assert shelf.documents(LEARNED) == []


def test_the_project_ships_its_examples_as_checked_online_answers():
    """Each example the project carries is an online answer the Guardian found grounded, with its supporting sources."""
    seeds = learned.seeds(ROOT)
    assert len(seeds) >= 5
    for record in seeds:
        assert record["question"] and record["answer"] and record["sources"] and 0 <= record["risk"] < 0.5
        assert all(s["url"].startswith("https://") and s["text"] for s in record["sources"])
        assert record["generator"].startswith("free-online:")


@pytest.fixture
def client(shelf, tmp_path):
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), root=tmp_path, load=False, library=shelf)) as c:
        yield c


class Online(SimpleNamespace):
    def model_dump(self, mode=None):
        return {"status": self.status, "text": self.text}


def test_the_api_keeps_a_verified_online_answer_lists_switches_and_forgets(client, monkeypatch):
    answer = Online(status="checked", report=SimpleNamespace(verdict="grounded", risk=0.1), text=TEXT, question=QUESTION,
                    generator="free:groq/m", citations=[cite("supports")])
    monkeypatch.setattr(free, "answer_free", lambda *a, **k: answer)
    result = events(client.post("/api/ask/free", json={"question": QUESTION}))[-1]
    assert result["learned"]["question"] == QUESTION and result["answer"]["text"] == TEXT
    listed = client.get("/api/learned").json()
    assert listed["on"] is True and [i["question"] for i in listed["items"]] == [QUESTION]
    kept = listed["items"][0]["id"]
    assert client.delete(f"/api/library/documents/{kept}").status_code == 404  # removing "mine" never reaches it
    assert client.post("/api/learned/settings", json={"on": False}).json() == {"on": False}
    learned_again = events(client.post("/api/ask/free", json={"question": "Another question?"}))[-1]["learned"]
    assert learned_again is None  # switched off: nothing more is kept
    assert client.delete(f"/api/learned/{kept}").json()["removed"] == kept
    assert client.get("/api/learned").json()["items"] == []
    assert client.delete("/api/learned/999").status_code == 404
