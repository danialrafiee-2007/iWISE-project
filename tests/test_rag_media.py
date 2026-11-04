import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from truth_guardian.media.contract import Place, Reading, Segment
from truth_guardian.rag.answer import OPINION_NOTE, answer
from truth_guardian.rag.chunks import MAX_WEIGHT
from truth_guardian.rag.library import MAX_DRAFTS, MINE, Library
from truth_guardian.rag.media import Kept, clock, concerns, cut, kind_of, shown
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore

from test_rag_answer import Checker, Script, not_checked
from test_rag_library import fake_encode
from test_web_api import FakeEngine, events


def said(*lines: tuple[str, float, float], language: str = "en", reasons: tuple[str, ...] = ()) -> Reading:
    segments = [Segment(text=text, role="transcript", language=language, place=Place(start=start, end=end)) for text, start, end in lines]
    return Reading(kind="audio", reader="whisper-small", segments=segments, language=language, reasons=list(reasons))


def picture(words: str = "", seen: str = "", language: str | None = None) -> Reading:
    segments = [Segment(text=line, role="ocr", place=Place(box=(0, 0, 9, 9))) for line in words.splitlines()]
    segments += [Segment(text=seen, role="description")] if seen else []
    return Reading(kind="image", reader="tesseract", segments=segments, language=language, reasons=["an image description is the model's opinion, not proof on its own"] if seen else [])


class Readers:
    """Stands in for the media readers, and records what they were asked."""

    def __init__(self, reading: Reading):
        self.reading, self.asked = reading, []

    def __call__(self, name, data, languages, describe) -> Reading:
        self.asked.append((name, list(languages), describe))
        return self.reading


@pytest.fixture
def lenient(monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)


def shelf(tmp_path, reading: Reading) -> Library:
    return Library(tmp_path / "library.sqlite", fake_encode, Readers(reading))


@pytest.mark.parametrize("name, kind", [("talk.MP3", "audio"), ("note.webm", "audio"), ("page.png", "image"), ("a.pdf", None), ("noname", None)])
def test_a_file_is_told_apart_by_its_ending(name, kind):
    assert kind_of(name) == kind


def test_a_clock_reads_minutes_and_hours():
    assert (clock(0), clock(83.9), clock(3725)) == ("00:00", "01:23", "1:02:05")


def test_a_recording_is_cut_into_passages_that_know_when_they_were_said():
    line = " ".join(["word"] * 50)
    found = cut(said((line, 0.0, 20.0), (line, 20.0, 40.0), (line, 40.0, 60.0), (line, 60.0, 80.0)))
    assert [p.place for p in found] == ["00:00-00:40", "00:20-01:00", "00:40-01:20"]
    assert all(p.role == "transcript" and p.page is None for p in found)
    assert all(len(p.text.split()) <= MAX_WEIGHT for p in found)


def test_a_segment_too_long_for_one_passage_is_split_and_keeps_its_time():
    found = cut(said((" ".join(["word"] * (MAX_WEIGHT * 2 + 5)), 3.0, 70.0)))
    assert len(found) >= 3 and {p.place for p in found} == {"00:03-01:10"}
    assert all(len(p.text.split()) <= MAX_WEIGHT for p in found)


def test_an_image_gives_the_words_read_and_the_opinion_apart():
    found = cut(picture("Fire exit\nOpen 9 to 5.", "A green sign on a wall."))
    assert [p.role for p in found] == ["ocr", "description"] and all(p.place is None for p in found)
    assert found[0].text == "Fire exit Open 9 to 5." and found[1].text == "A green sign on a wall."


def test_a_readers_doubts_are_kept_but_the_opinion_notice_is_not_a_doubt_about_words():
    reading = picture("Fire exit", "A sign.")
    reading.review("the language is uncertain (en 0.36)")
    assert concerns(reading) == ["the language is uncertain (en 0.36)"]


