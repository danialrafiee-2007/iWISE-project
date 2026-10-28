"""Sentence segmentation that keeps character offsets into the original text."""

import re
from functools import lru_cache
from typing import NamedTuple

import spacy
from spacy.lang.en.stop_words import STOP_WORDS

_LINE = re.compile(r"[^\n]+")
# Chinese and Japanese end sentences with full-width marks and no space, which the English sentencizer never splits at.
_CJK_PIECE = re.compile(r"[^。！？]+[。！？]*|[。！？]+")
_WORD = re.compile(r"\w+")


class Sentence(NamedTuple):
    start: int
    end: int
    text: str


@lru_cache(maxsize=1)
def _nlp():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def split_sentences(text: str) -> list[Sentence]:
    """Split on line breaks first (structured data is one fact per line), then after Chinese full stops, then into
    sentences. A line without 。！？ is split exactly as before they were handled."""
    sentences = []
    for line in _LINE.finditer(text):
        pieces = _CJK_PIECE.finditer(line.group()) if any(c in line.group() for c in "。！？") else [line]
        for piece in pieces:
            offset = line.start() + (piece.start() if piece is not line else 0)
            for sent in _nlp()(piece.group()).sents:
                if _WORD.search(sent.text):
                    sentences.append(Sentence(offset + sent.start_char, offset + sent.end_char, sent.text))
    return sentences


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP_WORDS]


def content_words(text: str) -> set[str]:
    return set(tokens(text))
