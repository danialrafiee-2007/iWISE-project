import base64
import hashlib
import re
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from truth_guardian.rag import library as library_module
from truth_guardian.rag.chunks import MAX_WEIGHT, passages, weight
from truth_guardian.rag.library import MINE, PROJECT, Library, fuse, open_library
from truth_guardian.rag.words import WordIndex, terms
from truth_guardian.web import examples
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore

from test_documents import docx_with, pdf_with
from test_web_api import FakeEngine, events

FRANK = b"Anne Frank died of typhus in February 1945 at Bergen-Belsen."
EGGS = b"Global egg prices rose sharply in 2023 after bird flu reduced the number of laying hens."


def fake_encode(texts: list[str], kind: str) -> np.ndarray:
    vectors = np.zeros((len(texts), 64), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in re.findall(r"\w+", text.lower()):
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


@pytest.fixture
def shelf(tmp_path) -> Library:
    books = Library(tmp_path / "library.sqlite", fake_encode)
    yield books
    books.close()


def test_passages_hold_whole_sentences_and_repeat_the_last_one():
    sentences = [f"Sentence {i} " + "word " * 38 + "ends." for i in range(12)]
    cut = passages(" ".join(sentences), page=3)
    assert len(cut) > 1 and all(weight(p.text) <= MAX_WEIGHT and p.page == 3 for p in cut)
    assert cut[1].text.startswith(cut[0].text[cut[0].text.rindex("Sentence") :])
    assert all(s in " ".join(p.text for p in cut) for s in sentences)


def test_a_long_line_or_long_chinese_text_is_cut_to_fit():
    table = passages("cell " * (MAX_WEIGHT * 2 + 50))
    assert len(table) == 3 and all(weight(p.text) <= MAX_WEIGHT for p in table)
    chinese = passages("博物馆" * 400)
    assert len(chinese) > 1 and all(weight(p.text) <= MAX_WEIGHT for p in chinese)


def test_nothing_to_read_gives_no_passages():
    assert passages("") == [] and passages("... !!!") == []


def test_a_file_is_found_again_by_its_content(shelf):
    entry = shelf.add("frank.txt", FRANK)
    shelf.add("eggs.txt", EGGS)
    assert (entry.name, entry.collection, entry.kind, entry.passages, entry.language) == ("frank.txt", MINE, "text", 1, "en")
    found = shelf.search("When did Anne Frank die?")
    assert found.hits[0].document == "frank.txt" and "1945" in found.hits[0].text and found.hits[0].collection == MINE
    assert found.hits[0].similarity == pytest.approx(found.similarity)


def test_a_pdf_passage_keeps_its_page_and_a_word_file_has_none(shelf):
    shelf.add("paper.pdf", pdf_with("Anne Frank died in 1945."))
    shelf.add("report.docx", docx_with(["Egg prices rose in 2023."]))
    assert shelf.search("Anne Frank died in 1945", k=1).hits[0].page == 1
    assert shelf.search("Egg prices rose", k=1).hits[0].page is None


def test_the_same_file_twice_is_kept_and_embedded_once(tmp_path):
    calls = []
    books = Library(tmp_path / "l.sqlite", lambda texts, kind: calls.append(kind) or fake_encode(texts, kind))
    first, again = books.add("a.txt", FRANK), books.add("copy.txt", FRANK)
    assert first == again and calls == ["passage"] and len(books.documents()) == 1
    books.close()


def test_the_library_survives_a_restart(tmp_path):
    books = Library(tmp_path / "l.sqlite", fake_encode)
    books.add("frank.txt", FRANK)
    books.close()
    reopened = Library(tmp_path / "l.sqlite", fake_encode)
    assert reopened.search("Anne Frank").hits[0].document == "frank.txt"
    reopened.close()


def test_a_removed_document_is_no_longer_found_and_the_projects_cannot_be_removed_as_the_persons(shelf):
    mine = shelf.add("frank.txt", FRANK)
    theirs = shelf.add("eggs.txt", EGGS, PROJECT)
    assert shelf.search("Anne Frank").hits
    assert not shelf.remove(theirs.id) and shelf.remove(mine.id) and not shelf.remove(mine.id)
    assert [h.document for h in shelf.search("Anne Frank").hits] == ["eggs.txt"]
    assert shelf.documents(MINE) == []


def test_a_search_stays_in_the_collections_asked_for(shelf):
    shelf.add("frank.txt", FRANK)
    shelf.add("eggs.txt", EGGS, PROJECT)
    assert [h.document for h in shelf.search("egg prices", (MINE,)).hits] == ["frank.txt"]
    assert [h.document for h in shelf.search("Anne Frank", (PROJECT,)).hits] == ["eggs.txt"]
    assert shelf.search("Anne Frank", (MINE, PROJECT), k=1).hits[0].document == "frank.txt"


def test_an_empty_library_finds_nothing_and_is_not_enough(shelf):
    assert shelf.search("anything") == library_module.Found([], 0.0, False)


def test_enough_follows_the_closest_passage(shelf, monkeypatch):
    shelf.add("frank.txt", FRANK)
    monkeypatch.setattr(library_module, "LINES", {"en": 0.3})
    monkeypatch.setattr(library_module, "LINE_ACROSS_LANGUAGES", 0.3)
    assert shelf.search("Anne Frank died of typhus in February 1945").enough
    assert not shelf.search("zebra quantum physics is about the smallest things in the world").enough


def test_the_line_depends_on_the_languages_of_the_question_and_the_passage():
    assert library_module.enough_line("en", "en") == library_module.LINES["en"] > library_module.LINE_ACROSS_LANGUAGES
    assert library_module.enough_line("zh", "zh") == library_module.LINES["zh"]
    assert library_module.enough_line("fa", "fa") == library_module.LINE_OTHER_LANGUAGE
    assert library_module.enough_line("fa", "en") == library_module.enough_line(None, "en") == library_module.enough_line("en", None) == library_module.LINE_ACROSS_LANGUAGES


def test_fusion_counts_words_only_where_they_are_shared():
    dense, no_words = np.array([0.9, 0.5, 0.1]), np.zeros(3)
    assert np.argsort(-fuse(dense, no_words, 1.0)).tolist() == [0, 1, 2]
    shared = np.array([0.0, 0.0, 4.0])
    fused = fuse(dense, shared, 1.0)
    assert fused[2] > fuse(dense, no_words, 1.0)[2] and fused[1] == fuse(dense, no_words, 1.0)[1]
    assert np.argsort(-fused).tolist()[0] == 2
    assert fuse(dense, shared, 0.1)[2] < fused[2]


def test_word_search_reads_each_language_without_its_common_words():
    assert terms("The museum opened in 1950") == ["museum", "opened", "1950"]
    assert terms("El museo de la ciudad se abrió") == ["museo", "ciudad", "abrió"]
    assert terms("Музей открылся в городе") == ["музей", "открылся", "городе"]
    assert terms("موزه در سال ۱۳۲۹ باز شد") == terms("موزه سال ۱۳۲۹ باز")
    assert terms("博物馆开放") == ["博物", "物馆", "馆开", "开放"]
    assert "2" in terms("Step 2 of the plan") and terms("D-137") == ["137"]


def test_word_search_finds_a_rare_word_and_common_words_find_nothing():
    index = WordIndex(["The camp was liberated in 1945.", "El museo de la ciudad se abrió en 1950.", "Prices rose."])
    assert np.argmax(index.scores("liberated")) == 0 and np.argmax(index.scores("¿Cuándo se abrió el museo?")) == 1
    assert index.scores("de la el en").max() == 0
    assert index.scores("1950")[1] > 0 and index.scores("unheard").max() == 0
    assert WordIndex([]).scores("anything").size == 0


def test_a_file_that_cannot_be_used_is_explained_and_leaves_nothing(shelf):
    with pytest.raises(ValueError, match="not supported"):
        shelf.add("photo.png", b"\x89PNG")
    with pytest.raises(ValueError, match="no text"):
        shelf.add("empty.txt", b"   \n ")
    assert shelf.documents() == []


def test_a_full_library_says_so(shelf, monkeypatch):
    monkeypatch.setattr(library_module, "MAX_DOCUMENTS", 1)
    shelf.add("frank.txt", FRANK)
    with pytest.raises(ValueError, match="library is full"):
        shelf.add("eggs.txt", EGGS)


def test_the_projects_documents_are_added_once_and_replaced_when_they_change(tmp_path, shelf):
    (tmp_path / "README.md").write_text("Truth Guardian checks answers.", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "DEMO.md").write_text("Show the demo.", encoding="utf-8")
    assert shelf.ensure_project(tmp_path) == 2 and shelf.ensure_project(tmp_path) == 0
    (tmp_path / "README.md").write_text("Truth Guardian finds hallucinations.", encoding="utf-8")
    assert shelf.ensure_project(tmp_path) == 1
    assert sorted(e.name for e in shelf.documents(PROJECT)) == ["README.md", "docs/DEMO.md"]
    assert "hallucinations" in shelf.search("Truth Guardian", (PROJECT,), k=1).hits[0].text


def test_the_library_lives_under_the_one_folder_docker_may_write_to(tmp_path):
    books = open_library(tmp_path, fake_encode)
    assert (tmp_path / "data" / "web" / "library" / "library.sqlite").is_file()
    books.close()


def test_the_rag_cannot_change_the_guardian():
    package = Path(examples.__file__).resolve().parents[1]
    digest = hashlib.sha256()
    guardian = [p for p in sorted(package.rglob("*.py")) if not {"web", "rag"} & set(p.relative_to(package).parts)]
    for path in guardian:
        digest.update(path.read_bytes())
    assert examples.brain_fingerprint() == digest.hexdigest()[:16]
    assert not [p.name for p in guardian if "truth_guardian.rag" in p.read_text(encoding="utf-8")]


@pytest.fixture
def client(shelf):
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False, library=shelf)) as c:
        yield c