def test_a_recording_goes_on_the_shelf_with_its_reader_language_and_doubts(tmp_path):
    readers = Readers(said(("The museum opened in 1950.", 83.0, 90.0), language="zh-Hans", reasons=("the language is uncertain (zh 0.4)",)))
    books = Library(tmp_path / "library.sqlite", fake_encode, readers)
    entry = books.add("talk.mp3", b"sound", languages=["fa"], describe=False)
    assert (entry.kind, entry.language, entry.reader, entry.concerns, entry.passages) == ("audio", "zh", "whisper-small", "the language is uncertain (zh 0.4)", 1)
    assert readers.asked == [("talk.mp3", ["fa"], False)]
    (hit, *_) = books.search("museum 1950", (MINE,)).hits
    assert (hit.place, hit.role, hit.document) == ("01:23-01:30", "transcript", "talk.mp3")
    assert books.add("again.mp3", b"sound").id == entry.id and len(readers.asked) == 1
    books.close()


def test_a_file_where_nothing_was_read_is_refused_in_words(tmp_path):
    books = shelf(tmp_path, picture())
    with pytest.raises(ValueError, match="no text was found"):
        books.add("blank.png", b"pixels")
    assert books.documents() == []
    books.close()


def test_documents_still_go_through_the_document_reader(tmp_path):
    readers = Readers(picture("x"))
    books = Library(tmp_path / "library.sqlite", fake_encode, readers)
    entry = books.add("a.txt", "The museum opened in 1950.".encode())
    assert entry.kind != "image" and entry.reader is None and readers.asked == []
    assert books.search("museum", (MINE,)).hits[0].role is None
    books.close()


