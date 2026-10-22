from truth_guardian.card import build_card, grade
from truth_guardian.heal import Change, apply, corrections
from truth_guardian.report import ClaimReport, Evidence, Fix, Report


def claim(start, end, text, status="supported", fixes=(), evidence=None, cautions=()):
    return ClaimReport(start=start, end=end, text=text, status=status, risk=0.9 if status != "supported" else 0.1,
                       explanation="", action="keep", fixes=list(fixes), evidence=evidence, cautions=list(cautions))


def report(claims, risk=0.6):
    return Report(id="x", verdict="hallucinated", risk=risk, response_threshold=0.4, sentence_threshold=0.3, claims=claims)


def test_grades_follow_risk_bands():
    assert [grade(r) for r in (0.05, 0.2, 0.3, 0.5, 0.9)] == ["A", "B", "C", "D", "F"]


def test_card_counts_supported_claims_and_overclaims():
    card = build_card(report([claim(0, 5, "a"), claim(6, 10, "b", "unsupported", cautions=["overclaim: x"])]))
    dims = {d.name: d.score for d in card.dimensions}
    assert card.grade == "D" and dims["claims supported"] == 0.5 and dims["certainty"] == 0.5 and dims["citations"] is None


def test_corrections_replace_values_swap_in_evidence_and_remove_unsupported():
    text = "Frank died in 2022. Brazil beat Germany. It has 300 stores."
    claims = [
        claim(0, 19, "Frank died in 2022.", "contradicted", fixes=[Fix(start=14, end=18, original="2022", replacement="1945", confidence=0.9)]),
        claim(20, 40, "Brazil beat Germany.", "contradicted", evidence=Evidence(text="Germany beat Brazil.")),
        claim(41, 60, "It has 300 stores.", "unsupported"),
    ]
    changes = corrections(report(claims))
    assert [c.new for c in changes] == ["1945", "Germany beat Brazil.", ""]
    assert apply(text, changes) == "Frank died in 1945. Germany beat Brazil."


def test_contested_claims_are_kept_and_empty_list_items_dropped():
    assert corrections(report([claim(0, 5, "a", "contested")])) == []
    assert apply("Steps:\n1. Mix.\n2. Bake.", [Change(15, 23, "2. Bake.", "", "removed")]) == "Steps:\n1. Mix."


def test_paragraph_breaks_survive():
    assert apply("Intro.\n\nFact one. Fact two.", [Change(18, 27, "Fact two.", "", "removed")]) == "Intro.\n\nFact one."