def upload(client, name: str, data: bytes):
    return client.post("/api/library/documents", json={"name": name, "data": base64.b64encode(data).decode()})


def test_the_api_adds_lists_searches_and_removes(client):
    assert client.get("/api/library").json()["documents"] == []
    found = events(upload(client, "frank.txt", FRANK))
    assert [e["type"] for e in found] == ["stage", "result"] and found[0]["done"] == found[0]["total"] == 1
    document = found[-1]["document"]
    assert document["name"] == "frank.txt" and [d["id"] for d in client.get("/api/library").json()["documents"]] == [document["id"]]
    hits = client.post("/api/library/search", json={"query": "Anne Frank", "k": 1}).json()
    assert hits["hits"][0]["document"] == "frank.txt" and "1945" in hits["hits"][0]["text"] and hits["enough"] in (True, False)
    assert client.delete(f"/api/library/documents/{document['id']}").json() == {"removed": document["id"]}
    assert client.delete(f"/api/library/documents/{document['id']}").status_code == 404


def test_the_api_refuses_what_it_cannot_use(client):
    assert events(upload(client, "photo.png", b"x"))[-1]["type"] == "error"
    assert client.post("/api/library/documents", json={"name": "a.txt", "data": "%%%"}).status_code == 422
    assert client.post("/api/library/search", json={"query": ""}).status_code == 422
    assert client.post("/api/library/search", json={"query": "x", "collections": ["theirs"]}).status_code == 422
    assert client.post("/api/library/search", json={"query": "x", "k": 500}).status_code == 422


def test_without_the_retrieval_model_the_api_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.media.models_dir", lambda: tmp_path)
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False)) as c:
        missing = c.get("/api/library")
    assert missing.status_code == 503 and "not on this computer" in missing.json()["detail"]
