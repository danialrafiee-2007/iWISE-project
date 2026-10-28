"""What a media file gives the claim check as evidence (D-135).

Only the words read in the file count: the lines of text found in an image or a frame and the segments of what was
said. The image model's descriptions stay out, since they are its opinion of the picture, not a reading of it (D-125),
and a check must not rest on a model agreeing with itself. Each piece goes on a line of its own: the check splits its
sources at line breaks before it splits sentences, so every source sentence it quotes as evidence falls inside one
line, and `lines` names the segment, and so the place in the file (a box, a time range), that line came from.

The checks read English, Arabic, Chinese, French, Russian and Spanish (language.py, D-137). A file read in another
language is marked as not checkable rather than checked as if it were one of these; one whose language could not be told
may still be checked at the person's request, which the page then says.
"""

import hashlib

from pydantic import BaseModel, Field

from truth_guardian.language import CHECKED
from truth_guardian.media.contract import Reading

EVIDENCE_ROLES = ("ocr", "transcript")
# The image model's answer is always flagged as an opinion; that reason says nothing about how well the words were read.
OPINION = "opinion"


class MediaEvidence(BaseModel):
    parts: list[str] = Field(description="The words read, one segment per line, split at line breaks into sources the check accepts")
    lines: list[int] = Field(description="For each line of the parts in order, the index of its segment in the reading")
    language: str | None
    checkable: bool
    why_not: str | None = Field(default=None, description="'empty', 'language' or 'unknown_language' when not checkable")
    concerns: list[str] = Field(default=[], description="The reading's own reasons for review about the words read")
    sha256: str
    reader: str


def evidence(reading: Reading, raw: bytes, max_chars: int, max_parts: int) -> MediaEvidence:
    lines: list[str] = []
    index: list[int] = []
    for i, segment in enumerate(reading.segments):
        text = " ".join(segment.text.split())
        if segment.role in EVIDENCE_ROLES and text:
            lines.append(text[:max_chars])
            index.append(i)
    parts: list[str] = []
    for line in lines:
        if parts and len(parts[-1]) + 1 + len(line) <= max_chars:
            parts[-1] += "\n" + line
        elif len(parts) < max_parts:
            parts.append(line)
        else:  # past what the check takes: the rest of the file is not evidence, and the lines say so by stopping
            index = index[: sum(p.count("\n") + 1 for p in parts)]
            break
    language = reading.language
    why_not = "empty" if not parts else "unknown_language" if language is None else None if language.split("-")[0] in CHECKED else "language"
    return MediaEvidence(
        parts=parts,
        lines=index,
        language=language,
        checkable=why_not is None,
        why_not=why_not,
        concerns=[r for r in reading.reasons if OPINION not in r],
        sha256=hashlib.sha256(raw).hexdigest(),
        reader=reading.reader,
    )
