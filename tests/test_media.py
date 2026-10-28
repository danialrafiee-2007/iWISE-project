import base64
import hashlib
import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from truth_guardian.media import contract, multilingual, ocr, status
from truth_guardian.media.evidence import evidence
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore

from test_web_api import FakeEngine

have = {row["name"]: row["files_present"] and row["runtime_ready"] for row in status.status()}
needs = lambda name: pytest.mark.skipif(not have.get(name), reason=f"the {name} reader is not installed here")


@pytest.fixture
def client():
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False)) as c:
        yield c


def english_page(text: str = "The meeting is in the room of the library at ten") -> Image.Image:
    image = Image.new("RGB", (1300, 160), "white")
    ImageDraw.Draw(image).text((30, 40), text, fill="black", font=ImageFont.truetype("arial.ttf", 54))
    return image


def test_review_reasons_are_kept_once_and_language_codes_map_to_bcp47():
    reading = contract.Reading(kind="image", reader="x")
    reading.review("no text was found")
    reading.review("no text was found")
    assert reading.needs_review and reading.reasons == ["no text was found"]
    assert [contract.bcp47(c) for c in ("fas", "jpn_vert", "chi_sim", "amh", "xyz")] == ["fa", "ja", "zh-Hans", "am", "xyz"]


@needs("ocr")
def test_ocr_tries_only_the_languages_of_the_script_with_the_persons_choice_first():
    assert ocr.candidates("Arabic", [], tall=False) == ["ara", "fas", "urd"]
    assert ocr.candidates("Arabic", ["fas"], tall=False)[0] == "fas"
    assert ocr.candidates("Japanese", [], tall=True) == ["jpn_vert", "jpn"]
    assert ocr.candidates("Ethiopic", [], tall=False) == ["amh", "tir"]
    assert ocr.candidates(None, [], tall=False) == ["eng"]
    assert len(ocr.candidates("Han", ["kor"], tall=True)) <= ocr.MAX_TRIES
    assert ocr.tesseract_codes(["fa", "ja", "zh-Hans", "amh"]) == ["fas", "jpn", "chi_sim", "amh"]


def test_latin_text_is_not_assumed_to_be_english():
    assert ocr.latin_language("Mji mkuu wa Kenya ni Nairobi na ni mji mkubwa wa Afrika")[0] == "swa"
    assert ocr.latin_language("The meeting is in the room of the library")[0] == "eng"
    assert ocr.latin_language("Nairobi Kenya")[0] is None


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_boxes_found_in_a_turned_image_map_back_to_the_original(angle):
    original = Image.new("L", (300, 200), 255)
    ImageDraw.Draw(original).rectangle((40, 30, 119, 69), fill=0)  # x 40, y 30, 80 x 40
    turned = np.array(original.rotate(angle, expand=True)) < 128
    ys, xs = np.nonzero(turned)
    found = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
    assert ocr.unrotate(found, angle, original.size) == (40, 30, 80, 40)


def test_a_long_premise_is_read_in_overlapping_windows():
    assert multilingual.windows(list(range(10))) == [list(range(10))]
    chunks = multilingual.windows(list(range(1000)))
    assert all(len(c) <= multilingual.WINDOW for c in chunks) and chunks[-1][-1] == 999
    assert all(a[-1] >= b[0] for a, b in zip(chunks, chunks[1:]))


def test_status_keeps_installed_run_and_evaluated_apart():
    rows = status.status()
    assert [r["name"] for r in rows] == ["speech", "ocr", "vision", "video", "retrieval", "nli"]
    for row in rows:
        assert {"files_present", "runtime_ready", "run_tested", "quality_evaluated"} <= row.keys()
        assert row["quality_evaluated"] is False  # no labelled evaluation yet


def test_media_endpoints_report_status_and_refuse_what_they_cannot_read(client):
    assert len(client.get("/api/media/status").json()["components"]) == 6
    data = base64.b64encode(b"hello").decode()
    assert client.post("/api/media/read", json={"name": "notes.txt", "data": data}).status_code == 422
    assert client.post("/api/media/read", json={"name": "a.png", "data": data, "languages": ["fa; rm -rf"]}).status_code == 422
    assert client.post("/api/media/read", json={"name": "a.png", "data": data, "languages": ["fa", "ja", "am", "en"]}).status_code == 422
    # The type can be overridden (a browser's sound recording comes as .webm), but only for a file type that is read.
    assert client.post("/api/media/read", json={"name": "notes.txt", "data": data, "kind": "audio"}).status_code == 422
    assert client.post("/api/media/read", json={"name": "a.png", "data": data, "question": "x" * 501}).status_code == 422


def test_evidence_keeps_the_words_read_one_per_line_with_their_segments():
    reading = contract.Reading(kind="image", reader="t", language="en", segments=[
        contract.Segment(text="The camp was  liberated\nin April 1945.", role="ocr", place=contract.Place(box=(1, 2, 3, 4))),
        contract.Segment(text="A red circle on white.", role="description"),
        contract.Segment(text="  ", role="ocr"),
        contract.Segment(text="Anne Frank died in 1945.", role="ocr", place=contract.Place(box=(5, 6, 7, 8))),
    ])
    reading.review("an image description is the model's opinion, not proof on its own")
    reading.review("the text is hard to read (mean confidence 0.45)")
    found = evidence(reading, b"x", max_chars=1000, max_parts=10)
    # The image model's description is not evidence, and a segment's own line breaks do not split it.
    assert found.parts == ["The camp was liberated in April 1945.\nAnne Frank died in 1945."]
    assert found.lines == [0, 3] and found.checkable and found.why_not is None
    assert found.concerns == ["the text is hard to read (mean confidence 0.45)"]
    assert found.sha256 == hashlib.sha256(b"x").hexdigest()


