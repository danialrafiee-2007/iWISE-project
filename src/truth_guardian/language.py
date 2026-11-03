"""The language of each text the engine is given, so that every text goes to a check that can read it (D-137).

The language comes from the texts themselves, never from the interface's language: a page in Spanish may be checking an
English answer. English answers over English sources go to the English engine. Arabic, Chinese, French, Russian and
Spanish (the interface's other languages, Persian aside) go to the multilingual check, also when the answer and its
sources are in different ones of these. Persian and every other language get no verdict: Persian is left out by the
owner's decision, and the multilingual NLI model was not trained on it (XNLI has no Persian).

Told without a model: the script of the letters first; where several languages share a script, function words (the OCR
reader's lists, with question words and Cyrillic lists added here) and letters only one of them writes. A text too short
to tell, such as a number or a name, has no language of its own and takes the question's or the sources'. On XQuAD
(English, Arabic, Spanish, Russian, Chinese; the data these lists were tuned on, so a fresh set must confirm it) the
contexts are named right 99.6 to 100% of the time and the answers, told with their question, 99.9 to 100%.
"""

import re
import unicodedata
from collections import Counter
from typing import Literal, NamedTuple

from truth_guardian.media.contract import bcp47
from truth_guardian.media.ocr import FUNCTION_WORDS, OWN_LETTERS, SHARED_SCRIPTS, WORD

ENGLISH = "en"
MULTILINGUAL = ("ar", "es", "fr", "ru", "zh")
CHECKED = (ENGLISH, *MULTILINGUAL)
MIN_LETTERS = 4  # fewer letters than this say nothing about a language
MIN_WORDS = 4  # fewer words than this say nothing about which of a script's languages it is
# Below this many words, a short answer's own words may pick a neighbouring language ("a Portuguese king" read as
# Portuguese), so its language is told together with the question's words.
SURE_WORDS = 8

# Unicode's name for a letter's script (the first word of the character's name) to a script.
SCRIPT_OF = {"LATIN": "Latin", "ARABIC": "Arabic", "CYRILLIC": "Cyrillic", "CJK": "Han", "HIRAGANA": "Kana", "KATAKANA": "Kana",
             "HANGUL": "Hangul", "GREEK": "Greek", "HEBREW": "Hebrew", "DEVANAGARI": "Devanagari", "THAI": "Thai"}
ONE_LANGUAGE = {"Hangul": "ko", "Greek": "el", "Hebrew": "he", "Thai": "th"}
# A Chinese or Japanese character carries about a word, a Hangul block a syllable: counted as this many letters, so a
# Chinese question with a Latin name in it ("Internet2与谁达成合作伙伴关系") stays Chinese.
WEIGHT = {"Han": 3, "Kana": 3, "Hangul": 2}
MORE_WORDS = {
    "eng": "what who when where which how did does do at from has have were an not or but its their there had his her they",
    "spa": "qué quién cuándo dónde cuál cómo lo al su sus más fue son pero le les este esta ha a o no",
    "fra": "qui quoi quand où quel quelle comment ce il elle sont ont été mais se ne son sa ses plus par",
    "por": "não são foi qual quem quando onde seu sua mais ao pelo pela",
    "rus": "и в не на что с он я как это по но к из у за то от же так все она был для бы о кто где когда какой каком какое "
           "какая какие сколько почему его их том было были который которые также при после",
    "ukr": "і в не на що з як це та до у за від але так він вона був для або хто де коли який яка які скільки чому його їх "
           "було також після",
    "bul": "и в не на да е се за от че с са по като това той тя беше със кой къде кога какво колко защо ще",
}
ORDINAL = re.compile(r"\d+[-‑–]\w+")  # "99-й", "19-го": a number's ending, not a word of its own
WORDS = {code: set(f"{FUNCTION_WORDS.get(code, '')} {MORE_WORDS.get(code, '')}".split()) for code in {*FUNCTION_WORDS, *MORE_WORDS}}
# Letters one language of a shared script writes and its neighbours here do not. Typed Persian uses its own forms of
# yeh and kaf (ی ک), typed Arabic the Arabic ones (ي ك) and the closed taa (ة), which Persian keeps only in loanwords.
OWN = {**OWN_LETTERS, "fas": OWN_LETTERS["fas"] + "یک", "ara": "يكة", "rus": "ыэё", "ukr": "іїєґ",
       "spa": "ñ¿¡", "por": "ãõ", "fra": "œ", "deu": "ß", "tur": "ğış"}
