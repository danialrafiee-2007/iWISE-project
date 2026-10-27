"""Video through the other readers: PyAV (which carries FFmpeg's libraries) hands the soundtrack to speech.py and a few
timed frames to ocr.py, and optionally to vision.py. No video model was downloaded, so a video is only as well read as
its sound and the frames sampled: an event missing from those frames is not shown to be missing from the video, and
every reading says so.
"""

import time
from pathlib import Path

from truth_guardian.media import ocr, speech, vision
from truth_guardian.media.contract import Place, Reading

FRAMES = 6
MIN_GAP = 4.0  # seconds between sampled frames at least


def frames(path: str | Path, count: int = FRAMES) -> list[tuple[float, "object"]]:
    """(time in seconds, PIL image) for up to `count` frames spread evenly over the video, at least MIN_GAP apart."""
    import av

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return []
        duration = float(container.duration / av.time_base) if container.duration else float(stream.duration * stream.time_base) if stream.duration else 0.0
        count = max(1, min(count, int(duration // MIN_GAP) + 1)) if duration else 1
        times = [duration * (i + 0.5) / count for i in range(count)] if duration else [0.0]
        found = []
        for at in times:
            container.seek(int(at / stream.time_base), stream=stream, any_frame=False, backward=True)
            for frame in container.decode(stream):
                if frame.time is None or frame.time >= at - 0.05:
                    found.append((round(float(frame.time or at), 2), frame.to_image()))
                    break
        return found


def has_sound(path: str | Path) -> bool:
    import av

    with av.open(str(path)) as container:
        return any(s.type == "audio" for s in container.streams)


def read_video(path: str | Path, languages: list[str] | None = None, describe: bool = False) -> Reading:
    """The soundtrack's transcript and the text on sampled frames, each segment with its time; with `describe`, also what
    each frame shows (slower: the image model runs once per frame)."""
    started = time.perf_counter()
    reading = Reading(kind="video", reader=f"PyAV frames and sound; {ocr.reader_name()}; {speech.reader_name()}")
    reading.notes.append(f"only {FRAMES} frames at most are read; something absent from them may still be in the video")
    if has_sound(path):
        heard = speech.transcribe(Path(path), language=None)
        reading.segments += heard.segments
        reading.language, reading.language_confidence = heard.language, heard.language_confidence
        for reason in heard.reasons:
            reading.review(f"sound: {reason}")
        reading.notes += [f"sound: {n}" for n in heard.notes]
    else:
        reading.notes.append("the video has no soundtrack")
    for at, image in frames(path):
        seen = ocr.read_text(image, languages)
        for segment in seen.segments:
            segment.place = Place(box=segment.place.box, start=at, end=at)
            reading.segments.append(segment)
        if describe:
            shown = vision.describe(image)
            for segment in shown.segments:
                segment.place = Place(box=segment.place.box, start=at, end=at)
                reading.segments.append(segment)
            reading.review("frame descriptions are the image model's opinion, not proof on their own")
    if not reading.segments:
        reading.review("nothing was heard or read in the video")
    scored = [s.confidence for s in reading.segments if s.confidence is not None]
    reading.quality = round(sum(scored) / len(scored), 3) if scored else None
    reading.seconds = round(time.perf_counter() - started, 2)
    return reading
