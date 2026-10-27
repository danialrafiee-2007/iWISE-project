import base64
import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from truth_guardian.media import contract, multilingual, ocr, status
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
