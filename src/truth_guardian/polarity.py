"""Polarity check: does an answer sentence state the opposite of a source sentence it otherwise restates?

The rule proposes, NLI confirms. Only near-restatements are compared (most content words shared, source
not much longer), checking a negation mismatch (one side negated, the other not) and an antonym mismatch
(the answer uses a word whose WordNet antonym the source uses instead). On natural answers such rules
alone mostly flag paraphrases, so each candidate is confirmed by the NLI model on just that sentence pair.
Antonyms come from WordNet, a general lexicon, not from our own test edits; thresholds were set on
RAGTruth train.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from truth_guardian import models
from truth_guardian.correct import _singular
from truth_guardian.retrieval import Bm25
from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, content_words, split_sentences

NLTK_DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "nltk_data"
NEGATIONS = {"not", "no", "never", "none", "nobody", "nothing", "neither", "nor", "without", "cannot"}
IMPLICIT_NEGATIONS = {"avoid", "avoids", "avoiding", "lack", "lacks", "lacking", "fail", "fails", "failed", "refuse", "refused", "unable", "prevent", "prevents", "deny", "denied"}
MIN_OVERLAP = 0.65
MAX_LENGTH_RATIO = 2.5
CANDIDATES = 3
CONFIRM_CONTRADICTION = 0.8
_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")


class PolarityCheck(NamedTuple):
    negation_mismatch: bool
    antonym_spans: list[tuple[int, int]]
    negation_spans: list[tuple[int, int]]
    overlap: float
    evidence: str
    contradiction: float | None = None

    @property
    def candidate(self) -> bool:
        return self.negation_mismatch or bool(self.antonym_spans)

    @property
    def confirmed(self) -> bool:
        return self.candidate and (self.contradiction or 0.0) >= CONFIRM_CONTRADICTION


@lru_cache(maxsize=1)
def _wordnet():
    import nltk

    if str(NLTK_DATA) not in nltk.data.path:
        nltk.data.path.insert(0, str(NLTK_DATA))
    from nltk.corpus import wordnet

    wordnet.ensure_loaded()
    return wordnet


@lru_cache(maxsize=50_000)
def lemmas(word: str) -> frozenset[str]:
    wn = _wordnet()
    word = word.lower()
    forms = {word} | {m for pos in ("a", "v", "r", "n") if (m := wn.morphy(word, pos))}
    return frozenset(forms)


@lru_cache(maxsize=50_000)
def antonyms(word: str) -> frozenset[str]:
    wn = _wordnet()
    found = set()
    for lemma in lemmas(word):
        for synset in wn.synsets(lemma):
            for l in synset.lemmas():
                if l.name().lower() == lemma:
                    found |= {a.name().lower().replace("_", " ") for a in l.antonyms()}
    return frozenset(found)


def _is_negation(word: str) -> bool:
    word = word.lower().replace("’", "'")
    return word in NEGATIONS or word.endswith("n't")


def _negated(words: list[str]) -> bool:
    """Implicit negators ("avoid", "lack") count here, so paraphrases like "avoid X" vs "don't X" agree."""
    return any(_is_negation(w) or w.lower() in IMPLICIT_NEGATIONS for w in words)


@lru_cache(maxsize=256)
def _index(texts: tuple[str, ...]) -> tuple[list[str], Bm25]:
    sentences = [s.text for t in texts for s in split_sentences(t)]
    return sentences, Bm25([_singular(s) for s in sentences])


def check_sentence(sentence: Sentence, source_texts: tuple[str, ...]) -> PolarityCheck:
    sources, bm25 = _index(source_texts)
    words = list(_WORD.finditer(sentence.text))
    answer_words = {w for w in content_words(sentence.text) if not _is_negation(w) and w not in {"isn", "aren", "wasn", "weren", "don", "doesn", "didn", "t"}}
    scores = bm25.scores(_singular(sentence.text)) if sources else []
    ranked = sorted(range(len(sources)), key=lambda i: -scores[i])[:CANDIDATES]
    best = PolarityCheck(False, [], [], 0.0, "")
    for i in ranked:
        if scores[i] <= 0:
            continue
        source = sources[i]
        source_content = content_words(source)
        overlap = len(answer_words & source_content) / max(len(answer_words), 1)
        if overlap < MIN_OVERLAP or len(source_content) > MAX_LENGTH_RATIO * max(len(answer_words), 1):
            continue
        source_words = [w.group() for w in _WORD.finditer(source)]
        source_lemmas = {l for w in source_words for l in lemmas(w)}
        negation = _negated([w.group() for w in words]) != _negated(source_words)
        negation_spans = [(sentence.start + w.start(), sentence.start + w.end()) for w in words if negation and _is_negation(w.group())]
        antonym_spans = [
            (sentence.start + w.start(), sentence.start + w.end())
            for w in words
            if not lemmas(w.group()) & source_lemmas and antonyms(w.group()) & source_lemmas
        ]
        candidate = PolarityCheck(negation, antonym_spans, negation_spans, overlap, source)
        if not candidate.candidate:
            return candidate
        if not best.candidate:
            best = candidate
    return best


def check_sample(sample: Sample, sentences: list[Sentence], classify=models.nli_probabilities) -> list[PolarityCheck]:
    """Rule candidates are confirmed with one NLI call on (source sentence, answer sentence) pairs."""
    texts = tuple(d.text for d in sample.documents)
    checks = [check_sentence(s, texts) for s in sentences]
    pending = [i for i, c in enumerate(checks) if c.candidate]
    if pending:
        probs = classify([(checks[i].evidence, sentences[i].text) for i in pending])
        for i, row in zip(pending, probs):
            checks[i] = checks[i]._replace(contradiction=float(row[models.NLI_LABELS.index("contradiction")]))
    return checks
