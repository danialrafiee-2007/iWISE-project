"""A second online opinion on an image or a recording, and the Guardian judging between the two (rag/second.py, D-200).
No test reaches the internet: the services are stood in for."""

import json

from truth_guardian.rag import second
from truth_guardian.rag.seen import check_seen
from truth_guardian.report import ClaimReport, Report
from truth_guardian.web.engine import NotChecked


class Engine:
    def __init__(self, statuses=None, refuse=None):
        self.statuses, self.refuse = statuses or [], refuse

    def analyze(self, sample, cancelled=None):
        if self.refuse:
            raise NotChecked(self.refuse, "language")
        claims = [ClaimReport(start=0, end=1, text=text, status=status, risk=0.5, explanation="x", action="keep") for text, status in self.statuses]
        return Report(id=sample.id, verdict="grounded", risk=0.1, response_threshold=0.4, sentence_threshold=0.3, claims=claims)


class Route:
    answer = "fa"


def test_the_second_model_reads_and_answers_and_its_words_are_split_off(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_SECOND_OPINION", "1")
    (tmp_path / "free.local.env").write_text("GROQ_API_KEY=gsk_test\n", encoding="utf-8")
    asked = {}

    def fetch(url, data=None, headers=None, timeout=None):
        asked.update(url=url, model=data["model"], image=data["messages"][1]["content"][1]["image_url"]["url"][:22])
        return 200, json.dumps({"choices": [{"message": {"content": "It is a logo of a helicopter company.\nTEXT IN IMAGE: CHOPPER هلیکوپتری دنا"}}]})

    found = second.look("What is this?", b"\x89PNG\r\n\x1a\nrest", root=tmp_path, fetch=fetch)
    assert found == ("groq/qwen/qwen3.8-27b", "It is a logo of a helicopter company.", "CHOPPER هلیکوپتری دنا")
    assert asked["image"] == "data:image/png;base64," and "groq.com" in asked["url"]


def test_without_a_key_or_with_the_switch_off_nothing_is_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_SECOND_OPINION", "1")
    assert second.look("?", b"x", root=tmp_path, fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent"))) is None
    assert second.hear("a.wav", b"x", root=tmp_path) is None
    monkeypatch.setenv("TG_SECOND_OPINION", "0")
    (tmp_path / "free.local.env").write_text("GROQ_API_KEY=gsk_test\n", encoding="utf-8")
    assert second.hear("a.wav", b"x", root=tmp_path) is None


def test_the_second_listeners_transcript_comes_back(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_SECOND_OPINION", "1")
    (tmp_path / "free.local.env").write_text("GROQ_API_KEY=gsk_test\n", encoding="utf-8")
    sent = []
    heard = second.hear("talk.wav", b"RIFFsound", root=tmp_path, send=lambda request: sent.append(request) or json.dumps({"text": " The museum opened in 1950. "}))
    assert heard == ("groq/whisper-large-v3", "The museum opened in 1950.") and b"whisper-large-v3" in sent[0].data


def test_each_sentence_is_agreed_or_disputed_by_the_second_opinion():
    engine = Engine([("It opened in 1950.", "supported"), ("It holds 9,000 books.", "contradicted")])
    found = second.opinion("recording", "groq/whisper-large-v3", "It opened in 1950 and holds 12,000 books.", "It opened in 1950. It holds 9,000 books.", "?", engine)
    assert [c.status for c in found.claims] == ["agreed", "disputed"] and found.verdict == "disputed"


def test_in_a_language_the_engine_does_not_read_numbers_found_in_both_agree():
    found = second.opinion("image", "m", "قله زردکوه ۴۵۴۸ متر است", "ارتفاع ۴۵۴۸ متر است. رنگ آن آبی است.", "?", Engine(refuse=Route()))
    assert [c.status for c in found.claims] == ["agreed", "unclear"] and found.verdict == "agreed"


def test_when_the_reader_read_nothing_the_two_models_readings_are_compared():
    answer = 'The word "CHOPPER" is on it. The text reads "هایکویتری دا".'
    seen = check_seen(answer, "", "CHOPPER هلیکوپتری دنا قله زردکوه")
    assert [c.status for c in seen.claims] == ["agreed", "disputed"] and seen.verdict == "disputed"
