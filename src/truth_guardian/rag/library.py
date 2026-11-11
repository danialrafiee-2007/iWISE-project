"""The document library: what the person adds and the project's own documents, cut into passages, embedded once and kept
on disk, then found again by meaning and by word.

Meaning comes from multilingual E5, so a question finds a passage in another language; words come from BM25 (words.py),
which finds names and numbers that embeddings blur. Their rankings are fused (retrieval.py's RRF), counting BM25 only for
passages that share a word with the question, at the weight scripts/evaluate_retrieval.py chose. `Found.enough` says
whether the closest passage is close enough for the library to hold an answer (D-163).

Recordings and images come in through their readers (rag/media.py).

Everything stays in one SQLite file under data/web, which is the one folder the Docker image may write to and which the
ready-made package carries. Nothing here reaches the network.
"""

import hashlib
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np

from truth_guardian.language import detect
from truth_guardian.media.contract import Reading
from truth_guardian.rag.chunks import Passage, passages
from truth_guardian.rag.media import Kept, concerns, cut, kind_of, picture_of, read_file, reviewed
from truth_guardian.rag.words import WordIndex, terms
from truth_guardian.retrieval import RRF_K, _ranks
from truth_guardian.web.documents import extract

MINE = "mine"
PROJECT = "project"
# Online answers the Guardian found grounded, kept to be answered offline next time (rag/learned.py, D-222).
LEARNED = "learned"
FOLDER = Path("data") / "web" / "library"
MAX_DOCUMENTS = 200
MAX_PASSAGES = 50_000
BATCH = 32
MAX_DRAFTS = 16
LINES ={"en": 0.810, "ar": 0.806, "es": 0.824, "ru": 0.812, "zh": 0.858}
LINE_OTHER_LANGUAGE = 0.810
LINE_ACROSS_LANGUAGES = 0.747
WORD_WEIGHT = 0.25
# A passage just under the line still counts when it holds this share of the question's words (D-168).
WORD_MARGIN, WORD_SHARE = 0.02, 0.5
PROJECT_FILES = (
    "README.md", "docs/DEMO.md", "docs/DECISIONS.md", "docs/DATA_CARD.md", "docs/DATA_CARD_MULTILINGUAL.md", "docs/DOCKER.md", "docs/CREDITS.md",
    "docs/AI_USAGE.md", "benchmark/README.md",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY, collection TEXT NOT NULL, name TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL, pages INTEGER,
    language TEXT, added_at TEXT NOT NULL, reader TEXT, concerns TEXT, reviewed_at TEXT, UNIQUE (collection, sha256)
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE, page INTEGER, text TEXT NOT NULL, vector BLOB NOT NULL,
    place TEXT, role TEXT
);
CREATE TABLE IF NOT EXISTS pictures (document_id INTEGER PRIMARY KEY REFERENCES documents (id) ON DELETE CASCADE, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS seconds (document_id INTEGER PRIMARY KEY REFERENCES documents (id) ON DELETE CASCADE, model TEXT NOT NULL, text TEXT NOT NULL);
"""
ADDED_COLUMNS = {"documents": ("reader", "concerns", "reviewed_at"), "passages": ("place", "role")}
Encode = Callable[[list[str], str], np.ndarray]
Read = Callable[[str, bytes, Sequence[str], bool], Reading]


class Entry(NamedTuple):
    id: int
    collection: str
    name: str
    kind: str
    pages: int | None
    language: str | None
    added_at: str
    passages: int
    reader: str | None = None
    concerns: str | None = None
    reviewed_at: str | None = None


class Draft(NamedTuple):
    """What was read in a file, waiting for a person to review it. Of the file it holds only the reduced copy of an image."""

    id: str
    name: str
    digest: str
    reading: Reading
    picture: bytes | None = None


class Hit(NamedTuple):
    passage_id: int
    document_id: int
    document: str
    collection: str
    page: int | None
    text: str
    similarity: float
    score: float
    place: str | None = None
    role: str | None = None
    reviewed: bool = False


class Found(NamedTuple):
    hits: list[Hit]
    similarity: float
    enough: bool


class _Index(NamedTuple):
    rows: list[tuple]
    vectors: np.ndarray
    words: WordIndex


def fuse(dense: np.ndarray, lexical: np.ndarray, weight: float | None = None) -> np.ndarray:
    """Reciprocal rank fusion of the two rankings; a passage sharing no word with the question gets nothing from BM25."""
    score = 1.0 / (RRF_K + _ranks(dense))
    if lexical.max(initial=0.0) > 0:
        score = score + (WORD_WEIGHT if weight is None else weight) * np.where(lexical > 0, 1.0 / (RRF_K + _ranks(lexical)), 0.0)
    return score


def enough_line(question: str | None, passage: str | None) -> float:
    """How close the closest passage must be, by language: the same scale does not hold across them. A question and a
    passage in different languages sit lower and overlap, so only the clearly unrelated stop here and the answer's own
    check decides the rest; so does a language that could not be told, since wrongly saying "not in the documents" is the
    worse mistake."""
    if question is None or passage is None or question != passage:
        return LINE_ACROSS_LANGUAGES
    return LINES.get(question, LINE_OTHER_LANGUAGE)


def close_enough(similarity: float, line: float, question: str, passage: str) -> bool:
    if similarity >= line:
        return True
    wanted = set(terms(question))
    return similarity >= line - WORD_MARGIN and bool(wanted) and len(wanted & set(terms(passage))) / len(wanted) >= WORD_SHARE


def _default_encode(texts: list[str], kind: str) -> np.ndarray:
    from truth_guardian.media import multilingual

    return multilingual.embed(texts, kind)


class Library:
    def __init__(self, path: Path, encode: Encode | None = None, read: Read = read_file):
        self.encode, self.read = encode or _default_encode, read
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        for table, columns in ADDED_COLUMNS.items():
            have = {row[1] for row in self._db.execute(f"PRAGMA table_info({table})")}
            for column in columns:
                if column not in have:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        self._lock = threading.Lock()
        self._indexes: dict[tuple[str, ...], _Index] = {}
        self._drafts: OrderedDict[str, Draft] = OrderedDict()
        # A second listener for a recording as it is added (rag/second.py, D-200): (name, bytes) -> (model, transcript) or None.
        self.hear: Callable[[str, bytes], tuple[str, str] | None] | None = None

    def close(self) -> None:
        self._db.close()

    def documents(self, collection: str | None = None) -> list[Entry]:
        where, values = ("WHERE d.collection = ?", (collection,)) if collection else ("", ())
        query = f"""SELECT d.id, d.collection, d.name, d.kind, d.pages, d.language, d.added_at, COUNT(p.id), d.reader, d.concerns, d.reviewed_at FROM documents d
                    LEFT JOIN passages p ON p.document_id = d.id {where} GROUP BY d.id ORDER BY d.id"""
        with self._lock:
            return [Entry(*row) for row in self._db.execute(query, values)]

    def add(
        self, name: str, data: bytes, collection: str = MINE, progress: Callable[[int, int], None] | None = None, languages: Sequence[str] = (), describe: bool = True,
    ) -> Entry:
        """Raises ValueError with a message meant for the person when the file cannot be used. Adding the same file again
        changes nothing. languages and describe are for a recording or an image: see rag/media.py."""
        digest = hashlib.sha256(data).hexdigest()
        known = self._known(collection, digest)
        if known is not None:
            return known
        if kind_of(name):
            entry = self._store_reading(name, digest, self.read(name, data, languages, describe), collection, progress, picture=picture_of(name, data))
            if kind_of(name) == "audio" and self.hear is not None:
                try:  # a second transcript is a help, never a reason the file is not added
                    heard = self.hear(name, data)
                except Exception:
                    heard = None
                if heard:
                    self.set_second(entry.id, *heard)
            return entry
        found = extract(name, data)
        pieces = [p for page, text in enumerate(found.by_page, 1) for p in passages(text, page)] if found.by_page else passages(found.text)
        return self._store(name, digest, pieces, collection, progress, found.kind, found.pages, detect(found.text[:5000]).code)

    def draft(self, name: str, data: bytes, languages: Sequence[str] = (), describe: bool = True) -> Draft:
        """Reads a recording or an image without adding it; add_reviewed takes it from there. Only the latest MAX_DRAFTS wait."""
        made = Draft(secrets.token_hex(8), name, hashlib.sha256(data).hexdigest(), self.read(name, data, languages, describe), picture_of(name, data))
        with self._lock:
            self._drafts[made.id] = made
            while len(self._drafts) > MAX_DRAFTS:
                self._drafts.popitem(last=False)
        return made

    def has_draft(self, draft_id: str) -> bool:
        with self._lock:
            return draft_id in self._drafts

    def add_reviewed(self, draft_id: str, kept: Sequence[Kept], collection: str = MINE, progress: Callable[[int, int], None] | None = None) -> Entry:
        """Adds a reading as a person left it, in place of any copy of the file added without review. Raises KeyError for a
        draft that is gone, and ValueError as add does. A draft that could not be used stays, so the person can try again."""
        with self._lock:
            made = self._drafts[draft_id]
        reading = reviewed(made.reading, kept)
        if not cut(reading):
            raise ValueError("nothing is left to add; keep at least one part")
        old = self._known(collection, made.digest)
        if old is not None:
            self.remove(old.id, collection)
        entry = self._store_reading(made.name, made.digest, reading, collection, progress, time.strftime("%Y-%m-%dT%H:%M:%S"), made.picture)
        with self._lock:
            self._drafts.pop(draft_id, None)
        return entry

    def passages_of(self, document_id: int) -> list[Passage]:
        """What the library holds of a document, so a person can see what was extracted."""
        with self._lock:
            return [Passage(*row) for row in self._db.execute("SELECT text, page, place, role FROM passages WHERE document_id = ? ORDER BY id", (document_id,))]

    def second_of(self, document_id: int) -> tuple[str, str] | None:
        """A second model's transcript of a recording: (model, text), kept when it was added."""
        with self._lock:
            row = self._db.execute("SELECT model, text FROM seconds WHERE document_id = ?", (document_id,)).fetchone()
        return (row[0], row[1]) if row else None

    def set_second(self, document_id: int, model: str, text: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO seconds (document_id, model, text) VALUES (?, ?, ?)", (document_id, model, text))

    def picture(self, document_id: int) -> bytes | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM pictures WHERE document_id = ?", (document_id,)).fetchone()
        return row[0] if row else None

    def _store_reading(self, name: str, digest: str, reading: Reading, collection: str, progress, reviewed_at: str | None = None, picture: bytes | None = None) -> Entry:
        pieces = cut(reading)
        language = reading.language.split("-")[0] if reading.language else detect(" ".join(p.text for p in pieces)[:5000]).code
        return self._store(name, digest, pieces, collection, progress, reading.kind, None, language, reading.reader, "\n".join(concerns(reading)) or None, reviewed_at, picture)

    def _store(
        self, name: str, digest: str, pieces: list[Passage], collection: str, progress, kind: str, pages: int | None, language: str | None,
        reader: str | None = None, doubts: str | None = None, reviewed_at: str | None = None, picture: bytes | None = None,
    ) -> Entry:
        if not pieces:
            raise ValueError("no text was found in the file")
        with self._lock:
            documents, stored = self._db.execute("SELECT (SELECT COUNT(*) FROM documents), (SELECT COUNT(*) FROM passages)").fetchone()
        if documents >= MAX_DOCUMENTS or stored + len(pieces) > MAX_PASSAGES:
            raise ValueError(f"the library is full ({MAX_DOCUMENTS} documents or {MAX_PASSAGES:,} passages); remove something first")
        vectors = self._embed([p.text for p in pieces], progress)
        with self._lock, self._db:
            row = self._db.execute(
                "INSERT INTO documents (collection, name, sha256, kind, pages, language, added_at, reader, concerns, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (collection, name, digest, kind, pages, language, time.strftime("%Y-%m-%dT%H:%M:%S"), reader, doubts, reviewed_at),
            )
            self._db.executemany(
                "INSERT INTO passages (document_id, page, text, vector, place, role) VALUES (?, ?, ?, ?, ?, ?)",
                [(row.lastrowid, p.page, p.text, vector.tobytes(), p.place, p.role) for p, vector in zip(pieces, vectors)],
            )
            if picture:
                self._db.execute("INSERT INTO pictures (document_id, data) VALUES (?, ?)", (row.lastrowid, picture))
            self._indexes.clear()
        return self._known(collection, digest)

    def remove(self, document_id: int, collection: str = MINE) -> bool:
        """Only within the collection named, so a request about the person's documents can never remove the project's."""
        with self._lock, self._db:
            removed = self._db.execute("DELETE FROM documents WHERE id = ? AND collection = ?", (document_id, collection)).rowcount
            self._indexes.clear()
        return bool(removed)

    def search(self, query: str, collections: tuple[str, ...] = (MINE, PROJECT, LEARNED), k: int = 5) -> Found:
        index = self._index(tuple(sorted(collections)))
        if not index.rows:
            return Found([], 0.0, False)
        dense = index.vectors @ np.asarray(self.encode([query], "query")[0], dtype=np.float32)
        fused = fuse(dense, index.words.scores(query))
        hits = [Hit(*index.rows[i][:6], float(dense[i]), float(fused[i]), *index.rows[i][7:9], index.rows[i][9] is not None) for i in np.argsort(-fused, kind="stable")[:k]]
        closest = int(dense.argmax())
        best = float(dense[closest])
        return Found(hits, best, close_enough(best, enough_line(detect(query).code, index.rows[closest][6]), query, index.rows[closest][5]))

    def ensure_project(self, root: Path) -> int:
        """Adds the project's own documents, replacing one whose text changed; returns how many were added."""
        added = 0
        for relative in PROJECT_FILES:
            path = root / relative
            if not path.is_file():
                continue
            data = path.read_bytes()
            if self._known(PROJECT, hashlib.sha256(data).hexdigest()) is not None:
                continue
            for entry in self.documents(PROJECT):
                if entry.name == relative:
                    self.remove(entry.id, PROJECT)
            self.add(relative, data, PROJECT)
            added += 1
        return added

    def _known(self, collection: str, digest: str) -> Entry | None:
        with self._lock:
            row = self._db.execute("SELECT id FROM documents WHERE collection = ? AND sha256 = ?", (collection, digest)).fetchone()
        return next((e for e in self.documents(collection) if e.id == row[0]), None) if row else None

    def _embed(self, texts: list[str], progress: Callable[[int, int], None] | None) -> np.ndarray:
        vectors = []
        for start in range(0, len(texts), BATCH):
            vectors.append(np.asarray(self.encode(texts[start : start + BATCH], "passage"), dtype=np.float32))
            if progress:
                progress(min(start + BATCH, len(texts)), len(texts))
        return np.vstack(vectors)

    def _index(self, collections: tuple[str, ...]) -> _Index:
        marks = ", ".join("?" * len(collections))
        query = f"""SELECT p.id, p.document_id, d.name, d.collection, p.page, p.text, d.language, p.place, p.role, d.reviewed_at, p.vector FROM passages p JOIN documents d ON d.id = p.document_id
                    WHERE d.collection IN ({marks}) ORDER BY p.id"""
        with self._lock:
            if collections in self._indexes:
                return self._indexes[collections]
            rows = self._db.execute(query, collections).fetchall()
            vectors = np.stack([np.frombuffer(row[10], dtype=np.float32) for row in rows]) if rows else np.zeros((0, 0), dtype=np.float32)
            index = _Index([row[:10] for row in rows], vectors, WordIndex([row[5] for row in rows]))
            self._indexes[collections] = index
            return index


def open_library(root: Path, encode: Encode | None = None) -> Library:
    return Library(root / FOLDER / "library.sqlite", encode)
