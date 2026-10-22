from truth_guardian.claims import localize, split_claims
from truth_guardian.text import Sentence


def sentence(text: str, start: int = 0) -> Sentence:
    return Sentence(start, start + len(text), text)


def texts(s: Sentence) -> list[tuple[str, str]]:
    return [(c.text, c.verify_text) for c in split_claims(s)]


def test_coordinated_predicates_share_the_subject_for_verification():
    assert texts(sentence("Anne Frank died in 1945 and was buried in Bergen-Belsen.")) == [
        ("Anne Frank died in 1945", "Anne Frank died in 1945"),
        ("was buried in Bergen-Belsen", "Anne Frank was buried in Bergen-Belsen"),
    ]


def test_relative_clause_becomes_its_own_claim():
    result = dict(texts(sentence("The cafe, which opened in 1990, serves Italian food.")))
    assert result["which opened in 1990"] == "The cafe opened in 1990"
    assert "The cafe serves Italian food" in result


def test_simple_sentence_stays_whole_and_offsets_are_absolute():
    s = sentence("It is open every day.", start=40)
    (claim,) = split_claims(s)
    assert claim.spans == [(40, 61)] and claim.text == s.text


def test_noun_lists_are_not_split():
    assert len(split_claims(sentence("They serve pizza, pasta and salads."))) == 1


def test_localize_keeps_only_the_wrong_claim():
    s = sentence("Anne Frank died in 1945 and was buried in Paris.")
    consistency = lambda pairs: [0.9 if "1945" in h else 0.1 for _, h in pairs]
    spans = localize(s, {}, lambda claim: "evidence", consistency)
    assert [s.text[a:b] for a, b in spans] == ["was buried in Paris"]


def test_localize_prefers_symbolic_spans_and_falls_back_to_whole_sentence():
    s = sentence("Anne Frank died in 2022 and was buried in Bergen-Belsen.")
    row = {"sym_spans": [[19, 23]]}
    never = lambda pairs: (_ for _ in ()).throw(AssertionError("HHEM should not be needed"))
    assert [s.text[a:b] for a, b in localize(s, row, lambda c: "", never)] == ["Anne Frank died in 2022"]
    everything_bad = lambda pairs: [0.1] * len(pairs)
    assert localize(s, {}, lambda c: "", everything_bad) == [(0, len(s.text))]
