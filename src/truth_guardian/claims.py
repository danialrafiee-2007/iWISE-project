"""Atomic claims: split a sentence into its separate statements with a dependency parse (no language model).

Coordinated predicates ("died in 1945 and was buried in Y") and relative clauses ("which opened in 1990")
each become a claim. A claim without its own subject borrows the main subject for verification, while its
highlight spans stay on the words the answer actually wrote. Inside a flagged sentence, each claim is checked
on its own, so a sentence that is half right gets only its wrong half highlighted.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import NamedTuple

from truth_guardian.text import Sentence

PREDICATE_DEPS = {"conj", "relcl"}
VERBAL = {"VERB", "AUX"}
SUBJECTS = {"nsubj", "nsubjpass", "expl", "csubj"}
RELATIVE_PRONOUNS = {"which", "who", "whom", "that", "whose"}
CLAIM_CONSISTENCY = 0.5


class Claim(NamedTuple):
    spans: list[tuple[int, int]]
    text: str
    verify_text: str


@lru_cache(maxsize=1)
def _parser():
    import spacy

    return spacy.load("en_core_web_sm", exclude=["ner", "lemmatizer"])


def _runs(tokens) -> list[tuple[int, int]]:
    """Contiguous character ranges covering the given tokens."""
    spans: list[tuple[int, int]] = []
    previous = None
    for t in tokens:
        start, end = t.idx, t.idx + len(t.text)
        if previous is not None and t.i == previous + 1:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
        previous = t.i
    return spans


def _join(tokens) -> str:
    """Token texts with original spacing, and a single space wherever removed tokens left a gap."""
    parts = []
    for t, following in zip(tokens, list(tokens[1:]) + [None]):
        parts.append(t.text + (t.whitespace_ if following is not None and following.i == t.i + 1 else " "))
    return " ".join("".join(parts).split())


def split_claims(sentence: Sentence) -> list[Claim]:
    whole = [Claim([(sentence.start, sentence.end)], sentence.text, sentence.text)]
    doc = _parser()(sentence.text)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None:
        return whole
    heads = [root] + [
        t for t in doc
        if t.dep_ in PREDICATE_DEPS and t.pos_ in VERBAL and (t.dep_ == "relcl" or t.head.pos_ in VERBAL)
    ]
    if len(heads) == 1:
        return whole
    subject = next((c for c in root.children if c.dep_ in SUBJECTS), None)
    subject_text = "".join(t.text_with_ws for t in subject.subtree).strip() if subject is not None else ""
    claims = []
    for head in heads:
        nested = {t.i for other in heads if other is not head and other in set(head.subtree) for t in other.subtree}
        tokens = [
            t for t in head.subtree
            if t.i not in nested and not (t.is_punct and (t.i - 1 in nested or t.i + 1 in nested))
        ]
        while tokens and (tokens[0].dep_ == "cc" or tokens[0].is_punct):
            tokens = tokens[1:]
        while tokens and (tokens[-1].dep_ == "cc" or tokens[-1].is_punct):
            tokens = tokens[:-1]
        if not tokens:
            continue
        text = _join(tokens)
        verify = text
        if head.dep_ == "conj" and subject_text and not any(c.dep_ in SUBJECTS for c in head.children):
            verify = f"{subject_text} {text}"
        elif head.dep_ == "relcl" and tokens[0].lower_ in RELATIVE_PRONOUNS:
            noun = "".join(t.text_with_ws for t in head.head.lefts if t.dep_ in {"det", "compound", "amod"}) + head.head.text
            verify = f"{noun} {_join(tokens[1:])}"
        spans = [(sentence.start + a, sentence.start + b) for a, b in _runs(tokens)]
        claims.append(Claim(spans, text, verify))
    return sorted(claims, key=lambda c: c.spans[0]) or whole


def _overlaps(spans: list[tuple[int, int]], others: list[tuple[int, int]]) -> bool:
    return any(a < d and c < b for a, b in spans for c, d in others)


def localize(
    sentence: Sentence,
    row: dict,
    premise_for: Callable[[str], str],
    consistency: Callable[[list[tuple[str, str]]], list[float]],
) -> list[tuple[int, int]]:
    """Spans to highlight in a flagged sentence: the claims carrying the error, or the whole sentence if none stands out.

    A claim is suspect when a symbolic or polarity span falls inside it, or when HHEM finds it inconsistent
    with the evidence retrieved for that claim alone.
    """
    claims = split_claims(sentence)
    if len(claims) == 1:
        return [(sentence.start, sentence.end)]
    flagged_words = [tuple(s) for s in row.get("sym_spans", []) + row.get("pol_spans", [])]
    suspects = [c for c in claims if flagged_words and _overlaps(c.spans, flagged_words)]
    if not suspects:
        scores = consistency([(premise_for(c.verify_text), c.verify_text) for c in claims])
        suspects = [c for c, s in zip(claims, scores) if s < CLAIM_CONSISTENCY]
    if not suspects or len(suspects) == len(claims):
        return [(sentence.start, sentence.end)]
    return [span for c in suspects for span in c.spans]