def test_evidence_in_a_language_no_check_reads_or_an_unknown_one_is_not_checked():
    said = contract.Segment(text="جلسه ساعت ده است", role="transcript")
    assert evidence(contract.Reading(kind="audio", reader="t", language="fa", segments=[said]), b"", 100, 10).why_not == "language"
    assert evidence(contract.Reading(kind="audio", reader="t", segments=[said]), b"", 100, 10).why_not == "unknown_language"
    assert evidence(contract.Reading(kind="audio", reader="t", language="en"), b"", 100, 10).why_not == "empty"
    written = contract.Segment(text="博物馆于1950年开放", role="ocr")
    assert evidence(contract.Reading(kind="image", reader="t", language="zh-Hans", segments=[written]), b"", 100, 10).checkable


def test_long_evidence_is_split_into_sources_the_check_accepts():
    segments = [contract.Segment(text=f"line {i} " + "x" * 40, role="transcript") for i in range(10)]
    found = evidence(contract.Reading(kind="audio", reader="t", language="en", segments=segments), b"", max_chars=100, max_parts=3)
    assert len(found.parts) == 3 and all(len(p) <= 100 for p in found.parts)
    assert len("\n".join(found.parts).split("\n")) == len(found.lines) == 6
    assert found.lines == list(range(6))


def test_the_script_of_the_letters_read_is_told_by_their_unicode_names():
    assert ocr.written_script("FIRST SLIDE ONE") == "Latin"
    assert ocr.written_script("שלום עולם") == "Hebrew"
    assert ocr.written_script("سلام دنیا") == "Arabic"
    assert ocr.written_script("カタカナとひらがな") == "Japanese"
    assert ocr.written_script("12 / 34") is None


@needs("ocr")
def test_capital_latin_on_a_frame_is_not_read_as_another_script():
    # Hebrew, Devanagari, Hangul, Arabic and Thai script models read these words as well as the Latin one does.
    image = Image.new("RGB", (960, 540), "white")
    ImageDraw.Draw(image).text((120, 230), "FIRST SLIDE ONE", fill="black", font=ImageFont.truetype("arial.ttf", 64))
    assert ocr.read_text(image).text == "FIRST SLIDE ONE"


@needs("video")
def test_frames_are_spread_over_a_video_whose_frame_times_are_broken(tmp_path):
    import av
    from truth_guardian.media import video

    path = tmp_path / "broken.webm"
    with av.open(str(path), "w", format="webm") as out:
        stream = out.add_stream("libvpx", rate=10)
        stream.width, stream.height, stream.pix_fmt = 320, 240, "yuv420p"
        for i in range(80):  # 8 s, growing lighter; no frame times given, as some recorders write them
            frame = av.VideoFrame.from_image(Image.new("RGB", (320, 240), (3 * i, 3 * i, 3 * i)))
            frame.pts = None
            out.mux(stream.encode(frame))
        out.mux(stream.encode())
    picked = video.frames(path)
    assert len(picked) == 3
    times = [at for at, _ in picked]
    shades = [np.asarray(image.convert("L")).mean() for _, image in picked]
    assert times == sorted(times) and times[-1] - times[0] > 4
    assert shades == sorted(shades) and shades[-1] - shades[0] > 60


@needs("ocr")
def test_ocr_reads_an_english_page_and_names_its_language():
    reading = ocr.read_text(english_page())
    assert "meeting" in reading.text.lower() and "library" in reading.text.lower()
    assert reading.language == "en" and reading.segments[0].script == "Latin"
    box = reading.segments[0].place.box
    assert box and box[0] >= 0 and box[0] + box[2] <= 1300


@needs("ocr")
def test_reading_an_image_through_the_api(client):
    buffer = io.BytesIO()
    english_page().save(buffer, format="PNG")
    response = client.post("/api/media/read", json={"name": "page.png", "data": base64.b64encode(buffer.getvalue()).decode()})
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "image" and "library" in " ".join(s["text"] for s in body["reading"]["segments"]).lower()
    # What the claim check gets from it: the words read, checkable since they are English.
    assert body["evidence"]["checkable"] and "library" in body["evidence"]["parts"][0].lower()


@needs("speech")
def test_silence_is_not_turned_into_words(tmp_path):
    from truth_guardian.media import speech

    path = tmp_path / "quiet.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes((np.random.default_rng(1).integers(-5, 6, 16_000 * 3)).astype("<i2").tobytes())
    reading = speech.transcribe(path)
    assert reading.segments == [] and reading.needs_review and "no speech was found" in reading.reasons


@needs("nli")
def test_multilingual_nli_reads_its_labels_by_name():
    judged = multilingual.judge("会議は午前十時に始まります。", "会議は正午に始まります。")
    assert judged["label"] == "contradiction"
    assert {"entailment", "neutral", "contradiction"} <= judged.keys()
