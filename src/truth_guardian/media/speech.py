"""Speech to text with Whisper Small (faster-whisper on CTranslate2, int8 on the CPU), from local files only.

The language is not assumed: with no hint, Whisper detects it for the whole file and again for every segment long enough
to judge (LANGUAGE_SECONDS), so a recording that switches language is reported as such. Silence is cut by the voice
activity filter shipped with faster-whisper, so it is not turned into invented words. A segment Whisper itself doubts
(a likely non-speech segment, a low average log-probability) or a language below LOW_LANGUAGE sends the reading to review.
"""

import math
import threading
import time
from pathlib import Path
from typing import BinaryIO

from truth_guardian.media import models_dir
from truth_guardian.media.contract import LOW_LANGUAGE, LOW_TEXT, Place, Reading, Segment

MODEL = "whisper-small-ct2"
SAMPLE_RATE = 16_000
LANGUAGE_SECONDS = 2.0
NO_SPEECH = 0.6
THREADS = 4

_model = None
_lock = threading.Lock()


def model():
    """The Whisper model, loaded once (about 0.5 GB); unload() frees it."""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(str(models_dir() / MODEL), device="cpu", compute_type="int8", cpu_threads=THREADS, num_workers=1, local_files_only=True)
        return _model


def unload() -> None:
    global _model
    with _lock:
        _model = None


def files_present() -> bool:
    return (models_dir() / MODEL / "model.bin").is_file()


def reader_name() -> str:
    import faster_whisper

    return f"faster-whisper {faster_whisper.__version__}, Whisper Small (CTranslate2 int8)"


def decode(source: str | Path | BinaryIO):
    """The first sound track of a file (any format FFmpeg reads) as 16 kHz mono float32 samples. This is
    faster-whisper's decode_audio, done here because 1.2.1 passes PyAV a `metadata_errors` option that PyAV 19 removed."""
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    with av.open(str(source) if isinstance(source, Path) else source, mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        for frame in container.decode(stream):
            chunks += [out.to_ndarray() for out in resampler.resample(frame)]
        chunks += [out.to_ndarray() for out in resampler.resample(None)]
    samples = np.concatenate(chunks, axis=1).reshape(-1) if chunks else np.zeros(0, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def transcribe(source: str | Path | BinaryIO, language: str | None = None) -> Reading:
    """Transcribes a sound file (any format FFmpeg reads, through PyAV). `language` (a Whisper code such as "fa") skips
    detection when the person already knows it."""
    started = time.perf_counter()
    audio = decode(source)
    whisper = model()
    pieces, info = whisper.transcribe(
        audio, language=language, task="transcribe", beam_size=5, vad_filter=True, word_timestamps=True, multilingual=language is None,
    )
    reading = Reading(kind="audio", reader=reader_name(), language=info.language, language_confidence=round(info.language_probability, 3))
    confidences = []
    for piece in pieces:
        text = piece.text.strip()
        if not text:
            continue
        lang, lang_p = info.language, info.language_probability
        if language is None and piece.end - piece.start >= LANGUAGE_SECONDS:
            clip = audio[int(piece.start * SAMPLE_RATE) : int(piece.end * SAMPLE_RATE)]
            lang, lang_p, _ = whisper.detect_language(clip)
        # The mean word probability is Whisper's own sense of how sure it is of the words; the log-probability fallback
        # covers segments without word times.
        words = piece.words or []
        confidence = sum(w.probability for w in words) / len(words) if words else math.exp(piece.avg_logprob)
        confidences.append(confidence)
        reading.segments.append(
            Segment(text=text, role="transcript", language=lang, language_confidence=round(lang_p, 3), confidence=round(confidence, 3), place=Place(start=round(piece.start, 2), end=round(piece.end, 2)))
        )
        if piece.no_speech_prob > NO_SPEECH:
            reading.review(f"{piece.start:.1f}-{piece.end:.1f} s may not be speech")
        if language is None and lang_p < LOW_LANGUAGE:
            reading.review(f"the language at {piece.start:.1f} s is uncertain ({lang} {lang_p:.2f})")
    if not reading.segments:
        reading.review("no speech was found")
    if language is None and info.language_probability < LOW_LANGUAGE:
        reading.review(f"the language is uncertain ({info.language} {info.language_probability:.2f})")
    spoken = {s.language for s in reading.segments if s.language}
    if len(spoken) > 1:
        reading.notes.append(f"the recording switches language: {', '.join(sorted(spoken))}")
    if confidences:
        reading.quality = round(sum(confidences) / len(confidences), 3)
        if reading.quality < LOW_TEXT:
            reading.review(f"the transcript is uncertain (mean word confidence {reading.quality:.2f})")
    reading.seconds = round(time.perf_counter() - started, 2)
    return reading
