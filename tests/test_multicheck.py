import numpy as np

from truth_guardian import multicheck
from truth_guardian.pipeline import make_sample
from truth_guardian.text import split_sentences


def test_chinese_sentences_are_split_at_their_full_stops_and_english_lines_as_before():
    text = "他死于1945年。她出生于1929年！真的吗？\nThe museum opened in 1950. It is old."
    assert [s.text for s in split_sentences(text)] == ["他死于1945年。", "她出生于1929年！", "真的吗？", "The museum opened in 1950.", "It is old."]
    assert all(text[s.start : s.end] == s.text for s in split_sentences(text))


def test_a_citation_is_not_a_number_of_the_claim():
    assert multicheck.numbers("El museo se abrió en 1950 [1].") == [{"1950"}]
    assert multicheck.numbers("Abierto en 1950 [1, 2] y cerrado en 1960 [۳].") == [{"1950"}, {"1960"}]
    text = "El museo se abrió en 1950 [1]."
    (start, end, forms), = multicheck.number_spans(text)
    assert text[start:end] == "1950" and forms == {"1950"}


def test_numbers_are_read_alike_in_every_script_and_separator():
    forms = lambda text: [sorted(f) for f in multicheck.numbers(text)]
    assert forms("توفيت في عام ١٩٤٥") == [["1945"]]
    assert forms("murió en 1.945 o en 3,5 días") == [["1.945", "1945"], ["3.5", "35"]]
    assert forms("68 511 детей в 1945 3 раза") == [["68511"], ["1945"], ["3"]]
    assert forms("一千九百四十五年，一九四五年，3万人") == [["30000"], ["1945"], ["1945"]]
    assert forms("1. first item") == []


def test_content_words_drop_stop_words_and_read_chinese_as_character_pairs():
    assert multicheck.content_words("El museo se abrió en 1950") == {"museo", "abrió"}
    assert multicheck.content_words("博物馆开放") == {"博物", "物馆", "馆开", "开放"}
    assert multicheck.content_words("افتتح المتحف") == multicheck.content_words("افتتح متحف")


def test_long_lines_become_evidence_units_of_bounded_length():
    line = " ".join(f"word{i}" for i in range(95))
    assert [len(u.split()) for u in multicheck.units(line)] == [40, 40, 15]


def test_the_signal_reads_premises_numbers_and_scripts_per_sentence(monkeypatch):
    seen = []
    monkeypatch.setattr(multicheck, "_embed", lambda texts, kind: np.eye(len(texts), 4) if kind == "query" else np.eye(len(texts), 4))
    monkeypatch.setattr(multicheck, "nli", lambda pairs: seen.extend(pairs) or np.tile([0.7, 0.2, 0.1], (len(pairs), 1)))
    sample = make_sample("El museo abrió en 1944. 它很古老。", ["El museo abrió en 1945. Es el edificio más antiguo."])
    sentences = split_sentences(sample.answer)
    rows = multicheck.signal(sample, sentences)
    assert [r["m_numbers_unmatched"] for r in rows] == [1, 0]
    assert [r["m_lex_cross"] for r in rows] == [0, 1]
    assert rows[0]["m_nli_contradiction"] == 0.7 and len(seen) == 2
    assert seen[0] == ("El museo abrió en 1945. Es el edificio más antiguo.", "El museo abrió en 1944.")
