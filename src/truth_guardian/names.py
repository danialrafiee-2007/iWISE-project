"""Names written in another script: "Riverside Museum" in an agent's thought, "موزه ریورساید" in the task.

The live guardian (guardian.py) objects to a name absent from the question and every tool output so far, comparing
words; a model thinking in English about a Persian task writes the task's own names in Latin letters and drew that
objection before its first search (D-170: 3 of 4 Persian runs). Arabic, Persian and Cyrillic letters and Latin ones are
all brought to a skeleton of consonant classes, leaving out what these alphabets write differently or not at all: short
vowels, the letters that also stand for vowels (alef, vav, ye, w, y), h, and the difference between s and z. A name is
taken as written in the question when each of its words is either such a word of the question in another script or a
common English word ("Museum"), and at least one is the former. Chinese is not covered: its names are not spelled.
"""

import re
import unicodedata
from functools import lru_cache

from truth_guardian.text import STOP_WORDS

MIN_SKELETON = 3
_PAIRS = (("sch", "s"), ("sh", "s"), ("ch", "c"), ("zh", "s"), ("kh", "k"), ("gh", "g"), ("ph", "f"), ("th", "t"), ("ck", "k"), ("ts", "c"))
_LATIN = {**dict.fromkeys("aeiouyhwv", ""), "q": "k", "x": "k", "c": "k", "z": "s"}
_ARABIC = {
    **dict.fromkeys("اآأإءعهةیيىوؤئحـ", ""), "ب": "b", "پ": "p", "ت": "t", "ط": "t", "ث": "s", "س": "s", "ص": "s", "ج": "j", "چ": "c",
    "خ": "k", "د": "d", "ذ": "s", "ز": "s", "ض": "s", "ظ": "s", "ژ": "s", "ر": "r", "ش": "s", "غ": "g", "ف": "f", "ق": "k", "ک": "k",
    "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
}
_CYRILLIC = {
    **dict.fromkeys("аеёиоуыэюяйьъв", ""), "б": "b", "г": "g", "д": "d", "ж": "s", "з": "s", "к": "k", "л": "l", "м": "m", "н": "n",
    "п": "p", "р": "r", "с": "s", "т": "t", "ф": "f", "х": "k", "ц": "c", "ч": "c", "ш": "s", "щ": "s",
}
_WORD = re.compile(r"[^\W\d_]+")
_LATIN_WORD = re.compile(r"[a-z]+")


def skeleton(word: str) -> str:
    word = "".join(c for c in unicodedata.normalize("NFKD", word.lower()) if not unicodedata.combining(c))
    if _LATIN_WORD.fullmatch(word):
        for pair, single in _PAIRS:
            word = word.replace(pair, single)
        letters = [_LATIN.get(c, c) for c in word]
    else:
        letters = [_ARABIC.get(c, _CYRILLIC.get(c, "?")) for c in word]
    out = re.sub(r"(.)\1+", r"\1", "".join(letters))
    return "" if "?" in out else out


@lru_cache(maxsize=4096)
def _common(word: str) -> bool:
    from truth_guardian.polarity import _wordnet

    return bool(_wordnet().synsets(word.lower()))


def written_in(name: str, question: str | None) -> bool:
    """Whether a Latin-letter name stands for words the question writes in another script."""
    foreign = {s for w in _WORD.findall(question or "") if not w.isascii() and len(s := skeleton(w)) >= MIN_SKELETON}
    if not foreign:
        return False
    matched = False
    for word in _WORD.findall(name):
        if not word.isascii():
            return False
        if word.lower() in STOP_WORDS:
            continue
        if skeleton(word) in foreign:
            matched = True
        elif not _common(word):
            return False
    return matched
