import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pytest

from truth_guardian.language import detect

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "eval" / "rag_documents"
QUESTIONS = json.loads((ROOT / "eval" / "rag_questions.json").read_text(encoding="utf-8"))["languages"]
SOURCES = json.loads((DOCUMENTS / "SOURCES.json").read_text(encoding="utf-8"))
PROJECT_LANGUAGES = {"en", "ar", "es", "fa", "fr", "ru", "zh"}


def plain(text: str) -> str:
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return re.sub(r"[\s,٬.٫]", "", unicodedata.normalize("NFKC", text).translate(digits)).casefold()


CASES = [(code, case) for code, group in QUESTIONS.items() for case in group["answerable"]]


def test_every_language_of_the_project_has_documents_and_questions():
    assert set(QUESTIONS) == PROJECT_LANGUAGES == {source["language"] for source in SOURCES}
    assert all(len(group["answerable"]) == 8 and len(group["unanswerable"]) == 3 for group in QUESTIONS.values())


@pytest.mark.parametrize("code, case", CASES, ids=[f"{code}-{i}" for i, (code, _) in enumerate(CASES)])
def test_every_answer_is_in_its_own_document(code, case):
    text = plain((DOCUMENTS / code / case["document"]).read_text(encoding="utf-8"))
    assert any(plain(gold) in text for gold in case["gold"]), case["question"]


def test_a_document_is_what_its_source_says_and_every_source_names_its_licence_and_revision():
    assert {source["file"] for source in SOURCES} == {f"{p.parent.name}/{p.name}" for p in DOCUMENTS.glob("*/*.txt")}
    for source in SOURCES:
        assert hashlib.sha256((DOCUMENTS / source["file"]).read_bytes()).hexdigest() == source["sha256"]
        assert source["licence"] and "oldid=" in source["url"] and source["revision"]


@pytest.mark.parametrize("code", sorted(PROJECT_LANGUAGES))
def test_questions_are_written_in_their_own_language(code):
    questions = [case["question"] for case in QUESTIONS[code]["answerable"]] + QUESTIONS[code]["unanswerable"]
    told = [detect(q).code for q in questions]
    assert sum(found in (code, None) for found in told) >= len(questions) - 2, told
