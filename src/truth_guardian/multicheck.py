"""The multilingual check's signals (D-138): what the fusion model reads for answers in Arabic, Chinese, French, Russian
and Spanish, or whose sources are in another of these languages or in English (language.py decides which check runs).

One pass per answer gives every signal, because they share the costly part: the sources are cut into evidence units
(sentences, and long lines such as a business's JSON data in pieces of EVIDENCE_WORDS words), embedded once with
multilingual E5, and each answer sentence takes its PREMISE_UNITS closest units, in their original order, as the premise
that mDeBERTa NLI judges. Two units rather than the English engine's five: this CPU reads mDeBERTa at about three pairs
a second, and the premise's length sets that pace. Per sentence:

  m_dense_max          the closest unit's cosine similarity
  m_nli_*              mDeBERTa's contradiction, entailment and neutral probabilities for the sentence given its premise
  m_lex_unsupported    share of the sentence's content words (Chinese: character pairs) found nowhere in the sources
  m_lex_cross          1 when the sentence and the sources are written in different scripts, where word overlap means nothing
  m_numbers(_unmatched) numbers in the sentence, and those no source or question has: digits of any script, decimal
                       commas or points, thousands separators and Chinese numerals (一千九百四十五) are read alike

Not here, unlike the English engine: HHEM, the spaCy and WordNet rules (negation, swapped roles), and number words.
"""

import re
import unicodedata
from functools import lru_cache

import numpy as np

from truth_guardian.language import script
from truth_guardian.models import NLI_LABELS, _cached
from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, split_sentences

EVIDENCE_WORDS = 40  # a longer unit is cut into pieces of this many words (Chinese: this many characters, times two)
PREMISE_UNITS = 2
BATCH = 8
# Answer languages with labelled answers in the check's dev set; Russian has none (XQuAD's edits are not real answers).
MEASURED = ("en", "ar", "es", "fr", "zh")

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹０１２３４５６７８９", "0123456789" * 3)
# Digits with decimal or thousands marks between them; a space joins only a group of exactly three ("68 511", not "1945 3").
_NUMBER = re.compile(r"\d+(?:(?:[.,]|[   ](?=\d{3}(?!\d)))\d+)*")
_LIST_MARKER = re.compile(r"^\s*\d{1,2}[.)]\s")
_CITATION = re.compile(r"\[\d{1,3}(?:\s*,\s*\d{1,3})*\]")
_HAN_NUMBER = re.compile("[零〇一二两三四五六七八九十百千万亿]{2,}")
_HAN_SCALED = re.compile(r"(\d+(?:\.\d+)?)\s*(万|亿)")
_HAN_DIGIT = {c: i for i, c in enumerate("零一二三四五六七八九")} | {"〇": 0, "两": 2}
_HAN_UNIT = {"十": 10, "百": 100, "千": 1000}
_HAN_BIG = {"万": 10**4, "亿": 10**8}
_WORD = re.compile(r"[^\W\d_]+")
_HAN = re.compile(r"[㐀-鿿]")
_ARABIC_MARKS = re.compile("[ً-ٰٟ]")
_ARABIC_PREFIX = re.compile("^(?:وال|بال|فال|كال|لل|ال)")


@lru_cache(maxsize=1)
def stop_words() -> frozenset[str]:
    """spaCy's stop words of the six checked languages together (no model, no download)."""
    from spacy.lang.ar.stop_words import STOP_WORDS as ar
    from spacy.lang.en.stop_words import STOP_WORDS as en
    from spacy.lang.es.stop_words import STOP_WORDS as es
    from spacy.lang.fr.stop_words import STOP_WORDS as fr
    from spacy.lang.ru.stop_words import STOP_WORDS as ru
    from spacy.lang.zh.stop_words import STOP_WORDS as zh

    return frozenset(ar | en | es | fr | ru | zh)


def _arabic(word: str) -> str:
    word = _ARABIC_MARKS.sub("", word).translate(str.maketrans("أإآىة", "ااايه"))
    return _ARABIC_PREFIX.sub("", word) if len(word) > 4 else word


def content_words(text: str) -> set[str]:
    """Lower-cased words without stop words; Arabic without vowel marks and the article; Chinese as character pairs."""
    words = set()
    for run in _WORD.findall(unicodedata.normalize("NFKC", text).lower()):
        han = _HAN.findall(run)
        if han:
            words |= {a + b for a, b in zip(han, han[1:])} or set(han)
            run = _HAN.sub(" ", run)
        for word in run.split():
            word = _arabic(word) if "؀" <= word[0] <= "ۿ" else word
            if len(word) > 1 and word not in stop_words():
                words.add(word)
    return words


