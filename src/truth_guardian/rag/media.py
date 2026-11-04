"""A recording or an image as passages for the library (D-165).

What was said goes in with the time it was said, and the words in an image as they were read. The image model's
description goes in as well, so a picture without words can still be found and asked about, but marked: it is the model's
opinion (D-125), so an answer is never checked against it (rag/answer.py), since a check must not rest on a model agreeing
with itself. A reading is the reader's reading, so its own doubts are kept with the document.

A person can read what was extracted before it goes in: correct it, remove parts of it, and say that a description is right.
What they leave is marked as reviewed, and a description they confirmed then counts as words like any other (D-167).
"""

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from truth_guardian.media.contract import LOW_TEXT, Reading, Segment
from truth_guardian.media.evidence import OPINION
from truth_guardian.rag.chunks import MAX_WEIGHT, OVERLAP, Passage, _join, _pieces, passages, weight

MEDIA_KINDS = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    # .webm is what the browser's recorder makes; it is read for its sound only.
    "audio": {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma", ".weba", ".webm"},
}


def kind_of(name: str) -> str | None:
    suffix = Path(name).suffix.lower()
    return next((kind for kind, suffixes in MEDIA_KINDS.items() if suffix in suffixes), None)


def read_file(name: str, data: bytes, languages: Sequence[str] = (), describe: bool = True) -> Reading:
    """languages: what the person says the file uses, tried first; otherwise the readers find out."""
    from truth_guardian.media import ocr, speech, vision

    with tempfile.TemporaryDirectory(prefix="tg-media-") as folder:
        path = Path(folder) / f"input{Path(name).suffix.lower()}"
        path.write_bytes(data)
        if kind_of(name) == "audio":
            return speech.transcribe(path, language=languages[0].replace("_", "-").split("-")[0].lower() if languages else None)
        reading = ocr.read_text(path, list(languages))
        if describe:
            seen = vision.describe(path)
            reading.segments += seen.segments
            reading.seconds = round(reading.seconds + seen.seconds, 2)
            for reason in seen.reasons:
                reading.review(reason)
        return reading


def clock(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{rest:02}" if hours else f"{minutes:02}:{rest:02}"


def _spoken(segments: list[Segment]) -> list[Passage]:
    """Passages like chunks.passages, whole segments up to MAX_WEIGHT with the last one repeated, that know their time."""
    out, current, used = [], [], 0

    def close() -> None:
        text = _join([piece for piece, _ in current])
        out.append(Passage(text, None, f"{clock(current[0][1].place.start or 0)}-{clock(current[-1][1].place.end or 0)}", "transcript"))

    for segment in segments:
        for piece in _pieces(" ".join(segment.text.split())):
            size = weight(piece)
            if current and used + size > MAX_WEIGHT:
                close()
                current = current[-OVERLAP:]
                used = sum(weight(p) for p, _ in current)
                if used + size > MAX_WEIGHT:
                    current, used = [], 0
            current.append((piece, segment))
            used += size
    if current:
        close()
    return out


def cut(reading: Reading) -> list[Passage]:
    by_role = lambda role: [s for s in reading.segments if s.role == role and s.text.strip()]
    in_role = lambda role: (p._replace(role=role) for p in passages("\n".join(s.text for s in by_role(role))))
    return [*_spoken(by_role("transcript")), *in_role("ocr"), *in_role("confirmed"), *in_role("description")]


def concerns(reading: Reading) -> list[str]:
    return [reason for reason in reading.reasons if OPINION not in reason]


class Kept(NamedTuple):
    """One part of a reading as a person left it; a part they do not send back is removed."""

    index: int
    text: str
    confirmed: bool = False


def reviewed(reading: Reading, kept: Sequence[Kept]) -> Reading:
    """Raises ValueError with a message meant for the person when the parts do not belong to this reading."""
    indexes = [item.index for item in kept]
    if len(set(indexes)) < len(indexes) or not all(0 <= i < len(reading.segments) for i in indexes):
        raise ValueError("the reviewed parts do not match what was read; read the file again")
    segments = []
    for item in sorted(kept, key=lambda item: item.index):
        segment = reading.segments[item.index]
        if item.text.strip():
            role = "confirmed" if segment.role == "description" and item.confirmed else segment.role
            segments.append(segment.model_copy(update={"text": item.text.strip(), "role": role}))
    return reading.model_copy(update={"segments": segments})


def shown(reading: Reading) -> list[dict]:
    """The parts of a reading for a person to review, with where each came from and whether the reader doubts it."""
    place = lambda s: f"{clock(s.place.start)}-{clock(s.place.end)}" if s.place.start is not None and s.place.end is not None else None
    return [
        {
            "index": i, "text": s.text, "role": s.role, "place": place(s), "box": s.place.box, "confidence": s.confidence,
            "doubtful": s.confidence is not None and s.confidence < LOW_TEXT, "opinion": s.role == "description",
        }
        for i, s in enumerate(reading.segments)
    ]
