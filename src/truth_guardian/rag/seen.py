"""What can be checked in an answer about an image (D-199).

An answer resting on the image model's description cannot be checked against that description: a model agreeing with
itself proves nothing (D-125, rag/media.py). What it says about the image's words can be checked, though, against what a
different reader read: Tesseract, the OCR reader, which only reads letters and has no opinion of the picture. So:

- a sentence that quotes words it says the image shows ("CHOPPER", «قله زردکوه») is "supported" when every quoted piece
  is close to something Tesseract read, and "contradicted" when Tesseract read words in the image but none close to a
  quoted piece: the model has read, or made up, words that are not there;
- when Tesseract read nothing at all, such a sentence is "unverifiable" (no text was read to compare with), as is every
  sentence about what the image shows rather than says (colours, shapes, people): only the model sees those.

When Tesseract read nothing (stylised letters, a logo) and a second online model looked at the image too (rag/second.py,
D-200), the quoted words are compared with what that model read instead: "agreed" when it read them too, "disputed" when
it read something else. Two models agreeing is weaker than a reader confirming, and is labelled apart.

The verdict is "hallucinated" when a sentence is contradicted by the reader, "disputed" when the two models read the
words differently, "grounded" when the quoted text is found or agreed, else "unverifiable"; with the share of sentences
that could be checked at all. It says what was checked, never more.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, Field

from truth_guardian.text import split_sentences

CLOSE = 0.75  # how alike a quoted piece and a stretch of the reading must be, after both are normalised
MIN_QUOTE = 2  # characters: shorter quoted pieces ("a", "") say nothing to check
# Quoted pieces: straight and curly double quotes, guillemets, and single quotes around two or more letters.
_QUOTED = re.compile(r'"([^"\n]{2,120})"|“([^”\n]{2,120})”|«([^»\n]{2,120})»|‘([^’\n]{2,120})’|(?<!\w)\'([^\'\n]{2,120})\'(?!\w)')
_MARK = re.compile(r"\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\]")
# Letters Persian and Arabic type differently, the joiner and the tatweel, all set to one form.
_SAME = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "‌": "", "ـ": ""})


class SeenClaim(BaseModel):
    start: int
    end: int
    text: str
    status: Literal["supported", "contradicted", "agreed", "disputed", "unverifiable"]
    reason: Literal["found", "not_read", "no_text", "visual", "second_read", "second_differs"]
    quoted: list[str] = Field(default_factory=list)


class SeenCheck(BaseModel):
    claims: list[SeenClaim] = Field(default_factory=list)
    verdict: Literal["grounded", "hallucinated", "disputed", "unverifiable"] = "unverifiable"
    checked_share: float = 0.0
    read: str = Field(default="", description="What Tesseract read in the image, cut short")


def flat(text: str) -> str:
    """Letters and digits only, in one form: case, accents, Persian and Arabic letter variants and spacing set aside."""
    text = unicodedata.normalize("NFKC", text).lower().translate(_SAME)
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if ch.isalnum())


def found_in(piece: str, reading: str) -> bool:
    """Whether a quoted piece is in the reading, letter for letter or nearly (OCR misreads a letter here and there)."""
    want, have = flat(piece), flat(reading)
    if len(want) < MIN_QUOTE or not have:
        return False
    if want in have:
        return True
    width = len(want)
    best = max((SequenceMatcher(None, want, have[i:i + width]).ratio() for i in range(0, max(1, len(have) - width + 1))), default=0.0)
    return best >= CLOSE


def check_seen(answer: str, reading: str, second_read: str = "") -> SeenCheck:
    """Each sentence of an answer about an image, against what the OCR reader read in it (empty: it read nothing), and
    when it read nothing, against what a second model read in it (second_read)."""
    claims = []
    for sentence in split_sentences(answer):
        text = _MARK.sub("", sentence.text).strip()
        if not re.search(r"\w", text):
            continue
        quoted = [next(g for g in m.groups() if g) for m in _QUOTED.finditer(text)]
        quoted = [q.strip() for q in quoted if len(flat(q)) >= MIN_QUOTE]
        if not quoted:
            status, reason = "unverifiable", "visual"
        elif not flat(reading) and flat(second_read):
            status, reason = ("agreed", "second_read") if all(found_in(q, second_read) for q in quoted) else ("disputed", "second_differs")
        elif not flat(reading):
            status, reason = "unverifiable", "no_text"
        elif all(found_in(q, reading) for q in quoted):
            status, reason = "supported", "found"
        else:
            status, reason = "contradicted", "not_read"
        claims.append(SeenClaim(start=sentence.start, end=sentence.end, text=text, status=status, reason=reason, quoted=quoted))
    checked = [c for c in claims if c.status != "unverifiable"]
    verdict = ("hallucinated" if any(c.status == "contradicted" for c in claims) else "disputed" if any(c.status == "disputed" for c in claims)
               else "grounded" if checked else "unverifiable")
    return SeenCheck(claims=claims, verdict=verdict, checked_share=round(len(checked) / len(claims), 3) if claims else 0.0, read=" ".join(reading.split())[:600])
