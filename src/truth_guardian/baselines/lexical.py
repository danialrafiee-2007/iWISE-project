"""B1: a sentence is suspicious when its content words do not appear in the sources (or the question)."""

from truth_guardian.evaluation import Prediction, SentenceScore
from truth_guardian.schema import Sample
from truth_guardian.text import content_words, split_sentences


def sentence_score(sentence: str, context_words: set[str]) -> float:
    words = content_words(sentence)
    if not words:
        return 0.0
    return 1 - len(words & context_words) / len(words)


def predict(sample: Sample) -> Prediction:
    context = content_words(" ".join([sample.question or "", *(d.text for d in sample.documents)]))
    sentences = [
        SentenceScore(start=s.start, end=s.end, score=sentence_score(s.text, context))
        for s in split_sentences(sample.answer)
    ]
    return Prediction(id=sample.id, score=max((s.score for s in sentences), default=0.0), sentences=sentences)