def test_a_library_from_before_media_gains_its_columns_and_keeps_its_documents(tmp_path):
    path = tmp_path / "library.sqlite"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE documents (id INTEGER PRIMARY KEY, collection TEXT NOT NULL, name TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL, pages INTEGER,
            language TEXT, added_at TEXT NOT NULL, UNIQUE (collection, sha256));
        CREATE TABLE passages (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, page INTEGER, text TEXT NOT NULL, vector BLOB NOT NULL);
        INSERT INTO documents VALUES (1, 'mine', 'old.txt', 'abc', 'text', NULL, 'en', '2026-11-04T00:00:00');
    """)
    old.executemany("INSERT INTO passages (document_id, text, vector) VALUES (1, 'The museum.', ?)", [(fake_encode(["The museum."], "passage")[0].astype("float32").tobytes(),)])
    old.commit()
    old.close()
    books = Library(path, fake_encode)
    assert [e.name for e in books.documents()] == ["old.txt"]
    (hit,) = books.search("museum", (MINE,)).hits
    assert hit.place is None and hit.role is None
    books.close()
    Library(path, fake_encode).close()


def test_an_answer_from_a_recording_cites_the_moment_and_is_checked_against_what_was_said(tmp_path, lenient):
    words = "The museum opened in 1950 in the old town."
    books = shelf(tmp_path, said((words, 83.0, 90.0)))
    books.add("talk.mp3", b"sound")
    guardian, writer = Checker(), Script("It opened in 1950 [1].")
    found = answer("When did the museum open in the old town?", books, guardian, writer, (MINE,))
    assert found.status == "checked" and found.citations[0].place == "01:23-01:30" and found.citations[0].role == "transcript"
    assert "(talk.mp3, 01:23-01:30)" in writer.asked[0][1][-1]["content"]
    assert guardian.samples[0].documents[0].text == words
    books.close()


def test_an_answer_resting_on_the_image_models_description_is_not_checked_and_says_so(tmp_path, lenient):
    books = shelf(tmp_path, picture(seen="A green fire exit sign on a white wall."))
    books.add("sign.png", b"pixels")
    guardian, writer = Checker(), Script("A green sign [1].")
    found = answer("What colour is the fire exit sign on the wall?", books, guardian, writer, (MINE,))
    assert found.status == "opinion" and found.report is None and OPINION_NOTE in found.notes and guardian.samples == []
    assert found.citations[0].role == "description"
    assert "what an image model says it sees" in writer.asked[0][1][-1]["content"]
    books.close()


def test_the_check_reads_the_words_in_an_image_and_never_the_description(tmp_path, lenient):
    books = shelf(tmp_path, picture("The fire exit sign is open from 9 to 5.", "A green fire exit sign on a white wall."))
    books.add("sign.png", b"pixels")
    guardian = Checker()
    found = answer("When is the fire exit sign open?", books, guardian, Script("From 9 to 5 [1]."), (MINE,))
    assert found.status == "checked" and found.citations[0].role == "ocr"
    assert all("green" not in d.text for d in guardian.samples[0].documents if d.source != "question")
    books.close()


def test_the_light_check_also_leaves_the_description_out(tmp_path, lenient):
    books = shelf(tmp_path, picture("موزه در سال ۱۳۲۹ باز شد.", "A green sign. The year 1999 is on it."))
    books.add("sign.png", b"pixels")
    found = answer("موزه در چه سالی باز شد؟", books, Checker(refuses=not_checked("language")), Script("موزه در سال ۱۹۹۹ باز شد [1]."), (MINE,))
    assert found.status == "light" and found.light[0].status == "doubtful" and "number" in found.light[0].reasons[0]
    books.close()


def test_reading_for_review_adds_nothing_and_shows_each_part_with_its_doubts(tmp_path):
    reading = said(("The musem opened in 1950.", 83.0, 90.0))
    reading.segments[0].confidence = 0.4
    books = shelf(tmp_path, reading)
    made = books.draft("talk.mp3", b"sound")
    assert books.documents() == [] and books.has_draft(made.id)
    (part,) = shown(made.reading)
    assert (part["index"], part["text"], part["place"], part["doubtful"], part["opinion"]) == (0, "The musem opened in 1950.", "01:23-01:30", True, False)
    assert shown(picture(seen="A sign."))[0]["opinion"] is True
    books.close()


def test_a_correction_is_what_the_library_finds_and_says_a_person_reviewed_it(tmp_path, lenient):
    books = shelf(tmp_path, said(("The musem opened in 1905.", 83.0, 90.0)))
    made = books.draft("talk.mp3", b"sound")
    entry = books.add_reviewed(made.id, [Kept(0, "The museum opened in 1950.")])
    assert entry.reviewed_at is not None and entry.reader == "whisper-small" and not books.has_draft(made.id)
    (hit,) = books.search("museum 1950", (MINE,)).hits
    assert (hit.text, hit.place, hit.role, hit.reviewed) == ("The museum opened in 1950.", "01:23-01:30", "transcript", True)
    found = answer("When did the museum open in 1950?", books, Checker(), Script("In 1950 [1]."), (MINE,))
    assert found.citations[0].reviewed is True
    books.close()


def test_a_file_added_without_review_says_so(tmp_path):
    books = shelf(tmp_path, said(("The museum opened in 1950.", 0.0, 5.0)))
    assert books.add("talk.mp3", b"sound").reviewed_at is None
    assert books.search("museum", (MINE,)).hits[0].reviewed is False
    books.close()


def test_a_part_left_out_or_emptied_is_removed(tmp_path):
    books = shelf(tmp_path, said(("First part.", 0.0, 5.0), ("Second part.", 5.0, 9.0), ("Third part.", 9.0, 12.0)))
    made = books.draft("talk.mp3", b"sound")
    entry = books.add_reviewed(made.id, [Kept(2, "Third part."), Kept(1, "   ")])
    assert [p.text for p in books.passages_of(entry.id)] == ["Third part."]
    books.close()


def test_a_confirmed_description_counts_as_words_and_the_answer_is_checked_against_it(tmp_path, lenient):
    seen = "A green fire exit sign on a white wall."
    books = shelf(tmp_path, picture(seen=seen))
    made = books.draft("sign.png", b"pixels")
    entry = books.add_reviewed(made.id, [Kept(0, seen, confirmed=True)])
    assert [p.role for p in books.passages_of(entry.id)] == ["confirmed"]
    guardian = Checker()
    found = answer("What colour is the fire exit sign on the wall?", books, guardian, Script("It is green [1]."), (MINE,))
    assert found.status == "checked" and found.citations[0].role == "confirmed" and guardian.samples[0].documents[0].text == seen
    books.close()


def test_a_description_reviewed_but_not_confirmed_stays_an_opinion(tmp_path, lenient):
    seen = "A green fire exit sign on a white wall."
    books = shelf(tmp_path, picture(seen=seen))
    made = books.draft("sign.png", b"pixels")
    books.add_reviewed(made.id, [Kept(0, seen)])
    found = answer("What colour is the fire exit sign on the wall?", books, Checker(), Script("It is green [1]."), (MINE,))
    assert found.status == "opinion" and found.citations[0].reviewed is True
    books.close()


def test_a_review_replaces_the_copy_added_without_one(tmp_path):
    books = shelf(tmp_path, said(("The musem.", 0.0, 5.0)))
    first = books.add("talk.mp3", b"sound")
    made = books.draft("talk.mp3", b"sound")
    second = books.add_reviewed(made.id, [Kept(0, "The museum.")])
    assert [e.id for e in books.documents()] == [second.id] and first.reviewed_at is None and second.reviewed_at
    assert [p.text for p in books.passages_of(second.id)] == ["The museum."]
    books.close()


@pytest.mark.parametrize("kept", [[Kept(5, "x")], [Kept(-1, "x")], [Kept(0, "x"), Kept(0, "y")]])
def test_parts_that_are_not_of_this_reading_are_refused_and_the_draft_stays(tmp_path, kept):
    books = shelf(tmp_path, said(("The museum.", 0.0, 5.0)))
    made = books.draft("talk.mp3", b"sound")
    with pytest.raises(ValueError, match="read the file again"):
        books.add_reviewed(made.id, kept)
    assert books.has_draft(made.id) and books.documents() == []
    books.close()


def test_removing_everything_is_refused_and_keeps_the_copy_already_there(tmp_path):
    books = shelf(tmp_path, said(("The museum.", 0.0, 5.0)))
    first = books.add("talk.mp3", b"sound")
    made = books.draft("talk.mp3", b"sound")
    with pytest.raises(ValueError, match="nothing is left"):
        books.add_reviewed(made.id, [])
    assert [e.id for e in books.documents()] == [first.id] and books.has_draft(made.id)
    books.close()


def test_only_the_latest_drafts_wait(tmp_path):
    books = shelf(tmp_path, said(("The museum.", 0.0, 5.0)))
    made = [books.draft("talk.mp3", bytes([n])) for n in range(MAX_DRAFTS + 1)]
    assert not books.has_draft(made[0].id) and books.has_draft(made[-1].id)
    with pytest.raises(KeyError):
        books.add_reviewed(made[0].id, [Kept(0, "x")])
    books.close()


class AnsweringEngine(FakeEngine):
    pass


def client_of(tmp_path, reading: Reading | Exception) -> TestClient:
    def read(name, data, languages, describe):
        if isinstance(reading, Exception):
            raise reading
        return reading

    books = Library(tmp_path / "library.sqlite", fake_encode, read)
    return TestClient(create_app(AnsweringEngine(), ExampleStore(ROOT), load=False, library=books))


def upload(name: str, data: bytes = b"bytes", **more) -> dict:
    return {"name": name, "data": base64.b64encode(data).decode(), **more}


def test_the_api_adds_a_recording_and_tells_its_stages(tmp_path):
    with client_of(tmp_path, said(("The museum opened in 1950.", 0.0, 5.0))) as c:
        found = events(c.post("/api/library/documents", json=upload("talk.mp3")))
        assert [e["stage"] for e in found if e["type"] == "stage"][0] == "reading"
        assert found[-1]["document"]["kind"] == "audio" and found[-1]["document"]["reader"] == "whisper-small"
        listed = c.get("/api/library").json()
        assert ".mp3" in listed["media_types"] and ".png" in listed["media_types"] and listed["max_media_bytes"] == 25_000_000
        assert [d["name"] for d in listed["documents"]] == ["talk.mp3"]


def test_the_api_takes_a_recording_too_large_for_a_document_but_not_a_document(tmp_path):
    big = b"x" * 11_000_000
    with client_of(tmp_path, said(("The museum opened in 1950.", 0.0, 5.0))) as c:
        assert events(c.post("/api/library/documents", json=upload("long.wav", big)))[-1]["type"] == "result"
        assert "limit is 10 MB" in events(c.post("/api/library/documents", json=upload("long.txt", b"y" * 11_000_000)))[-1]["message"]
        assert c.post("/api/library/documents", json=upload("huge.wav", b"x" * 26_000_000)).status_code == 422


@pytest.mark.parametrize(
    "failure, words",
    [(ImportError("no module"), "not installed"), (OSError("bad file"), "could not be read: OSError"), (RuntimeError("bad"), "could not be read: RuntimeError")],
)
def test_the_api_says_in_words_why_a_file_could_not_be_read(tmp_path, monkeypatch, failure, words):
    monkeypatch.setattr("truth_guardian.web.app._absent_reader", lambda kind, describe: None)
    with client_of(tmp_path, failure) as c:
        assert words in events(c.post("/api/library/documents", json=upload("talk.mp3")))[-1]["message"]
        assert events(c.post("/api/library/documents", json=upload("talk.mp3")))[-1]["type"] == "error"


def test_the_api_reads_for_review_then_adds_what_the_person_left(tmp_path):
    with client_of(tmp_path, said(("The musem opened.", 83.0, 90.0))) as c:
        read = events(c.post("/api/library/read", json=upload("talk.mp3")))
        assert read[0]["stage"] == "reading"
        result = read[-1]
        assert result["kind"] == "audio" and result["parts"][0]["text"] == "The musem opened." and result["parts"][0]["place"] == "01:23-01:30"
        assert c.get("/api/library").json()["documents"] == []
        added = events(c.post("/api/library/reviewed", json={"draft": result["draft"], "parts": [{"index": 0, "text": "The museum opened."}]}))[-1]["document"]
        assert added["reviewed_at"] is not None
        passages = c.get(f"/api/library/documents/{added['id']}/passages").json()["passages"]
        assert passages[0]["text"] == "The museum opened." and passages[0]["place"] == "01:23-01:30" and passages[0]["role"] == "transcript"


def test_the_api_refuses_what_it_cannot_review(tmp_path):
    with client_of(tmp_path, said(("The museum.", 0.0, 5.0))) as c:
        assert c.post("/api/library/read", json=upload("notes.txt")).status_code == 422
        assert c.post("/api/library/reviewed", json={"draft": "gone", "parts": []}).status_code == 404
        assert c.get("/api/library/documents/99/passages").status_code == 404
        draft = events(c.post("/api/library/read", json=upload("talk.mp3")))[-1]["draft"]
        wrong = events(c.post("/api/library/reviewed", json={"draft": draft, "parts": [{"index": 9, "text": "x"}]}))[-1]
        assert wrong["type"] == "error" and "read the file again" in wrong["message"]
        assert events(c.post("/api/library/reviewed", json={"draft": draft, "parts": [{"index": 0, "text": "The museum."}]}))[-1]["type"] == "result"
        assert c.post("/api/library/reviewed", json={"draft": draft, "parts": []}).status_code == 404
        assert c.post("/api/library/reviewed", json={"draft": draft, "parts": [{"index": 0, "text": "x", "other": 1}]}).status_code == 422


def test_the_api_says_a_damaged_image_could_not_be_read(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.web.app._absent_reader", lambda kind, describe: None)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    with TestClient(create_app(AnsweringEngine(), ExampleStore(ROOT), load=False, library=books)) as c:
        assert "could not be read: UnidentifiedImageError" in events(c.post("/api/library/documents", json=upload("photo.png", b"\x89PNG")))[-1]["message"]
        assert c.get("/api/library").json()["documents"] == []


def test_the_api_names_a_reader_that_is_not_on_this_computer(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.web.app._absent_reader", lambda kind, describe: "the speech model")
    with client_of(tmp_path, OSError("no files")) as c:
        assert "the speech model is not on this computer" in events(c.post("/api/library/documents", json=upload("talk.mp3")))[-1]["message"]
