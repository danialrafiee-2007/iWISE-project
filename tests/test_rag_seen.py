"""What an answer about an image says the image reads, checked against the OCR reader (rag/seen.py, D-199)."""

from truth_guardian.rag.seen import check_seen, flat, found_in

ANSWER = 'The image shows a logo. The word "CHOPPER" is on the right. The text reads «قله زردکوه» below. The background is white.'


def test_quoted_words_found_in_the_reading_are_supported_and_the_rest_cannot_be_checked():
    seen = check_seen(ANSWER, "CHOPPER\nقله زرد كوه")  # Arabic kaf and a space where the answer has none
    assert [c.status for c in seen.claims] == ["unverifiable", "supported", "supported", "unverifiable"]
    assert seen.verdict == "grounded" and seen.checked_share == 0.5


def test_words_the_reader_did_not_read_contradict_and_nothing_read_leaves_them_unverifiable():
    assert check_seen('It reads "DRAGON".', "CHOPPER").verdict == "hallucinated"
    nothing = check_seen('It reads "DRAGON".', "")
    assert nothing.verdict == "unverifiable" and nothing.claims[0].reason == "no_text"


def test_a_letter_misread_by_the_reader_still_matches():
    assert found_in("CHOPPER", "CH0PPER") and not found_in("DRAGON", "CHOPPER")
    assert flat("Hélló, Wörld!") == "hellowor ld".replace(" ", "")