SHARED = {**SHARED_SCRIPTS, "Arabic": ["ara", "fas", "urd"], "Cyrillic": ["rus", "ukr", "bul"]}

Check = Literal["english", "multilingual"]


class Language(NamedTuple):
    code: str | None  # BCP 47 (en, ar, zh); None when the text is too short or the evidence ties
    script: str | None
    confidence: float  # the share of letters in that script, times the share of words that told the language


class Route(NamedTuple):
    check: Check | None  # None: no check reads these texts
    answer: str | None
    sources: list[str | None]
    why_not: str | None = None  # "language" (one is not checked) or "unknown_language" (the answer's could not be told)
    guessed: bool = False  # the language could not be told and was taken as the checked one its script most likely is


# A text too short to tell, in a script only one checked language writes among the likely ones, is taken as that one;
# Arabic script is never guessed, since it may be Persian.
GUESS = {"Latin": ENGLISH, "Cyrillic": "ru"}


def script(text: str) -> tuple[str | None, float]:
    """The script most letters are written in (by weight) and its share of them; None with fewer than MIN_LETTERS."""
    counts = Counter()
    for ch in text:
        if ch.isalpha():
            name = SCRIPT_OF.get(unicodedata.name(ch, "").split(" ")[0])
            counts[name] += WEIGHT.get(name, 1)
    letters = sum(counts.values())
    counts.pop(None, None)
    if letters < MIN_LETTERS or not counts:
        return None, 0.0
    best, n = counts.most_common(1)[0]
    if best == "Han" and counts["Kana"]:
        best, n = "Kana", n + counts["Kana"]  # Japanese writes Chinese characters among its kana
    return best, round(n / letters, 3)


def _shared(script_name: str, text: str) -> tuple[str | None, float]:
    """Function words plus letters only one language writes; None when the evidence is thin or tied."""
    words = [w.lower() for w in WORD.findall(ORDINAL.sub(" ", text))]
    if script_name == "Latin" and len(words) < MIN_WORDS:
        return None, 0.0
    scores = {}
    for code in SHARED[script_name]:
        hits = sum(w in WORDS.get(code, ()) for w in words)
        scores[code] = hits + 2 * min(3, sum(text.count(letter) for letter in OWN.get(code, "")))
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top < 2 or top == second:
        return None, 0.0
    return best, round(min(1.0, top / max(1, len(words))), 3)


def detect(text: str) -> Language:
    name, share = script(text)
    if name is None:
        return Language(None, None, 0.0)
    if name == "Han":
        return Language("zh", name, share)
    if name == "Kana":
        return Language("ja", name, share)
    if name in ONE_LANGUAGE:
        return Language(ONE_LANGUAGE[name], name, share)
    if name not in SHARED:
        return Language(None, name, 0.0)
    code, sure = _shared(name, text)
    return Language(bcp47(code) if code else None, name, round(share * sure, 3) if code else 0.0)


def _sure(text: str) -> str | None:
    """The language of a text long enough for its words to tell it from its script's other languages."""
    found = detect(text)
    if found.script in SHARED and len(WORD.findall(text)) < SURE_WORDS:
        return None
    return found.code


def route(answer: str, sources: list[str], question: str | None = None, hint: str | None = None) -> Route:
    """Which check reads these texts. The answer's language decides; a short answer is told together with the
    question, then with all the texts, then from `hint` (the language a media reader found in the file), and last
    guessed from the script (GUESS). Sources too short to tell on their own are left out of the decision."""
    found = [detect(s).code for s in sources]
    language = _sure(answer) or (_sure(f"{question}\n{answer}") if question else None)
    everything = "\n".join([question or "", answer, *sources])
    if language is None:
        language = detect(everything).code or (hint.replace("_", "-").split("-")[0].lower() if hint else None)
    guessed = language is None
    if guessed:
        language = GUESS.get(script(everything)[0])
    if language is None:
        return Route(None, None, found, "unknown_language")
    every = {language, *(code for code in found if code)}
    if every <= {ENGLISH}:
        return Route("english", language, found, guessed=guessed)
    if every <= set(CHECKED):
        return Route("multilingual", language, found, guessed=guessed)
    return Route(None, language, found, "language", guessed)