def _han_value(text: str) -> int | None:
    total, section, digit = 0, 0, None
    for ch in text:
        if ch in _HAN_DIGIT:
            digit = _HAN_DIGIT[ch] if digit is None else digit * 10 + _HAN_DIGIT[ch]  # 一九四五 read digit by digit
        elif ch in _HAN_UNIT:
            section += (1 if digit is None else digit) * _HAN_UNIT[ch]
            digit = None
        elif ch in _HAN_BIG:
            total += (section + (digit or 0)) * _HAN_BIG[ch]
            section, digit = 0, None
    value = total + section + (digit or 0)
    return value or None


def _forms(raw: str) -> set[str]:
    """A number written with separators read both ways: 1.945 and 1,945 are 1945 or 1.945."""
    digits = re.sub(r"\D", "", raw)
    forms = {digits.lstrip("0") or "0"}
    parts = re.split(r"[.,]", raw.replace(" ", "").replace(" ", "").replace(" ", ""))
    if len(parts) == 2 and parts[1]:
        forms.add(f"{parts[0].lstrip('0') or '0'}.{parts[1].rstrip('0')}".rstrip("."))
    return forms


def numbers(text: str) -> list[set[str]]:
    """Each number in the text as the set of forms it may stand for; a citation such as [1] is not a number of the claim."""
    text = _CITATION.sub(" ", unicodedata.normalize("NFKC", text).translate(_DIGITS))
    found = []
    for line in text.split("\n"):
        line = _LIST_MARKER.sub(" ", line)
        for value, scale in _HAN_SCALED.findall(line):
            found.append({str(round(float(value) * _HAN_BIG[scale]))})
        line = _HAN_SCALED.sub(" ", line)
        found += [_forms(m.group()) for m in _NUMBER.finditer(line)]
        found += [{str(v)} for v in map(_han_value, _HAN_NUMBER.findall(line)) if v is not None]
    return found


def number_spans(text: str) -> list[tuple[int, int, set[str]]]:
    """Where the numbers are, for showing them: the same reading as `numbers` but on the text as written (no NFKC, so
    offsets hold), which differs from it only on superscript, circled and fraction characters."""
    blank = lambda m: " " * len(m.group())
    text = re.sub(r"(?m)" + _LIST_MARKER.pattern, blank, _CITATION.sub(blank, text.translate(_DIGITS)))
    found = [(m.start(), m.end(), {str(round(float(m.group(1)) * _HAN_BIG[m.group(2)]))}) for m in _HAN_SCALED.finditer(text)]
    text = _HAN_SCALED.sub(blank, text)
    found += [(m.start(), m.end(), _forms(m.group())) for m in _NUMBER.finditer(text)]
    found += [(m.start(), m.end(), {str(v)}) for m in _HAN_NUMBER.finditer(text) if (v := _han_value(m.group())) is not None]
    return sorted(found, key=lambda f: f[0])


