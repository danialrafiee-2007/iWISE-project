"""The document library: what the person adds and the project's own documents, cut into passages, embedded once and kept
on disk, then found again by meaning and by word.

Meaning comes from multilingual E5, so a question finds a passage in another language; words come from BM25 (words.py),
which finds names and numbers that embeddings blur. Their rankings are fused (retrieval.py's RRF), counting BM25 only for
passages that share a word with the question, at the weight scripts/evaluate_retrieval.py chose. `Found.enough` says
whether the closest passage is close enough for the library to hold an answer (D-163).

Everything stays in one SQLite file under data/web, which is the one folder the Docker image may write to and which the
ready-made package carries. Nothing here reaches the network.
"""

import hashlib
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import numpy as np

from truth_guardian.language import detect
from truth_guardian.rag.chunks import passages
from truth_guardian.rag.words import WordIndex
from truth_guardian.retrieval import RRF_K, _ranks
from truth_guardian.web.documents import extract

MINE = "mine"
PROJECT = "project"
FOLDER = Path("data") / "web" / "library"
MAX_DOCUMENTS = 200
MAX_PASSAGES = 50_000
BATCH = 32
LINES = {"en": 0.810, "ar": 0.806, "es": 0.824, "ru": 0.812, "zh": 0.858}
LINE_OTHER_LANGUAGE = 0.810
LINE_ACROSS_LANGUAGES = 0.747
WORD_WEIGHT = 0.25
PROJECT_FILES = (
    "README.md", "docs/DEMO.md", "docs/DECISIONS.md", "docs/DATA_CARD.md", "docs/DATA_CARD_MULTILINGUAL.md", "docs/DOCKER.md", "docs/CREDITS.md",
    "docs/AI_USAGE.md", "benchmark/README.md",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY, collection TEXT NOT NULL, name TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL, pages INTEGER,
    language TEXT, added_at TEXT NOT NULL, UNIQUE (collection, sha256)
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE, page INTEGER, text TEXT NOT NULL, vector BLOB NOT NULL
);
"""
Encode = Callable[[list[str], str], np.ndarray]


class Entry(NamedTuple):
    id: int
    collection: str
    name: str
    kind: str
    pages: int | None
    language: str | None
    added_at: str
    passages: int


class Hit(NamedTuple):
    passage_id: int
    document_id: int
    document: str
    collection: str
    page: int | None
    text: str
    similarity: float
    score: float


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


def _default_encode(texts: list[str], kind: str) -> np.ndarray:
    from truth_guardian.media import multilingual

    return multilingual.embed(texts, kind)


class Library:
    def __init__(self, path: Path, encode: Encode | None = None):
        self.encode = encode or _default_encode
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._indexes: dict[tuple[str, ...], _Index] = {}

    def close(self) -> None:
        self._db.close()

    def documents(self, collection: str | None = None) -> list[Entry]:
        where, values = ("WHERE d.collection = ?", (collection,)) if collection else ("", ())
        query = f"""SELECT d.id, d.collection, d.name, d.kind, d.pages, d.language, d.added_at, COUNT(p.id) FROM documents d
                    LEFT JOIN passages p ON p.document_id = d.id {where} GROUP BY d.id ORDER BY d.id"""
        with self._lock:
            return [Entry(*row) for row in self._db.execute(query, values)]

    def add(self, name: str, data: bytes, collection: str = MINE, progress: Callable[[int, int], None] | None = None) -> Entry:
        """Raises ValueError with a message meant for the person when the file cannot be used. Adding the same file again
        changes nothing."""
        digest = hashlib.sha256(data).hexdigest()
        known = self._known(collection, digest)
        if known is not None:
            return known
        found = extract(name, data)
        cut = [p for page, text in enumerate(found.by_page, 1) for p in passages(text, page)] if found.by_page else passages(found.text)
        if not cut:
            raise ValueError("no text was found in the file")
        with self._lock:
            documents, stored = self._db.execute("SELECT (SELECT COUNT(*) FROM documents), (SELECT COUNT(*) FROM passages)").fetchone()
        if documents >= MAX_DOCUMENTS or stored + len(cut) > MAX_PASSAGES:
            raise ValueError(f"the library is full ({MAX_DOCUMENTS} documents or {MAX_PASSAGES:,} passages); remove something first")
        vectors = self._embed([p.text for p in cut], progress)
        with self._lock, self._db:
            row = self._db.execute(
                "INSERT INTO documents (collection, name, sha256, kind, pages, language, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (collection, name, digest, found.kind, found.pages, detect(found.text[:5000]).code, time.strftime("%Y-%m-%dT%H:%M:%S")),
            )
            self._db.executemany(
                "INSERT INTO passages (document_id, page, text, vector) VALUES (?, ?, ?, ?)",
                [(row.lastrowid, p.page, p.text, vector.tobytes()) for p, vector in zip(cut, vectors)],
            )
            self._indexes.clear()
        return self._known(collection, digest)

    def remove(self, document_id: int, collection: str = MINE) -> bool:
        """Only within the collection named, so a request about the person's documents can never remove the project's."""
        with self._lock, self._db:
            removed = self._db.execute("DELETE FROM documents WHERE id = ? AND collection = ?", (document_id, collection)).rowcount
            self._indexes.clear()
        return bool(removed)

    def search(self, query: str, collections: tuple[str, ...] = (MINE, PROJECT), k: int = 5) -> Found:
        index = self._index(tuple(sorted(collections)))
        if not index.rows:
            return Found([], 0.0, False)
        dense = index.vectors @ np.asarray(self.encode([query], "query")[0], dtype=np.float32)
        fused = fuse(dense, index.words.scores(query))
        hits = [Hit(*index.rows[i][:6], float(dense[i]), float(fused[i])) for i in np.argsort(-fused, kind="stable")[:k]]
        closest = int(dense.argmax())
        best = float(dense[closest])
        return Found(hits, best, best >= enough_line(detect(query).code, index.rows[closest][6]))

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
        query = f"""SELECT p.id, p.document_id, d.name, d.collection, p.page, p.text, d.language, p.vector FROM passages p JOIN documents d ON d.id = p.document_id
                    WHERE d.collection IN ({marks}) ORDER BY p.id"""
        with self._lock:
            if collections in self._indexes:
                return self._indexes[collections]
            rows = self._db.execute(query, collections).fetchall()
            vectors = np.stack([np.frombuffer(row[7], dtype=np.float32) for row in rows]) if rows else np.zeros((0, 0), dtype=np.float32)
            index = _Index([row[:7] for row in rows], vectors, WordIndex([row[5] for row in rows]))
            self._indexes[collections] = index
            return index


def open_library(root: Path, encode: Encode | None = None) -> Library:
    return Library(root / FOLDER / "library.sqlite", encode)
