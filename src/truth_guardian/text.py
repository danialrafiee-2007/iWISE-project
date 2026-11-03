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
_CITATION_START = re.compile(r"\[?\d{1,3}(?:\s*,\s*\d{1,3})*\](?:\s*\[\d{1,3}(?:\s*,\s*\d{1,3})*\])*[^\w\s]*\s*")


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
    sentences. A line without 。！？ is split exactly as before they were handled. The sentencizer ends a sentence right after
    its full stop and the opening bracket, so "in 1945. [1] It" comes out as "in 1945. [" and "1] It"; the citation goes
    back to the sentence it belongs to, since it is not a claim of its own."""
    sentences = []
    for line in _LINE.finditer(text):
        first_of_line = len(sentences)
        pieces = _CJK_PIECE.finditer(line.group()) if any(c in line.group() for c in "。！？") else [line]
        for piece in pieces:
            offset = line.start() + (piece.start() if piece is not line else 0)
            for sent in _nlp()(piece.group()).sents:
                if not _WORD.search(sent.text):
                    continue
                start, end = offset + sent.start_char, offset + sent.end_char
                citation = _CITATION_START.match(sent.text) if len(sentences) > first_of_line else None
                if citation and (sentences[-1].text.endswith("[") or citation.end() == len(sent.text)):
                    before = sentences[-1]
                    stop = start + len(citation.group().rstrip())
                    sentences[-1] = Sentence(before.start, stop, text[before.start : stop])
                    start += citation.end()
                    if not _WORD.search(text[start:end]):
                        continue
                sentences.append(Sentence(start, end, text[start:end]))
    return sentences


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP_WORDS]


def content_words(text: str) -> set[str]:
    return set(tokens(text))
