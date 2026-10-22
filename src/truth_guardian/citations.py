"""Citation check: when an answer cites a passage ("(Passage 2)", "according to Source 1", "[3]"), does it support the claim?

Each citing sentence is scored with HHEM against the best-matching sentences of the cited documents and of every other
document. The citation is wrong when the cited documents do not support the claim but another document clearly does;
a claim no document supports is left to the main check, and citation-only lines ("Passage 3:") are skipped. Documents
are numbered in the order they were given.
`cite` goes the other way: it adds [n] markers to supported claims from their evidence document.
"""

import re
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.correct import _singular
from truth_guardian.retrieval import Bm25
from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, content_words, split_sentences

CITATION = re.compile(r"\b(?:passages?|sources?|documents?)\s*#?\s*(\d+(?:\s*(?:,|&|and|or)\s*(?:passages?\s*)?\d+)*)|\[(\d+(?:\s*,\s*\d+)*)\]", re.IGNORECASE)
SUPPORT = 0.5
MARGIN = 0.3
PREMISE_SENTENCES = 3
MIN_CLAIM_WORDS = 3


class CitationCheck(NamedTuple):
    cited: list[int]
    cited_support: float
    best_other: int | None
    other_support: float

    @property
    def wrong(self) -> bool:
        return self.cited_support < SUPPORT and self.other_support >= SUPPORT and self.other_support - self.cited_support >= MARGIN


def cited_documents(text: str, documents: int) -> list[int]:
    """1-based document numbers cited in a sentence, keeping only those that exist."""
    found = []
    for m in CITATION.finditer(text):
        found += [int(n) for n in re.findall(r"\d+", m.group(1) or m.group(2))]
    return sorted({n for n in found if 1 <= n <= documents})


def _premise(document: str, claim: str) -> str:
    sentences = [s.text for s in split_sentences(document)]
    if not sentences:
        return ""
    scores = Bm25([_singular(s) for s in sentences]).scores(_singular(claim))
    top = sorted(range(len(sentences)), key=lambda i: -scores[i])[:PREMISE_SENTENCES]
    return " ".join(sentences[i] for i in sorted(top))


def check_sample(sample: Sample, sentences: list[Sentence], consistency=models.hhem_consistency) -> list[CitationCheck | None]:
    """One check per sentence that cites at least one existing document, None for the others."""
    documents = [d.text for d in sample.documents]
    plans, pairs = [], []
    for s in sentences:
        cited = cited_documents(s.text, len(documents))
        if not cited:
            plans.append(None)
            continue
        claim = CITATION.sub("", s.text).strip(" ()[],.;:")
        if len(content_words(claim)) < MIN_CLAIM_WORDS:
            plans.append(None)
            continue
        plans.append((cited, len(pairs)))
        pairs += [(_premise(d, claim), claim) for d in documents]
    scores = consistency(pairs) if pairs else []
    checks = []
    for plan in plans:
        if plan is None:
            checks.append(None)
            continue
        cited, offset = plan
        support = [float(x) for x in scores[offset : offset + len(documents)]]
        others = [i for i in range(len(documents)) if i + 1 not in cited]
        best = max(others, key=lambda i: support[i], default=None)
        checks.append(CitationCheck(cited, max(support[n - 1] for n in cited), None if best is None else best + 1, support[best] if best is not None else 0.0))
    return checks


def cite(answer: str, claims: list[tuple[int, int, int | None]]) -> str:
    """The answer with a [n] marker after each claim that has a supporting document n; claims = (start, end, n)."""
    out, last = [], 0
    for start, end, document in sorted(claims):
        if document is None:
            continue
        stop = end - 1 if end > start and answer[end - 1] in ".!?" else end
        out += [answer[last:stop], f" [{document}]"]
        last = stop
    return "".join(out) + answer[last:]
