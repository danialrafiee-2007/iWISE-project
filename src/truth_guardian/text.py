"""Sentence segmentation that keeps character offsets into the original text."""

import re
from functools import lru_cache
from typing import NamedTuple

import spacy
from spacy.lang.en.stop_words import STOP_WORDS

_LINE = re.compile(r"[^\n]+")
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
    """Split on line breaks first (structured data is one fact per line), then into sentences."""
    sentences = []
    for line in _LINE.finditer(text):
        for sent in _nlp()(line.group()).sents:
            if _WORD.search(sent.text):
                start = line.start() + sent.start_char
                sentences.append(Sentence(start, line.start() + sent.end_char, sent.text))
    return sentences


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP_WORDS]


def content_words(text: str) -> set[str]:
    return set(tokens(text))
