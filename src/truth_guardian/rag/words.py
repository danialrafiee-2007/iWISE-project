"""Word search (BM25) that reads every language the library may hold.

retrieval.py's BM25 drops English stop words only, so in Spanish or Russian the commonest words decide the ranking, and a
question in one language "matches" a passage in another through words such as "de" and "la". Here the stop words of the
checked languages and Persian go, Arabic loses its vowel marks and article, and Chinese and Japanese are read as pairs of
characters. Numbers stay, since a year or a decision's number is what word search is for.
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np

from truth_guardian.multicheck import _HAN, _arabic, stop_words

_RUN = re.compile(r"[^\W_]+")
K1 = 1.5
B = 0.75


@lru_cache(maxsize=1)
def _stopped() -> frozenset[str]:
    from spacy.lang.fa.stop_words import STOP_WORDS as persian

    return stop_words() | frozenset(persian)


def terms(text: str) -> list[str]:
    out = []
    for run in _RUN.findall(unicodedata.normalize("NFKC", text).lower()):
        han = _HAN.findall(run)
        if han:
            out += [a + b for a, b in zip(han, han[1:])] or han
            run = _HAN.sub(" ", run)
        for word in run.split():
            word = _arabic(word) if "؀" <= word[0] <= "ۿ" else word
            if word.isdigit() or (len(word) > 1 and word not in _stopped()):
                out.append(word)
    return out


class WordIndex:
    """Okapi BM25 over postings, so a query touches only the passages that hold its words."""

    def __init__(self, documents: list[str]):
        counted = [Counter(terms(d)) for d in documents]
        self.size = len(counted)
        lengths = np.array([sum(c.values()) for c in counted], dtype=float)
        self.norm = K1 * (1 - B + B * lengths / max(lengths.mean(), 1e-9)) if self.size else np.zeros(0)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, count in enumerate(counted):
            for term, frequency in count.items():
                postings[term].append((i, frequency))
        self.postings = {term: (np.array([i for i, _ in rows]), np.array([f for _, f in rows], dtype=float)) for term, rows in postings.items()}

    def scores(self, query: str) -> np.ndarray:
        result = np.zeros(self.size)
        for term in set(terms(query)):
            if term in self.postings:
                where, frequency = self.postings[term]
                idf = math.log((self.size - len(where) + 0.5) / (len(where) + 0.5) + 1)
                result[where] += idf * frequency * (K1 + 1) / (frequency + self.norm[where])
        return result
