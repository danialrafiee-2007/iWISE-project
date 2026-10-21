from truth_guardian.explain import explain_sentence, refine_spans
from truth_guardian.schema import HallucinationType


def test_symbolic_mismatch_gives_word_level_spans():
    row = {"sym_numbers_unmatched": 1, "sym_spans": [[12, 16]], "nli_contradiction": 0.9}
    e = explain_sentence(row, 0, 20)
    assert e.type == HallucinationType.NUMERIC_ENTITY_MISMATCH and e.spans == [(12, 16)]


def test_null_attribute_is_unsupported():
    e = explain_sentence({"sym_null_mentions": 1, "sym_spans": [[3, 10]]}, 0, 20)
    assert e.type == HallucinationType.UNSUPPORTED and "unspecified" in e.reason


def test_contradiction_from_nli():
    row = {"nli_contradiction": 0.7, "nli_entailment": 0.1, "nli_neutral": 0.2, "dense_max": 0.8}
    assert explain_sentence(row, 5, 9).type == HallucinationType.CONTRADICTED


def test_weak_evidence_when_nothing_relevant():
    row = {"nli_contradiction": 0.1, "nli_entailment": 0.1, "nli_neutral": 0.8, "dense_max": 0.1}
    assert explain_sentence(row, 0, 4).type == HallucinationType.WEAK_EVIDENCE


def test_default_is_unsupported_whole_sentence():
    e = explain_sentence({"nli_neutral": 0.9, "dense_max": 0.7}, 0, 4)
    assert e.type == HallucinationType.UNSUPPORTED and e.spans == [(0, 4)]


def test_refine_spans_only_touches_flagged_sentences():
    rows = [{"sym_numbers_unmatched": 1, "sym_spans": [[2, 4]]}, {"dense_max": 0.9}, {"dense_max": 0.9}]
    spans = refine_spans([(0, 10), (11, 20)], rows, [0, 11, 21], [10, 20, 30])
    assert spans == [(2, 4), (11, 20)]