def explain(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    """For the report, per sentence: its closest evidence unit, the units in order of closeness (for fixes) and where its
    unmatched numbers are (answer offsets)."""
    evidence = [u for d in sample.documents for u in units(d.text)]
    context = " ".join([sample.question or "", *(d.text for d in sample.documents)])
    known = set().union(*numbers(context)) if context.strip() else set()
    similarity = _embed(_without_citations(sentences), "query") @ _embed(evidence, "passage").T if evidence and sentences else None
    rows = []
    for k, s in enumerate(sentences):
        ranked = [evidence[int(i)] for i in np.argsort(-similarity[k])[:3]] if similarity is not None else []
        rows.append({
            "m_evidence": ranked[0] if ranked else "",
            "m_closest": ranked,
            "m_number_spans": [[s.start + a, s.start + b] for a, b, forms in number_spans(s.text) if not forms & known],
        })
    return rows


def fixes(sentence: Sentence, row: dict) -> list:
    """Fix-it for the numbers no source has: the same kind of number in the closest passages, chosen by the words around
    it as the English Fix-it does (correct.py); names are left alone, since its name finder reads English only."""
    from truth_guardian.correct import Suggestion, _best_number
    from truth_guardian.symbolic import Atom

    out = []
    for start, end in row.get("m_number_spans", []):
        text = sentence.text[start - sentence.start : end - sentence.start]
        found = _best_number(Atom(start - sentence.start, end - sentence.start, text, "number"), sentence.text, row.get("m_closest", []))
        replacement, evidence, confidence = found if found else (None, (row.get("m_closest") or [""])[0], 0.3)
        out.append(Suggestion(start, end, text, replacement, evidence, "number", confidence))
    return out


def units(text: str) -> list[str]:
    out = []
    for s in split_sentences(text):
        if _HAN.search(s.text):
            size = EVIDENCE_WORDS * 2
            out += [s.text[i : i + size] for i in range(0, len(s.text), size)]
        else:
            words = s.text.split()
            out += [" ".join(words[i : i + EVIDENCE_WORDS]) for i in range(0, len(words), EVIDENCE_WORDS)]
    return [u for u in out if u.strip()]


def _embed(texts: list[str], kind: str) -> np.ndarray:
    from truth_guardian.media import multilingual

    return _cached(f"e5:{kind}", list(texts), lambda batch: multilingual.embed(batch, kind) if batch else np.zeros((0, 384)))


def nli(pairs: list[tuple[str, str]]) -> np.ndarray:
    """(premise, hypothesis) to mDeBERTa probabilities in models.NLI_LABELS order; batched by length to pad little."""

    def compute(batch):
        import torch

        from truth_guardian.media import multilingual

        tokenizer, model, labels = multilingual.nli()
        columns = [next(i for i, name in labels.items() if name == label) for label in NLI_LABELS]
        order = sorted(range(len(batch)), key=lambda i: len(batch[i][0]) + len(batch[i][1]))
        out = np.zeros((len(batch), 3))

        def run(chunk, truncation):
            enc = tokenizer([p for p, _ in chunk], [h for _, h in chunk], return_tensors="pt", padding=True, truncation=truncation, max_length=512)
            with torch.inference_mode():
                return model(**enc).logits.softmax(-1).numpy()[:, columns]

        for start in range(0, len(order), BATCH):
            chunk = [batch[i] for i in order[start : start + BATCH]]
            try:
                out[order[start : start + BATCH]] = run(chunk, "only_first")
            except Exception:  # a sentence longer than the model reads on its own: that pair is cut on its longer side
                for i in order[start : start + BATCH]:
                    try:
                        out[i] = run([batch[i]], "only_first")[0]
                    except Exception:
                        out[i] = run([batch[i]], "longest_first")[0]
        return out

    return _cached("mnli", [tuple(p) for p in pairs], compute)


def _without_citations(sentences: list[Sentence]) -> list[str]:
    """What the models read: a citation such as [1] says nothing, and counted as a word no source has it flagged right answers."""
    return [_CITATION.sub("", s.text).strip() or s.text for s in sentences]


def signal(sample: Sample, sentences: list[Sentence]) -> list[dict]:
    if not sentences:
        return []
    evidence = [u for d in sample.documents for u in units(d.text)]
    context = " ".join([sample.question or "", *(d.text for d in sample.documents)])
    known = set().union(*numbers(context)) if context.strip() else set()
    known_words = content_words(context)
    source_script = script(" ".join(d.text for d in sample.documents))[0]
    texts = _without_citations(sentences)
    if evidence:
        similarity = _embed(texts, "query") @ _embed(evidence, "passage").T
        nearest = [sorted(np.argsort(-row)[:PREMISE_UNITS]) for row in similarity]
        premises = [" ".join(evidence[i] for i in near) for near in nearest]
        probs = nli(list(zip(premises, texts)))
        dense = similarity.max(axis=1)
    else:
        probs, dense = np.zeros((len(texts), 3)), np.zeros(len(texts))
    rows = []
    for k, text in enumerate(texts):
        words = content_words(text)
        found = numbers(text)
        rows.append({
            "m_dense_max": float(dense[k]),
            **{f"m_nli_{label}": float(p) for label, p in zip(NLI_LABELS, probs[k])},
            "m_lex_unsupported": 1 - len(words & known_words) / len(words) if words else 0.0,
            "m_lex_cross": int(source_script is not None and script(text)[0] not in (None, source_script)),
            "m_numbers": len(found),
            "m_numbers_unmatched": sum(not (forms & known) for forms in found),
        })
    return rows


def version() -> str:
    from truth_guardian.media.multilingual import E5, NLI

    return f"v1:{E5}:{NLI}:units{EVIDENCE_WORDS}:premise{PREMISE_UNITS}"
