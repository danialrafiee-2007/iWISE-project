"""What every media reader returns: text segments, each with where it came from and how sure the reader is.

A reading is never treated as the truth about the file: a transcript or an OCR line is the reader's reading of it, and an
image description is a model's opinion. `needs_review` is set, with its reasons, whenever the language is unknown or
uncertain, nothing was found, or the reader's own confidence is low; nothing falls back to English silently.
"""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["audio", "image"]
Role = Literal["transcript", "ocr", "description"]

# Below these a reading goes to review.
LOW_LANGUAGE = 0.5
LOW_TEXT = 0.6


class Place(BaseModel):
    """Where a segment is in the file: a box in the original image's pixels, a time range in seconds, or both (a frame)."""

    box: tuple[int, int, int, int] | None = Field(default=None, description="x, y, width, height in the original image")
    start: float | None = None
    end: float | None = None


class Segment(BaseModel):
    text: str
    role: Role
    language: str | None = Field(default=None, description="BCP 47 code when known (fa, ja, am, zh-Hans); None when not")
    language_confidence: float | None = None
    script: str | None = Field(default=None, description="Writing system, as Tesseract names it (Arabic, Japanese, Latin)")
    confidence: float | None = Field(default=None, description="The reader's own confidence in the text, 0 to 1")
    place: Place = Field(default_factory=Place)


class Alternative(BaseModel):
    language: str
    confidence: float


class Reading(BaseModel):
    kind: Kind
    reader: str = Field(description="Reader and model with their versions")
    segments: list[Segment] = []
    language: str | None = None
    language_confidence: float | None = None
    alternatives: list[Alternative] = []
    quality: float | None = Field(default=None, description="Mean confidence of the text read, 0 to 1")
    seconds: float = 0.0
    needs_review: bool = False
    reasons: list[str] = Field(default=[], description="Why the reading needs review")
    notes: list[str] = Field(default=[], description="What else is worth knowing, such as a change of language")

    def review(self, reason: str) -> None:
        self.needs_review = True
        if reason not in self.reasons:
            self.reasons.append(reason)

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.segments if s.text)


# Tesseract's ISO 639-2/3 names to BCP 47, for the languages the interface speaks and the ones the handover names.
BCP47 = {
    "eng": "en", "fas": "fa", "ara": "ar", "urd": "ur", "pus": "ps", "jpn": "ja", "jpn_vert": "ja", "kor": "ko", "kor_vert": "ko",
    "chi_sim": "zh-Hans", "chi_sim_vert": "zh-Hans", "chi_tra": "zh-Hant", "chi_tra_vert": "zh-Hant", "rus": "ru", "ukr": "uk",
    "bul": "bg", "fra": "fr", "spa": "es", "deu": "de", "ita": "it", "por": "pt", "tur": "tr", "hin": "hi", "mar": "mr",
    "nep": "ne", "ben": "bn", "ell": "el", "heb": "he", "tha": "th", "amh": "am", "tir": "ti", "swa": "sw", "yor": "yo",
    "afr": "af", "hye": "hy", "kat": "ka", "tam": "ta", "tel": "te", "kan": "kn", "mal": "ml", "guj": "gu", "pan": "pa",
    "ori": "or", "khm": "km", "lao": "lo", "mya": "my", "bod": "bo", "sin": "si",
}


def bcp47(code: str) -> str:
    return BCP47.get(code, code)
