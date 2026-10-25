"""Controlled edits that turn a grounded answer into a hallucinated one, with exact gold spans.

Powers the "Can you fool it?" demo and a robustness test: each edit kind is a known hallucination type,
and the span note keeps what the text said before ("Original: ..."), so Fix-it can be scored exactly.
"""

import random
import re
from typing import NamedTuple

from truth_guardian.schema import HallucinationType, Labels, Sample, Span
from truth_guardian.symbolic import _ner, _numbers_in, normalize_number
from truth_guardian.text import split_sentences

KINDS = ("number", "entity", "negation", "antonym", "addition", "role_swap", "quantifier", "certainty")
ENTITY_LABELS = ("PERSON", "ORG", "GPE", "NORP", "LOC")

_AUXILIARY = re.compile(r"\b(is|are|was|were|has|have|had|can|will|does|did|should|could|would)\b(?!\s+not\b)", re.IGNORECASE)
_ANTONYMS = {
    "increase": "decrease", "increased": "decreased", "more": "fewer", "higher": "lower", "before": "after",
    "open": "closed", "allowed": "banned", "first": "last", "largest": "smallest", "best": "worst",
    "positive": "negative", "rose": "fell", "won": "lost", "always": "never", "early": "late",
    "cheap": "expensive", "many": "few", "large": "small", "popular": "unpopular", "available": "unavailable",
}
_ANTONYMS |= {v: k for k, v in _ANTONYMS.items()}
_STRONGER = {
    "some": "all", "several": "all", "many": "all", "most": "all", "often": "always", "sometimes": "always",
    "occasionally": "always", "usually": "always", "frequently": "always", "generally": "always", "typically": "always",
    "commonly": "always", "mostly": "entirely", "largely": "entirely", "mainly": "entirely", "partly": "entirely",
}
_CERTAIN = {
    "may": "will", "might": "will", "possibly": "definitely", "probably": "certainly", "perhaps": "certainly",
    "reportedly": "definitely", "allegedly": "definitely", "potentially": "definitely", "apparently": "clearly",
    "suggests": "proves", "suggest": "prove", "suggested": "proved", "likely": "certainly",
}
_BE = {"is", "are", "was", "were", "be", "been", "being"}
_ADDITIONS = (
    ", which was founded in {year}",
    ", according to a {year} survey",
    ", and it has more than {count} locations nationwide",
    ", a figure confirmed by officials in {year}",
)


class Edit(NamedTuple):
    start: int
    end: int
    original: str
    new: str
    kind: str


def _source_numbers(sample: Sample) -> set[str]:
    text = " ".join(d.text for d in sample.documents)
    return {f for m in _numbers_in(text) for f in normalize_number(m.group())}


def _changed_number(text: str, rng: random.Random, taken: set[str]) -> str | None:
    """A plausible wrong value; None for strings that only look numeric, such as an address "192.168.1.1"."""
    if not re.fullmatch(r"\d+(?::\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+", text):
        return None
    for _ in range(20):
        if ":" in text:
            if len(text.split(":")) != 2 or not text.replace(":", "").isdigit():
                return None
            hour, minute = (int(p) for p in text.split(":"))
            new = f"{(hour + rng.choice([-2, -1, 1, 2])) % 24}:{minute:02d}"
        elif "." in text.replace(",", ""):
            value = float(text.replace(",", "")) + rng.choice([-1.0, -0.5, 0.5, 1.0])
            new = f"{max(value, 0.5):.1f}"
        else:
            value = int(text.replace(",", ""))
            if 1000 <= value <= 2100:
                new_value = value + rng.choice([-1, 1]) * rng.randint(3, 15)
            elif value < 10:
                new_value = value + rng.randint(2, 5)
            else:
                new_value = round(value * rng.choice([0.5, 1.5, 2.0]))
            new = f"{new_value:,}" if "," in text else str(new_value)
        if new != text and not normalize_number(new) & taken:
            return new
    return None


def _edit_number(sample: Sample, rng: random.Random) -> Edit | None:
    taken = _source_numbers(sample)
    options = [m for m in _numbers_in(sample.answer) if normalize_number(m.group()) & taken]
    rng.shuffle(options)
    for m in options:
        new = _changed_number(m.group(), rng, taken)
        if new:
            return Edit(m.start(), m.end(), m.group(), new, "number")
    return None


def _edit_entity(sample: Sample, rng: random.Random, pool: dict[str, list[str]]) -> Edit | None:
    sources = " ".join(d.text for d in sample.documents).lower()
    entities = [e for e in _ner()(sample.answer).ents if e.label_ in ENTITY_LABELS]
    rng.shuffle(entities)
    for e in entities:
        choices = [p for p in pool.get(e.label_, []) if p.lower() not in sources and p.lower() != e.text.lower()]
        if choices:
            return Edit(e.start_char, e.end_char, e.text, rng.choice(sorted(choices)), "entity")
    return None


def _edit_negation(sample: Sample, rng: random.Random) -> Edit | None:
    matches = list(_AUXILIARY.finditer(sample.answer))
    if not matches:
        return None
    m = rng.choice(matches)
    return Edit(m.start(), m.end(), m.group(), f"{m.group()} not", "negation")


def _edit_antonym(sample: Sample, rng: random.Random) -> Edit | None:
    matches = [m for m in re.finditer(r"\b[A-Za-z]+\b", sample.answer) if m.group().lower() in _ANTONYMS]
    if not matches:
        return None
    m = rng.choice(matches)
    new = _ANTONYMS[m.group().lower()]
    return Edit(m.start(), m.end(), m.group(), new.capitalize() if m.group()[0].isupper() else new, "antonym")


