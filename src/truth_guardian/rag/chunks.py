"""Documents cut into passages for retrieval, each with the page it came from.

A passage holds whole sentences up to MAX_WEIGHT and repeats the last sentence of the one before, so a fact split across a
boundary can still be found. Multilingual E5 reads 512 tokens, and MAX_WEIGHT leaves room for languages whose words take
several tokens. A line without sentence marks, such as a table row or a long list, is cut by words.
"""

import re
from typing import NamedTuple

from truth_guardian.text import split_sentences

MAX_WEIGHT = 120
OVERLAP = 1
_WIDE = re.compile("[぀-ヿ㐀-鿿]")


class Passage(NamedTuple):
    text: str
    page: int | None


def weight(text: str) -> int:
    """About how many words: Chinese and Japanese write without spaces, at about two characters a word."""
    return len(text.split()) + len(_WIDE.findall(text)) // 2


def _pieces(sentence: str) -> list[str]:
    if weight(sentence) <= MAX_WEIGHT:
        return [sentence]
    if _WIDE.search(sentence):
        size = (MAX_WEIGHT - 1) * 2
        return [sentence[i : i + size] for i in range(0, len(sentence), size)]
    words = sentence.split()
    return [" ".join(words[i : i + MAX_WEIGHT]) for i in range(0, len(words), MAX_WEIGHT)]


def _join(pieces: list[str]) -> str:
    return ("" if _WIDE.search(pieces[0]) else " ").join(pieces)


def passages(text: str, page: int | None = None) -> list[Passage]:
    out, current, used = [], [], 0
    for sentence in split_sentences(text):
        for piece in _pieces(sentence.text):
            size = weight(piece)
            if current and used + size > MAX_WEIGHT:
                out.append(Passage(_join(current), page))
                current = current[-OVERLAP:]
                used = sum(map(weight, current))
                if used + size > MAX_WEIGHT:
                    current, used = [], 0
            current.append(piece)
            used += size
    if current:
        out.append(Passage(_join(current), page))
    return out