def _edit_addition(sample: Sample, rng: random.Random) -> Edit | None:
    sentences = split_sentences(sample.answer)
    if not sentences:
        return None
    last = sentences[-1]
    insert_at = last.end - 1 if sample.answer[last.end - 1] in ".!?" else last.end
    taken = _source_numbers(sample)
    year = next(y for y in rng.sample(range(1950, 2016), 66) if str(y) not in taken)
    text = rng.choice(_ADDITIONS).format(year=year, count=rng.choice([50, 120, 300]))
    return Edit(insert_at, insert_at, "", text, "addition")


MAX_PARTICIPANT_WORDS = 5


def _participant(token) -> tuple[int, int, bool] | None:
    """(start, end, starts with a determiner) of the short noun phrase headed by a noun or name; None otherwise."""
    chunk = next((c for c in token.doc.noun_chunks if c.root.i == token.i), None)
    if chunk is None or token.pos_ not in {"NOUN", "PROPN"} or len(chunk) > MAX_PARTICIPANT_WORDS:
        return None
    if any(t.pos_ in {"PRON", "NUM"} or t.dep_ == "poss" for t in chunk):
        return None
    return chunk.start_char, chunk.end_char, chunk[0].dep_ == "det"


def _recase(phrase: str, determiner: bool, sentence_start: bool) -> str:
    """A phrase moved into or out of sentence-initial position keeps a determiner's case right."""
    if not determiner:
        return phrase
    return phrase[0].upper() + phrase[1:] if sentence_start else phrase[0].lower() + phrase[1:]


def _edit_role_swap(sample: Sample, rng: random.Random) -> Edit | None:
    """Exchange the subject and object of an active verb ("Germany beat Brazil" -> "Brazil beat Germany")."""
    from truth_guardian.polarity import lemmas
    from truth_guardian.shifts import SYMMETRIC_VERBS, _parser

    options = []
    for sentence in split_sentences(sample.answer):
        for verb in _parser()(sentence.text):
            subject = next((c for c in verb.children if c.dep_ == "nsubj"), None)
            obj = next((c for c in verb.children if c.dep_ == "dobj"), None)
            if verb.pos_ != "VERB" or subject is None or obj is None or lemmas(verb.text) & SYMMETRIC_VERBS:
                continue
            first, second = _participant(subject), _participant(obj)
            if not first or not second or first[1] > second[0]:
                continue
            a1, b1, d1 = first
            a2, b2, d2 = second
            one, two = sentence.text[a1:b1], sentence.text[a2:b2]
            if subject.text.lower() == obj.text.lower():
                continue
            moved = _recase(two, d2, a1 == 0) + sentence.text[b1:a2] + _recase(one, d1, False)
            options.append((sentence.start + a1, sentence.start + b2, moved))
    if not options:
        return None
    start, end, moved = rng.choice(options)
    return Edit(start, end, sample.answer[start:end], moved, "role_swap")


def _replace_word(sample: Sample, rng: random.Random, table: dict[str, str], kind: str) -> Edit | None:
    matches = [m for m in re.finditer(r"\b[A-Za-z]+\b", sample.answer) if m.group().lower() in table]
    if not matches:
        return None
    m = rng.choice(matches)
    new = table[m.group().lower()]
    previous = re.findall(r"[A-Za-z]+", sample.answer[: m.start()])[-1:]
    if m.group().lower() == "likely" and previous and previous[0].lower() in _BE:
        new = "certain"
    return Edit(m.start(), m.end(), m.group(), new.capitalize() if m.group()[0].isupper() else new, kind)


def perturb(sample: Sample, kind: str, rng: random.Random, entity_pool: dict[str, list[str]] | None = None) -> Sample | None:
    """A hallucinated copy of a grounded sample with one edit of the given kind, or None if it does not apply."""
    edit = {
        "number": lambda: _edit_number(sample, rng),
        "entity": lambda: _edit_entity(sample, rng, entity_pool or {}),
        "negation": lambda: _edit_negation(sample, rng),
        "antonym": lambda: _edit_antonym(sample, rng),
        "addition": lambda: _edit_addition(sample, rng),
        "role_swap": lambda: _edit_role_swap(sample, rng),
        "quantifier": lambda: _replace_word(sample, rng, _STRONGER, "quantifier"),
        "certainty": lambda: _replace_word(sample, rng, _CERTAIN, "certainty"),
    }[kind]()
    if edit is None:
        return None
    answer = sample.answer[: edit.start] + edit.new + sample.answer[edit.end :]
    span_type = {
        "number": HallucinationType.NUMERIC_ENTITY_MISMATCH,
        "entity": HallucinationType.NUMERIC_ENTITY_MISMATCH,
        "addition": HallucinationType.UNSUPPORTED,
        "quantifier": HallucinationType.OVERCLAIM,
        "certainty": HallucinationType.OVERCLAIM,
    }.get(kind, HallucinationType.CONTRADICTED)
    span = Span(start=edit.start, end=edit.start + len(edit.new), text=edit.new, type=span_type, source_label=f"perturb:{kind}", note=f"Original: {edit.original}")
    return sample.model_copy(update={
        "id": f"perturb-{kind}-{sample.id}",
        "answer": answer,
        "labels": Labels(response="hallucinated", spans=[span]),
        "meta": sample.meta.model_copy(update={"dataset": "tg_perturb", "synthetic": True}),
    })


def entity_pool(samples: list[Sample]) -> dict[str, list[str]]:
    """Named entities by label, collected from other answers, used as plausible wrong replacements."""
    pool: dict[str, set[str]] = {label: set() for label in ENTITY_LABELS}
    for s in samples:
        for e in _ner()(s.answer).ents:
            if e.label_ in pool and len(e.text) > 2:
                pool[e.label_].add(e.text)
    return {label: sorted(v) for label, v in pool.items()}
